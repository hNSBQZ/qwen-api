import logging
import os
import time
import base64
import asyncio
import concurrent.futures
from datetime import datetime

from database import save_chat_record
from config import DEFAULT_SYSTEM_PROMPT, TTS_SAMPLE_RATE, TTS_VOICE, REAL_TIME_AUDIO_URL, QWEN_API_KEY
from up_to_oss import upload_and_cleanup, upload_image_file
from audio_transcription import transcribe_audio_from_url
from chat_service import generate_vlm_response_stream
from tts_realtime_client import TTSRealtimeClient, SessionMode
from audio_converter import create_mp3_converter

logger = logging.getLogger(__name__)


class VLMProcessor:
    """VLM处理服务类，负责处理完整的多模态处理流程"""
    
    def __init__(self, socketio):
        self.socketio = socketio
    
    def process_complete_vlm(self, session_id, session):
        """处理完整的VLM数据 - 图像和音频已流式写入完成"""
        try:
            audio_filepath = session.get('audio_filepath')
            image_filepath = session.get('image_filepath')
            
            logger.info(f"VLM处理开始: 音频={audio_filepath}, 图像={image_filepath}")
            
            # 验证文件存在
            if not audio_filepath or not os.path.exists(audio_filepath):
                raise Exception("音频文件不存在")
            if not image_filepath or not os.path.exists(image_filepath):
                raise Exception("图像文件不存在")
            
            # 获取文件大小和处理时长
            audio_size = os.path.getsize(audio_filepath)
            image_size = os.path.getsize(image_filepath)
            duration = (datetime.now() - session['start_time']).total_seconds()
            
            logger.info(f"VLM文件准备完成: 音频大小={audio_size}bytes, 图像大小={image_size}bytes, 用时={duration:.2f}s")
            
            # 上传文件到OSS
            audio_oss_result = self._upload_audio_to_oss(audio_filepath, session_id)
            image_oss_result = self._upload_image_to_oss(image_filepath, session_id)
            
            # 语音识别
            transcription_result = self._transcribe_audio(audio_oss_result, session_id)
            
            # 多模态对话生成和TTS合成
            vlm_result = self._process_vlm_chat_and_tts(
                transcription_result, image_oss_result, session_id
            )
            
            # 清理本地文件
            self._cleanup_local_files(audio_filepath, image_filepath, 
                                    audio_oss_result, image_oss_result)
            
            # 发送完成通知
            response_data = {
                'message': 'VLM处理完成',
                'audio_file': os.path.basename(audio_filepath),
                'image_file': os.path.basename(image_filepath),
                'audio_size': audio_size,
                'image_size': image_size,
                'duration': duration,
                'transcription': transcription_result.get('text', '') if transcription_result else '',
                'vlm_response': vlm_result.get('response', '') if vlm_result else ''
            }
            
            self.socketio.emit('vlm_complete', response_data, 
                             namespace='/v1/chat/vlm', room=session_id)
            
            return True
            
        except Exception as e:
            logger.error(f"处理完整VLM数据时出错: {e}")
            self.socketio.emit('error', {'message': f'处理VLM数据时出错: {str(e)}'}, 
                             namespace='/v1/chat/vlm', room=session_id)
            return False
    
    def _upload_audio_to_oss(self, audio_filepath, session_id):
        """上传音频文件到OSS"""
        audio_oss_result = None
        try:
            logger.info(f"开始上传音频文件到OSS: {audio_filepath}")
            audio_oss_result = upload_and_cleanup(audio_filepath, keep_local=True)
            
            if audio_oss_result and audio_oss_result['success']:
                logger.info(f"音频文件OSS上传成功: {audio_oss_result['file_url']}")
            else:
                logger.error("音频文件OSS上传失败")
        except Exception as e:
            logger.error(f"音频OSS上传过程中出错: {str(e)}")
        
        return audio_oss_result
    
    def _upload_image_to_oss(self, image_filepath, session_id):
        """上传图像文件到OSS"""
        image_oss_result = None
        try:
            logger.info(f"开始上传图像文件到OSS: {image_filepath}")
            image_oss_result = upload_image_file(image_filepath)
            
            if image_oss_result and image_oss_result['success']:
                logger.info(f"图像文件OSS上传成功: {image_oss_result['file_url']}")
            else:
                logger.error("图像文件OSS上传失败")
        except Exception as e:
            logger.error(f"图像OSS上传过程中出错: {str(e)}")
        
        return image_oss_result
    
    def _transcribe_audio(self, audio_oss_result, session_id):
        """语音识别"""
        transcription_result = None
        if audio_oss_result and audio_oss_result['success']:
            try:
                logger.info("开始语音识别...")
                # 通知客户端开始语音识别
                self.socketio.emit('transcription_started', {
                    'message': '开始语音识别...',
                    'oss_url': audio_oss_result['file_url']
                }, namespace='/v1/chat/vlm', room=session_id)
                
                transcription_result = transcribe_audio_from_url(audio_oss_result['file_url'])
                
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
    
    def _process_vlm_chat_and_tts(self, transcription_result, image_oss_result, session_id):
        """处理多模态对话生成和TTS合成"""
        vlm_result = None
        
        if (transcription_result and transcription_result['success'] and 
            transcription_result['text'].strip() and 
            image_oss_result and image_oss_result['success']):
            
            try:
                user_message = transcription_result['text'].strip()
                image_url = image_oss_result['file_url']
                
                logger.info(f"开始多模态对话生成，用户消息: {user_message}, 图像URL: {image_url}")
                
                # 通知客户端开始多模态对话生成
                self.socketio.emit('vlm_chat_started', {
                    'message': '开始生成多模态AI回答...',
                    'user_message': user_message,
                    'image_url': image_url
                }, namespace='/v1/chat/vlm', room=session_id)
                
                # 实时流式VLM对话和TTS合成
                vlm_result = self._streaming_vlm_chat_and_tts(user_message, image_url, session_id)
                
                if vlm_result and vlm_result['success']:
                    logger.info("流式VLM对话和TTS合成完成")
                    
                    # 保存到数据库
                    self._save_to_database(transcription_result, vlm_result, image_url)
                    
                    # 通知客户端完成
                    self._notify_vlm_chat_tts_complete(vlm_result, transcription_result, session_id)
                else:
                    logger.error(f"流式VLM对话和TTS处理失败: {vlm_result.get('error', '未知错误') if vlm_result else '未知错误'}")
                    vlm_result = {
                        'success': False,
                        'error': vlm_result.get('error', '未知错误') if vlm_result else '未知错误'
                    }
                    
            except Exception as e:
                logger.error(f"VLM对话生成和TTS处理过程中出错: {str(e)}")
                vlm_result = {
                    'success': False,
                    'error': str(e)
                }
        else:
            error_msg = "缺少必要数据："
            if not transcription_result or not transcription_result['success']:
                error_msg += " 语音识别失败"
            if not image_oss_result or not image_oss_result['success']:
                error_msg += " 图像上传失败"
            logger.error(error_msg)
            vlm_result = {
                'success': False,
                'error': error_msg
            }
        
        return vlm_result
    
    def _streaming_vlm_chat_and_tts(self, user_message, image_url, session_id):
        """实时流式VLM对话和TTS合成 - 基于audio_processor.py的成熟实现"""
        def process_streaming_vlm_and_tts():
            """处理流式VLM对话并实时TTS合成"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def streaming_vlm_with_tts():
                    assistant_response = ""
                    text_buffer = ""  # 用于积累文本
                    
                    # 标点符号，用于判断句子结束
                    sentence_endings = ['。', '！', '？', '.', '!', '?', '\n']
                    
                    logger.info("开始流式生成VLM内容...")
                    
                    # 通知客户端开始TTS合成
                    self.socketio.emit('tts_started', {
                        'message': '开始语音合成...'
                    }, namespace='/v1/chat/vlm', room=session_id)
                    
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
                                    }, namespace='/v1/chat/vlm', room=session_id)
                                    
                                    logger.info(f"发送VLM MP3音频块 {audio_chunks_sent}, PCM: {len(audio_bytes)} bytes -> MP3: {len(mp3_data)} bytes, 时间戳: {audio_timestamp:.3f}")
                                    
                                    # 让出控制权，允许其他任务执行
                                    await asyncio.sleep(0.01)  # 10ms延迟，平衡速度和稳定性
                                
                                pcm_queue.task_done()
                                
                            except asyncio.TimeoutError:
                                # 没有新数据，让出控制权给其他任务
                                await asyncio.sleep(0)
                                continue
                            except Exception as e:
                                logger.error(f"VLM MP3转换处理出错: {e}")
                                break
                        
                        # 处理剩余数据
                        remaining_mp3 = mp3_converter.flush_remaining()
                        if remaining_mp3:
                            audio_chunks_sent += 1
                            mp3_base64 = base64.b64encode(remaining_mp3).decode('utf-8')
                            self.socketio.emit('audio_stream', {
                                'event': 'data',
                                'data': mp3_base64
                            }, namespace='/v1/chat/vlm', room=session_id)
                            logger.info(f"发送VLM最后的MP3音频块 {audio_chunks_sent}, 大小: {len(remaining_mp3)} bytes")
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
                    
                    # 使用 dashscope 的多模态流式对话生成器
                    vlm_response_generator = generate_vlm_response_stream(
                        user_message=user_message,
                        image_url=image_url,
                        system_prompt=DEFAULT_SYSTEM_PROMPT
                    )
                    
                    # 流式获取VLM对话响应并实时发送到TTS
                    for chunk in vlm_response_generator:
                        assistant_response += chunk
                        text_buffer += chunk
                        
                        # 实时发送流式响应给客户端
                        self.socketio.emit('vlm_chat_chunk', {
                            'chunk': chunk,
                            'full_response': assistant_response
                        }, namespace='/v1/chat/vlm', room=session_id)
                        
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
                            logger.info(f"发送VLM TTS合成片段 {text_segments_sent}: {text_to_synthesize[:50]}{'...' if len(text_to_synthesize) > 50 else ''}")
                            
                            # 直接发送到同一个TTS连接
                            await client.append_text(text_to_synthesize)
                            
                            # 短暂等待确保发送完成
                            await asyncio.sleep(0.1)
                            
                            # 清空缓冲区
                            text_buffer = ""
                    
                    logger.info(f"VLM对话生成完成，完整回答: {assistant_response}")
                    
                    # 处理剩余的文本缓冲区
                    if text_buffer.strip():
                        text_segments_sent += 1
                        logger.info(f"发送VLM最后的TTS合成片段 {text_segments_sent}: {text_buffer.strip()[:50]}{'...' if len(text_buffer.strip()) > 50 else ''}")
                        await client.append_text(text_buffer.strip())
                        await asyncio.sleep(0.1)
                    
                    # 结束TTS会话
                    await client.finish_session()
                    logger.info(f"已向VLM TTS发送 {text_segments_sent} 个文本片段，发送会话结束信号，等待服务器完成处理...")
                    
                    # 等待TTS真正完成 - 等待handle_messages处理完所有消息
                    try:
                        await asyncio.wait_for(consumer_task, timeout=180.0)
                        logger.info("VLM TTS消息处理完成")
                        logger.info(f"VLM TTS会话真正结束，总共发送了 {text_segments_sent} 个文本片段，生成了 {audio_chunks_sent} 个MP3音频块")
                    except asyncio.TimeoutError:
                        logger.warning("VLM TTS消息处理超时，强制结束")
                        consumer_task.cancel()
                    except Exception as e:
                        logger.error(f"VLM TTS消息处理出错: {e}")
                        consumer_task.cancel()
                    
                    # 关闭TTS连接
                    await client.close()
                    
                    # ⚠️ 重要：确保PCM队列完全处理完毕后再停止MP3任务
                    logger.info("VLM TTS连接已关闭，等待PCM队列完全处理...")
                    
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
                            logger.info(f"VLM PCM队列还有 {current_size} 个数据包待处理...")
                        
                        await asyncio.sleep(0.1)
                        wait_cycles += 1
                    
                    if wait_cycles >= max_wait_cycles:
                        remaining_pcm = pcm_queue.qsize()
                        logger.warning(f"VLM PCM队列处理超时，强制停止（剩余 {remaining_pcm} 个数据包）")
                        logger.warning(f"⚠️  可能丢失VLM音频时长约: {remaining_pcm * 0.32:.1f}秒 (每包约0.32秒)")
                    else:
                        logger.info("✅ VLM PCM队列已完全清空，所有音频数据处理完成")
                    
                    # 现在可以安全停止MP3处理任务
                    processing_active = False
                    
                    # 等待MP3处理任务完成
                    try:
                        await asyncio.wait_for(mp3_task, timeout=10.0)
                        logger.info("VLM MP3处理任务完成")
                    except asyncio.TimeoutError:
                        logger.warning("VLM MP3处理任务超时，强制取消")
                        mp3_task.cancel()
                    except Exception as e:
                        logger.error(f"VLM MP3处理任务出错: {e}")
                        mp3_task.cancel()
                    
                    # 发送完成信号 - 严格按照要求的格式
                    self.socketio.emit('audio_stream', {
                        'event': 'finished'
                    }, namespace='/v1/chat/vlm', room=session_id)
                    
                    # 发送完成信号后让出控制权
                    await asyncio.sleep(0)
                    
                    logger.info(f"✅ 发送VLM完成信号给客户端")
                    logger.info(f"🎵 VLM流式合成最终统计:")
                    logger.info(f"  - 向TTS发送: {text_segments_sent} 个文本片段")
                    logger.info(f"  - 生成MP3块: {audio_chunks_sent} 个")
                    logger.info(f"  - PCM队列最终状态: {pcm_queue.qsize()} 个剩余数据包")
                    
                    return {
                        'success': True,
                        'response': assistant_response,
                        'audio_chunks': audio_chunks_sent
                    }
                
                # 执行流式VLM对话和TTS
                return loop.run_until_complete(streaming_vlm_with_tts())
                
            except Exception as e:
                logger.error(f"流式VLM对话和TTS处理出错: {str(e)}")
                return {
                    'success': False,
                    'error': str(e)
                }
            finally:
                loop.close()
        
        # 在线程池中执行
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(process_streaming_vlm_and_tts)
            return future.result(timeout=180)  # 3分钟超时，VLM处理可能需要更长时间
    
    def _save_to_database(self, transcription_result, vlm_result, image_url):
        """保存对话记录到数据库"""
        try:
            if (transcription_result and transcription_result.get('success') and
                vlm_result and vlm_result.get('success')):
                
                user_message = transcription_result.get('text', '')
                assistant_response = vlm_result.get('response', '')
                
                # 在用户消息中包含图像信息
                user_message_with_image = f"[图像: {image_url}] {user_message}"
                
                save_chat_record(user_message_with_image, assistant_response)
                logger.info("VLM对话记录已保存到数据库")
        except Exception as e:
            logger.error(f"保存VLM对话记录时出错: {e}")
    
    def _notify_vlm_chat_tts_complete(self, vlm_result, transcription_result, session_id):
        """通知VLM对话和TTS完成"""
        try:
            self.socketio.emit('vlm_chat_tts_complete', {
                'message': 'VLM对话和TTS合成完成',
                'user_message': transcription_result.get('text', ''),
                'assistant_response': vlm_result.get('response', ''),
                'audio_chunks': vlm_result.get('audio_chunks', 0)
            }, namespace='/v1/chat/vlm', room=session_id)
        except Exception as e:
            logger.error(f"发送VLM完成通知时出错: {e}")
    
    def _cleanup_local_files(self, audio_filepath, image_filepath, 
                           audio_oss_result, image_oss_result):
        """清理本地文件"""
        try:
            # 删除音频文件
            if audio_filepath and os.path.exists(audio_filepath):
                if audio_oss_result and audio_oss_result.get('success'):
                    os.remove(audio_filepath)
                    logger.info(f"已删除本地音频文件: {audio_filepath}")
                else:
                    logger.warning(f"音频文件OSS上传失败，保留本地文件: {audio_filepath}")
            
            # 删除图像文件
            if image_filepath and os.path.exists(image_filepath):
                if image_oss_result and image_oss_result.get('success'):
                    os.remove(image_filepath)
                    logger.info(f"已删除本地图像文件: {image_filepath}")
                else:
                    logger.warning(f"图像文件OSS上传失败，保留本地文件: {image_filepath}")
                    
        except Exception as e:
            logger.error(f"清理本地文件时出错: {e}")