from flask import request
from flask_socketio import emit
import json
import logging
import base64
import time
import os
from datetime import datetime

from config import TTS_OUTPUT_DIR
from services.audio_processor import AudioProcessor

logger = logging.getLogger(__name__)

# 存储音频数据包的字典，按session_id组织
audio_sessions = {}

# 创建音频文件存储目录
AUDIO_STORAGE_DIR = 'audio_files'
if not os.path.exists(AUDIO_STORAGE_DIR):
    os.makedirs(AUDIO_STORAGE_DIR)

# 创建TTS输出目录
if not os.path.exists(TTS_OUTPUT_DIR):
    os.makedirs(TTS_OUTPUT_DIR)


def register_audio_handlers(socketio):
    """注册音频WebSocket事件处理器"""
    
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
                audio_processor = AudioProcessor(socketio)
                
                def process_audio_task():
                    """处理音频的后台任务"""
                    try:
                        # 处理完整的音频数据
                        success = audio_processor.process_complete_audio(session_id, session)
                        if success:
                            # 清理会话数据
                            if session_id in audio_sessions:
                                del audio_sessions[session_id]
                    except Exception as e:
                        logger.error(f"后台音频处理任务出错: {e}")
                        # 清理会话数据
                        if session_id in audio_sessions:
                            del audio_sessions[session_id]
                
                socketio.start_background_task(process_audio_task)

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