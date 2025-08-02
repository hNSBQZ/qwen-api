from flask import Blueprint, request, jsonify, Response
import requests
import json
import logging

from database import save_chat_record
from config import QWEN_API_KEY, QWEN_API_CHAT_URL, QWEN_CHAT_MODEL

logger = logging.getLogger(__name__)

# 创建聊天API蓝图
chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/v1/chat/completions', methods=['POST'])
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