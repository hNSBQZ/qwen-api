FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 使用国内镜像源加速软件包安装
RUN echo "deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free" > /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-backports main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian-security/ bookworm-security main contrib non-free" >> /etc/apt/sources.list && \
    apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p tts_outputs audio_files vlm_files

# 暴露端口
EXPOSE 5000

# 启动应用
CMD ["python", "app.py"]