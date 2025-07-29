#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time

def test_stream_api():
    """测试流式API功能"""
    
    # API endpoint
    url = "http://localhost:5000/v1/chat/completions"
    
    # 测试数据
    data = {
        "model": "qwen-plus",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant."
            },
            {
                "role": "user", 
                "content": "你是谁？请介绍一下自己。"
            }
        ],
        "stream": True
    }
    
    # 请求头
    headers = {
        "Authorization": "Bearer test-key",  # 使用测试key
        "Content-Type": "application/json"
    }
    
    print("=== 测试流式API ===")
    print(f"请求URL: {url}")
    print(f"请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
    print("\n=== 流式响应 ===")
    
    try:
        # 发送流式请求
        response = requests.post(url, headers=headers, json=data, stream=True)
        
        if response.status_code != 200:
            print(f"请求失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            return
        
        # 读取流式响应
        complete_content = ""
        chunk_count = 0
        
        for line in response.iter_lines(decode_unicode=True):
            if line.strip():
                chunk_count += 1
                print(f"Chunk {chunk_count}: {line}")
                
                try:
                    chunk_data = json.loads(line)
                    # 提取内容
                    if ('choices' in chunk_data and 
                        len(chunk_data['choices']) > 0 and 
                        'delta' in chunk_data['choices'][0] and 
                        'content' in chunk_data['choices'][0]['delta']):
                        content = chunk_data['choices'][0]['delta']['content']
                        if content:
                            complete_content += content
                except json.JSONDecodeError:
                    print(f"  (无法解析的JSON数据)")
        
        print(f"\n=== 流式响应完成 ===")
        print(f"总chunk数: {chunk_count}")
        print(f"完整内容: {complete_content}")
        
    except Exception as e:
        print(f"测试出错: {e}")

def test_non_stream_api():
    """测试非流式API功能（对比）"""
    
    # API endpoint
    url = "http://localhost:5000/v1/chat/completions"
    
    # 测试数据
    data = {
        "model": "qwen-plus",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant."
            },
            {
                "role": "user", 
                "content": "你是谁？请介绍一下自己。"
            }
        ],
        "stream": False
    }
    
    # 请求头
    headers = {
        "Authorization": "Bearer test-key",  # 使用测试key
        "Content-Type": "application/json"
    }
    
    print("\n=== 测试非流式API ===")
    print(f"请求URL: {url}")
    print(f"请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
    
    try:
        # 发送非流式请求
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            print(f"请求失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            return
        
        result = response.json()
        print(f"\n=== 非流式响应 ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"测试出错: {e}")

if __name__ == "__main__":
    print("开始测试API...")
    
    # 测试流式API
    test_stream_api()
    
    time.sleep(2)
    
    # 测试非流式API
    test_non_stream_api()
    
    print("\n测试完成！") 