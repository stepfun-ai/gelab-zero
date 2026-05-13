# GELab-Zero 极简运行指南（State Compress 入口）

本文面向 `examples/run_single_task_state_compress.py`，采用标准 OpenAI 兼容 API 服务运行，不包含 ollama / vllm / llama.cpp 的部署过程。

推荐你从项目根目录执行本文中的所有命令。

## 0. 项目作用与基本流程

### 0.1 这个项目是做什么的

`GELab-Zero` 是一个面向 Android 手机上的 GUI Agent 运行框架。它把“大模型理解屏幕并做决策”和“手机真实执行操作”串起来，方便你直接验证手机 Agent 任务。

![GELab-Zero 主图](./images/main_cn.png)

你可以把它理解成一条完整链路：

1. 你给 Agent 一个自然语言任务
2. 电脑通过 ADB 连接手机并截图
3. Agent 把当前截图、历史轨迹和任务描述发给多模态模型
4. 模型输出下一步动作，比如 `AWAKE`、`CLICK`、`TYPE`、`SLIDE`
5. 框架把动作真正执行到手机上
6. 每一步截图、动作和模型输出都会被记录
7. 最后再通过可视化页面按 `Session ID` 回看整个过程

### 0.2 本运行入口的工作流程

以 `examples/run_single_task_state_compress.py` 为例，运行时会依次做这些事：

1. 通过 `adb` 找到可用手机
2. 获取屏幕分辨率等设备信息
3. 初始化 `LocalStateCompressServer`
4. 用 `tools/ask_llm_v2.py` 读取 `model_config.yaml`，调用你配置的标准 OpenAI 兼容 API
5. 在长轨迹任务中定期做 state compression，压缩历史上下文
6. 把模型动作执行到手机上，并持续记录本地日志
7. 将日志写入 `running_log/server_log/os-copilot-local-eval-logs/`

这个入口的重点就是：直接跑真实手机任务，并默认启用 state compression。

## 1. 手机环境配置

这部分可参考 `README_CN.md` 的安卓设备配置章节，最少需要完成下面 3 件事：

### 1.1 打开开发者模式和 USB 调试

1. 打开手机“设置”。
2. 进入“关于手机”或“系统”。
3. 连续点击“版本号”10 次以上，直到出现“已处于开发者模式”之类的提示。
4. 回到“设置”，进入“开发者选项”。
5. 打开“USB 调试”。这一步必须开启。

不同品牌手机入口可能不同，可以自行搜索“你的手机品牌 + 开发者模式 / USB 调试”。

可参考下面两张示意图：

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/developer_mode_1.png" alt="开发者模式示意图 1" style="flex: 1; height: 230px; object-fit: contain; margin-right: 1px;"/>
  <img src="images/developer_mode_2.png" alt="开发者模式示意图 2" style="flex: 1; height: 230px; object-fit: contain; margin-left: 1px;"/>
</div>

### 1.2 安装 ADB

- Windows：
  - 下载 `platform-tools`：`https://dl.google.com/android/repository/platform-tools-latest-windows.zip`
  - 解压后把目录加入 `PATH`
- Mac：
  ```bash
  brew install android-platform-tools
  ```
- Linux：
  - 使用系统包管理器安装 ADB / platform-tools 即可

### 1.3 连接手机并确认可控

用 USB 数据线连接手机后执行：

```bash
adb devices
```

看到类似输出即可：

```text
List of devices attached
AN2CVB4C28000731    device
```

如果显示 `unauthorized`，请到手机上点“允许 USB 调试”。

首次授权时，大致会看到类似弹窗：

<div style="display: flex; align-items: center; justify-content: center; width: 80%; margin: 0 auto;">
  <img src="images/developer_mode_auth.png" alt="USB 调试授权示意图" style="flex: 1; height: 230px; object-fit: contain; margin-right: 1px;"/>
</div>

## 2. 电脑运行环境配置

### 2.1 安装 Python 3.12+

推荐按 `README_CN.md` 使用 Miniforge。

- Windows：请使用 PowerShell
  1. 安装 Miniforge：`https://github.com/conda-forge/miniforge`
  2. 初始化 conda：
     ```powershell
     conda init powershell
     Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
     ```

- Mac / Linux：
  ```bash
  curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
  bash Miniforge3-$(uname)-$(uname -m).sh
  conda create -n gelab-zero python=3.12 -y
  conda activate gelab-zero
  ```

### 2.2 拉代码并安装依赖

```bash
git clone https://github.com/stepfun-ai/gelab-zero
cd gelab-zero
pip install -r requirements.txt
```

### 2.3 配置标准 OpenAI 兼容 API 服务

本仓库的 LLM 调用会读取 `model_config.yaml`，并通过 `tools/ask_llm_v2.py` 发起请求。

先修改 `model_config.yaml` 中的 `local` 配置，填入你自己的标准 OpenAI 兼容服务地址和 API Key：

```yaml
stepfun:
    api_base: "https://api.stepfun.com/v1"
    api_key: "YOUR_API_KEY"
```

然后修改 `examples/run_single_task_state_compress.py` 里的模型配置：

```python
local_model_config = {
    "task_type": "parser_0920_summary_adv_state_compress",
    "model_config": {
        "model_name": "step-3.6",
        "model_provider": "stepfun",
        "args": {
            "temperature": 1,
            "top_p": 0.95,
            "frequency_penalty": 0.05,
            "max_tokens": 32768,
        },
    },
    "config": {
        "enable_state_compression": True,
        "state_compression_interval": 10,
        "state_compression_recent_window": 10,
        "state_compression_max_field_items": 10,
    },
    "max_steps": 400,
    "delay_after_capture": 3,
    "debug": False,
}
```

重点：`temperature` 建议保持为 `1`，不要改成 `0.1` 或 `0.5`。

### 2.4 运行单任务

先确认手机仍然能被 ADB 识别：

```bash
adb devices
```

然后从项目根目录启动：

```bash
python examples/run_single_task_state_compress.py \
  --task "帮我看看微博文娱热搜上有哪些内容，总结一下给我"
```

如果你有多台设备，建议显式指定：

```bash
python examples/run_single_task_state_compress.py \
  --device-id AN2CVB4C28000731 \
  --task "帮我看看微博文娱热搜上有哪些内容，总结一下给我"
```

运行后终端会打印：

- `Session ID: ...`
- 每一步的耗时
- 当前动作
- 最终总耗时

任务日志默认保存在：

- `running_log/server_log/os-copilot-local-eval-logs/traces`
- `running_log/server_log/os-copilot-local-eval-logs/images`

如果执行过程中模型发出 `INFO` 动作，终端会要求你补充信息，直接在命令行输入回复并回车即可。

## 3. 可视化结果页面配置与启动

现在 `visualization/` 目录只保留本地结果查看相关内容，唯一页面是 `visualization/pages/main_page.py`。

`examples/run_single_task_state_compress.py` 默认把日志写到本地目录，因此直接使用这个页面即可：

```bash
streamlit run visualization/pages/main_page.py --server.address 127.0.0.1 --server.port 33503
```

如果你想让局域网内其他设备也能访问：

```bash
streamlit run visualization/pages/main_page.py --server.address 0.0.0.0 --server.port 33503
```

启动后在浏览器打开：

```text
http://localhost:33503
```

使用方式：

1. 从任务终端复制 `Session ID`
2. 粘贴到页面输入框
3. 点击“查找”
4. 查看每一步截图、模型思考和动作结果

## 4. 推荐参数

以 `examples/run_single_task_state_compress.py` 当前入口为准，推荐先不要随意改下面这些参数：

| 参数 | 推荐值 | 作用 |
| --- | --- | --- |
| `task_type` | `parser_0920_summary_adv_state_compress` | 指定使用带状态压缩能力的解析与执行链路 |
| `temperature` | `1` | 控制采样随机性，当前入口建议开到 1，避免策略过于保守 |
| `top_p` | `0.95` | 控制 nucleus sampling 的候选范围，帮助模型保留合理多样性 |
| `frequency_penalty` | `0.05` | 轻微抑制重复表达，减少模型在思考和动作中的重复倾向 |
| `max_tokens` | `32768` | 限制单次模型返回长度，给长思考和长上下文留足空间 |
| `max_steps` | `400` | 限制单任务最多可执行的动作步数，防止无限循环 |
| `delay_after_capture` | `3` | 每步操作后等待截图与页面稳定的秒数 |
| `enable_state_compression` | `True` | 开启长轨迹历史压缩，降低上下文膨胀 |
| `state_compression_interval` | `10` | 每隔多少步做一次历史压缩 |
| `state_compression_recent_window` | `10` | 压缩时保留最近多少步的原始细节不动 |
| `state_compression_max_field_items` | `10` | 限制压缩摘要里每类字段保留的信息条数 |

其中最重要的是：`temperature = 1`。

## 5. 最短路径总结

如果你只想快速跑通，最短路径就是：

1. 手机打开开发者模式和 USB 调试
2. 电脑安装 Python 3.12+ 和依赖
3. `adb devices` 确认手机在线
4. 改 `model_config.yaml`
5. 改 `examples/run_single_task_state_compress.py` 的 `model_provider` / `model_name`
6. 运行 `python examples/run_single_task_state_compress.py --task "你的任务"`
7. 运行 `streamlit run visualization/pages/main_page.py --server.port 33503`

---

## 6. Pass@N 评测入口（带 VLM Judge）

除了 `run_single_task_state_compress.py`，本仓库还提供了 `examples/run_single_task_with_judge.py`，在原有执行能力基础上新增了两个核心功能：**Pass@N 重试** 和 **VLM Judge 自动判定**。

### 6.1 功能概述

| 功能 | 说明 |
|------|------|
| **Pass@N** | 每个任务最多执行 N 次（默认 3），Judge 判定通过即提前退出，节省不必要的重试 |
| **VLM Judge** | 任务结束后自动调用 LLM，结合执行期截图和动作日志判断任务是否真正完成 |
| **截图分叉** | Agent 每步截图同时保留一份给 Judge，Judge 看到的是 Agent 决策时的真实画面，而非事后补截 |
| **场景自动检测** | 任务描述含"公众号/推文/文章"等关键词时，自动注入滑动阅读全文的约束和验收标准 |
| **交叉核验** | Judge 对比截图实际内容与 Agent 返回值，捕捉读图幻觉类错误 |

### 6.2 配置 model_config.yaml

在原有 `stepfun` 配置基础上，新增 `judge` 节：

```yaml
stepfun:
    api_base: "https://api.stepfun.com/v1"
    api_key: "YOUR_API_KEY"

# judge 独立一节，换模型只改 model_name，无需动代码
judge:
    api_base: "https://api.stepfun.com/v1"
    api_key: "YOUR_API_KEY"
    model_name: "step-3.6"
```

`judge` 可以和 `stepfun` 使用同一套 API，也可以指向不同服务商。

### 6.3 运行

```bash
python examples/run_single_task_with_judge.py "你的任务描述"
```

示例：

```bash
python examples/run_single_task_with_judge.py "打开微信，查看通讯录第一个联系人的名字"
python examples/run_single_task_with_judge.py "打开设置，查看当前手机型号"
```

### 6.4 输出说明

任务执行过程日志（LLM 推理、每步动作）输出后，末尾会打印独立的评测报告：

```
############################################################
#                   EVALUATION REPORT                     #
############################################################
  状态      : ✅ SUCCESS
  耗时      : 48.2s  (1/3 次 attempt)
  stop      : COMPLETE

  📤 Agent 输出
  ──────────────────────────────────────────────────────
  打开设置后，当前手机型号为 XXX

  🔍 Judge 判定
  ──────────────────────────────────────────────────────
  verdict       : ✅ pass  (confidence=100%)
  reason        : 截图清晰显示榜单页面，返回值与截图一致
  process_score : 1.0/1.0  执行路径高效，无冗余步骤
############################################################
```

每步截图保存在：

```
running_log/server_log/os-copilot-local-eval-logs/images/{session_id}_step_{N}.jpeg
```

### 6.5 Judge 判定逻辑

Judge 采用分级策略，按开销从低到高依次处理：

1. **0 次 LLM**：ABORT、return_val 含失败关键词、要求滑动但无 SLIDE → 直接 fail
2. **1 次 LLM（文本模式）**：COMPLETE 但无截图 → 纯文本判定
3. **1 次 LLM（视觉模式）**：COMPLETE + 有截图 → 全量 VLM，截图与返回值交叉核验

Judge 模型调用失败时自动重试最多 3 次，全部失败则以 `stop_reason` 兜底。

