import logging
from dashscope import Generation, MultiModalConversation
from config import QWEN_API_KEY, QWEN_CHAT_MODEL, QWEN_VLM_MODEL

# 设置日志
logger = logging.getLogger(__name__)

def generate_chat_response_stream(user_message: str, system_prompt: str = "你是一个有帮助的AI助手，请用简洁、友好的语气回答用户问题。"):
    """
    生成流式对话响应 - 简化版本，不保存对话历史
    
    Args:
        user_message: 用户消息
        system_prompt: 系统提示词
        
    Yields:
        str: 流式响应的文本片段
    """
    try:
        # 构建消息
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message}
        ]
        
        logger.info(f"开始生成对话响应，用户消息: {user_message[:100]}...")
        
        # 调用千问流式API
        responses = Generation.call(
            api_key=QWEN_API_KEY,
            model=QWEN_CHAT_MODEL,
            messages=messages,
            result_format='message',
            stream=True,
            incremental_output=True
        )
        
        full_content = ""
        for response in responses:
            try:
                content = response.output.choices[0].message.content
                if content:
                    full_content += content
                    yield content
            except (AttributeError, IndexError) as e:
                logger.error(f"解析响应内容时出错: {e}")
                continue
        
        logger.info(f"对话响应生成完成，总长度: {len(full_content)}")
        
    except Exception as e:
        logger.error(f"生成对话响应时出错: {str(e)}")
        yield f"抱歉，生成回答时出现错误：{str(e)}"


async def generate_chat_response_stream_async(user_message: str, system_prompt: str = "你是一个有帮助的AI助手，请用简洁、友好的语气回答用户问题。"):
    """
    异步生成流式对话响应 - 优化版本，避免阻塞事件循环
    
    Args:
        user_message: 用户消息
        system_prompt: 系统提示词
        
    Yields:
        str: 流式响应的文本片段
    """
    import asyncio
    import concurrent.futures
    
    try:
        # 构建消息
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message}
        ]
        
        logger.info(f"开始异步生成对话响应，用户消息: {user_message[:100]}...")
        
        def sync_generation():
            """在线程池中执行同步的千问API调用"""
            try:
                responses = Generation.call(
                    api_key=QWEN_API_KEY,
                    model=QWEN_CHAT_MODEL,
                    messages=messages,
                    result_format='message',
                    stream=True,
                    incremental_output=True
                )
                
                chunks = []
                for response in responses:
                    try:
                        content = response.output.choices[0].message.content
                        if content:
                            chunks.append(content)
                    except (AttributeError, IndexError) as e:
                        logger.error(f"解析响应内容时出错: {e}")
                        continue
                return chunks
            except Exception as e:
                logger.error(f"同步生成对话响应时出错: {str(e)}")
                return [f"抱歉，生成回答时出现错误：{str(e)}"]
        
        # 在线程池中执行同步操作，添加超时保护
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='ChatGen') as executor:
            try:
                chunks = await asyncio.wait_for(
                    loop.run_in_executor(executor, sync_generation),
                    timeout=60.0  # 60秒超时
                )
            except asyncio.TimeoutError:
                logger.error("聊天生成超时，返回错误信息")
                chunks = ["抱歉，AI回答生成超时，请重试。"]
            
            full_content = ""
            for chunk in chunks:
                full_content += chunk
                yield chunk
                # 让出控制权给其他协程
                await asyncio.sleep(0)
        
        logger.info(f"异步对话响应生成完成，总长度: {len(full_content)}")
        
    except Exception as e:
        logger.error(f"异步生成对话响应时出错: {str(e)}")
        yield f"抱歉，生成回答时出现错误：{str(e)}"


def generate_vlm_response_stream(user_message: str, image_url: str, system_prompt: str = "You are a helpful assistant."):
    """
    生成多模态流式对话响应
    
    Args:
        user_message: 用户文本消息
        image_url: 图像URL
        system_prompt: 系统提示词
        
    Yields:
        str: 流式响应的文本片段
    """
    try:
        # 构建多模态消息
        messages = [
            {
                "role": "system",
                "content": [{"text": system_prompt}]
            },
            {
                "role": "user",
                "content": [
                    {"image": image_url},
                    {"text": user_message}
                ]
            }
        ]
        
        logger.info(f"开始生成多模态对话响应，用户消息: {user_message[:100]}..., 图像: {image_url}")
        
        # 调用千问多模态流式API
        responses = MultiModalConversation.call(
            api_key=QWEN_API_KEY,
            model=QWEN_VLM_MODEL,
            messages=messages,
            stream=True,
            incremental_output=True
        )
        
        full_content = ""
        for response in responses:
            try:
                # 解析多模态响应
                content = response["output"]["choices"][0]["message"].content[0]["text"]
                if content:
                    full_content += content
                    yield content
            except (KeyError, IndexError, TypeError) as e:
                logger.error(f"解析多模态响应内容时出错: {e}")
                continue
        
        logger.info(f"多模态对话响应生成完成，总长度: {len(full_content)}")
        
    except Exception as e:
        logger.error(f"生成多模态对话响应时出错: {str(e)}")
        yield f"抱歉，生成多模态回答时出现错误：{str(e)}"


async def generate_vlm_response_stream_async(user_message: str, image_url: str, system_prompt: str = "You are a helpful assistant."):
    """
    异步生成多模态流式对话响应 - 优化版本，避免阻塞事件循环
    
    Args:
        user_message: 用户文本消息
        image_url: 图像URL
        system_prompt: 系统提示词
        
    Yields:
        str: 流式响应的文本片段
    """
    import asyncio
    import concurrent.futures
    
    try:
        # 构建多模态消息
        messages = [
            {
                "role": "system",
                "content": [{"text": system_prompt}]
            },
            {
                "role": "user",
                "content": [
                    {"image": image_url},
                    {"text": user_message}
                ]
            }
        ]
        
        logger.info(f"开始异步生成多模态对话响应，用户消息: {user_message[:100]}..., 图像: {image_url}")
        
        def sync_vlm_generation():
            """在线程池中执行同步的千问多模态API调用"""
            try:
                responses = MultiModalConversation.call(
                    api_key=QWEN_API_KEY,
                    model=QWEN_VLM_MODEL,
                    messages=messages,
                    stream=True,
                    incremental_output=True
                )
                
                chunks = []
                for response in responses:
                    try:
                        # 解析多模态响应
                        content = response["output"]["choices"][0]["message"].content[0]["text"]
                        if content:
                            chunks.append(content)
                    except (KeyError, IndexError, TypeError) as e:
                        logger.error(f"解析多模态响应内容时出错: {e}")
                        continue
                return chunks
            except Exception as e:
                logger.error(f"同步生成多模态对话响应时出错: {str(e)}")
                return [f"抱歉，生成多模态回答时出现错误：{str(e)}"]
        
        # 在线程池中执行同步操作，添加超时保护
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='VLMGen') as executor:
            try:
                chunks = await asyncio.wait_for(
                    loop.run_in_executor(executor, sync_vlm_generation),
                    timeout=90.0  # 90秒超时，多模态处理可能需要更长时间
                )
            except asyncio.TimeoutError:
                logger.error("多模态生成超时，返回错误信息")
                chunks = ["抱歉，多模态AI回答生成超时，请重试。"]
            
            full_content = ""
            for chunk in chunks:
                full_content += chunk
                yield chunk
                # 让出控制权给其他协程
                await asyncio.sleep(0)
        
        logger.info(f"异步多模态对话响应生成完成，总长度: {len(full_content)}")
        
    except Exception as e:
        logger.error(f"异步生成多模态对话响应时出错: {str(e)}")
        yield f"抱歉，生成多模态回答时出现错误：{str(e)}"
