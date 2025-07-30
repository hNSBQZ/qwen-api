import os
import logging
from datetime import datetime
import alibabacloud_oss_v2 as oss
from config import ACCESSKEY_ID, ACCESSKEY_SECRET, BUCKET, REGIN

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upload_file_to_oss(file_path, object_key=None, folder_prefix="audio"):
    """
    上传文件到阿里云OSS
    
    Args:
        file_path (str): 要上传的本地文件路径
        object_key (str, optional): OSS中的对象名称，如果不提供则自动生成
        folder_prefix (str): OSS中的文件夹前缀，默认为"audio"
    
    Returns:
        dict: 上传结果信息，包含状态码、URL等
        None: 上传失败时返回None
    """
    try:
        # 验证文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return None
        
        # 如果没有提供object_key，则自动生成
        if object_key is None:
            filename = os.path.basename(file_path)
            timestamp = datetime.now().strftime("%Y%m%d/%H%M%S")
            object_key = f"{folder_prefix}/{timestamp}/{filename}"
        
        logger.info(f"开始上传文件到OSS: {file_path} -> {object_key}")
        
        # 设置环境变量，用于SDK身份验证
        os.environ['OSS_ACCESS_KEY_ID'] = ACCESSKEY_ID
        os.environ['OSS_ACCESS_KEY_SECRET'] = ACCESSKEY_SECRET
        
        # 从环境变量中加载凭证信息
        credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()
        
        # 加载SDK的默认配置
        cfg = oss.config.load_default()
        cfg.credentials_provider = credentials_provider
        cfg.region = REGIN
        
        # 创建OSS客户端
        client = oss.Client(cfg)
        
        # 执行上传
        result = client.put_object_from_file(
            oss.PutObjectRequest(
                bucket=BUCKET,
                key=object_key
            ),
            file_path
        )
        
        # 检查上传结果
        if result.status_code == 200:
            # 构造文件的公网访问URL
            file_url = f"https://{BUCKET}.oss-{REGIN}.aliyuncs.com/{object_key}"
            
            upload_info = {
                'success': True,
                'status_code': result.status_code,
                'request_id': result.request_id,
                'etag': result.etag,
                'object_key': object_key,
                'file_url': file_url,
                'bucket': BUCKET,
                'file_size': os.path.getsize(file_path)
            }
            
            logger.info(f"文件上传成功: {file_url}")
            logger.info(f"上传详情: status_code={result.status_code}, "
                       f"request_id={result.request_id}, "
                       f"etag={result.etag}")
            
            return upload_info
        else:
            logger.error(f"上传失败，状态码: {result.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"上传文件到OSS时出错: {str(e)}")
        return None

def upload_audio_file(file_path):
    """
    专门用于上传音频文件的便捷函数
    
    Args:
        file_path (str): 音频文件路径
    
    Returns:
        dict: 上传结果信息
    """
    return upload_file_to_oss(file_path, folder_prefix="audio")

def delete_local_file(file_path):
    """
    删除本地文件
    
    Args:
        file_path (str): 要删除的文件路径
    
    Returns:
        bool: 删除成功返回True，失败返回False
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"已删除本地文件: {file_path}")
            return True
        else:
            logger.warning(f"文件不存在，无需删除: {file_path}")
            return True
    except Exception as e:
        logger.error(f"删除本地文件时出错: {str(e)}")
        return False

def upload_and_cleanup(file_path, keep_local=False):
    """
    上传文件到OSS并可选择删除本地文件
    
    Args:
        file_path (str): 要上传的文件路径
        keep_local (bool): 是否保留本地文件，默认为False（删除）
    
    Returns:
        dict: 上传结果信息
    """
    # 上传文件
    result = upload_file_to_oss(file_path)
    
    if result and result['success'] and not keep_local:
        # 上传成功且不保留本地文件时，删除本地文件
        delete_local_file(file_path)
    
    return result

# 测试函数
def test_upload():
    """测试上传功能"""
    import tempfile
    
    # 创建一个临时测试文件
    test_content = b"This is a test file for OSS upload"
    
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp_file:
        temp_file.write(test_content)
        temp_file_path = temp_file.name
    
    try:
        # 测试上传
        result = upload_file_to_oss(temp_file_path, "test/test_file.txt")
        
        if result:
            print("✅ 上传测试成功")
            print(f"文件URL: {result['file_url']}")
        else:
            print("❌ 上传测试失败")
            
    finally:
        # 清理测试文件
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

if __name__ == "__main__":
    # 运行测试
    test_upload()
