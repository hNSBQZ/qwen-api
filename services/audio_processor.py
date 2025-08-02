import logging
import os
import time
import base64
import asyncio
import concurrent.futures
from datetime import datetime

from database import save_chat_record
from config import DEFAULT_SYSTEM_PROMPT, TTS_SAMPLE_RATE, TTS_VOICE, REAL_TIME_AUDIO_URL, QWEN_API_KEY
from up_to_oss import upload_and_cleanup
from audio_transcription import transcribe_audio_from_url
from chat_service import generate_chat_response_stream
from tts_realtime_client import TTSRealtimeClient, SessionMode
from audio_converter import create_mp3_converter

logger = logging.getLogger(__name__)


class AudioProcessor:
    """音频处理服务类，负责处理完整的音频处理流程"""
    
    def __init__(self, socketio):
        self.socketio = socketio
    
    def process_complete_audio(self, session_id, session):
        """处理完整的音频数据 - 已流式写入完成"""
        try:
            filepath = session['filepath']
            
            # 获取文件大小和处理时长
            file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            duration = (datetime.now() - session['start_time']).total_seconds()
            filename = os.path.basename(filepath)
            
            logger.info(f"音频流式写入完成: {filepath}, 大小: {file_size} bytes, 用时: {duration:.2f}s")
            
            # 上传到OSS
            oss_result = self._upload_to_oss(filepath, session_id)
            
            # 语音识别
            transcription_result = self._transcribe_audio(oss_result, session_id)
            
            # 对话生成和TTS合成
            chat_result = self._process_chat_and_tts(transcription_result, session_id)
            
            # 构造和发送响应数据
            response_data = self._build_response_data(
                filename, filepath, file_size, duration, session,
                oss_result, transcription_result, chat_result
            )
            
            # 清理本地文件
            self._cleanup_local_file(filepath, oss_result, response_data)
            
            # 发送完成通知
            self.socketio.emit('audio_complete', response_data, namespace='/v1/chat/audio', room=session_id)
            
            return True
            
        except Exception as e:
            logger.error(f"处理完整音频数据时出错: {e}")
            self.socketio.emit('error', {'message': f'处理音频数据时出错: {str(e)}'}, 
                             namespace='/v1/chat/audio', room=session_id)
            return False
    
    def _upload_to_oss(self, filepath, session_id):
        """上传音频文件到OSS"""
        oss_result = None
        try:
            logger.info(f"开始上传音频文件到OSS: {filepath}")
            oss_result = upload_and_cleanup(filepath, keep_local=True)  # 先保留本地文件
            
            if oss_result and oss_result['success']:
                logger.info(f"音频文件OSS上传成功: {oss_result['file_url']}")
            else:
                logger.error("音频文件OSS上传失败")
        except Exception as e:
            logger.error(f"OSS上传过程中出错: {str(e)}")
        
        return oss_result
    
    def _transcribe_audio(self, oss_result, session_id):
        """语音识别"""
        transcription_result = None
        if oss_result and oss_result['success']:
            try:
                logger.info("开始语音识别...")
                # 通知客户端开始语音识别
                self.socketio.emit('transcription_started', {
                    'message': '开始语音识别...',
                    'oss_url': oss_result['file_url']
                }, namespace='/v1/chat/audio', room=session_id)
                
                transcription_result = transcribe_audio_from_url(oss_result['file_url'])
                
                if transcription_result['success']:
                    logger.info(f"语音识别成功: {transcription_result['text']}")
                else:
                    logger.error(f"语音识别失败: {transcription_result.get('error', '未知错误')}")
                    
            except Exception as e:
                logger.error(f"语音识别过程中出错: {str(e)}")
                transcription_result = {
                    'success': False,
                    'error': f'语音识别出错: {str(e)}',
                    'text': ''
                }
        
        return transcription_result
    
    def _process_chat_and_tts(self, transcription_result, session_id):
        """处理对话生成和TTS合成"""
        chat_result = None
        
        if transcription_result and transcription_result['success'] and transcription_result['text'].strip():
            try:
                user_message = transcription_result['text'].strip()
                logger.info(f"开始对话生成，用户消息: {user_message}")
                
                # 通知客户端开始对话生成
                self.socketio.emit('chat_started', {
                    'message': '开始生成AI回答...',
                    'user_message': user_message
                }, namespace='/v1/chat/audio', room=session_id)
                
                # 实时流式对话和TTS合成
                chat_result = self._streaming_chat_and_tts(user_message, session_id)
                
                if chat_result and chat_result['success']:
                    logger.info("流式对话和TTS合成完成")
                    
                    # 保存到数据库
                    self._save_to_database(transcription_result, chat_result)
                    
                    # 通知客户端完成
                    self._notify_chat_tts_complete(chat_result, transcription_result, session_id)
                else:
                    logger.error(f"流式对话和TTS处理失败: {chat_result.get('error', '未知错误') if chat_result else '未知错误'}")
                    chat_result = {
                        'success': False,
                        'error': chat_result.get('error', '未知错误') if chat_result else '未知错误'
                    }
                    
            except Exception as e:
                logger.error(f"对话生成和TTS处理过程中出错: {str(e)}")
                chat_result = {
                    'success': False,
                    'error': str(e)
                }
        else:
            logger.info("跳过对话生成：语音识别失败或结果为空")
        
        return chat_result
    
    def _streaming_chat_and_tts(self, user_message, session_id):
        """实时流式对话和TTS合成"""
        def process_streaming_chat_and_tts():
            """处理流式对话并实时TTS合成"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def streaming_chat_with_tts():
                    assistant_response = ""
                    text_buffer = ""  # 用于积累文本
                    
                    # 标点符号，用于判断句子结束
                    sentence_endings = ['。', '！', '？', '.', '!', '?', '\n']
                    
                    logger.info("开始流式生成内容...")
                    
                    # 通知客户端开始TTS合成
                    self.socketio.emit('tts_started', {
                        'message': '开始语音合成...'
                    }, namespace='/v1/chat/audio', room=session_id)
                    
                    # 创建单一TTS连接和音频处理队列
                    audio_chunks_sent = 0  # MP3音频块发送计数
                    text_segments_sent = 0  # 向TTS发送的文本片段计数
                    pcm_queue = asyncio.Queue()
                    processing_active = True
                    
                    def audio_callback(audio_bytes: bytes):
                        # 快速将PCM数据放入队列，不阻塞TTS通信
                        try:
                            pcm_queue.put_nowait(audio_bytes)
                            logger.debug(f"PCM数据入队: {len(audio_bytes)} bytes")
                        except asyncio.QueueFull:
                            logger.warning("PCM队列已满，丢弃数据")
                    
                    # 异步MP3转换和发送任务
                    async def process_pcm_to_mp3():
                        nonlocal audio_chunks_sent, processing_active
                        mp3_converter = create_mp3_converter(
                            sample_rate=TTS_SAMPLE_RATE,
                            channels=1,
                            sample_width=2,
                            buffer_duration_ms=500
                        )
                        
                        while processing_active:
                            try:
                                # 等待PCM数据
                                audio_bytes = await asyncio.wait_for(pcm_queue.get(), timeout=0.1)
                                
                                # 转换为MP3
                                mp3_data = mp3_converter.add_pcm_data(audio_bytes)
                                
                                if mp3_data:
                                    audio_chunks_sent += 1
                                    audio_timestamp = time.time()
                                    
                                    # 发送MP3数据给客户端
                                    mp3_base64 = base64.b64encode(mp3_data).decode('utf-8')
                                    self.socketio.emit('audio_stream', {
                                        'event': 'data',
                                        'data': mp3_base64
                                    }, namespace='/v1/chat/audio', room=session_id)
                                    
                                    logger.info(f"发送MP3音频块 {audio_chunks_sent}, PCM: {len(audio_bytes)} bytes -> MP3: {len(mp3_data)} bytes, 时间戳: {audio_timestamp:.3f}")
                                    
                                    # 让出控制权，允许其他任务（如handle_messages）执行
                                    # 减少延迟提高处理速度，同时保证ping-pong机制正常工作  
                                    await asyncio.sleep(0.01)  # 10ms延迟，平衡速度和稳定性
                                
                                pcm_queue.task_done()
                                
                            except asyncio.TimeoutError:
                                # 没有新数据，让出控制权给其他任务
                                await asyncio.sleep(0)
                                continue
                            except Exception as e:
                                logger.error(f"MP3转换处理出错: {e}")
                                break
                        
                        # 处理剩余数据
                        remaining_mp3 = mp3_converter.flush_remaining()
                        if remaining_mp3:
                            audio_chunks_sent += 1
                            mp3_base64 = base64.b64encode(remaining_mp3).decode('utf-8')
                            self.socketio.emit('audio_stream', {
                                'event': 'data',
                                'data': mp3_base64
                            }, namespace='/v1/chat/audio', room=session_id)
                            logger.info(f"发送最后的MP3音频块 {audio_chunks_sent}, 大小: {len(remaining_mp3)} bytes")
                            # 让出控制权
                            await asyncio.sleep(0)
                    
                    # 启动MP3处理任务
                    mp3_task = asyncio.create_task(process_pcm_to_mp3())
                    
                    client = TTSRealtimeClient(
                        base_url=REAL_TIME_AUDIO_URL,
                        api_key=QWEN_API_KEY,
                        voice=TTS_VOICE,
                        mode=SessionMode.SERVER_COMMIT,
                        audio_callback=audio_callback
                    )
                    
                    # 建立TTS连接
                    await client.connect()
                    
                    # 启动消息处理任务
                    consumer_task = asyncio.create_task(client.handle_messages())
                    
                    # 流式获取对话响应并实时发送到TTS
                    for chunk in generate_chat_response_stream(user_message, DEFAULT_SYSTEM_PROMPT):
                        assistant_response += chunk
                        text_buffer += chunk
                        
                        # 实时发送流式响应给客户端
                        self.socketio.emit('chat_chunk', {
                            'chunk': chunk,
                            'full_response': assistant_response
                        }, namespace='/v1/chat/audio', room=session_id)
                        
                        # 让出一点控制权给其他任务
                        await asyncio.sleep(0)
                        
                        # 检查是否需要进行TTS合成
                        should_synthesize = False
                        
                        # 方法1: 遇到句子结束标点
                        if any(ending in chunk for ending in sentence_endings):
                            should_synthesize = True
                        
                        # 方法2: 文本缓冲区过长（避免句子太长不包含标点的情况）
                        elif len(text_buffer.strip()) >= 50:  # 50个字符
                            should_synthesize = True
                        
                        # 如果需要合成且缓冲区有内容
                        if should_synthesize and text_buffer.strip():
                            text_to_synthesize = text_buffer.strip()
                            text_segments_sent += 1
                            logger.info(f"发送TTS合成片段 {text_segments_sent}: {text_to_synthesize[:50]}{'...' if len(text_to_synthesize) > 50 else ''}")
                            
                            # 直接发送到同一个TTS连接
                            await client.append_text(text_to_synthesize)
                            
                            # 短暂等待确保发送完成
                            await asyncio.sleep(0.1)
                            
                            # 清空缓冲区
                            text_buffer = ""
                    
                    logger.info(f"对话生成完成，完整回答: {assistant_response}")
                    
                    # 处理剩余的文本缓冲区
                    if text_buffer.strip():
                        text_segments_sent += 1
                        logger.info(f"发送最后的TTS合成片段 {text_segments_sent}: {text_buffer.strip()[:50]}{'...' if len(text_buffer.strip()) > 50 else ''}")
                        await client.append_text(text_buffer.strip())
                        await asyncio.sleep(0.1)
                    
                    # 结束TTS会话
                    await client.finish_session()
                    logger.info(f"已向TTS发送 {text_segments_sent} 个文本片段，发送会话结束信号，等待服务器完成处理...")
                    
                    # 等待TTS真正完成 - 等待handle_messages处理完所有消息
                    try:
                        await asyncio.wait_for(consumer_task, timeout=180.0)
                        logger.info("TTS消息处理完成")
                        logger.info(f"TTS会话真正结束，总共发送了 {text_segments_sent} 个文本片段，生成了 {audio_chunks_sent} 个MP3音频块")
                    except asyncio.TimeoutError:
                        logger.warning("TTS消息处理超时，强制结束")
                        consumer_task.cancel()
                    except Exception as e:
                        logger.error(f"TTS消息处理出错: {e}")
                        consumer_task.cancel()
                    
                    # 关闭TTS连接
                    await client.close()
                    
                    # ⚠️ 重要：确保PCM队列完全处理完毕后再停止MP3任务
                    logger.info("TTS连接已关闭，等待PCM队列完全处理...")
                    
                    # 等待PCM队列基本清空
                    queue_empty_count = 0
                    max_wait_cycles = 100  # 最多等待10秒，确保所有PCM数据处理完成
                    wait_cycles = 0
                    
                    while queue_empty_count < 5 and wait_cycles < max_wait_cycles:
                        current_size = pcm_queue.qsize()
                        if current_size == 0:
                            queue_empty_count += 1
                        else:
                            queue_empty_count = 0
                            logger.info(f"PCM队列还有 {current_size} 个数据包待处理...")
                        
                        await asyncio.sleep(0.1)
                        wait_cycles += 1
                    
                    if wait_cycles >= max_wait_cycles:
                        remaining_pcm = pcm_queue.qsize()
                        logger.warning(f"PCM队列处理超时，强制停止（剩余 {remaining_pcm} 个数据包）")
                        logger.warning(f"⚠️  可能丢失音频时长约: {remaining_pcm * 0.32:.1f}秒 (每包约0.32秒)")
                    else:
                        logger.info("✅ PCM队列已完全清空，所有音频数据处理完成")
                    
                    # 现在可以安全停止MP3处理任务
                    processing_active = False
                    
                    # 等待MP3处理任务完成
                    try:
                        await asyncio.wait_for(mp3_task, timeout=10.0)
                        logger.info("MP3处理任务完成")
                    except asyncio.TimeoutError:
                        logger.warning("MP3处理任务超时，强制取消")
                        mp3_task.cancel()
                    except Exception as e:
                        logger.error(f"MP3处理任务出错: {e}")
                        mp3_task.cancel()
                    
                    # 发送完成信号 - 严格按照要求的格式
                    self.socketio.emit('audio_stream', {
                        'event': 'finished'
                    }, namespace='/v1/chat/audio', room=session_id)
                    
                    # 发送完成信号后让出控制权
                    await asyncio.sleep(0)
                    
                    logger.info(f"✅ 发送完成信号给客户端")
                    logger.info(f"🎵 流式合成最终统计:")
                    logger.info(f"  - 向TTS发送: {text_segments_sent} 个文本片段")
                    logger.info(f"  - 生成MP3块: {audio_chunks_sent} 个")
                    logger.info(f"  - PCM队列最终状态: {pcm_queue.qsize()} 个剩余数据包")
                    
                    return {
                        'success': True,
                        'assistant_response': assistant_response,
                        'tts_result': {
                            'success': True,
                            'method': 'single_connection'
                        }
                    }
                
                # 执行流式对话和TTS
                return loop.run_until_complete(streaming_chat_with_tts())
                
            except Exception as e:
                logger.error(f"流式对话和TTS处理出错: {str(e)}")
                return {
                    'success': False,
                    'error': str(e)
                }
            finally:
                loop.close()
        
        # 在线程池中执行
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(process_streaming_chat_and_tts)
            return future.result(timeout=120)  # 2分钟超时
    
    def _save_to_database(self, transcription_result, chat_result):
        """保存对话记录到数据库"""
        user_message_for_db = transcription_result.get('text', '').strip()
        assistant_response_for_db = chat_result.get('assistant_response', '').strip()
        
        if user_message_for_db and assistant_response_for_db:
            try:
                save_result = save_chat_record(user_message_for_db, assistant_response_for_db)
                if save_result:
                    logger.info("语音对话记录已保存到数据库")
                    logger.info(f"用户提示词: {user_message_for_db[:100]}{'...' if len(user_message_for_db) > 100 else ''}")
                    logger.info(f"AI回复: {assistant_response_for_db[:100]}{'...' if len(assistant_response_for_db) > 100 else ''}")
                else:
                    logger.warning("语音对话记录保存失败")
            except Exception as e:
                logger.error(f"保存语音对话记录时出错: {e}")
        else:
            logger.warning("用户提示词或AI回复为空，跳过数据库保存")
    
    def _notify_chat_tts_complete(self, chat_result, transcription_result, session_id):
        """通知客户端对话和TTS完成"""
        tts_result = chat_result.get('tts_result', {})
        user_message_for_db = transcription_result.get('text', '').strip()
        assistant_response_for_db = chat_result.get('assistant_response', '').strip()
        
        self.socketio.emit('chat_tts_complete', {
            'message': '实时对话生成和语音合成完成',
            'assistant_response': chat_result['assistant_response'],
            'tts_success': tts_result.get('success', False),
            'segments_count': tts_result.get('segments_count', 0),
            'total_segments': tts_result.get('total_segments', 0),
            'db_saved': user_message_for_db and assistant_response_for_db
        }, namespace='/v1/chat/audio', room=session_id)
    
    def _build_response_data(self, filename, filepath, file_size, duration, session, 
                           oss_result, transcription_result, chat_result):
        """构造响应数据"""
        response_data = {
            'message': '音频接收、上传和识别完成',
            'filename': filename,
            'filepath': filepath,
            'size': file_size,
            'packets': session['total_packets'],
            'duration': duration
        }
        
        # 添加OSS相关信息
        if oss_result and oss_result['success']:
            response_data.update({
                'oss_uploaded': True,
                'oss_url': oss_result['file_url'],
                'oss_object_key': oss_result['object_key'],
                'oss_etag': oss_result['etag']
            })
        else:
            response_data['oss_uploaded'] = False
        
        # 添加语音识别结果
        if transcription_result:
            response_data.update({
                'transcription_success': transcription_result['success'],
                'transcription_text': transcription_result.get('text', ''),
                'transcription_error': transcription_result.get('error', ''),
                'transcription_task_id': transcription_result.get('task_id', '')
            })
            
            if 'warning' in transcription_result:
                response_data['transcription_warning'] = transcription_result['warning']
        else:
            response_data.update({
                'transcription_success': False,
                'transcription_text': '',
                'transcription_error': 'OSS上传失败，无法进行语音识别'
            })
        
        # 添加对话生成结果
        if chat_result:
            response_data.update({
                'chat_success': chat_result['success'],
                'assistant_response': chat_result.get('assistant_response', ''),
                'chat_error': chat_result.get('error', ''),
                'response_chunks_count': len(chat_result.get('response_chunks', []))
            })
            
            # 添加TTS合成结果
            if chat_result.get('tts_result'):
                tts_data = chat_result['tts_result']
                response_data.update({
                    'tts_success': tts_data['success'],
                    'tts_segments_count': tts_data.get('segments_count', 0),
                    'tts_total_segments': tts_data.get('total_segments', 0),
                    'tts_error': tts_data.get('error', '')
                })
            else:
                response_data.update({
                    'tts_success': False,
                    'tts_error': '对话生成失败，无法进行TTS合成'
                })
        else:
            response_data.update({
                'chat_success': False,
                'assistant_response': '',
                'chat_error': '语音识别失败或结果为空，无法进行对话生成',
                'tts_success': False,
                'tts_error': '无法进行TTS合成'
            })
        
        # 更新消息描述
        if chat_result and chat_result['success']:
            if chat_result.get('tts_result') and chat_result['tts_result']['success']:
                response_data['message'] = '音频接收、识别、对话生成和实时语音合成全部完成'
            else:
                response_data['message'] = '音频接收、识别和对话生成完成，实时语音合成失败'
        else:
            response_data['message'] = '音频接收、上传和识别完成，对话生成失败'
        
        return response_data
    
    def _cleanup_local_file(self, filepath, oss_result, response_data):
        """清理本地文件"""
        if oss_result and oss_result['success']:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logger.info(f"已删除本地缓存文件: {filepath}")
                    response_data['local_file_cleaned'] = True
                else:
                    logger.warning(f"本地文件不存在，无需删除: {filepath}")
                    response_data['local_file_cleaned'] = True
            except Exception as e:
                logger.error(f"删除本地文件时出错: {str(e)}")
                response_data['local_file_cleaned'] = False
                response_data['cleanup_error'] = str(e)
        else:
            response_data['local_file_cleaned'] = False
            response_data['cleanup_reason'] = 'OSS上传失败，保留本地文件'