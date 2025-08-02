from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
import logging

from database import init_database
from config import FFMPEG_PATH
from audio_converter import setup_ffmpeg
from routes.chat_api import chat_bp
from routes.health import health_bp
from routes.audio_websocket import register_audio_handlers

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 初始化FFmpeg
setup_ffmpeg(FFMPEG_PATH)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # 生产环境中应使用环境变量

# 设置日志 - 只输出INFO级别
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 设置第三方库日志级别
logging.getLogger('werkzeug').setLevel(logging.WARNING)  # Flask服务器日志
logging.getLogger('urllib3').setLevel(logging.WARNING)   # HTTP请求日志
logging.getLogger('requests').setLevel(logging.WARNING)  # requests库日志
logging.getLogger('websockets').setLevel(logging.WARNING) # websocket日志
logging.getLogger('dashscope').setLevel(logging.WARNING)  # 阿里云SDK日志

# 初始化SocketIO - 增加超时配置
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    logger=False, 
    engineio_logger=False,
    ping_timeout=60,  # 60秒ping超时
    ping_interval=25  # 25秒ping间隔
)

# 配置CORS，允许跨域访问
CORS(app, resources={
    r"/v1/chat/completions": {
        "origins": "*",  # 允许所有域名访问
        "methods": ["POST"],
        "allow_headers": ["Content-Type", "Authorization"]
    },
    r"/health": {
        "origins": "*",  # 允许所有域名访问
        "methods": ["GET"]
    }
})

# 初始化数据库
init_database()

# 注册蓝图
app.register_blueprint(chat_bp)
app.register_blueprint(health_bp)

# 注册音频WebSocket处理器
register_audio_handlers(socketio)

# 检查配置
from config import QWEN_API_KEY, QWEN_API_CHAT_URL, QWEN_CHAT_MODEL
logger.info(f"QWEN_API_KEY: {'已设置' if QWEN_API_KEY else '未设置'}")
logger.info(f"QWEN_API_CHAT_URL: {QWEN_API_CHAT_URL}")
logger.info(f"QWEN_CHAT_MODEL: {QWEN_CHAT_MODEL}")

if __name__ == '__main__':
    # 使用SocketIO启动应用
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)