import logging
from http import HTTPStatus
from dashscope.audio.asr import Transcription
import json
import os
import glob
import requests
from config import QWEN_API_KEY, QWEN_AUDIO_RECOGNIZE_MODEL
from up_to_oss import upload_file_to_oss

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 设置dashscope API key
import dashscope
dashscope.api_key = QWEN_API_KEY

def transcribe_audio_from_url(file_url, language_hints=['zh', 'en']):
    """
    从URL异步转录音频文件
    
    Args:
        file_url (str): 音频文件的URL
        language_hints (list): 语言提示，支持 ['zh', 'en'] 等
    
    Returns:
        dict: 转录结果，包含成功状态和文本内容
    """
    try:
        logger.info(f"开始语音识别: {file_url}")
        
        # 发起异步转录任务
        task_response = Transcription.async_call(
            model=QWEN_AUDIO_RECOGNIZE_MODEL,
            file_urls=[file_url],
            language_hints=language_hints
        )
        
        if not task_response or not hasattr(task_response, 'output') or not task_response.output:
            logger.error("异步转录任务创建失败")
            return {
                'success': False,
                'error': '异步转录任务创建失败',
                'text': ''
            }
        
        task_id = task_response.output.task_id
        logger.info(f"转录任务已创建，任务ID: {task_id}")
        
        # 等待转录完成 - 同步等待结果
        logger.info("等待转录完成...")
        transcribe_response = Transcription.wait(task=task_id)
        
        if transcribe_response.status_code == HTTPStatus.OK:
            logger.info("语音识别完成")
            
            # 解析转录结果
            output = transcribe_response.output
            logger.info(f"转录原始结果: {json.dumps(output, indent=2, ensure_ascii=False)}")
            
            # 提取文本内容
            transcribed_text = extract_text_from_result(output)
            
            if transcribed_text:
                logger.info(f"识别到的文本: {transcribed_text}")
                return {
                    'success': True,
                    'text': transcribed_text,
                    'task_id': task_id,
                    'raw_output': output
                }
            else:
                logger.warning("转录结果为空")
                return {
                    'success': True,
                    'text': '',
                    'task_id': task_id,
                    'raw_output': output,
                    'warning': '转录结果为空'
                }
        
        else:
            logger.error(f"转录失败，状态码: {transcribe_response.status_code}")
            return {
                'success': False,
                'error': f'转录失败，状态码: {transcribe_response.status_code}',
                'text': '',
                'task_id': task_id
            }
        
    except Exception as e:
        logger.error(f"语音识别过程中出错: {str(e)}")
        return {
            'success': False,
            'error': f'语音识别出错: {str(e)}',
            'text': ''
        }

def download_transcription_result(transcription_url):
    """
    从transcription_url下载识别结果JSON
    
    Args:
        transcription_url (str): 转录结果的URL
    
    Returns:
        dict: 下载的JSON内容，失败时返回None
    """
    try:
        logger.info(f"下载转录结果: {transcription_url}")
        response = requests.get(transcription_url, timeout=30)
        
        if response.status_code == 200:
            result_json = response.json()
            logger.info("转录结果下载成功")
            return result_json
        else:
            logger.error(f"下载转录结果失败，状态码: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"下载转录结果时出错: {str(e)}")
        return None

def extract_text_from_result(output):
    """
    从转录结果中提取文本内容
    
    Args:
        output: dashscope转录API的输出结果
    
    Returns:
        str: 提取的文本内容
    """
    try:
        if not output or not isinstance(output, dict):
            return ""
        
        # API返回格式：results数组包含transcription_url
        # {
        #   "results": [
        #     {
        #       "file_url": "...",
        #       "transcription_url": "https://...",
        #       "subtask_status": "SUCCEEDED"
        #     }
        #   ]
        # }
        
        all_texts = []
        
        logger.info(f"解析输出结构，找到results数组，长度: {len(output.get('results', []))}")
        
        if 'results' in output and isinstance(output['results'], list):
            for i, result in enumerate(output['results']):
                logger.info(f"处理第{i+1}个结果: {result.get('file_url', 'N/A')}")
                if 'transcription_url' in result and result.get('subtask_status') == 'SUCCEEDED':
                    # 下载转录结果JSON
                    transcription_json = download_transcription_result(result['transcription_url'])
                    
                    if transcription_json:
                        # 从下载的JSON中提取文本
                        logger.info(f"转录JSON结构: {json.dumps(transcription_json, indent=2, ensure_ascii=False)[:500]}...")
                        text = extract_text_from_transcription_json(transcription_json)
                        
                        if text:
                            logger.info(f"成功提取文本: {text}")
                            all_texts.append(text)
                        else:
                            logger.warning("从转录JSON中未能提取到文本")
                    else:
                        logger.error(f"下载转录结果失败: {result['transcription_url']}")
                        
                else:
                    logger.info(f"跳过结果（无transcription_url或状态不是SUCCEEDED）: {result}")
        
        # 合并所有文本（如果有多个文件）
        full_text = ' '.join(all_texts).strip()
        return full_text
        
    except Exception as e:
        logger.error(f"提取文本时出错: {str(e)}")
        return ""

def extract_text_from_transcription_json(transcription_json):
    """
    从下载的转录JSON中提取文本
    
    Args:
        transcription_json (dict): 从transcription_url下载的JSON内容
    
    Returns:
        str: 提取的文本内容
    """
    try:
        if not transcription_json or not isinstance(transcription_json, dict):
            return ""
        
        if 'transcripts' in transcription_json and isinstance(transcription_json['transcripts'], list):
            texts = []
            for transcript in transcription_json['transcripts']:
                if 'text' in transcript and transcript['text']:
                    texts.append(transcript['text'])
            
            return ' '.join(texts).strip()
        
        return ""
        
    except Exception as e:
        logger.error(f"从转录JSON提取文本时出错: {str(e)}")
        return ""



def test_transcription():
    """测试语音识别功能 - 使用官方示例"""
    # 使用官方示例URL进行测试
    test_url = "https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav"
    
    logger.info("开始测试语音识别（官方示例）...")
    print(f"🎵 测试音频: {test_url}")
    
    result = transcribe_audio_from_url(test_url)
    
    if result['success']:
        print("✅ 语音识别测试成功")
        print(f"📝 识别结果: {result['text']}")
        print(f"🆔 任务ID: {result.get('task_id', 'N/A')}")
        
        # 显示原始输出（用于调试）
        if 'raw_output' in result:
            print(f"📊 原始输出结构:")
            raw = result['raw_output']
            if isinstance(raw, dict):
                if 'results' in raw:
                    print(f"  - 文件数量: {len(raw['results'])}")
                    for i, res in enumerate(raw['results']):
                        print(f"  - 文件{i+1}: {res.get('file_url', 'N/A')}")
                        print(f"    状态: {res.get('subtask_status', 'N/A')}")
                        if 'transcription_url' in res:
                            print(f"    转录URL: {res['transcription_url'][:80]}...")
    else:
        print("❌ 语音识别测试失败")
        print(f"错误信息: {result['error']}")
    
    return result

def test_local_audio_files():
    """测试本地音频文件：上传到OSS + 语音识别"""
    audio_dir = "audio_files"
    
    if not os.path.exists(audio_dir):
        print(f"❌ 音频文件夹不存在: {audio_dir}")
        return False
    
    # 支持的音频格式
    audio_extensions = ['*.mp3', '*.wav', '*.m4a', '*.aac', '*.flac']
    audio_files = []
    
    # 扫描音频文件
    for ext in audio_extensions:
        audio_files.extend(glob.glob(os.path.join(audio_dir, ext)))
    
    if not audio_files:
        print(f"❌ 在 {audio_dir} 文件夹中没有找到音频文件")
        return False
    
    print(f"📁 找到 {len(audio_files)} 个音频文件:")
    for file in audio_files:
        file_size = os.path.getsize(file) / 1024  # KB
        print(f"  - {os.path.basename(file)} ({file_size:.1f} KB)")
    
    success_count = 0
    total_count = len(audio_files)
    
    for audio_file in audio_files:
        filename = os.path.basename(audio_file)
        print(f"\n🎵 处理文件: {filename}")
        
        try:
            # Step 1: 上传到OSS
            print("  📤 上传到OSS...")
            upload_result = upload_file_to_oss(audio_file, folder_prefix="test_audio")
            
            if not upload_result or not upload_result['success']:
                print(f"  ❌ OSS上传失败: {filename}")
                continue
            
            oss_url = upload_result['file_url']
            print(f"  ✅ OSS上传成功: {oss_url}")
            
            # Step 2: 语音识别
            print("  🎙️ 开始语音识别...")
            transcription_result = transcribe_audio_from_url(oss_url)
            
            if transcription_result['success']:
                print(f"  ✅ 语音识别成功: {transcription_result['text']}")
                if transcription_result.get('warning'):
                    print(f"  ⚠️ 警告: {transcription_result['warning']}")
                success_count += 1
            else:
                print(f"  ❌ 语音识别失败: {transcription_result.get('error', '未知错误')}")
            
            # 显示详细信息
            print(f"  📊 OSS对象键: {upload_result['object_key']}")
            print(f"  🆔 识别任务ID: {transcription_result.get('task_id', 'N/A')}")
            
        except Exception as e:
            print(f"  ❌ 处理文件时出错: {str(e)}")
            logger.error(f"处理文件 {filename} 时出错: {str(e)}")
    
    # 总结
    print(f"\n📋 测试完成:")
    print(f"  - 总文件数: {total_count}")
    print(f"  - 成功处理: {success_count}")
    print(f"  - 失败数量: {total_count - success_count}")
    print(f"  - 成功率: {success_count/total_count*100:.1f}%")
    
    return success_count == total_count

if __name__ == "__main__":
    print("🎙️ 语音识别模块测试")
    print("=" * 50)
    
    # 测试1：官方示例
    print("\n📝 测试1: 官方示例语音识别")
    print("-" * 30)
    test_transcription()
    
    # 测试2：本地音频文件
    print("\n📁 测试2: 本地音频文件处理")
    print("-" * 30)
    test_local_audio_files()
    
    print("\n✅ 所有测试完成！") 