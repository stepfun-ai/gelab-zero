
![GELab-Zero 主图](./images/main_cn.png)

> 👋 hi大家好！我们很荣幸推出首个同时包含模型和基础设施的全开源 GUI Agent。我们的解决方案主打即插即用的工程化体验，无需依赖云端，赋予您完全的隐私控制权。

<p align="center">
  <a href="https://arxiv.org/abs/2512.15431"><img src="https://img.shields.io/badge/arXiv-Step--GUI Technical Report-B31B1B.svg?logo=arxiv&logoColor=white" alt="arXiv" /></a>
  <a href="https://opengelab.github.io/"><img src="https://img.shields.io/badge/🌐%20Website-Project%20Page-blue" alt="Website" /></a>
  <a href="https://huggingface.co/stepfun-ai/GELab-Zero-4B-preview"><img src="https://img.shields.io/badge/🤗%20Hugging%20Face-GELab--Zero--4B--preview-orange" alt="Hugging Face Model" /></a>
  <a href="https://huggingface.co/datasets/stepfun-ai/AndroidDaily"><img src="https://img.shields.io/badge/📚%20Hugging%20Face-AndroidDaily-yellow" alt="Hugging Face Dataset" /></a>
  <a href="https://modelscope.cn/models/stepfun-ai/GELab-Zero-4B-preview"><img src="https://img.shields.io/badge/🤖%20Model%20Scope-GELab--Zero--4B--preview-blue" alt="Model Scope" /></a>
</p>

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README_CN.md">简体中文</a>
</p>

---

# 🚀 Fork 增强版

> **本项目基于 [stepfun-ai/gelab-zero](https://github.com/stepfun-ai/gelab-zero) 进行增强开发**
> 
> 以下内容为本 Fork 新增的功能和优化

## 🖥️ Web UI 功能特性

启动命令：`python start_web_ui.py`，然后访问 `http://localhost:8866`

**左栏 - 控制面板**

| 模块 | 功能 |
|------|------|
| **📱 设备管理** | 检查设备状态、查看设备列表、重启 ADB 服务 |
| **📶 无线调试** | 通过 IP 地址无线连接设备、启用 TCP/IP 模式 |
| **📊 任务监控** | 查看任务状态、⏸️ **暂停/注入/继续**、选择历史 Session |
| **💬 命令/回复** | 输入任务指令或回复 Agent 询问，支持 `Ctrl+Enter` |
| **⚙️ 参数配置** | 选择模型提供商、🔍 **检查模型连接**、配置 API 参数 |
| **🛠 实用工具** | 启动 scrcpy、获取应用列表、📄 **导出PDF轨迹**、📦 **扫描应用映射** |

> ⚠️ **重要提示**：对于新手机或重新启用开发者模式后，需要先通过 USB 数据线连接一次。这次初始 USB 连接用于授权电脑的 ADB 访问权限。授权完成后，后续可以一直使用无线连接，无需再进行有线连接。

**右栏 - 任务展示**

| 模块 | 功能 |
|------|------|
| **📱 任务轨迹** | 可视化回放每个执行步骤，包含截图、思考过程、动作详情 |
| **📋 实时日志** | 实时显示任务执行的终端输出，支持清空和复制 |

## ✨ 新增功能

### ⏸️ 暂停 / 注入 / 继续

在任务执行过程中，可以随时：
- **立即暂停**：点击暂停按钮立即终止当前执行
- **注入指令**：输入修正指令（如"改为搜索xxx"）
- **无缝继续**：从同一 Session 继续执行，保持轨迹完整性

> 💡 解决了 Agent 执行过程中无法人工干预修正的痛点

### 🔍 模型连接检查

参数配置面板新增一键检测功能：
- 快速测试本地/在线模型是否可用
- 自动区分本地 (Ollama) 和在线 API
- 显示连接状态、模型名称

### 📋 多模型提供商配置

从 `model_config.yaml` 自动加载，每个提供商可配置：

```yaml
local:
    display_name: "本地模型 (Ollama)"
    api_base: "http://localhost:11434/v1"
    api_key: "EMPTY"
    default_model: "gelab-zero-4b-preview"

stepfun:
    display_name: "阶跃星辰 (StepFun)"
    api_base: "https://api.stepfun.com/v1"
    api_key: "YOUR_API_KEY"
    default_model: "step-gui"
```

### 📄 PDF 轨迹导出

- 导出任务执行轨迹为 PDF 文件
- 包含截图、思考过程、动作详情
- 支持自动下载

### 🎨 UI 优化

- **三行独立配置**：Base URL、API Key、模型名称分行显示，更易填写
- **改进的状态显示**：更清晰的任务状态反馈（就绪/运行中/等待输入/已暂停）
- **回复交互修复**：Agent 询问时能正确检测等待输入状态

### 📦 应用映射扫描

自动扫描设备上已安装的应用，建立**中文应用名→包名**的映射，让 AWAKE 功能能识别更多应用。

**文件结构：**

```
项目根目录/
├── default_package_map.yaml      # 默认映射库（160+条，项目提供）
├── user_package_map.yaml         # 用户映射（扫描结果+自定义）
├── user_package_map.yaml.example # 模板文件
└── aapt2-8.5.0-11315950-windows/ # aapt2 工具（Windows）
```

**功能特性：**

- **实时加载**：修改 YAML 文件后立即生效，无需重启程序
- **智能扫描**：优先从映射表匹配（秒级），未匹配的自动用 aapt2 深度解析
- **优先级**：`user_package_map.yaml` > `default_package_map.yaml`

**使用方法：**

1. 在 Web UI 点击「🔍 扫描应用映射」
2. 扫描结果自动保存到 `user_package_map.yaml`
3. 在「📝 应用映射编辑器」中手动编辑/添加映射

**⏱️ 扫描时间参考：**

| 匹配方式 | 单个应用耗时 | 说明 |
|---------|-------------|------|
| 映射表匹配 | <1 秒 | 从 160+ 条映射中快速查找 |
| 深度解析 | 5-15 秒 | 拉取 APK 并用 aapt2 解析 |

> ⚠️ **注意**：如手机安装应用较多（如 300+ 个），且大部分未在默认映射中，深度扫描可能需要 **20-40 分钟**。建议先手动编辑 `default_package_map.yaml` 添加常用应用。

> 💡 项目已内置 `aapt2` 工具，路径自动适配，无需额外配置

---

# 📖 官方原版内容

> 以下内容来自 [stepfun-ai/gelab-zero](https://github.com/stepfun-ai/gelab-zero) 原版 README

## 📰 新闻

* 🎁 **[2025-12-18]** 我们在 **[arXiv](https://arxiv.org/abs/2512.15431)** 上发布了 **Step-GUI 技术报告**！
* 🎁 **[2025-12-18]** 我们发布了更强大的 GUI 自动化任务 **API**。[点击此处申请 API 访问权限](https://wvixbzgc0u7.feishu.cn/share/base/form/shrcnNStxEmuE7aY6jTW07CZHMf)！
* 🎁 **[2025-12-12]** 我们发布了支持多设备管理和任务分发的 **MCP-Server**。请参阅 [安装-快速开始](#-安装-快速开始) 和 [MCP-Server 配置](#可选-mcp-server-配置) 了解配置说明。
* 🎁 **[2025-12-01]** 感谢以下项目和作者提供量化工具及教程：[GGUF_v1](https://huggingface.co/bartowski/stepfun-ai_GELab-Zero-4B-preview-GGUF)、[GGUF_v2](https://huggingface.co/noctrex/GELab-Zero-4B-preview-GGUF)、[EXL3](https://huggingface.co/ArtusDev/stepfun-ai_GELab-Zero-4B-preview-EXL3)、[中文教程](http://xhslink.com/o/1WrmgHGWFYh)、[英文教程](https://www.youtube.com/watch?v=4BMiDyQOpos)。
* 🎁 **[2025-11-31]** 我们在 **[Hugging Face](https://huggingface.co/stepfun-ai/GELab-Zero-4B-preview)** 和 **[Model Scope](https://modelscope.cn/models/stepfun-ai/GELab-Zero-4B-preview)** 上发布了轻量级 **4B** 模型 GELab-Zero-4B-preview。
* 🎁 **[2025-11-31]** 我们发布了 **[AndroidDaily](https://huggingface.co/datasets/stepfun-ai/AndroidDaily)** 基准测试中的任务数据。
* 🎁 **[2025-11-30]** 我们发布了当前的 **GELab-Zero** 工程基础设施。
* 🎁 **[2025-10]** 我们关于 GELab-Engine 的 **[研究论文](https://github.com/summoneryhl/gelab-engine)** 被 **NeurIPS 2025** 录用。


## 📑 目录

- [📖 背景](#-背景)
- [🎥 应用演示](#-应用演示)
- [🏆 开放基准测试](#-开放基准测试)
- [🚀 安装-快速开始](#-安装-快速开始)
- [📝 引用](#-引用)


## 📧 联系我们

欢迎加入我们的微信群与我们联系和交流：

| WeChat Group |
|:-------------------------:|
| <img src="images/wechat_group2.jpeg" width="200"> |


## 📖 背景

随着 AI 体验日益深入消费级终端设备，移动 Agent 研究正处于从 **"可行性验证"** 向 **"大规模应用"** 转型的关键节点。虽然基于 GUI 的方案具有通用兼容性，但移动生态的碎片化带来了沉重的工程负担，阻碍了创新。GELab-Zero 旨在打破这些壁垒。

* **⚡️ 开箱即用的全栈基建**
解决移动生态碎片化痛点，提供统一的一键推理管道。自动处理多设备 ADB 连接、依赖安装及权限配置，让开发者专注于策略创新而非工程基础设施。
* **🖥️ 消费级硬件本地部署**
内置 4B GUI Agent 模型，**针对 Mac (M系列芯片) 及 NVIDIA RTX 4060 进行全方位优化**。支持完全本地化运行，在标准消费级硬件上保障数据隐私与低延迟交互。
* **📱 灵活的任务分发与编排**
支持跨多设备分发任务并记录交互轨迹。提供 ReAct 循环、多智能体协作及定时任务三种通用模式，以处理复杂的真实业务场景。
* **🚀 加速从原型到落地**
赋能开发者快速验证交互策略，同时允许企业直接复用底层基建实现零成本 MCP 集成，跨越从"可行性验证"到"大规模应用"的关键鸿沟。

## 🎥 应用演示


###  推荐 - 科幻电影
任务：帮我找一些最近好看的科幻电影

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/video_2.gif" alt="Sci-Fi Movies Recommendation Demo" style="flex: 1; height: 400px; object-fit: contain; margin-right: 1px;"/>
</div>

**[📹 点击查看演示视频](./images/video_2.mp4)**

###  推荐 - 旅游目的地
任务：帮我找一个周末适合带孩子去的地方

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/video_4.gif" alt="Travel Destination Recommendation Demo" style="flex: 1; height: 400px; object-fit: contain; margin-right: 1px;"/>
</div>

**[📹 点击查看演示视频](./images/video_4.mp4)**


###  实用任务 - 领取补贴
任务：在企业福利平台上领取餐补

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/video_3.gif" alt="Claim Meal Vouchers Demo" style="flex: 1; height: 400px; object-fit: contain; margin-right: 1px;"/>
</div>

**[📹 点击查看演示视频](./images/video_3.mp4)**

### 实用任务 - 地铁线路查询
任务：检查地铁 1 号线是否正常运行，然后导航到最近的 1 号线地铁站入口

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/video_5.gif" alt="Metro Line Query Demo" style="flex: 1; height: 400px; object-fit: contain; margin-right: 1px;"/>
</div>

**[📹 点击查看演示视频](./images/video_5.mp4)**


### 复杂任务 - 多商品购物
任务：在饿了么上前往最近的盒马鲜生门店购买：红颜草莓 300g、秘鲁比安卡蓝莓 125g（果径18mm+）、当季鲜黄土豆 500g、贝贝南瓜 750g、盒马大颗粒虾滑、2 瓶盒马醇豆浆（黑豆）300ml、小王子澳洲坚果可可脆 120g、盒马菠菜手擀面、盒马五香酱牛肉、5 袋好欢螺柳州螺蛳粉（加辣加臭版）400g、m&m's 牛奶巧克力豆 100g

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/video_1.gif" alt="Multi-Item Shopping Demo" style="flex: 1; height: 400px; object-fit: contain; margin-right: 1px;"/>
</div>

**[📹 点击查看演示视频](./images/video_1.mp4)**


### 复杂任务 - 信息检索
任务：在知乎上搜索"如何学习理财"，并查看第一个点赞超过 1万 的回答

**[📹 点击查看演示视频](./images/video_6.mp4)**

### 复杂任务 - 条件搜索
任务：在淘宝上找一双 37 码的白色帆布鞋，价格在 100 元以内，然后收藏第一个符合条件的商品

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/video_7.gif" alt="Conditional Search Demo" style="flex: 1; height: 400px; object-fit: contain; margin-right: 1px;"/>
</div>

**[📹 点击查看演示视频](./images/video_7.mp4)**

### 复杂任务 - 在线测验
任务：去百词斩帮我完成背单词任务

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/video_8.gif" alt="Online Quiz Demo" style="flex: 1; height: 400px; object-fit: contain; margin-right: 1px;"/>
</div>

**[📹 点击查看演示视频](./images/video_8.mp4)**


## 🏆 开放基准测试

我们对 GELab-Zero-4B-preview 模型在多个开源基准测试上进行了综合评估，涵盖 GUI 理解、定位、交互等多个维度。与其他开源模型的对比结果如下：

![开放基准测试对比结果](./images/Result.jpeg)

基准测试结果表明，GELab-Zero-4B-preview 在多个开源基准测试中均表现出优异的性能，特别是在真实的移动场景（Android World）中结果尤为突出，证明了其在实际应用中的强大能力。


## 🚀 安装-快速开始

端到端推理只需要几个简单的步骤：
1. 搭建大模型（LLM）推理环境（ollama 或 vllm）
2. 搭建安卓设备执行环境（adb 配置）并开启开发者模式
3. 搭建 Agent 运行环境（使用 gelab-zero 一键部署脚本）
4. 搭建轨迹可视化环境（可选）

以上依赖的第三方基础设施都已经非常成熟，无需担心。

我们假设你已经安装了 Python 3.12+ 环境，并具备一定的命令行操作基础。如果尚未安装 Python 环境，请参考 Step 0 进行安装。

### Step 0: Python 环境准备

如果你还没有安装 Python 3.12+ 环境，可以参考以下步骤进行安装：
出于商业友好性和跨平台支持的考虑，我们推荐使用 miniforge 来安装和管理 Python 环境。官方网址：https://github.com/conda-forge/miniforge

- **Windows 用户**： **必须使用powershell**

1. 直接下载并手动安装miniforge 即可。 参加：https://github.com/conda-forge/miniforge Install章节。安装过程中需要注意勾选，将conda 加入PATH 的选项，以确保conda 能够被正确激活。

2. 安装完成后需要激活conda，powershell 后输入：
```bash
# 在powershell 中激活conda
conda init powershell

# 允许conda 脚本随powershell 启动
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

激活成功后可见"(base)" 括号显示在最新一行的开头。

3. 执行和调试代码建议使用vs code，可在官网下载安装：https://code.visualstudio.com/ 


- **Mac 和 Linux 用户**：

1. 使用命令行下载并安装 miniforge：
```bash
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash Miniforge3-$(uname)-$(uname -m).sh
```

安装完成后，新建并激活一个 Python 环境：
```bash
conda create -n gelab-zero python=3.12 -y
conda activate gelab-zero
```

### Step 1: 大模型推理环境搭建

我们验证了两种主流的本地 LLM 推理部署方案：ollama 和 vllm。个人用户推荐使用 ollama 方案；企业用户或具备一定技术背景的用户可以选择 vllm 方案，以获得更稳定的推理服务。

ollama 部署在某些 Mac 设备可能无法正常运行（表征是吐 token 特慢，原因待进一步排查），可使用 llama.cpp 部署。

#### Step 1.1: Ollama 搭建（推荐个人用户）

对于做本地推理的个人用户，我们强烈推荐使用 Ollama 方式进行本地部署，该方式具有安装简单、使用便捷的优势。


- **Windows 和 Mac 用户**: 可直接前往官网下载安装图形化版本：https://ollama.com/。

- **Linux 用户**: 可参考官方文档进行安装：https://ollama.com/download/linux。Linux 用户的一键安装命令如下：
```bash
# 下载并安装 Linux 最新版 Ollama AppImage
curl -fsSL https://ollama.com/install.sh | sh
```

#### Step 1.2: GELab-Zero-4B-preview 模型部署

完成 ollama 安装后，需要通过如下命令下载并部署 gelab-zero-4b-preview 模型：

```bash
# 若尚未安装 huggingface cli，先执行此命令
pip install huggingface_hub

# 如果在国内下载速度较慢，可以尝试使用 镜像加速 "https://hf-mirror.com"

# WINDOWS 用户可以使用以下命令:
# $env:HF_ENDPOINT = "https://hf-mirror.com"

# LINUX 和 MAC 用户可以使用以下命令:
# export HF_ENDPOINT="https://hf-mirror.com"

# 从 huggingface 下载 gelab-zero-4b-preview 模型权重
hf download --no-force-download stepfun-ai/GELab-Zero-4B-preview --local-dir gelab-zero-4b-preview


# 将模型导入 ollama
cd gelab-zero-4b-preview
ollama create gelab-zero-4b-preview -f Modelfile
# windows 用户如遇报错，需要指定安装路径，例如：
# C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe create gelab-zero-4b-preview -f Modelfile

# 如果电脑配置较低，可以考虑量化模型以提升推理速度。注意，量化可能会带来一定的模型性能损失。
# 文档详细见：https://docs.ollama.com/import#quantizing-a-model

# 使用int8 精度量化模型（精度损失较小，模型尺寸变为4.4G ）：
ollama create -q q8_0 gelab-zero-4b-preview 

# 使用int4 精度量化模型（精度损失较大，模型尺寸变为2.2G ）：
ollama create -q Q4_K_M gelab-zero-4b-preview

# 换回原始精度：
ollama create -q f16 gelab-zero-4b-preview
```

- **Windows 用户**： 可以打开ollama app，选择模型 gelab-zero-4b-preview，发一条消息测试模型是否能够正确回复。

- **Mac 和 Linux 用户**： 可以通过下面的命令测试模型是否安装成功：
```bash
curl -X POST http://localhost:11434/v1/chat/completions \
 -H "Content-Type: application/json" \
 -d '{
       "model": "gelab-zero-4b-preview",
       "messages": [{"role": "user", "content": "Hello, GELab-Zero!"}]
     }'
```

期望的输出应包含模型的回复内容，表示模型已成功安装并在运行。例如：
```json
{"id":"chatcmpl-174","object":"chat.completion","created":1764405566,"model":"gelab-zero-4b-preview","system_fingerprint":"fp_ollama","choices":[{"index":0,"message":{"role":"assistant","content":"Hello! I'm here to help with any questions or information you might need. How can I assist you today?"},"finish_reason":"stop"}],"usage":{"prompt_tokens":16,"completion_tokens":24,"total_tokens":40}}
```

完成以上步骤后，说明你的 ollama 环境与 gelab-zero-4b-preview 模型已经安装成功，可以继续下一步配置手机执行环境。

### Step 2: 安卓设备执行环境搭建

为了让 GELab-Zero 能够控制手机执行任务，你需要完成以下步骤来配置手机执行环境：
1. 在手机上开启开发者模式和 USB 调试。
2. 安装 ADB 工具，并确保电脑可以通过 ADB 连接手机。（如果你已经安装过 adb 工具，可跳过此步骤）
3. 通过 USB 数据线将手机连接到电脑，并使用 adb devices 命令确认连接成功。  

#### Step 2.1: 开启开发者模式和 USB 调试


通常可以按如下步骤在安卓手机上开启开发者模式和 USB 调试：
1. 打开手机上的「设置」应用。
2. 找到「关于手机」或「系统」选项，连续点击「版本号」10 次以上，直到看到"您已处于开发者模式"或类似提示。
3. 返回「设置」主页面，找到「开发者选项」。【重要，必须开启】
4. 在「开发者选项」中，找到并开启「USB 调试」功能，按照屏幕提示完成 USB 调试的启用。【重要，必须开启】

不同品牌手机的具体步骤可能略有差异，请根据实际情况调整。一般可以搜索「<手机品牌> 如何开启开发者模式」获得具体教程。
设置完成后，大致效果如下图所示：


<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/developer_mode_1.png" alt="小米手机开发者模式截图" style="flex: 1; height: 230px; object-fit: contain; margin-right: 1px;"/>
  <img src="images/developer_mode_2.png" alt="荣耀手机开发者模式截图" style="flex: 1; height: 230px; object-fit: contain; margin-left: 1px;"/>
</div>

#### Step 2.2: 安装 ADB 工具

ADB（Android Debug Bridge，安卓调试桥）是连接安卓设备与电脑进行通信的工具。你可以按如下步骤安装 ADB 工具：

- **Windows 用户**：
  1. 下载 ADB 工具压缩包：https://dl.google.com/android/repository/platform-tools-latest-windows.zip 并解压到合适的位置。
  2. 将解压后的文件夹路径加入系统环境变量，这样就可以在命令行中直接使用 adb 命令。详细步骤参见：https://learn.microsoft.com/en-us/previous-versions/office/developer/sharepoint-2010/ee537574(v=office.14) 。具体包括：
```
1. 在「开始」菜单中右键点击「计算机」，选择「属性」。
2. 点击「高级系统设置」。
3. 在「系统属性」对话框中，点击「环境变量」按钮。
4. 在「系统变量」区域找到并选中「Path」变量，然后点击「编辑」按钮。
5. 在「编辑环境变量」对话框中点击「新建」，然后输入 ADB 工具解压后的路径。
6. 点击「确定」保存更改并关闭所有对话框。
```

- **Mac 和 Linux 用户**：

1. 可通过 Homebrew（Mac）或系统自带包管理器（Linux）安装 ADB 工具。如果尚未安装 Homebrew，可先执行：
```bash
ruby -e $(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)
```
  2. 然后使用以下命令安装 ADB 工具：
```bash
brew cask install android-platform-tools
```

#### Step 2.3: 将安卓设备连接到电脑

使用 USB 数据线将手机连接到电脑后，打开终端或命令提示符，并执行：

```bash
adb devices
```


如果连接成功，你会看到类似如下的输出，显示已连接的设备列表：

```bash
List of devices attached
AN2CVB4C28000731        device
```

如果没有看到任何设备，请检查数据线连接是否正常，以及手机上的 USB 调试选项是否正确开启。首次连接手机时，手机上可能会弹出授权提示，只需选择「允许」即可。如下图所示：

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/developer_mode_auth.png" alt="授权提示" style="flex: 1; height: 230px; object-fit: contain; margin-right: 1px;"/>
</div>

如果仍然无法成功安装或连接，可以参考第三方文档进行进一步排查：https://github.com/quickappcn/issues/issues/120

### Step 3: GELab-Zero Agent 运行环境搭建

完成以上步骤后，可以通过以下命令部署 GELab-Zero 的运行环境：

```bash
# 克隆代码仓库
git clone https://github.com/stepfun-ai/gelab-zero
cd gelab-zero

# 安装依赖
pip install -r requirements.txt

# 运行单个任务推理示例
python examples/run_single_task.py
```

### （可选）Step 4: 轨迹可视化环境搭建

任务轨迹会默认保存在 `running_log/server_log/os-copilot-local-eval-logs/` 目录下。你可以使用 streamlit 对轨迹进行可视化：

```bash
# 如果想让局域网内其他设备也能访问，可使用 --server.address 0.0.0.0
streamlit run --server.address 0.0.0.0 visualization/main_page.py --server.port 33503

# 如果只想在本机访问，可使用以下命令：
streamlit run --server.address 127.0.0.1 visualization/main_page.py --server.port 33503

```

然后在浏览器中访问 `http://localhost:33503` 即可进入可视化界面。

每次任务执行都会生成一个唯一的 session ID，可在可视化界面中通过该 ID 查询并展示对应的任务轨迹。

带有点击、滑动等坐标点的动作，会在截图上进行标记，以便更直观地理解 Agent 的行为。

### （可选）llama.cpp 部署

> 确保你已经下载了 GELab-Zero-4B-preview 模型到本地

#### Step 1：使用 llama.cpp 转化模型为 GGUF 格式

从 llama.cpp 官方仓库 Clone 代码

```bash
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
pip install -r requirements.txt
# 如果依赖有冲突，Conda 搞个虚拟环境
```

将模型转换为 GGUF 格式，指令参数：

1. 第一个路径为你从 Huggingface 下载的 GELab-Zero-4B-preview 路径
2. `--outtype`参数为量化精度；
3. `--outfile`参数为输出文件名，可以自定义路径

```bash
# 如果不量化，保留模型的效果
python convert_hf_to_gguf.py /PATH/TO/gelab-zero-4b-preview  --outtype f16 --verbose --outfile gelab-zero-4b-preview_f16.gguf

# 如果需要量化（加速并有损效果，已知问题是会把<THINK>错写为<THIN>），直接执行下面脚本
python convert_hf_to_gguf.py /PATH/TO/gelab-zero-4b-preview  --outtype q8_0 --verbose --outfile gelab-zero-4b-preview_q8_0.gguf
```

INT8 量化等级转换的 GGUF 格式文件大小为 4.28G，供参考。

GELab-Zero-4B-preview 是视觉模型，所以还需要再导出一个`mmproj`文件，指令如下：

```bash
# 此为 INT8 量化脚本
python convert_hf_to_gguf.py /PATH/TO/gelab-zero-4b-preview  --outtype q8_0 --verbose --outfile gelab-zero-4b-preview_q8_0_mmproj.gguf --mmproj
```

INT8 量化等级转换的 GGUF 格式大小为 454M，供参考。

#### Step 2：使用 Jan 本地部署服务

你可以使用任意支持 llama.cpp 的客户端在本地拉起 API 服务，以下以 [Jan](https://github.com/janhq/jan) 为例：

下载[jan](https://github.com/janhq/jan/releases)客户端，安装。

进入设置-模型提供商-选择llama.cpp，导入模型

<img src="images/jan_1.png" width="50%" alt="test model">

依次选择刚刚转换的两个 GGUF 文件

<img src="images/jan_2.png" width="50%" alt="test model">

回到模型界面后，记得点一下`开始`

创建一个聊天，测试一下模型是否能正常运营。

<img src="images/jan_3.png" width="50%" alt="test model">

确保模型可正常吐 token 后，启动本地 API 服务。

进入设置-本地 API 服务，服务器配置中创建一个 API 秘钥，然后启动服务。

<img src="images/jan_4.png" width="50%" alt="test model">

#### Step 3：修改 GELab-Zero Agent 的模型配置

llama.cpp的服务与 ollama 有些差异，需要修改 GELab-Zero Agent 代码中的模型配置，主要在以下两个地方：

1. `model_config.yaml`中的端口和 API_Key，其中api_key的值为刚才启动服务时创建的秘钥。

修改后：
 
```yaml
local:
    api_base: "http://localhost:1337/v1"
    api_key: "YOU_KEY"
```

2. `examples/run_single_task.py`示例代码中的模型名称，去掉参数后缀。

```python
# 第 21 行的模型名称修改为gelab-zero

local_model_config = {
    "task_type": "parser_0922_summary",
    "model_config": {
        "model_name": "gelab-zero",
        "model_provider": "local",
        "args": {
            "temperature": 0.1,
            "top_p": 0.95,
            "frequency_penalty": 0.0,
            "max_tokens": 4096,
        },
```

---

### (可选) MCP-Server 配置

#### 步骤 1：启动 MCP Server 以支持多设备管理和任务分发

```bash
# 启用 mcp server
python mcp_server/detailed_gelab_mcp_server.py

```

#### 步骤 2：在 Chatbox 中导入 MCP 工具

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
<img src="images/MCP-chatbox.png" alt="MCP-Demo" style="flex: 1; height: 400px; object-fit: contain; margin-right: 1px;"/>
</div>


## 📝 引用

如果您发现 GELab-Zero 对您的研究有帮助，请考虑引用我们的工作 :)



```bibtex
@misc{yan2025stepguitechnicalreport,
      title={Step-GUI Technical Report}, 
      author={Haolong Yan and Jia Wang and Xin Huang and Yeqing Shen and Ziyang Meng and Zhimin Fan and Kaijun Tan and Jin Gao and Lieyu Shi and Mi Yang and Shiliang Yang and Zhirui Wang and Brian Li and Kang An and Chenyang Li and Lei Lei and Mengmeng Duan and Danxun Liang and Guodong Liu and Hang Cheng and Hao Wu and Jie Dong and Junhao Huang and Mei Chen and Renjie Yu and Shunshan Li and Xu Zhou and Yiting Dai and Yineng Deng and Yingdan Liang and Zelin Chen and Wen Sun and Chengxu Yan and Chunqin Xu and Dong Li and Fengqiong Xiao and Guanghao Fan and Guopeng Li and Guozhen Peng and Hongbing Li and Hang Li and Hongming Chen and Jingjing Xie and Jianyong Li and Jingyang Zhang and Jiaju Ren and Jiayu Yuan and Jianpeng Yin and Kai Cao and Liang Zhao and Liguo Tan and Liying Shi and Mengqiang Ren and Min Xu and Manjiao Liu and Mao Luo and Mingxin Wan and Na Wang and Nan Wu and Ning Wang and Peiyao Ma and Qingzhou Zhang and Qiao Wang and Qinlin Zeng and Qiong Gao and Qiongyao Li and Shangwu Zhong and Shuli Gao and Shaofan Liu and Shisi Gao and Shuang Luo and Xingbin Liu and Xiaojia Liu and Xiaojie Hou and Xin Liu and Xuanti Feng and Xuedan Cai and Xuan Wen and Xianwei Zhu and Xin Liang and Xin Liu and Xin Zhou and Yingxiu Zhao and Yukang Shi and Yunfang Xu and Yuqing Zeng and Yixun Zhang and Zejia Weng and Zhonghao Yan and Zhiguo Huang and Zhuoyu Wang and Zheng Ge and Jing Li and Yibo Zhu and Binxing Jiao and Xiangyu Zhang and Daxin Jiang},
      year={2025},
      eprint={2512.15431},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2512.15431}, 
}

@software{gelab_zero_2025,
  title={GELab-Zero: An Advanced Mobile Agent Inference System},
  author={GELab Team},
  year={2025},
  url={https://github.com/stepfun-ai/gelab-zero}
}

@misc{gelab_engine,
      title={GUI Exploration Lab: Enhancing Screen Navigation in Agents via Multi-Turn Reinforcement Learning}, 
      author={Haolong Yan and Yeqing Shen and Xin Huang and Jia Wang and Kaijun Tan and Zhixuan Liang and Hongxin Li and Zheng Ge and Osamu Yoshie and Si Li and Xiangyu Zhang and Daxin Jiang},
      year={2025},
      eprint={2512.02423},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2512.02423}, 
}

```


## ⭐ Star 历史
<div align="center">
  <a href="https://star-history.com/#stepfun-ai/gelab-zero&Date">
    <img src="https://api.star-history.com/svg?repos=stepfun-ai/gelab-zero&type=Date" alt="Star History Chart" width="600">
  </a>
</div>
