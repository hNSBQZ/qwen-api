import logging
from http import HTTPStatus
from dashscope.audio.asr import Transcription
import json
import os
import requests
from config import QWEN_API_KEY, QWEN_AUDIO_RECOGNIZE_MODEL
from up_to_oss import upload_file_to_oss

# 设置日志

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
