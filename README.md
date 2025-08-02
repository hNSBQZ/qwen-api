# Qwen-API 服务

基于 Flask 的 Web 服务，提供与 Qwen 模型交互的接口，支持聊天、音频处理和视觉语言模型（VLM）功能。

注：为了方便测试，服务端会返回有部分不在之前需求文档上的json可用于反馈后端状态，并添加事件作为键，具体格式标注在接口部分。
现在还存在的问题有如下：
 - 对话模型返回来的信息含有无法读出的字符，在这些字符处会有奇怪的语音，可能需要配置提示词，有需要会后端改进过滤掉这些。
 - tts返回pcm的速度远大于转mp3的速度，如果回答太复杂语音太长可能会导致消息队列溢出造成语音丢失，最大音频长度尚未测试出来。

## 目录

- [Qwen-API 服务](#qwen-api-服务)
  - [目录](#目录)
  - [功能特性](#功能特性)
  - [项目结构](#项目结构)
  - [API 接口](#api-接口)
    - [聊天接口](#聊天接口)
      - [POST `/v1/chat/completions`](#post-v1chatcompletions)
    - [音频 WebSocket](#音频-websocket)
      - [WebSocket `/v1/chat/audio`](#websocket-v1chataudio)
    - [视觉语言模型 WebSocket](#视觉语言模型-websocket)
      - [WebSocket `/v1/chat/vlm`](#websocket-v1chatvlm)
    - [健康检查](#健康检查)
      - [GET `/health`](#get-health)
  - [安装](#安装)
  - [配置](#配置)
  - [使用示例](#使用示例)
    - [聊天 API 示例](#聊天-api-示例)
  - [文件说明](#文件说明)
    - [核心文件](#核心文件)
    - [音频处理相关](#音频处理相关)
    - [视觉语言模型相关](#视觉语言模型相关)
    - [存储相关](#存储相关)
    - [API 路由](#api-路由)
    - [测试文件](#测试文件)

## 功能特性

- 兼容 OpenAI 的聊天完成接口格式
- 通过 WebSocket 实现实时音频流处理
- 通过 WebSocket 实现视觉语言模型（VLM）处理
- 语音转文字（ASR）功能
- 文字转语音（TTS）功能
- 音频/图像文件处理和存储
- 聊天历史记录数据库集成
- 健康检查端点

## 项目结构

```
qwen-api/
├── app.py                 # 应用程序入口点
├── config.py              # 配置设置
├── database.py            # 数据库操作
├── chat_service.py        # Qwen 模型交互服务
├── audio_transcription.py # 音频转录服务
├── audio_converter.py     # 音频格式转换工具
├── tts_realtime_client.py # 实时 TTS 客户端
├── up_to_oss.py           # OSS（对象存储服务）上传工具
├── routes/                # API 路由处理器
│   ├── chat_api.py        # 聊天 API 端点
│   ├── audio_websocket.py # 音频 WebSocket 处理器
│   ├── vlm_websocket.py   # VLM WebSocket 处理器
│   └── health.py          # 健康检查端点
├── services/              # 业务逻辑服务
│   ├── audio_processor.py # 音频 处理服务
│   └── vlm_processor.py   # VLM 处理服务
└── test/                  # 测试 HTML 页面
    ├── test_chat_web.html
    ├── test_realtime_audio_stream.html
    └── test_vlm_stream.html
```

## API 接口

### 聊天接口

#### POST `/v1/chat/completions`

兼容 OpenAI 的聊天完成接口。

**请求头:**
- `Authorization: Bearer <api_key>` - 必需
- `Content-Type: application/json` - 必需

**请求体:**

```json
{
  "model": "qwen-plus",           // 可选，默认为 QWEN_CHAT_MODEL
  "messages": [                   // 必需
    {
      "role": "user",
      "content": "你好！"
    }
  ],
  "stream": false,                // 可选，默认为 false
  "temperature": 0.8,             // 可选
  "max_tokens": 1024              // 可选
}
```

**响应 (非流式):**

```json
{
  "id": "chatcmpl-96b7d62b-1e84-9b88-5a4d-c2c111ec145a",
  "object": "chat.completion",
  "created": 1714645945,
  "model": "qwen-plus",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好！我如何帮助你？"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 330,
    "completion_tokens": 14,
    "total_tokens": 344
  }
}
```

**响应 (流式):**

当设置 `stream: true` 时，响应遵循 Server-Sent Events 格式：

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":1714645945,"model":"qwen-plus","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":1714645945,"model":"qwen-plus","choices":[{"index":0,"delta":{"content":"你好"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":1714645945,"model":"qwen-plus","choices":[{"index":0,"delta":{"content":"！"},"finish_reason":null}]}

data: [DONE]
```

### 音频 WebSocket

#### WebSocket `/v1/chat/audio`

用于实时音频流处理的端点，支持语音转文字和文字转语音处理。

**连接:**
```
WebSocket URL: ws://<host>:<port>/v1/chat/audio
```

**客户端到服务器消息:**

1. 音频数据包:
```json
{
  "seq": 1,           // 数据包序列号 (从1开始)
  "total": 10,        // 总数据包数
  "data": "base64..." // Base64 编码的音频数据 (每个包最大8KB)
}
```

2. 连接事件由系统自动处理。

**服务器到客户端消息:**

所有消息都通过 WebSocket 发送，格式为包含事件类型和数据的 JSON 对象：

```json
{
  "event_type": "message_type",
  "data": {
    // 具体的消息内容
  }
}
```

或者某些消息直接以事件类型作为键：

```json
{
  "message_type": {
    // 具体的消息内容
  }
}
```

具体的消息类型如下：

1. 连接确认:
```json
{
  "connected": {
    "message": "音频连接已建立",
    "session_id": "session-uuid"
  }
}
```

2. 数据包确认:
```json
{
  "packet_ack": {
    "seq": 1,
    "received": 1,
    "total": 10
  }
}
```

3. 开始转录:
```json
{
  "transcription_started": {
    "message": "开始语音识别...",
    "oss_url": "https://bucket.oss-region.aliyuncs.com/audio/file.mp3"
  }
}
```

4. 开始聊天处理:
```json
{
  "chat_started": {
    "message": "开始生成AI回答...",
    "user_message": "转录的用户消息"
  }
}
```

5. 开始 TTS:
```json
{
  "tts_started": {
    "message": "开始语音合成..."
  }
}
```

6. 音频流数据:
```json
{
  "audio_stream": {
    "event": "data",
    "data": "base64..." // Base64 编码的 MP3 音频数据
  }
}
```

7. 音频流完成:
```json
{
  "audio_stream": {
    "event": "finished"
  }
}
```

8. 聊天和 TTS 完成:
```json
{
  "chat_tts_complete": {
    "message": "实时对话生成和语音合成完成",
    "assistant_response": "AI 回复文本",
    "tts_success": true,
    "segments_count": 5,
    "total_segments": 5,
    "db_saved": true
  }
}
```

9. 音频处理完成:
```json
{
  "audio_complete": {
    "message": "音频接收、识别、对话生成和实时语音合成全部完成",
    "filename": "audio_session_20240101_120000.mp3",
    "filepath": "audio_files/audio_session_20240101_120000.mp3",
    "size": 123456,
    "packets": 10,
    "duration": 5.23,
    "oss_uploaded": true,
    "oss_url": "https://bucket.oss-region.aliyuncs.com/audio/file.mp3",
    "transcription_success": true,
    "transcription_text": "用户说话内容",
    "chat_success": true,
    "assistant_response": "AI 回复内容",
    "tts_success": true
  }
}
```

10. 转录结果为空警告:
```json
{
  "chat_started": {
    "message": "跳过对话生成：语音识别失败或结果为空"
  }
}
```

11. 聊天块 (流式响应):
```json
{
  "chat_chunk": {
    "chunk": "回复文本块",
    "full_response": "到目前为止的完整回复文本"
  }
}
```

12. 错误消息:
```json
{
  "error": {
    "message": "错误描述"
  }
}
```

### 视觉语言模型 WebSocket

#### WebSocket `/v1/chat/vlm`

用于处理图像和音频问题的视觉语言模型端点。

**连接:**
```
WebSocket URL: ws://<host>:<port>/v1/chat/vlm
```

**客户端到服务器消息:**

1. 音频数据包:
```json
{
  "seq": 1,           // 数据包序列号 (从1开始)
  "total": 10,        // 总数据包数
  "type": "audio",    // 数据类型: "audio" 或 "image"
  "data": "base64..." // Base64 编码的数据 (每个包最大50KB)
}
```

2. 图像数据包:
```json
{
  "seq": 1,           // 数据包序列号 (从1开始)
  "total": 5,         // 总数据包数
  "type": "image",    // 数据类型: "audio" 或 "image"
  "data": "base64..." // Base64 编码的图像数据 (每个包最大50KB)
}
```

3. 结束信号:
```json
{
  "type": "end"
}
```

**服务器到客户端消息:**

所有消息都通过 WebSocket 发送，格式为包含事件类型的 JSON 对象。

具体的消息类型如下：

1. 连接确认:
```json
{
  "connected": {
    "message": "VLM连接已建立",
    "session_id": "session-uuid"
  }
}
```

2. 数据包确认:
```json
{
  "packet_ack": {
    "seq": 1,
    "type": "audio",
    "received": 1,
    "total": 10
  }
}
```

3. VLM 处理完成:
```json
{
  "vlm_complete": {
    "message": "VLM处理完成",
    "audio_file": "vlm_audio_session_20240101_120000.mp3",
    "image_file": "vlm_image_session_20240101_120000.jpg",
    "audio_size": 123456,
    "image_size": 789012,
    "duration": 3.45,
    "transcription": "转录的用户问题",
    "vlm_response": "VLM AI 回复"
  }
}
```

4. 开始转录:
```json
{
  "transcription_started": {
    "message": "开始语音识别...",
    "oss_url": "https://bucket.oss-region.aliyuncs.com/audio/file.mp3"
  }
}
```

5. VLM 聊天开始:
```json
{
  "vlm_chat_started": {
    "message": "开始生成多模态AI回答...",
    "user_message": "转录的用户问题",
    "image_url": "https://bucket.oss-region.aliyuncs.com/image/file.jpg"
  }
}
```

6. 开始 TTS:
```json
{
  "tts_started": {
    "message": "开始语音合成..."
  }
}
```

7. 音频流数据:
```json
{
  "audio_stream": {
    "event": "data",
    "data": "base64..." // Base64 编码的 MP3 音频数据
  }
}
```

8. 音频流完成:
```json
{
  "audio_stream": {
    "event": "finished"
  }
}
```

9. VLM 聊天块 (流式响应):
```json
{
  "vlm_chat_chunk": {
    "chunk": "回复文本块",
    "full_response": "到目前为止的完整回复文本"
  }
}
```

10. VLM 聊天和 TTS 完成:
```json
{
  "vlm_chat_tts_complete": {
    "message": "VLM对话和TTS合成完成",
    "user_message": "用户问题",
    "assistant_response": "VLM AI 回复",
    "audio_chunks": 15
  }
}
```

11. 错误消息:
```json
{
  "error": {
    "message": "错误描述"
  }
}
```

### 健康检查

#### GET `/health`

健康检查端点，用于验证服务状态。

**响应:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00.000000"
}
```

## 安装

1. 克隆仓库:
```bash
git clone <repository-url>
cd qwen-api
```

2. 安装依赖:
```bash
pip install -r requirements.txt
```

3. 设置环境变量 (参见 [配置](#配置))

4. 运行应用:
```bash
python app.py
```

## 配置

服务使用环境变量进行配置。在项目根目录创建 `.env` 文件：

```env
# Qwen API 配置
QWEN_API_KEY=your_api_key_here
QWEN_API_CHAT_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
QWEN_CHAT_MODEL=qwen-plus
QWEN_VLM_MODEL=qwen-vl-plus
QWEN_AUDIO_RECOGNIZE_MODEL=paraformer-v1

# TTS 配置
REAL_TIME_AUDIO_URL=wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen-tts-realtime
TTS_VOICE=Cherry
TTS_SAMPLE_RATE=24000
TTS_OUTPUT_DIR=tts_outputs

# OSS 配置
ACCESSKEY_ID=your_access_key_id
ACCESSKEY_SECRET=your_access_key_secret
BUCKET=your_bucket_name
REGIN=cn-beijing

# 数据库配置
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_NAME=your_db_name

# 系统配置
DEFAULT_SYSTEM_PROMPT="你是一个有帮助的助手。"
FFMPEG_PATH=/path/to/ffmpeg
```

## 使用示例

### 聊天 API 示例

```bash
curl -X POST http://localhost:5000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-plus",
    "messages": [
      {
        "role": "user",
        "content": "你好！"
      }
    ],
    "stream": false
  }'
```

## 文件说明

### 核心文件

- [app.py](app.py) - 应用程序入口，初始化 Flask 应用和各种服务
- [config.py](config.py) - 配置文件，包含所有环境变量和默认设置
- [database.py](database.py) - 数据库操作模块，处理聊天记录的存储和检索
- [chat_service.py](chat_service.py) - 聊天服务模块，与 Qwen 模型进行交互

### 音频处理相关

- [audio_transcription.py](audio_transcription.py) - 音频转录模块，使用 DashScope 进行语音识别
- [audio_converter.py](audio_converter.py) - 音频格式转换模块，处理 PCM 到 MP3 的转换
- [tts_realtime_client.py](tts_realtime_client.py) - 实时 TTS 客户端，与 DashScope 的 TTS 服务通信
- [routes/audio_websocket.py](routes/audio_websocket.py) - 音频 WebSocket 路由处理器
- [services/audio_processor.py](services/audio_processor.py) - 音频处理服务，协调整个音频处理流程

### 视觉语言模型相关

- [routes/vlm_websocket.py](routes/vlm_websocket.py) - VLM WebSocket 路由处理器
- [services/vlm_processor.py](services/vlm_processor.py) - VLM 处理服务，协调图像和音频的多模态处理流程

### 存储相关

- [up_to_oss.py](up_to_oss.py) - OSS 上传模块，处理文件上传到阿里云对象存储

### API 路由

- [routes/chat_api.py](routes/chat_api.py) - 聊天 API 路由，提供兼容 OpenAI 的接口
- [routes/health.py](routes/health.py) - 健康检查路由

### 测试文件

- [test/test_chat_web.html](test/test_chat_web.html) - 聊天 API 测试页面
- [test/test_realtime_audio_stream.html](test/test_realtime_audio_stream.html) - 实时音频流测试页面
- [test/test_vlm_stream.html](test/test_vlm_stream.html) - VLM 流测试页面