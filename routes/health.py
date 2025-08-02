from flask import Blueprint, jsonify
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 创建健康检查蓝图
health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    logger.info("收到健康检查请求")
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })