import asyncio
import websockets
import json
import base64
import time
import logging
import wave
import os
from typing import Optional, Callable, Dict, Any, List
from enum import Enum

# 设置日志
logger = logging.getLogger(__name__)

class SessionMode(Enum):
    """会话模式枚举"""
    SERVER_COMMIT = "server_commit"
    COMMIT = "commit"

class TTSRealtimeClient:
    """
    与 TTS Realtime API 交互的客户端 - 简化版本
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str,
        voice: str = "Cherry",
        mode: SessionMode = SessionMode.SERVER_COMMIT,
        audio_callback: Optional[Callable[[bytes], None]] = None
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.voice = voice
        self.mode = mode
        self.ws = None
        self.audio_callback = audio_callback
        
        # 音频数据收集
        self._audio_chunks: List[bytes] = []

    async def connect(self) -> None:
        """与 TTS Realtime API 建立 WebSocket 连接"""
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        self.ws = await websockets.connect(self.base_url, additional_headers=headers)
        
        # 设置默认会话配置
        await self.update_session({
            "mode": self.mode.value,
            "voice": self.voice,
            "response_format": "pcm",
            "sample_rate": 24000
        })

    async def send_event(self, event: Dict[str, Any]) -> None:
        """发送事件到服务器"""
        event['event_id'] = "event_" + str(int(time.time() * 1000))
        await self.ws.send(json.dumps(event))

    async def update_session(self, config: Dict[str, Any]) -> None:
        """更新会话配置"""
        event = {
            "type": "session.update",
            "session": config
        }
        await self.send_event(event)

    async def append_text(self, text: str) -> None:
        """向 API 发送文本数据"""
        event = {
            "type": "input_text_buffer.append",
            "text": text
        }
        await self.send_event(event)

    async def finish_session(self) -> None:
        """结束会话"""
        event = {
            "type": "session.finish"
        }
        await self.send_event(event)

    async def handle_messages(self) -> None:
        """处理来自服务器的消息"""
        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type")
                
                if event_type == "error":
                    logger.error(f"TTS API 错误: {event.get('error', {})}")
                    continue
                elif event_type == "session.created":
                    logger.info(f"TTS 会话创建，ID: {event.get('session', {}).get('id')}")
                elif event_type == "session.updated":
                    logger.info(f"TTS 会话更新，ID: {event.get('session', {}).get('id')}")
                elif event_type == "response.audio.delta" and self.audio_callback:
                    audio_bytes = base64.b64decode(event.get("delta", ""))
                    self._audio_chunks.append(audio_bytes)
                    self.audio_callback(audio_bytes)
                elif event_type == "response.audio.done":
                    logger.info("音频生成完成")
                elif event_type == "response.done":
                    logger.info("响应完成")
                elif event_type == "session.finished":
                    logger.info("会话已结束")
                    break

        except websockets.exceptions.ConnectionClosed:
            logger.warning("TTS WebSocket 连接已关闭")
        except Exception as e:
            logger.error(f"处理TTS消息时出错: {str(e)}")

    async def close(self) -> None:
        """关闭 WebSocket 连接"""
        if self.ws:
            await self.ws.close()

    def get_audio_chunks(self) -> List[bytes]:
        """获取收集到的音频数据块"""
        return self._audio_chunks.copy()

def save_audio_to_file(audio_chunks: List[bytes], filename: str = "output.wav", sample_rate: int = 24000) -> bool:
    """将音频数据保存为 WAV 文件"""
    if not audio_chunks:
        logger.warning("没有音频数据可保存")
        return False

    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        audio_data = b"".join(audio_chunks)
        with wave.open(filename, 'wb') as wav_file:
            wav_file.setnchannels(1)  # 单声道
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data)
        
        logger.info(f"音频已保存到: {filename}, 大小: {len(audio_data)} bytes")
        return True
        
    except Exception as e:
        logger.error(f"保存音频文件失败: {str(e)}")
        return False

async def synthesize_text_to_audio(text: str, base_url: str, api_key: str, voice: str = "Cherry", output_file: str = "output.wav") -> bool:
    """
    将文本转换为语音并保存为文件 - 简化版本
    """
    audio_chunks = []
    
    def audio_callback(audio_bytes: bytes):
        audio_chunks.append(audio_bytes)

    client = TTSRealtimeClient(
        base_url=base_url,
        api_key=api_key,
        voice=voice,
        mode=SessionMode.SERVER_COMMIT,
        audio_callback=audio_callback
    )

    try:
        # 建立连接
        await client.connect()

        # 并行执行消息处理与文本发送
        consumer_task = asyncio.create_task(client.handle_messages())
        
        # 发送文本（分割为较小片段）
        text_fragments = split_text(text)
        logger.info("发送文本片段...")
        
        for fragment in text_fragments:
            logger.info(f"发送片段: {fragment}")
            await client.append_text(fragment)
            await asyncio.sleep(0.1)  # 片段间稍作延时

        # 等待处理完成后结束会话
        await asyncio.sleep(1.0)
        await client.finish_session()

        # 等待所有音频数据收取完毕
        await asyncio.sleep(3)

        # 关闭连接
        await client.close()
        consumer_task.cancel()

        # 保存音频文件
        return save_audio_to_file(audio_chunks, output_file)
        
    except Exception as e:
        logger.error(f"TTS合成过程中出错: {str(e)}")
        await client.close()
        return False

def split_text(text: str, max_chunk_size: int = 100) -> List[str]:
    """将长文本分割为合适的片段"""
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    sentences = text.replace('。', '。\n').replace('！', '！\n').replace('？', '？\n').split('\n')
    
    current_chunk = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
    
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks if chunks else [text]
