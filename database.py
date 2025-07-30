import pymysql
import logging
from config import DB_CONFIG
from typing import List

# 设置日志
logger = logging.getLogger(__name__)

def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database'],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def init_database():
    """初始化数据库表"""
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            # 创建chat_records表
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS chat_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_prompt TEXT NOT NULL,
                model_response TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
            cursor.execute(create_table_sql)
        connection.commit()
        logger.info("数据库表初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

def save_chat_record(user_prompt: str, model_response: str) -> bool:
    """保存聊天记录到数据库"""
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            sql = "INSERT INTO chat_records (user_prompt, model_response) VALUES (%s, %s)"
            cursor.execute(sql, (user_prompt, model_response))
        connection.commit()
        return True
    except Exception as e:
        logger.error(f"保存聊天记录失败: {e}")
        return False
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

def get_chat_history(limit: int = 10) -> List[dict]:
    """获取聊天历史记录"""
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            sql = "SELECT * FROM chat_records ORDER BY created_at DESC LIMIT %s"
            cursor.execute(sql, (limit,))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"获取聊天历史记录失败: {e}")
        return []
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()
