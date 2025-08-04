# 生产环境部署指南

## 概述

本文档介绍如何在生产环境中部署 qwen-api 服务，包括 MySQL 数据库和 Python 应用容器。

## 部署架构

- MySQL 8.0 数据库容器
- Python 3.12 应用容器
- 使用 Docker Compose 进行容器编排

## 部署步骤

### 1. 配置环境变量

首先，需要配置生产环境的参数：

```bash
# 复制环境变量示例文件
cp .env.example .env

# 编辑 .env 文件，将占位符替换为实际值
vim .env
```

需要配置的参数包括：
- `DB_ROOT_PASSWORD` - MySQL root 用户密码
- `DB_PASSWORD` - MySQL qwen_user 用户密码
- `QWEN_API_KEY` - 千问 API 密钥
- `ACCESSKEY_ID` - 阿里云访问密钥 ID
- `ACCESSKEY_SECRET` - 阿里云访问密钥 Secret

如果需要自定义数据库名称或用户，也可以修改：
- `DB_NAME` - 数据库名称（默认：qwen_db）
- `DB_USER` - 数据库用户（默认：qwen_user）

### 2. 启动服务

使用以下命令启动生产环境服务：

```bash
# 启动服务
docker-compose up -d
```

### 3. 验证服务状态

```bash
# 查看服务状态
docker-compose ps

# 查看服务日志
docker-compose logs -f
```

### 4. 停止服务

```bash
# 停止服务
docker-compose down
```

## 环境变量说明

所有敏感配置信息都存储在 [.env](file:///data1/home/qingzhe/qwen-api/.env) 文件中，包括：
- 数据库密码
- API 密钥
- OSS 访问凭证

非敏感配置和默认值已经移至 [config.py](file:///data1/home/qingzhe/qwen-api/config.py) 文件中处理，这样可以减少 [.env](file:///data1/home/qingzhe/qwen-api/.env) 文件中的配置项数量，使其更加简洁。

我们提供了 [.env.example](file:///data1/home/qingzhe/qwen-api/.env.example) 文件作为配置示例，部署时只需复制该文件并填写实际值即可。

## 端口配置

由于服务器上的 3306 和 5000 端口已被占用，我们使用了替代端口：

- MySQL: 3307 (映射到容器内的 3306)
- 应用服务: 6000 (映到容器内的 5000)

访问服务时请使用相应端口。

## 数据持久化

MySQL 数据使用 Docker Volume 进行持久化存储，即使容器被删除，数据也不会丢失。

数据卷名称：`qwen_mysql_data`

## 目录挂载

以下目录在容器中被挂载到宿主机，确保数据持久化：

- `tts_outputs`: TTS 输出文件
- `audio_files`: 音频文件
- `vlm_files`: 视觉语言模型文件

## 注意事项

1. 请确保生产环境的敏感信息（如密码、API 密钥）安全存储
2. 建议定期备份 MySQL 数据
3. 根据实际需求调整容器资源限制
4. 在生产环境中建议使用反向代理（如 Nginx）进行访问控制