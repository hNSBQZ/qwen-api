from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests
import json
import logging
from datetime import datetime
import time
import base64
import os
import asyncio
import concurrent.futures

from database import init_database, save_chat_record, get_chat_history
from config import (QWEN_API_KEY, QWEN_API_CHAT_URL, QWEN_CHAT_MODEL,
                    REAL_TIME_AUDIO_URL, TTS_VOICE, TTS_SAMPLE_RATE, TTS_OUTPUT_DIR,
                    DEFAULT_SYSTEM_PROMPT)
from up_to_oss import upload_audio_file, upload_and_cleanup
from audio_transcription import transcribe_audio_from_url
from chat_service import generate_chat_response_stream
from tts_realtime_client import TTSRealtimeClient, SessionMode, synthesize_text_to_audio

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # 生产环境中应使用环境变量

# 设置日志 - 只输出INFO级别
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 设置第三方库日志级别
logging.getLogger('werkzeug').setLevel(logging.WARNING)  # Flask服务器日志
logging.getLogger('urllib3').setLevel(logging.WARNING)   # HTTP请求日志
logging.getLogger('requests').setLevel(logging.WARNING)  # requests库日志
logging.getLogger('websockets').setLevel(logging.WARNING) # websocket日志
logging.getLogger('dashscope').setLevel(logging.WARNING)  # 阿里云SDK日志

# 初始化SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)

# 配置CORS，允许跨域访问
CORS(app, resources={
    r"/v1/chat/completions": {
        "origins": "*",  # 允许所有域名访问
        "methods": ["POST"],
        "allow_headers": ["Content-Type", "Authorization"]
    },
    r"/health": {
        "origins": "*",  # 允许所有域名访问
        "methods": ["GET"]
    }
})

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 初始化数据库
init_database()

# 创建音频文件存储目录
AUDIO_STORAGE_DIR = 'audio_files'
if not os.path.exists(AUDIO_STORAGE_DIR):
    os.makedirs(AUDIO_STORAGE_DIR)

# 创建TTS输出目录
if not os.path.exists(TTS_OUTPUT_DIR):
    os.makedirs(TTS_OUTPUT_DIR)

# 存储音频数据包的字典，按session_id组织
audio_sessions = {}

# 检查配置
logger.info(f"QWEN_API_KEY: {'已设置' if QWEN_API_KEY else '未设置'}")
logger.info(f"QWEN_API_CHAT_URL: {QWEN_API_CHAT_URL}")
logger.info(f"QWEN_CHAT_MODEL: {QWEN_CHAT_MODEL}")

# WebSocket事件处理
@socketio.on('connect', namespace='/v1/chat/audio')
def handle_audio_connect():
    """处理音频WebSocket连接"""
    session_id = request.sid
    logger.info(f"音频WebSocket连接建立: {session_id}")
    
    # 初始化音频会话
    audio_sessions[session_id] = {
        'packets': {},  # 只存储乱序的包
        'total_packets': 0,
        'received_count': 0,
        'expected_seq': 1,  # 期望的下一个包序号
        'file_handle': None,  # 文件句柄
        'filepath': None,  # 文件路径
        'start_time': datetime.now()
    }
    
    emit('connected', {'message': '音频连接已建立', 'session_id': session_id})

@socketio.on('disconnect', namespace='/v1/chat/audio')
def handle_audio_disconnect():
    """处理音频WebSocket断开"""
    session_id = request.sid
    logger.info(f"音频WebSocket连接断开: {session_id}")
    
    # 清理会话数据和文件句柄
    if session_id in audio_sessions:
        session = audio_sessions[session_id]
        # 确保文件句柄被正确关闭
        if session.get('file_handle'):
            try:
                session['file_handle'].close()
                logger.info(f"已关闭文件句柄: {session.get('filepath', 'unknown')}")
            except Exception as e:
                logger.error(f"关闭文件句柄时出错: {e}")
        del audio_sessions[session_id]

@socketio.on('message', namespace='/v1/chat/audio')
def handle_audio_message(message):
    """处理音频消息 - 接收纯JSON数据"""
    session_id = request.sid
    
    try:
        # 如果收到的是字符串，尝试解析为JSON
        if isinstance(message, str):
            try:
                data = json.loads(message)
            except json.JSONDecodeError as e:
                emit('error', {'message': f'JSON解析错误: {str(e)}'})
                return
        else:
            data = message
        
        # 验证数据格式
        if not isinstance(data, dict):
            emit('error', {'message': '数据格式错误，必须是JSON对象'})
            return
        
        required_fields = ['seq', 'total', 'data']
        for field in required_fields:
            if field not in data:
                emit('error', {'message': f'缺少必要字段: {field}'})
                return
        
        seq = data['seq']
        total = data['total']
        audio_data = data['data']
        
        # 验证数据类型
        if not isinstance(seq, int) or not isinstance(total, int) or not isinstance(audio_data, str):
            emit('error', {'message': '数据类型错误'})
            return
        
        # 验证序号范围
        if seq < 1 or seq > total:
            emit('error', {'message': f'序号超出范围: {seq}'})
            return
        
        # 验证数据包大小（base64编码后的大小）
        if len(audio_data) > 11000:  # 考虑base64编码增加约1/3大小，8KB*4/3≈11KB
            emit('error', {'message': '数据包超过8KB限制'})
            return
        
        # 验证base64格式
        try:
            base64.b64decode(audio_data)
        except Exception as e:
            emit('error', {'message': f'无效的base64数据: {str(e)}'})
            return
        
        receive_timestamp = time.time()
        logger.info(f"收到音频数据包 {seq}/{total}, 会话ID: {session_id}, 时间戳: {receive_timestamp:.3f}")
        
        # 获取或初始化会话
        if session_id not in audio_sessions:
            audio_sessions[session_id] = {
                'packets': {},  # 只存储乱序的包
                'total_packets': 0,
                'received_count': 0,
                'expected_seq': 1,  # 期望的下一个包序号
                'file_handle': None,  # 文件句柄
                'filepath': None,  # 文件路径
                'start_time': datetime.now()
            }
        
        session = audio_sessions[session_id]
        
        # 设置总包数和创建文件（第一次接收时）
        if session['total_packets'] == 0:
            session['total_packets'] = total
            # 创建音频文件
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"audio_{session_id}_{timestamp}.mp3"
                filepath = os.path.join(AUDIO_STORAGE_DIR, filename)
                session['filepath'] = filepath
                session['file_handle'] = open(filepath, 'wb')
                logger.info(f"创建音频文件: {filepath}")
            except Exception as e:
                logger.error(f"创建音频文件失败: {e}")
                emit('error', {'message': f'创建音频文件失败: {str(e)}'})
                return
        elif session['total_packets'] != total:
            emit('error', {'message': f'总包数不一致: 期望{session["total_packets"]}, 收到{total}'})
            return
        
        # 确保文件句柄存在
        if not session.get('file_handle'):
            logger.error(f"文件句柄不存在，会话状态异常")
            emit('error', {'message': '文件句柄不存在，请重新连接'})
            return
        
        # 安全检查：确保关键字段存在（防止异常情况下的状态不一致）
        if 'expected_seq' not in session:
            logger.warning(f"会话缺少expected_seq字段，重新初始化")
            session['expected_seq'] = 1
        if 'received_count' not in session:
            logger.warning(f"会话缺少received_count字段，重新初始化")
            session['received_count'] = 0
        if 'packets' not in session:
            logger.warning(f"会话缺少packets字段，重新初始化")
            session['packets'] = {}
        
        # 检查是否重复接收
        if seq in session['packets'] or seq < session['expected_seq']:
            emit('error', {'message': f'重复或过期的数据包序号: {seq}'})
            return
        
        # 解码音频数据
        try:
            packet_data = base64.b64decode(audio_data)
        except Exception as e:
            emit('error', {'message': f'解码音频数据失败: {str(e)}'})
            return
        
        # 流式写入：检查是否是期望的包
        if seq == session['expected_seq']:
            # 按顺序到达，立即写入文件
            session['file_handle'].write(packet_data)
            session['file_handle'].flush()  # 确保写入磁盘
            session['expected_seq'] += 1
            session['received_count'] += 1
            logger.info(f"流式写入数据包 {seq}, 大小: {len(packet_data)} bytes")
            
            # 检查暂存的包中是否有下一个期望的包
            while session['expected_seq'] in session['packets']:
                next_seq = session['expected_seq']
                next_data = session['packets'].pop(next_seq)
                next_packet_data = base64.b64decode(next_data)
                session['file_handle'].write(next_packet_data)
                session['file_handle'].flush()
                session['expected_seq'] += 1
                session['received_count'] += 1
                logger.info(f"从缓存写入数据包 {next_seq}, 大小: {len(next_packet_data)} bytes")
        else:
            # 乱序到达，暂存在内存中
            session['packets'][seq] = audio_data
            logger.info(f"暂存乱序数据包 {seq}, 期望: {session['expected_seq']}")
        
        # 发送确认
        ack_timestamp = time.time()
        emit('packet_ack', {
            'seq': seq,
            'received': session['received_count'],
            'total': session['total_packets']
        })
        logger.info(f"发送ACK {seq}/{session['total_packets']}, 时间戳: {ack_timestamp:.3f}")
        
        # 检查是否接收完成
        if session['received_count'] == session['total_packets']:
            # 关闭文件句柄
            if session['file_handle']:
                session['file_handle'].close()
                session['file_handle'] = None
            
            # 检查是否有遗漏的包
            if session['packets']:
                missing_seqs = [str(s) for s in session['packets'].keys()]
                logger.warning(f"检测到遗漏的数据包: {', '.join(missing_seqs)}")
                emit('error', {'message': f'音频接收不完整，遗漏包: {", ".join(missing_seqs)}'})
                return
            
            logger.info(f"音频流式写入完成，会话ID: {session_id}")
            # 异步处理后续流程，避免阻塞WebSocket事件循环
            socketio.start_background_task(process_complete_audio, session_id)

    except Exception as e:
        logger.error(f"处理音频数据包时出错: {e}")
        # 清理文件句柄
        if session_id in audio_sessions:
            session = audio_sessions[session_id]
            if session.get('file_handle'):
                try:
                    session['file_handle'].close()
                    session['file_handle'] = None
                    logger.info(f"异常清理：已关闭文件句柄: {session.get('filepath', 'unknown')}")
                except:
                    pass
        emit('error', {'message': f'处理数据包时出错: {str(e)}'})

def process_complete_audio(session_id):
    """处理完整的音频数据 - 已流式写入完成"""
    try:
        session = audio_sessions[session_id]
        filepath = session['filepath']
        
        # 获取文件大小和处理时长
        file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        duration = (datetime.now() - session['start_time']).total_seconds()
        filename = os.path.basename(filepath)
        
        logger.info(f"音频流式写入完成: {filepath}, 大小: {file_size} bytes, 用时: {duration:.2f}s")
        
        # 上传到OSS
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
        
        # 语音识别
        transcription_result = None
        if oss_result and oss_result['success']:
            try:
                logger.info("开始语音识别...")
                # 通知客户端开始语音识别
                socketio.emit('transcription_started', {
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
        
        # 对话生成和TTS合成 - 简化版本
        chat_result = None
        
        if transcription_result and transcription_result['success'] and transcription_result['text'].strip():
            try:
                user_message = transcription_result['text'].strip()
                logger.info(f"开始对话生成，用户消息: {user_message}")
                
                # 通知客户端开始对话生成
                socketio.emit('chat_started', {
                    'message': '开始生成AI回答...',
                    'user_message': user_message
                }, namespace='/v1/chat/audio', room=session_id)
                
                # 实时流式对话和TTS合成
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
                            socketio.emit('tts_started', {
                                'message': '开始语音合成...'
                            }, namespace='/v1/chat/audio', room=session_id)
                            
                            # 创建单一TTS连接
                            audio_chunks_sent = 0
                            
                            def audio_callback(audio_bytes: bytes):
                                nonlocal audio_chunks_sent
                                audio_chunks_sent += 1
                                # 发送音频数据给客户端 - 严格按照要求的格式
                                audio_timestamp = time.time()
                                audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                                socketio.emit('audio_stream', {
                                    'event': 'data',
                                    'data': audio_base64
                                }, namespace='/v1/chat/audio', room=session_id)
                                logger.info(f"发送音频块 {audio_chunks_sent}, 大小: {len(audio_bytes)} bytes, 时间戳: {audio_timestamp:.3f}")
                            
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
                                socketio.emit('chat_chunk', {
                                    'chunk': chunk,
                                    'full_response': assistant_response
                                }, namespace='/v1/chat/audio', room=session_id)
                                
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
                                    logger.info(f"发送TTS合成片段: {text_to_synthesize[:50]}{'...' if len(text_to_synthesize) > 50 else ''}")
                                    
                                    # 直接发送到同一个TTS连接
                                    await client.append_text(text_to_synthesize)
                                    
                                    # 短暂等待确保发送完成
                                    await asyncio.sleep(0.1)
                                    
                                    # 清空缓冲区
                                    text_buffer = ""
                            
                            logger.info(f"对话生成完成，完整回答: {assistant_response}")
                            
                            # 处理剩余的文本缓冲区
                            if text_buffer.strip():
                                logger.info(f"发送最后的TTS合成片段: {text_buffer.strip()[:50]}{'...' if len(text_buffer.strip()) > 50 else ''}")
                                await client.append_text(text_buffer.strip())
                                await asyncio.sleep(0.1)
                            
                            # 结束TTS会话
                            await client.finish_session()
                            logger.info(f"TTS会话结束，已发送 {audio_chunks_sent} 个音频块")
                            
                            # 等待TTS真正完成 - 等待handle_messages处理完所有消息
                            try:
                                await asyncio.wait_for(consumer_task, timeout=10.0)
                                logger.info("TTS消息处理完成")
                            except asyncio.TimeoutError:
                                logger.warning("TTS消息处理超时，强制结束")
                                consumer_task.cancel()
                            except Exception as e:
                                logger.error(f"TTS消息处理出错: {e}")
                                consumer_task.cancel()
                            
                            # 关闭TTS连接
                            await client.close()
                            
                            # 发送完成信号 - 严格按照要求的格式
                            socketio.emit('audio_stream', {
                                'event': 'finished'
                            }, namespace='/v1/chat/audio', room=session_id)
                            
                            logger.info(f"✅ 发送完成信号给客户端")
                            logger.info(f"单一连接TTS合成完成，总共发送 {audio_chunks_sent} 个音频块")
                            
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
                    chat_result = future.result(timeout=120)  # 2分钟超时
                
                if chat_result and chat_result['success']:
                    logger.info("流式对话和TTS合成完成")
                    
                    # 保存用户提示词和AI回复到数据库
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
                    
                    # 通知客户端完成
                    tts_result = chat_result.get('tts_result', {})
                    socketio.emit('chat_tts_complete', {
                        'message': '实时对话生成和语音合成完成',
                        'assistant_response': chat_result['assistant_response'],
                        'tts_success': tts_result.get('success', False),
                        'segments_count': tts_result.get('segments_count', 0),
                        'total_segments': tts_result.get('total_segments', 0),
                        'db_saved': user_message_for_db and assistant_response_for_db
                    }, namespace='/v1/chat/audio', room=session_id)
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
        
        # 构造响应数据
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
        
        # 清理本地文件（仅在OSS上传成功时）
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
        
        # 发送完成通知
        socketio.emit('audio_complete', response_data, namespace='/v1/chat/audio', room=session_id)
        
        # 清理会话数据
        del audio_sessions[session_id]
        
    except Exception as e:
        logger.error(f"处理完整音频数据时出错: {e}")
        # 清理文件句柄和会话数据
        if session_id in audio_sessions:
            session = audio_sessions[session_id]
            if session.get('file_handle'):
                try:
                    session['file_handle'].close()
                    logger.info(f"异常清理：已关闭文件句柄: {session.get('filepath', 'unknown')}")
                except:
                    pass
            del audio_sessions[session_id]
        socketio.emit('error', {'message': f'处理音频数据时出错: {str(e)}'}, 
                     namespace='/v1/chat/audio', room=session_id)

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    """千问对话接口，兼容OpenAI格式，支持流式和非流式输出"""
    logger.info("收到聊天请求")
    
    try:
        # 获取请求数据
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing JSON data'}), 400
        
        # 验证必要参数
        if 'messages' not in data:
            return jsonify({'error': 'Missing messages parameter'}), 400
        
        # 获取Authorization header中的API key
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401
        
        # 检查是否需要流式输出
        is_stream = data.get('stream', False)
        
        # 构造发送给Qwen API的请求数据
        qwen_data = {
            'model': data.get('model', QWEN_CHAT_MODEL),
            'messages': data['messages'],
            'enable_thinking': False  # 强制设置为false
        }
        
        # 添加其他可选参数
        optional_params = ['temperature', 'top_p', 'max_tokens', 'stream']
        for param in optional_params:
            if param in data:
                qwen_data[param] = data[param]
        
        # 设置请求头
        headers = {
            'Authorization': f'Bearer {QWEN_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # 构造完整的Qwen API URL
        qwen_url = QWEN_API_CHAT_URL
        
        logger.info(f"转发请求到: {qwen_url}")
        logger.info(f"请求数据: {json.dumps(qwen_data, ensure_ascii=False)}")
        logger.info(f"流式模式: {is_stream}")
        
        # 提取用户提示词用于数据库记录
        user_prompt = ""
        for message in data['messages']:
            if message.get('role') == 'user':
                user_prompt = message.get('content', '')
                break
        
        if is_stream:
            # 流式输出处理
            return handle_stream_response(qwen_url, headers, qwen_data, user_prompt)
        else:
            # 非流式输出处理（保持原有逻辑）
            return handle_non_stream_response(qwen_url, headers, qwen_data, data, user_prompt)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"请求Qwen API时出错: {e}")
        return jsonify({'error': f'Request to Qwen API failed: {str(e)}'}), 500
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误: {e}")
        return jsonify({'error': 'Invalid JSON response from Qwen API'}), 500
    
    except Exception as e:
        logger.error(f"处理请求时出错: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

def handle_stream_response(qwen_url, headers, qwen_data, user_prompt):
    """处理流式响应"""
    def generate():
        try:
            # 发送流式请求到Qwen API
            response = requests.post(
                qwen_url,
                headers=headers,
                json=qwen_data,
                stream=True,
                timeout=60
            )
            
            if response.status_code != 200:
                logger.error(f"Qwen API请求失败: {response.status_code}, {response.text}")
                error_data = {
                    'error': f'Qwen API error: {response.status_code}',
                    'details': response.text
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                return
            
            # 用于收集完整的响应内容
            complete_response = ""
            
            # 逐行读取流式响应
            for line in response.iter_lines(decode_unicode=True):
                if line.strip():  # 跳过空行
                    # 只处理以 data: 开头的行
                    if line.startswith('data: '):
                        json_part = line[6:].strip()
                        if json_part == '[DONE]':
                            continue
                        try:
                            chunk_data = json.loads(json_part)
                            
                            # 提取内容用于数据库记录
                            if ('choices' in chunk_data and 
                                len(chunk_data['choices']) > 0 and 
                                'delta' in chunk_data['choices'][0] and 
                                'content' in chunk_data['choices'][0]['delta']):
                                content = chunk_data['choices'][0]['delta']['content']
                                if content:
                                    complete_response += content
                            
                            # 转发给客户端（保持原始格式）
                            yield f"{json_part}\n"
                            
                        except json.JSONDecodeError:
                            logger.warning(f"无法解析的JSON数据: {json_part}")
                            # 如果不是JSON，仍然转发（可能是其他格式的数据）
                            yield f"{json_part}\n"
                    else:
                        # 非data:行直接转发
                        yield f"{line}\n"
            
            # 流式完成后，记录到数据库
            if user_prompt and complete_response.strip():
                try:
                    save_result = save_chat_record(user_prompt, complete_response.strip())
                    if save_result:
                        logger.info("流式聊天记录已保存到数据库")
                    else:
                        logger.warning("流式聊天记录保存失败")
                except Exception as e:
                    logger.error(f"保存流式聊天记录时出错: {e}")
                    
        except Exception as e:
            logger.error(f"处理流式响应时出错: {e}")
            error_data = {'error': f'Stream processing error: {str(e)}'}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    # 返回流式响应
    return Response(
        generate(),
        mimetype='text/plain',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # 禁用nginx缓冲
        }
    )

def handle_non_stream_response(qwen_url, headers, qwen_data, original_data, user_prompt):
    """处理非流式响应（保持原有逻辑）"""
    # 发送请求到Qwen API
    response = requests.post(
        qwen_url,
        headers=headers,
        json=qwen_data,
        timeout=60
    )
    
    if response.status_code != 200:
        logger.error(f"Qwen API请求失败: {response.status_code}, {response.text}")
        return jsonify({
            'error': f'Qwen API error: {response.status_code}',
            'details': response.text
        }), response.status_code
    
    # 解析Qwen API响应
    qwen_response = response.json()
    logger.info(f"Qwen API响应: {json.dumps(qwen_response, ensure_ascii=False)}")
    
    # 提取模型回答用于数据库记录
    model_response = ""
    if 'choices' in qwen_response and len(qwen_response['choices']) > 0:
        choice = qwen_response['choices'][0]
        if 'message' in choice and 'content' in choice['message']:
            model_response = choice['message']['content']
    
    # 记录到数据库
    if user_prompt and model_response:
        try:
            save_result = save_chat_record(user_prompt, model_response)
            if save_result:
                logger.info("聊天记录已保存到数据库")
            else:
                logger.warning("聊天记录保存失败")
        except Exception as e:
            logger.error(f"保存聊天记录时出错: {e}")
    
    # 直接返回Qwen API的响应
    return jsonify(qwen_response)

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    logger.info("收到健康检查请求")
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    # 使用SocketIO启动应用
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
