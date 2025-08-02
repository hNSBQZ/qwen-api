import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

# ========== 千问API配置 ==========
# 千问API密钥 - 从环境变量获取，或在此直接设置
QWEN_API_KEY = os.getenv('QWEN_API_KEY', '')

# 千问API聊天URL
QWEN_API_CHAT_URL = os.getenv('QWEN_API_CHAT_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions')

# 千问聊天模型
QWEN_CHAT_MODEL = os.getenv('QWEN_CHAT_MODEL', 'qwen3-32b')

# 千问音频识别模型
QWEN_AUDIO_RECOGNIZE_MODEL = os.getenv('QWEN_AUDIO_RECOGNIZE_MODEL', 'paraformer-v2')

# ========== TTS配置 ==========
# 实时音频URL
REAL_TIME_AUDIO_URL = os.getenv('REAL_TIME_AUDIO_URL', 'wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen-tts-realtime')

# TTS语音
TTS_VOICE = os.getenv('TTS_VOICE', 'Cherry')

# TTS采样率
TTS_SAMPLE_RATE = int(os.getenv('TTS_SAMPLE_RATE', 24000))

# TTS输出目录
TTS_OUTPUT_DIR = os.getenv('TTS_OUTPUT_DIR', 'tts_outputs')

# ========== 阿里云OSS配置 ==========
# OSS访问密钥ID
ACCESSKEY_ID = os.getenv('ACCESSKEY_ID', '')

# OSS访问密钥Secret
ACCESSKEY_SECRET = os.getenv('ACCESSKEY_SECRET', '')

# OSS存储桶名称
BUCKET = os.getenv('BUCKET', 'vlm-audio')

# OSS区域
REGIN = os.getenv('REGIN', 'cn-beijing')

# ========== 数据库配置 ==========
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '192.168.0.164'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'hqz'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'qwen_chat')
}

# ========== 系统配置 ==========
# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = os.getenv('DEFAULT_SYSTEM_PROMPT', """你是一个智能语音助手，要求1.你的回答要被生成语音，禁止出现除正常标点符号以外的字符
2.回答简洁 3.不知道的如实回答

""")

# ========== 音频处理配置 ==========
# FFmpeg路径 - 用于音频编码
FFMPEG_PATH = os.getenv('FFMPEG_PATH', r'D:\ffmpeg-7.0.2-essentials_build\ffmpeg-7.0.2-essentials_build\bin\ffmpeg.exe')  # 假设ffmpeg在系统PATH中