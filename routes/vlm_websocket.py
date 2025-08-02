from flask import request
from flask_socketio import emit
import json
import logging
import base64
import time
import os
from datetime import datetime

from config import TTS_OUTPUT_DIR
from services.vlm_processor import VLMProcessor

logger = logging.getLogger(__name__)

# 存储VLM数据包的字典，按session_id组织
vlm_sessions = {}

# 创建文件存储目录
VLM_STORAGE_DIR = 'vlm_files'
if not os.path.exists(VLM_STORAGE_DIR):
    os.makedirs(VLM_STORAGE_DIR)

# 创建TTS输出目录
if not os.path.exists(TTS_OUTPUT_DIR):
    os.makedirs(TTS_OUTPUT_DIR)


def register_vlm_handlers(socketio):
    """注册VLM WebSocket事件处理器"""
    
    @socketio.on('connect', namespace='/v1/chat/vlm')
    def handle_vlm_connect():
        """处理VLM WebSocket连接"""
        session_id = request.sid
        logger.info(f"VLM WebSocket连接建立: {session_id}")
        
        # 初始化VLM会话
        vlm_sessions[session_id] = {
            'audio_packets': {},  # 音频数据包
            'image_packets': {},  # 图像数据包
            'audio_total': 0,
            'image_total': 0,
            'audio_received': 0,
            'image_received': 0,
            'audio_expected_seq': 1,
            'image_expected_seq': 1,
            'audio_file_handle': None,
            'image_file_handle': None,
            'audio_filepath': None,
            'image_filepath': None,
            'start_time': datetime.now(),
            'end_received': False,
            'current_data_type': None,  # 'audio' 或 'image'
            'audio_complete': False,
            'image_complete': False
        }
        
        emit('connected', {'message': 'VLM连接已建立', 'session_id': session_id})

    @socketio.on('disconnect', namespace='/v1/chat/vlm')
    def handle_vlm_disconnect():
        """处理VLM WebSocket断开"""
        session_id = request.sid
        logger.info(f"VLM WebSocket连接断开: {session_id}")
        
        # 清理会话数据和文件句柄
        if session_id in vlm_sessions:
            session = vlm_sessions[session_id]
            # 确保文件句柄被正确关闭
            for file_handle_key in ['audio_file_handle', 'image_file_handle']:
                if session.get(file_handle_key):
                    try:
                        session[file_handle_key].close()
                        logger.info(f"已关闭文件句柄: {file_handle_key}")
                    except Exception as e:
                        logger.error(f"关闭文件句柄时出错: {e}")
            del vlm_sessions[session_id]

    @socketio.on('message', namespace='/v1/chat/vlm')
    def handle_vlm_message(message):
        """处理VLM消息 - 接收图像/音频数据包或结束信号"""
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
            
            # 检查是否是结束信号
            if data.get('type') == 'end':
                handle_end_signal(session_id)
                return
            
            # 验证数据包格式
            required_fields = ['seq', 'total', 'type', 'data']
            for field in required_fields:
                if field not in data:
                    emit('error', {'message': f'缺少必要字段: {field}'})
                    return
            
            seq = data['seq']
            total = data['total']
            data_type = data['type']
            binary_data = data['data']
            
            # 验证数据类型
            if not isinstance(seq, int) or not isinstance(total, int) or data_type not in ['audio', 'image']:
                emit('error', {'message': '数据类型错误'})
                return
            
            if not isinstance(binary_data, str):
                emit('error', {'message': '数据内容必须是base64字符串'})
                return
            
            # 验证序号范围
            if seq < 1 or seq > total:
                emit('error', {'message': f'序号超出范围: {seq}'})
                return
            
            # 验证数据包大小（base64编码后的大小）
            if len(binary_data) > 50000:  # 50KB限制，考虑图像可能较大
                emit('error', {'message': '数据包超过50KB限制'})
                return
            
            # 验证base64格式
            try:
                base64.b64decode(binary_data)
            except Exception as e:
                emit('error', {'message': f'无效的base64数据: {str(e)}'})
                return
            
            receive_timestamp = time.time()
            logger.info(f"收到{data_type}数据包 {seq}/{total}, 会话ID: {session_id}, 时间戳: {receive_timestamp:.3f}")
            
            # 获取或初始化会话
            if session_id not in vlm_sessions:
                handle_vlm_connect()
            
            session = vlm_sessions[session_id]
            
            # 处理数据包
            success = process_data_packet(session, seq, total, data_type, binary_data, session_id)
            if not success:
                return
            
            # 发送确认
            ack_timestamp = time.time()
            if data_type == 'audio':
                emit('packet_ack', {
                    'seq': seq,
                    'type': data_type,
                    'received': session['audio_received'],
                    'total': session['audio_total']
                })
            else:  # image
                emit('packet_ack', {
                    'seq': seq,
                    'type': data_type,
                    'received': session['image_received'],
                    'total': session['image_total']
                })
            logger.info(f"发送{data_type} ACK {seq}/{total}, 时间戳: {ack_timestamp:.3f}")

        except Exception as e:
            logger.error(f"处理VLM数据包时出错: {e}")
            # 清理文件句柄
            cleanup_session_files(session_id)
            emit('error', {'message': f'处理数据包时出错: {str(e)}'})

    def process_data_packet(session, seq, total, data_type, binary_data, session_id):
        """处理数据包"""
        try:
            # 检查数据类型一致性 - 不允许交叉混合
            if session['current_data_type'] is None:
                session['current_data_type'] = data_type
            elif session['current_data_type'] != data_type:
                # 检查当前数据类型是否已完成
                if data_type == 'audio' and not session['audio_complete']:
                    if session['current_data_type'] == 'image' and not session['image_complete']:
                        emit('error', {'message': '不允许图像和音频数据包交叉混合'})
                        return False
                elif data_type == 'image' and not session['image_complete']:
                    if session['current_data_type'] == 'audio' and not session['audio_complete']:
                        emit('error', {'message': '不允许图像和音频数据包交叉混合'})
                        return False
                
                # 如果当前类型已完成，可以切换到新类型
                session['current_data_type'] = data_type
            
            # 根据数据类型处理
            if data_type == 'audio':
                return process_audio_packet(session, seq, total, binary_data, session_id)
            else:  # image
                return process_image_packet(session, seq, total, binary_data, session_id)
                
        except Exception as e:
            logger.error(f"处理{data_type}数据包时出错: {e}")
            emit('error', {'message': f'处理{data_type}数据包时出错: {str(e)}'})
            return False

    def process_audio_packet(session, seq, total, binary_data, session_id):
        """处理音频数据包"""
        try:
            # 设置总包数和创建文件（第一次接收时）
            if session['audio_total'] == 0:
                session['audio_total'] = total
                # 创建音频文件
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"vlm_audio_{session_id}_{timestamp}.mp3"
                filepath = os.path.join(VLM_STORAGE_DIR, filename)
                session['audio_filepath'] = filepath
                session['audio_file_handle'] = open(filepath, 'wb')
                logger.info(f"创建音频文件: {filepath}")
            elif session['audio_total'] != total:
                emit('error', {'message': f'音频总包数不一致: 期望{session["audio_total"]}, 收到{total}'})
                return False
            
            # 确保文件句柄存在
            if not session.get('audio_file_handle'):
                logger.error(f"音频文件句柄不存在，会话状态异常")
                emit('error', {'message': '音频文件句柄不存在，请重新连接'})
                return False
            
            # 检查是否重复接收
            if seq in session['audio_packets'] or seq < session['audio_expected_seq']:
                emit('error', {'message': f'重复或过期的音频数据包序号: {seq}'})
                return False
            
            # 解码音频数据
            try:
                packet_data = base64.b64decode(binary_data)
            except Exception as e:
                emit('error', {'message': f'解码音频数据失败: {str(e)}'})
                return False
            
            # 流式写入：检查是否是期望的包
            if seq == session['audio_expected_seq']:
                # 按顺序到达，立即写入文件
                session['audio_file_handle'].write(packet_data)
                session['audio_file_handle'].flush()
                session['audio_expected_seq'] += 1
                session['audio_received'] += 1
                logger.info(f"流式写入音频数据包 {seq}, 大小: {len(packet_data)} bytes")
                
                # 检查暂存的包中是否有下一个期望的包
                while session['audio_expected_seq'] in session['audio_packets']:
                    next_seq = session['audio_expected_seq']
                    next_data = session['audio_packets'].pop(next_seq)
                    next_packet_data = base64.b64decode(next_data)
                    session['audio_file_handle'].write(next_packet_data)
                    session['audio_file_handle'].flush()
                    session['audio_expected_seq'] += 1
                    session['audio_received'] += 1
                    logger.info(f"从缓存写入音频数据包 {next_seq}, 大小: {len(next_packet_data)} bytes")
            else:
                # 乱序到达，暂存在内存中
                session['audio_packets'][seq] = binary_data
                logger.info(f"暂存乱序音频数据包 {seq}, 期望: {session['audio_expected_seq']}")
            
            # 检查音频是否接收完成
            if session['audio_received'] == session['audio_total']:
                # 关闭音频文件句柄
                if session['audio_file_handle']:
                    session['audio_file_handle'].close()
                    session['audio_file_handle'] = None
                
                # 检查是否有遗漏的包
                if session['audio_packets']:
                    missing_seqs = [str(s) for s in session['audio_packets'].keys()]
                    logger.warning(f"检测到遗漏的音频数据包: {', '.join(missing_seqs)}")
                    emit('error', {'message': f'音频接收不完整，遗漏包: {", ".join(missing_seqs)}'})
                    return False
                
                session['audio_complete'] = True
                logger.info(f"音频流式写入完成，会话ID: {session_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"处理音频数据包时出错: {e}")
            return False

    def process_image_packet(session, seq, total, binary_data, session_id):
        """处理图像数据包"""
        try:
            # 设置总包数和创建文件（第一次接收时）
            if session['image_total'] == 0:
                session['image_total'] = total
                # 创建图像文件
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"vlm_image_{session_id}_{timestamp}.jpg"  # 假设是JPEG格式
                filepath = os.path.join(VLM_STORAGE_DIR, filename)
                session['image_filepath'] = filepath
                session['image_file_handle'] = open(filepath, 'wb')
                logger.info(f"创建图像文件: {filepath}")
            elif session['image_total'] != total:
                emit('error', {'message': f'图像总包数不一致: 期望{session["image_total"]}, 收到{total}'})
                return False
            
            # 确保文件句柄存在
            if not session.get('image_file_handle'):
                logger.error(f"图像文件句柄不存在，会话状态异常")
                emit('error', {'message': '图像文件句柄不存在，请重新连接'})
                return False
            
            # 检查是否重复接收
            if seq in session['image_packets'] or seq < session['image_expected_seq']:
                emit('error', {'message': f'重复或过期的图像数据包序号: {seq}'})
                return False
            
            # 解码图像数据
            try:
                packet_data = base64.b64decode(binary_data)
            except Exception as e:
                emit('error', {'message': f'解码图像数据失败: {str(e)}'})
                return False
            
            # 流式写入：检查是否是期望的包
            if seq == session['image_expected_seq']:
                # 按顺序到达，立即写入文件
                session['image_file_handle'].write(packet_data)
                session['image_file_handle'].flush()
                session['image_expected_seq'] += 1
                session['image_received'] += 1
                logger.info(f"流式写入图像数据包 {seq}, 大小: {len(packet_data)} bytes")
                
                # 检查暂存的包中是否有下一个期望的包
                while session['image_expected_seq'] in session['image_packets']:
                    next_seq = session['image_expected_seq']
                    next_data = session['image_packets'].pop(next_seq)
                    next_packet_data = base64.b64decode(next_data)
                    session['image_file_handle'].write(next_packet_data)
                    session['image_file_handle'].flush()
                    session['image_expected_seq'] += 1
                    session['image_received'] += 1
                    logger.info(f"从缓存写入图像数据包 {next_seq}, 大小: {len(next_packet_data)} bytes")
            else:
                # 乱序到达，暂存在内存中
                session['image_packets'][seq] = binary_data
                logger.info(f"暂存乱序图像数据包 {seq}, 期望: {session['image_expected_seq']}")
            
            # 检查图像是否接收完成
            if session['image_received'] == session['image_total']:
                # 关闭图像文件句柄
                if session['image_file_handle']:
                    session['image_file_handle'].close()
                    session['image_file_handle'] = None
                
                # 检查是否有遗漏的包
                if session['image_packets']:
                    missing_seqs = [str(s) for s in session['image_packets'].keys()]
                    logger.warning(f"检测到遗漏的图像数据包: {', '.join(missing_seqs)}")
                    emit('error', {'message': f'图像接收不完整，遗漏包: {", ".join(missing_seqs)}'})
                    return False
                
                session['image_complete'] = True
                logger.info(f"图像流式写入完成，会话ID: {session_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"处理图像数据包时出错: {e}")
            return False

    def handle_end_signal(session_id):
        """处理结束信号"""
        logger.info(f"收到结束信号，会话ID: {session_id}")
        
        if session_id not in vlm_sessions:
            emit('error', {'message': '会话不存在'})
            return
        
        session = vlm_sessions[session_id]
        session['end_received'] = True
        
        # 检查是否缺少必要的数据
        if session['audio_total'] == 0 and session['image_total'] == 0:
            emit('error', {'message': '必须发送音频和图像数据'})
            return
        
        if session['audio_total'] > 0 and not session['audio_complete']:
            emit('error', {'message': '音频数据未完整接收'})
            return
        
        if session['image_total'] > 0 and not session['image_complete']:
            emit('error', {'message': '图像数据未完整接收'})
            return
        
        # 开始处理VLM流程
        logger.info(f"开始VLM处理流程，会话ID: {session_id}")
        
        # 异步处理后续流程，避免阻塞WebSocket事件循环
        vlm_processor = VLMProcessor(socketio)
        
        def process_vlm_task():
            """处理VLM的后台任务"""
            try:
                # 处理完整的VLM数据
                success = vlm_processor.process_complete_vlm(session_id, session)
                if success:
                    # 清理会话数据
                    if session_id in vlm_sessions:
                        del vlm_sessions[session_id]
            except Exception as e:
                logger.error(f"后台VLM处理任务出错: {e}")
                # 清理会话数据
                cleanup_session_files(session_id)
        
        socketio.start_background_task(process_vlm_task)

    def cleanup_session_files(session_id):
        """清理会话文件"""
        if session_id in vlm_sessions:
            session = vlm_sessions[session_id]
            for file_handle_key in ['audio_file_handle', 'image_file_handle']:
                if session.get(file_handle_key):
                    try:
                        session[file_handle_key].close()
                        session[file_handle_key] = None
                        logger.info(f"异常清理：已关闭文件句柄: {file_handle_key}")
                    except:
                        pass
            del vlm_sessions[session_id]