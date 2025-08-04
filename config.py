import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

# ========== 千问API配置 ==========
# 千问API密钥 - 从环境变量获取，或在此直接设置
QWEN_API_KEY = os.getenv('QWEN_API_KEY', '')

# 千问API聊天URL
QWEN_API_CHAT_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'

# 千问聊天模型
QWEN_CHAT_MODEL = 'qwen3-32b'

# 千问多模态模型
QWEN_VLM_MODEL = 'qwen2.5-vl-32b-instruct'

# 千问音频识别模型
QWEN_AUDIO_RECOGNIZE_MODEL = 'paraformer-v2'

# ========== TTS配置 ==========
# 实时音频URL
REAL_TIME_AUDIO_URL = 'wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen-tts-realtime'

# TTS语音
TTS_VOICE = 'Cherry'

# TTS采样率
TTS_SAMPLE_RATE = 24000

# TTS输出目录
TTS_OUTPUT_DIR = 'tts_outputs'

# ========== 阿里云OSS配置 ==========
# OSS访问密钥ID
ACCESSKEY_ID = os.getenv('ACCESSKEY_ID', '')

# OSS访问密钥Secret
ACCESSKEY_SECRET = os.getenv('ACCESSKEY_SECRET', '')

# OSS存储桶名称
BUCKET = 'vlm-audio'

# OSS区域
REGIN = 'cn-beijing'

# ========== 数据库配置 ==========
DB_CONFIG = {
    'host': 'mysql',  # 在Docker环境中使用服务名
    'port': 3306,
    'user': os.getenv('DB_USER', 'qwen_user'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'qwen_db')
}

# ========== 系统配置 ==========
# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = """你是一个智能语音助手，要求1.你的回答要被生成语音，禁止出现除正常标点符号以外的字符
2.回答简洁 3.不知道的如实回答

"""

VLM_SYSTEM_PROMPT = """
你是一个生物安全智能专家，你会为用户提供安全，有帮助，准确的回答，你不会提供虚构的答案，回答简练、口语化。
请以简洁、连贯的文本格式回答，避免使用：
- 不必要的换行符
- 表情符号(如😊、😂等)
- 特殊装饰字符(如~~~、===、***等)
- 无序列表符号(如•、-、*等)
- 序号标记(如1.、2.、3.等)
- ASCII艺术或文本装饰

请使用完整的句子和段落，确保输出内容适合直接转换为语音。

"""

AUDIO_SYSTEM_PROMPT = """
你是一个生物安全智能专家，你会为用户提供安全，有帮助，准确的回答，你不会提供虚构的答案。
请以简洁、连贯的文本格式回答，避免使用：
- 不必要的换行符
- 表情符号(如😊、😂等)
- 特殊装饰字符(如~~~、===、***等)
- 无序列表符号(如•、-、*等)
- 序号标记(如1.、2.、3.等)
- ASCII艺术或文本装饰

请使用完整的句子和段落，确保输出内容适合直接转换为语音。
"""

# ========== 音频处理配置 ==========
# FFmpeg路径 - 用于音频编码
FFMPEG_PATH = '/usr/bin/ffmpeg'  # 在Docker容器中使用默认路径