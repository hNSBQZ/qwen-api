#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API测试脚本 - 测试chat completions接口
使用方法: python test_api.py
"""

import requests
import json
import os
import sys
from datetime import datetime

# 配置
API_BASE_URL = "http://localhost:5000"
API_ENDPOINT = "/v1/chat/completions"
# 这里使用一个测试用的API key，实际使用时应该从环境变量获取
TEST_API_KEY = os.getenv('QWEN_API_KEY', 'test-api-key')

def test_basic_chat():
    """测试基本聊天功能"""
    print("=== 测试基本聊天功能 ===")
    
    url = f"{API_BASE_URL}{API_ENDPOINT}"
    headers = {
        "Authorization": f"Bearer {TEST_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "qwen-plus",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant."
            },
            {
                "role": "user",
                "content": "你是谁？"
            }
        ]
    }
    
    try:
        print(f"发送请求到: {url}")
        print(f"请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        print(f"响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 请求成功!")
            print(f"响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
            # 验证响应格式
            if validate_openai_response(result):
                print("✅ 响应格式验证通过!")
            else:
                print("❌ 响应格式验证失败!")
                
        else:
            print(f"❌ 请求失败: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求异常: {e}")
    except Exception as e:
        print(f"❌ 其他错误: {e}")

def test_multiple_messages():
    """测试多轮对话"""
    print("\n=== 测试多轮对话 ===")
    
    url = f"{API_BASE_URL}{API_ENDPOINT}"
    headers = {
        "Authorization": f"Bearer {TEST_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "qwen-plus",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant."
            },
            {
                "role": "user",
                "content": "我的名字是小明"
            },
            {
                "role": "assistant",
                "content": "你好小明！很高兴认识你。"
            },
            {
                "role": "user",
                "content": "你还记得我的名字吗？"
            }
        ]
    }
    
    try:
        print(f"发送多轮对话请求...")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 多轮对话测试成功!")
            print(f"模型回答: {result['choices'][0]['message']['content']}")
        else:
            print(f"❌ 多轮对话测试失败: {response.text}")
            
    except Exception as e:
        print(f"❌ 多轮对话测试异常: {e}")

def test_with_parameters():
    """测试带参数的请求"""
    print("\n=== 测试带参数的请求 ===")
    
    url = f"{API_BASE_URL}{API_ENDPOINT}"
    headers = {
        "Authorization": f"Bearer {TEST_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "qwen-plus",
        "messages": [
            {
                "role": "user",
                "content": "写一个简短的Python函数"
            }
        ],
        "temperature": 0.7,
        "max_tokens": 200,
        "top_p": 0.9
    }
    
    try:
        print(f"发送带参数的请求...")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 带参数请求测试成功!")
            print(f"Token使用情况: {result.get('usage', 'N/A')}")
        else:
            print(f"❌ 带参数请求测试失败: {response.text}")
            
    except Exception as e:
        print(f"❌ 带参数请求测试异常: {e}")

def test_error_cases():
    """测试错误情况"""
    print("\n=== 测试错误情况 ===")
    
    # 测试无Authorization header
    print("测试无Authorization header...")
    url = f"{API_BASE_URL}{API_ENDPOINT}"
    headers = {"Content-Type": "application/json"}
    data = {"messages": [{"role": "user", "content": "test"}]}
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 401:
            print("✅ 无Authorization header测试通过 (401)")
        else:
            print(f"❌ 无Authorization header测试失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 无Authorization header测试异常: {e}")
    
    # 测试无messages参数
    print("测试无messages参数...")
    headers = {"Authorization": f"Bearer {TEST_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "qwen-plus"}
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 400:
            print("✅ 无messages参数测试通过 (400)")
        else:
            print(f"❌ 无messages参数测试失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 无messages参数测试异常: {e}")

def test_health_check():
    """测试健康检查接口"""
    print("\n=== 测试健康检查接口 ===")
    
    url = f"{API_BASE_URL}/health"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            result = response.json()
            print("✅ 健康检查通过!")
            print(f"状态: {result.get('status')}")
            print(f"时间戳: {result.get('timestamp')}")
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")

def validate_openai_response(response):
    """验证响应是否符合OpenAI格式"""
    required_fields = ['choices', 'object', 'created', 'model']
    
    for field in required_fields:
        if field not in response:
            print(f"缺少字段: {field}")
            return False
    
    if not isinstance(response['choices'], list) or len(response['choices']) == 0:
        print("choices字段格式不正确")
        return False
    
    choice = response['choices'][0]
    choice_required_fields = ['message', 'finish_reason', 'index']
    
    for field in choice_required_fields:
        if field not in choice:
            print(f"choice缺少字段: {field}")
            return False
    
    message = choice['message']
    message_required_fields = ['role', 'content']
    
    for field in message_required_fields:
        if field not in message:
            print(f"message缺少字段: {field}")
            return False
    
    return True

def main():
    """主函数"""
    print("🚀 开始API测试")
    print(f"测试时间: {datetime.now().isoformat()}")
    print(f"目标URL: {API_BASE_URL}")
    print("-" * 50)
    
    # 执行所有测试
    test_health_check()
    test_basic_chat()
    test_multiple_messages()
    test_with_parameters()
    test_error_cases()
    
    print("\n" + "=" * 50)
    print("📋 测试完成!")
    print("请检查上述测试结果，确保所有功能正常工作。")

if __name__ == "__main__":
    main() 