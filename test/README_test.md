# API 测试工具使用说明

本目录包含了用于测试 Qwen API 聊天接口的测试工具，包括 Python 自动化测试脚本和 Web 可视化测试界面。

## 文件说明

### 1. `test_api.py` - Python 自动化测试脚本

这是一个完整的 Python 测试脚本，用于自动化测试 API 的各项功能。

#### 功能特性
- ✅ 基本聊天功能测试
- ✅ 多轮对话测试
- ✅ 带参数请求测试（temperature、max_tokens、top_p）
- ✅ 错误情况测试（无授权、缺少参数等）
- ✅ 健康检查接口测试
- ✅ OpenAI 格式响应验证
- ✅ 详细的日志输出

#### 使用方法

1. **安装依赖**
   ```bash
   pip install requests
   ```

2. **设置环境变量**（可选）
   ```bash
   # Windows
   set QWEN_API_KEY=your_api_key_here
   
   # Linux/Mac
   export QWEN_API_KEY=your_api_key_here
   ```

3. **启动 API 服务**
   ```bash
   python app.py
   ```

4. **运行测试脚本**
   ```bash
   cd test
   python test_api.py
   ```

#### 测试输出示例
```
🚀 开始API测试
测试时间: 2024-01-01T12:00:00
目标URL: http://localhost:5000
--------------------------------------------------

=== 测试健康检查接口 ===
✅ 健康检查通过!
状态: healthy
时间戳: 2024-01-01T12:00:00

=== 测试基本聊天功能 ===
发送请求到: http://localhost:5000/v1/chat/completions
✅ 请求成功!
✅ 响应格式验证通过!
```

### 2. `test_web.html` - Web 可视化测试界面

这是一个现代化的 Web 界面，提供直观的聊天测试体验。

#### 功能特性
- 🎨 现代化的聊天界面设计
- ⚙️ 可配置的 API 设置（URL、API Key、模型参数）
- 💬 实时聊天对话
- 📝 预设示例消息
- 🔧 支持调整模型参数（temperature、max_tokens）
- 💾 自动保存配置到浏览器本地存储
- 📱 响应式设计，支持移动端
- 🏥 内置健康检查功能
- 🗑️ 清空对话历史功能

#### 使用方法

1. **启动 API 服务**
   ```bash
   python app.py
   ```

2. **打开测试界面**
   - 直接在浏览器中打开 `test_web.html` 文件
   - 或者通过 HTTP 服务器访问（推荐）

3. **配置设置**
   - 点击右上角的"配置设置"按钮
   - 输入你的 API Key
   - 确认 API 地址：`http://localhost:5000/v1/chat/completions`
   - 选择模型和调整参数

4. **开始测试**
   - 可以使用预设的示例消息
   - 或者输入自定义消息
   - 支持多轮对话
   - 查看 token 使用统计

#### 界面截图功能
- **配置区域**：设置 API Key、模型、参数
- **聊天区域**：显示对话历史
- **输入区域**：发送消息和快捷操作
- **状态栏**：显示请求状态和 token 使用情况

## 快速开始

### 方法一：使用 Python 脚本测试
```bash
# 1. 启动服务
python app.py

# 2. 新开终端，运行测试
cd test
python test_api.py
```

### 方法二：使用 Web 界面测试
```bash
# 1. 启动服务
python app.py

# 2. 打开浏览器访问
# 文件://path/to/test/test_web.html
```

## 环境要求

- Python 3.7+
- requests 库
- 现代浏览器（Chrome、Firefox、Safari、Edge）
- 正确配置的环境变量（.env 文件）

## 故障排除

### 常见问题

1. **连接失败**
   - 确认 API 服务正在运行（`python app.py`）
   - 检查端口 5000 是否被占用
   - 确认防火墙设置

2. **API Key 错误**
   - 检查环境变量 `QWEN_API_KEY` 是否正确设置
   - 确认 API Key 有效性

3. **请求超时**
   - 检查网络连接
   - 确认 Qwen API 服务可访问性
   - 增加超时时间设置

4. **响应格式错误**
   - 检查 Qwen API 配置
   - 确认模型名称正确
   - 查看服务端日志

### 调试建议

1. **查看服务端日志**
   ```bash
   python app.py
   # 观察终端输出的详细日志
   ```

2. **使用 curl 命令测试**
   ```bash
   curl -X POST http://localhost:5000/health
   ```

3. **检查数据库连接**
   - 确认数据库配置正确
   - 检查数据库服务状态

## 注意事项

- 🔐 请妥善保管你的 API Key，不要在公共环境中暴露
- 💰 注意 API 调用费用，避免过度测试
- 🛡️ 生产环境使用时请添加适当的安全措施
- 📊 定期检查数据库中的聊天记录

## 扩展功能

你可以基于这些测试工具进行扩展：

- 添加更多测试用例
- 集成到 CI/CD 流程
- 添加性能测试
- 支持更多模型参数
- 添加批量测试功能

如有问题，请检查控制台输出或联系开发者。 