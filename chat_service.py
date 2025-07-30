import logging
import os
from dashscope import Generation
from config import QWEN_API_KEY, QWEN_CHAT_MODEL

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

def test_chat_service():
    """测试对话服务"""
    logger.info("开始测试对话服务...")
    
    test_message = "你好，请简单介绍一下你自己"
    logger.info(f"测试消息: {test_message}")
    
    full_response = ""
    print("流式输出内容为：")
    
    try:
        for chunk in generate_chat_response_stream(test_message):
            full_response += chunk
            print(chunk, end="", flush=True)
        
        print()  # 换行
        print(f"完整内容为：{full_response}")
        return True
        
    except Exception as e:
        logger.error(f"对话服务测试失败: {str(e)}")
        return False

if __name__ == "__main__":
    # 设置基本日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    # 运行测试
    test_chat_service() 