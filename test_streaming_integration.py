#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
流式语音对话测试：语音识别 -> AI流式对话 + 实时TTS合成
"""

import asyncio
import logging
import os
from datetime import datetime

# 导入模块
from chat_service import generate_chat_response_stream, test_chat_service
from tts_realtime_client import TTSRealtimeClient, SessionMode
from audio_transcription import test_transcription
from config import QWEN_API_KEY, REAL_TIME_AUDIO_URL, TTS_VOICE, TTS_OUTPUT_DIR, TTS_SAMPLE_RATE

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

async def test_streaming_chat_tts(user_message: str):
    """测试流式对话 + 实时TTS合成"""
    try:
        assistant_response = ""
        text_buffer = ""  # 用于积累文本
        tts_tasks = []  # 存储TTS任务
        audio_chunks_list = []  # 存储所有音频片段
        
        # 标点符号，用于判断句子结束
        sentence_endings = ['。', '！', '？', '.', '!', '?', '\n']
        
        print("AI流式回答: ", end="", flush=True)
        
        async def synthesize_text_segment(text: str, segment_id: int):
            """合成单个文本片段"""
            try:
                print(f"\n[TTS片段{segment_id}] 开始合成: {text}")
                
                audio_chunks = []
                
                def audio_callback(audio_bytes: bytes):
                    audio_chunks.append(audio_bytes)
                
                client = TTSRealtimeClient(
                    base_url=REAL_TIME_AUDIO_URL,
                    api_key=QWEN_API_KEY,
                    voice=TTS_VOICE,
                    mode=SessionMode.SERVER_COMMIT,
                    audio_callback=audio_callback
                )
                
                # 建立连接
                await client.connect()
                
                # 处理消息和发送文本
                consumer_task = asyncio.create_task(client.handle_messages())
                
                # 发送文本
                await client.append_text(text)
                await asyncio.sleep(0.5)
                await client.finish_session()
                
                # 等待音频接收完成
                await asyncio.sleep(2)
                
                # 关闭连接
                await client.close()
                consumer_task.cancel()
                
                print(f"[TTS片段{segment_id}] 合成完成: {len(audio_chunks)} 个音频块")
                return audio_chunks
                
            except Exception as e:
                print(f"[TTS片段{segment_id}] 合成失败: {str(e)}")
                return None
        
        # 流式获取对话响应并实时TTS
        for chunk in generate_chat_response_stream(user_message):
            assistant_response += chunk
            text_buffer += chunk
            print(chunk, end="", flush=True)
            
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
                
                # 创建TTS任务
                tts_task = asyncio.create_task(
                    synthesize_text_segment(text_to_synthesize, len(tts_tasks))
                )
                tts_tasks.append(tts_task)
                
                # 清空缓冲区
                text_buffer = ""
        
        print()  # 换行
        
        # 处理剩余的文本缓冲区
        if text_buffer.strip():
            print(f"[最后片段] 开始合成: {text_buffer.strip()}")
            tts_task = asyncio.create_task(
                synthesize_text_segment(text_buffer.strip(), len(tts_tasks))
            )
            tts_tasks.append(tts_task)
        
        print(f"\n📊 对话生成完成，完整回答: {assistant_response}")
        print(f"📊 创建了 {len(tts_tasks)} 个TTS任务")
        
        # 等待所有TTS任务完成
        if tts_tasks:
            print("⏳ 等待所有TTS片段完成...")
            
            # 等待所有任务完成并收集结果
            tts_results = await asyncio.gather(*tts_tasks, return_exceptions=True)
            
            # 合并所有音频片段
            success_count = 0
            for i, result in enumerate(tts_results):
                if isinstance(result, Exception):
                    print(f"❌ TTS片段 {i} 失败: {result}")
                elif result:
                    audio_chunks_list.extend(result)
                    success_count += 1
            
            print(f"✅ 成功完成 {success_count}/{len(tts_tasks)} 个TTS片段")
            
            if audio_chunks_list and success_count > 0:
                print("-" * 50)
                print("🎉 流式对话 + 实时TTS测试成功！")
                print(f"🎤 用户消息: {user_message}")
                print(f"🤖 AI回答: {assistant_response[:100]}...")
                print(f"📊 TTS片段数: {success_count}")
                print(f"📊 总音频块数: {len(audio_chunks_list)}")
                
                # 可选：保存音频文件用于测试
                if audio_chunks_list:
                    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_file = os.path.join(TTS_OUTPUT_DIR, f"test_streaming_{timestamp}.wav")
                    
                    # 合并所有音频数据
                    merged_audio_data = b"".join(audio_chunks_list)
                    
                    import wave
                    with wave.open(output_file, 'wb') as wav_file:
                        wav_file.setnchannels(1)  # 单声道
                        wav_file.setsampwidth(2)  # 16-bit
                        wav_file.setframerate(TTS_SAMPLE_RATE)
                        wav_file.writeframes(merged_audio_data)
                    
                    file_size = os.path.getsize(output_file)
                    
                    print(f"🎵 测试音频已保存: {output_file}")
                    print(f"📄 文件大小: {file_size} bytes")
                    print(f"⏱️ 估算时长: {len(merged_audio_data) / (TTS_SAMPLE_RATE * 2):.2f} 秒")
                
                return True
            else:
                print("❌ 没有成功的TTS片段")
                return False
        else:
            print("❌ 没有创建TTS任务")
            return False
            
    except Exception as e:
        print(f"❌ 流式对话+TTS测试失败: {str(e)}")
        logger.error(f"流式对话+TTS测试失败: {str(e)}")
        return False

async def test_complete_pipeline():
    """测试完整的流程"""
    print("🎙️ 流式语音对话系统测试")
    print("=" * 60)
    
    # 检查配置
    if not QWEN_API_KEY:
        print("❌ QWEN_API_KEY 未配置")
        return False
    
    print(f"✅ API Key: 已配置")
    print(f"✅ TTS URL: {REAL_TIME_AUDIO_URL}")
    print(f"✅ 语音: {TTS_VOICE}")
    print("-" * 60)

    try:
        # 步骤1: 测试语音识别
        print("1️⃣ 测试语音识别（使用官方示例）...")
        transcription_result = test_transcription()
        
        if not transcription_result or not transcription_result['success']:
            print("❌ 语音识别测试失败")
            return False
        
        user_message = transcription_result['text']
        print(f"✅ 语音识别成功: {user_message}")
        print("-" * 60)
        
        # 步骤2: 测试流式对话+实时TTS
        print("2️⃣ 测试流式对话 + 实时TTS合成...")
        success = await test_streaming_chat_tts(user_message)
        
        if success:
            print("✅ 完整流程测试成功")
            return True
        else:
            print("❌ 流式对话和实时TTS测试失败")
            return False
            
    except Exception as e:
        print(f"❌ 测试过程中出错: {str(e)}")
        logger.error(f"测试失败: {str(e)}")
        return False

def test_individual_components():
    """分别测试各个组件"""
    print("🧪 分别测试各个组件")
    print("=" * 50)
    
    # 测试1: 对话服务
    print("📝 测试对话服务...")
    chat_success = test_chat_service()
    print(f"对话服务: {'✅ 成功' if chat_success else '❌ 失败'}")
    print("-" * 50)
    
    # 测试2: 语音识别
    print("🎤 测试语音识别...")
    transcription_result = test_transcription()
    transcription_success = transcription_result and transcription_result['success']
    print(f"语音识别: {'✅ 成功' if transcription_success else '❌ 失败'}")
    if transcription_success:
        print(f"识别结果: {transcription_result['text']}")
    print("-" * 50)
    
    return chat_success and transcription_success

async def main():
    """主函数"""
    try:
        # 测试各个组件
        components_ok = test_individual_components()
        
        if components_ok:
            # 测试完整流程
            pipeline_ok = await test_complete_pipeline()
            
            if pipeline_ok:
                print("🎊 所有测试都通过了！")
                return True
            else:
                print("⚠️ 完整流程测试失败")
                return False
        else:
            print("⚠️ 组件测试失败，跳过完整流程测试")
            return False
            
    except Exception as e:
        print(f"❌ 运行测试时出错: {str(e)}")
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        if success:
            print("\n✅ 测试完成")
        else:
            print("\n❌ 测试失败")
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 运行出错: {str(e)}")