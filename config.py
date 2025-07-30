import os

# ========== 千问API配置 ==========
# 千问API密钥 - 从环境变量获取，或在此直接设置
QWEN_API_KEY = os.getenv('QWEN_API_KEY', '')

# 千问API聊天URL
QWEN_API_CHAT_URL = os.getenv('QWEN_API_CHAT_URL', 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation')

# 千问聊天模型
QWEN_CHAT_MODEL = os.getenv('QWEN_CHAT_MODEL', 'qwen-plus')

# 千问音频识别模型
QWEN_AUDIO_RECOGNIZE_MODEL = os.getenv('QWEN_AUDIO_RECOGNIZE_MODEL', 'paraformer-realtime-v2')

# ========== TTS配置 ==========
# 实时音频URL
REAL_TIME_AUDIO_URL = os.getenv('REAL_TIME_AUDIO_URL', 'wss://dashscope.aliyuncs.com/api/v1/services/aigc/text2speech/synthesis')

# TTS语音
TTS_VOICE = os.getenv('TTS_VOICE', 'cosyvoice-v1')

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
BUCKET = os.getenv('BUCKET', 'your-bucket-name')

# OSS区域
REGIN = os.getenv('REGIN', 'oss-cn-hangzhou')

# ========== 数据库配置 ==========
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'your-db-password'),
    'database': os.getenv('DB_NAME', 'qwen_chat')
}

# ========== 系统配置 ==========
# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = os.getenv('DEFAULT_SYSTEM_PROMPT', """你是一个智能语音助手，具备以下特点：
1. 友善、耐心、专业的对话风格
2. 能够理解和回应各种话题
3. 回答简洁明了，避免过于冗长
4. 支持中文和英文交流
5. 在不确定时会诚实地说明

请根据用户的语音输入，提供有用、准确的回答。""")

# ========== 音频处理配置 ==========
# FFmpeg路径 - 用于音频编码
FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'ffmpeg')  # 假设ffmpeg在系统PATH中