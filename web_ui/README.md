# AutoGLM Web UI

基于 Gradio 构建的现代化 Web 界面，提供友好的用户体验来使用 AutoGLM 进行 Android 设备自动化操作。

## 快速开始

### 1. 安装依赖

```bash
# 在项目根目录下
pip install -r requirements.txt
```

### 2. 启动 Web UI

```bash
# 方法1：使用启动脚本（推荐）
python start_web_ui.py

# 方法2：直接运行
cd web_ui
python app.py
```

### 3. 访问界面

打开浏览器访问：http://localhost:7860

## 界面功能

### 左侧面板

- **设备状态**：检查 ADB 连接和 Android 设备状态
- **模型配置**：
  - 选项A：选择预设的模型服务配置
  - 选项B：自定义本地模型配置
- **应用列表**：查看所有支持的应用

### 右侧面板

- **命令输入**：输入自然语言命令
- **命令示例**：查看常用命令示例
- **执行结果**：显示 AI 的执行过程和结果

## 预设配置

Web UI 提供了以下预设配置：

1. **智谱AI (推荐)**：官方提供的 AutoGLM 服务
2. **本地Ollama**：本地部署的 Ollama 服务
3. **本地vLLM**：本地 vLLM 部署的模型服务

## 常用命令示例

- "打开美团搜索附近的火锅店"
- "发送微信消息给张三"
- "打开抖音并搜索美食视频"
- "设置明天早上8点的闹钟"
- "拍照并发送给联系人"

## 注意事项

1. 确保 ADB 已正确安装并配置环境变量
2. 确保 Android 设备已开启 USB 调试并连接电脑
3. 确保已安装并启用 ADB Keyboard
4. 确保模型服务正在运行（如果使用本地部署）

## 故障排除

### 设备未连接
- 检查 USB 数据线是否支持数据传输
- 确认手机已开启 USB 调试
- 点击"检查状态"按钮查看详细错误信息

### 模型连接失败
- 确认模型服务正在运行
- 检查网络连接和 URL 配置
- 验证 API Key 是否正确（如果需要）

### 命令执行失败
- 查看输出区域的错误信息
- 确认目标应用已安装在手机上
- 检查手机屏幕是否处于可操作状态

## 高级配置

### 修改端口

编辑 `web_ui/app.py` 文件，修改 `demo.launch()` 的 `server_port` 参数：

```python
demo.launch(
    server_name="0.0.0.0",
    server_port=8080,  # 修改为您想要的端口
    share=False,
    inbrowser=True,
    show_error=True
)
```

### 启用公网访问

如果您想让其他设备也能访问 Web UI，可以启用 `share` 参数：

```python
demo.launch(share=True)  # 会生成公网链接
```

### 自定义主题

编辑 `web_ui/app.py` 中的 `theme` 参数来更改界面主题：

```python
from gradio.themes import Soft, Base, Default

theme = Soft()  # 可选：Soft, Base, Default, Monochrome
```