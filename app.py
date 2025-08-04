from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
import logging
import os

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Set up logging for third-party libraries
logging.getLogger('werkzeug').setLevel(logging.WARNING)  # Flask server logs
logging.getLogger('urllib3').setLevel(logging.WARNING)   # HTTP request logs
logging.getLogger('requests').setLevel(logging.WARNING)  # requests library logs
logging.getLogger('websockets').setLevel(logging.WARNING) # websocket logs
logging.getLogger('dashscope').setLevel(logging.WARNING)  # Alibaba Cloud SDK logs

from database import init_database
from config import FFMPEG_PATH
from audio_converter import setup_ffmpeg
from routes.chat_api import chat_bp
from routes.health import health_bp
from routes.audio_websocket import register_audio_handlers
from routes.vlm_websocket import register_vlm_handlers

# 设置日志
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

# 这部分内容已移到日志配置的上方

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

# 注册VLM WebSocket处理器
register_vlm_handlers(socketio)

# 检查配置
from config import QWEN_API_KEY, QWEN_API_CHAT_URL, QWEN_CHAT_MODEL
logger.info(f"QWEN_API_KEY: {'已设置' if QWEN_API_KEY else '未设置'}")
logger.info(f"QWEN_API_CHAT_URL: {QWEN_API_CHAT_URL}")
logger.info(f"QWEN_CHAT_MODEL: {QWEN_CHAT_MODEL}")

if __name__ == '__main__':
    # 使用SocketIO启动应用，明确指定使用gevent以避免Werkzeug生产环境错误
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except RuntimeError as e:
        if "Werkzeug web server is not designed to run in production" in str(e):
            # 明确指定使用gevent以避免Werkzeug生产环境错误
            socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
        else:
            raise