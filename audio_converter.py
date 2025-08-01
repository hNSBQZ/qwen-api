#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频转换模块
负责PCM到MP3的流式转换功能
"""

import io
import logging
import subprocess
from pydub import AudioSegment

logger = logging.getLogger(__name__)


def setup_ffmpeg(ffmpeg_path: str) -> bool:
    """
    设置并验证FFmpeg配置
    
    Args:
        ffmpeg_path: FFmpeg可执行文件路径
        
    Returns:
        bool: 配置是否成功
    """
    try:
        # 验证FFmpeg是否可用
        result = subprocess.run([ffmpeg_path, '-version'], 
                              capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            version_info = result.stdout.split('\n')[0]
            logger.info(f"✅ FFmpeg配置成功: {version_info}")
            
            # 配置pydub使用指定的FFmpeg
            AudioSegment.converter = ffmpeg_path
            AudioSegment.ffmpeg = ffmpeg_path
            AudioSegment.ffprobe = ffmpeg_path.replace('ffmpeg', 'ffprobe') if 'ffmpeg' in ffmpeg_path else 'ffprobe'
            
            return True
        else:
            logger.error(f"❌ FFmpeg执行失败: {result.stderr}")
            return False
            
    except FileNotFoundError:
        logger.error(f"❌ 找不到FFmpeg: {ffmpeg_path}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("❌ FFmpeg响应超时")
        return False
    except Exception as e:
        logger.error(f"❌ FFmpeg配置出错: {e}")
        return False


class PCMToMP3StreamConverter:
    """PCM到MP3的流式转换器"""
    
    def __init__(self, sample_rate=24000, channels=1, sample_width=2, buffer_duration_ms=500):
        """
        初始化转换器
        
        Args:
            sample_rate: 采样率 (默认24000Hz)
            channels: 声道数 (默认1，单声道)
            sample_width: 采样位宽 (默认2字节，16-bit)
            buffer_duration_ms: 缓冲区时长(毫秒)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        
        # 计算缓冲区大小（字节）
        self.buffer_size = int((sample_rate * buffer_duration_ms / 1000) * channels * sample_width)
        
        # PCM数据缓冲区
        self.pcm_buffer = b""
        
        logger.info(f"PCM转MP3转换器初始化 - 采样率: {sample_rate}Hz, 缓冲区: {buffer_duration_ms}ms ({self.buffer_size} bytes)")
        
    def add_pcm_data(self, pcm_data: bytes) -> bytes:
        """
        添加PCM数据到缓冲区，当缓冲区满时转换为MP3
        
        Args:
            pcm_data: PCM音频数据
            
        Returns:
            bytes: MP3数据（如果缓冲区已满）或空字节
        """
        self.pcm_buffer += pcm_data
        
        # 检查缓冲区是否足够大
        if len(self.pcm_buffer) >= self.buffer_size:
            # 提取缓冲区大小的数据进行转换
            pcm_to_convert = self.pcm_buffer[:self.buffer_size]
            self.pcm_buffer = self.pcm_buffer[self.buffer_size:]
            
            # 转换为MP3
            return self._convert_pcm_to_mp3(pcm_to_convert)
        
        return b""
    
    def flush_remaining(self) -> bytes:
        """
        转换并返回缓冲区中剩余的PCM数据
        在音频流结束时调用
        
        Returns:
            bytes: 剩余的MP3数据
        """
        if len(self.pcm_buffer) > 0:
            mp3_data = self._convert_pcm_to_mp3(self.pcm_buffer)
            self.pcm_buffer = b""
            return mp3_data
        return b""
    
    def _convert_pcm_to_mp3(self, pcm_data: bytes) -> bytes:
        """
        将PCM数据转换为MP3格式
        
        Args:
            pcm_data: PCM原始数据
            
        Returns:
            bytes: MP3编码数据
        """
        try:
            if len(pcm_data) == 0:
                return b""
                
            # 创建AudioSegment对象
            audio_segment = AudioSegment(
                data=pcm_data,
                sample_width=self.sample_width,
                frame_rate=self.sample_rate,
                channels=self.channels
            )
            
            # 转换为MP3格式
            mp3_buffer = io.BytesIO()
            audio_segment.export(mp3_buffer, format="mp3", bitrate="128k")
            mp3_data = mp3_buffer.getvalue()
            mp3_buffer.close()
            
            logger.debug(f"PCM→MP3转换: {len(pcm_data)} bytes → {len(mp3_data)} bytes")
            return mp3_data
            
        except Exception as e:
            logger.error(f"PCM到MP3转换失败: {e}")
            raise
    
    def reset(self):
        """重置转换器状态"""
        self.pcm_buffer = b""


def create_mp3_converter(sample_rate=24000, channels=1, sample_width=2, buffer_duration_ms=500):
    """
    创建MP3转换器实例
    
    Args:
        sample_rate: 采样率
        channels: 声道数
        sample_width: 采样位宽
        buffer_duration_ms: 缓冲区时长
        
    Returns:
        PCMToMP3StreamConverter: 转换器实例
    """
    return PCMToMP3StreamConverter(
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
        buffer_duration_ms=buffer_duration_ms
    )