"""
runner.py — Pass@N retry wrapper with VLM Judge for gelab-zero.

使用方式：
    from evaluate.runner import run_task_pass_at_n

    result = run_task_pass_at_n(
        agent_server=l2_server,
        device_info=device_info,
        task="打开微信给柏茗发 helloworld",
        rollout_config=local_model_config,
    )
    print(result['success'], result['attempts'])
    print(result['judge']['verdict'], result['judge']['reason'])

Pass@N 行为：
  - Agent 完成 → 立即跑 Judge（inline 判断）
    - Judge=pass  → 成功，退出循环
    - Judge=fail  → 还有机会则继续重试，否则判失败
  - Agent 失败（ABORT / MAX_STEPS）→ 无论是否还有机会，快速 Judge 后决定是否重试
"""

import logging
import time
from typing import Literal

from copilot_agent_client.pu_client import evaluate_task_on_device
from copilot_front_end.mobile_action_helper import (
    capture_screenshot,
    open_screen,
    press_home_key,
)
from tools.image_tools import make_b64_url
from megfile import smart_remove

from evaluate.judge import (
    DEFAULT_JUDGE_PROVIDER,
    run_judge,
)

logger = logging.getLogger("evaluate.runner")

# Agent 完成后等待页面稳定再截图（秒）
_JUDGE_DELAY_SECONDS = 5


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _reset_device_env(device_id: str) -> None:
    """每次 attempt 前将设备回到主屏幕，保证干净起点。"""
    try:
        open_screen(device_id)
        press_home_key(device_id)
        logger.info(f"[Reset] 设备 {device_id} 已回到主屏幕")
    except Exception as e:
        logger.warning(f"[Reset] 设备重置失败（继续执行）: {e}")


def _take_judge_screenshot(
    device_id: str,
    delay_seconds: int = _JUDGE_DELAY_SECONDS,
) -> str | None:
    """
    等待页面稳定后截取最终状态截图。

    Args:
        device_id: ADB 设备 ID
        delay_seconds: 等待秒数，让页面从过渡态稳定下来

    Returns:
        data:image/jpeg;base64,... 格式的 URL；失败时返回 None
    """
    logger.info(f"[Screenshot] 等待 {delay_seconds}s 让页面稳定...")
    time.sleep(delay_seconds)
    try:
        tmp_path = capture_screenshot(device_id, "judge_screenshot_tmp", print_command=False)
        b64_url = make_b64_url(tmp_path)
        smart_remove(tmp_path)
        logger.info("[Screenshot] 稳定态截图已获取")
        return b64_url
    except Exception as e:
        logger.warning(f"[Screenshot] 截图失败: {e}")
        return None


# ---------------------------------------------------------------------------
# 核心入口
# ---------------------------------------------------------------------------


def run_task_pass_at_n(
    agent_server,
    device_info: dict,
    task: str,
    rollout_config: dict,
    pass_count: int = 3,
    judge_model_provider: str = DEFAULT_JUDGE_PROVIDER,
    judge_model_name: str | None = None,
    judge_mode: Literal["auto", "vlm", "text", "skip"] = "auto",
    judge_criteria: str = "",
    extra_info: dict | None = None,
) -> dict:
    """
    带 Pass@N 重试和 VLM Judge 的任务执行器。

    judge_model_name 默认为 None，自动从 model_config.yaml [judge] 节读取。
    要切换 judge 模型：修改 model_config.yaml 中 judge.model_name 即可，无需改代码。
    临时覆盖（测试用）：直接传入 judge_model_name="other-model-name"。

    judge_criteria: 额外的验收标准，Judge 会在判定时额外考量。
    例如："需要滑动到文章底部阅读全文，截图中应能看到文章末尾或评论区"

    Args:
        agent_server: LocalServer 实例
        device_info: {"device_id": str, "device_wm_size": tuple}
        task: 任务描述
        rollout_config: 模型和执行配置（与原始 evaluate_task_on_device 格式一致）
        pass_count: 最多尝试 N 次，默认 3
        judge_model_provider: model_config.yaml 中 judge 的 provider key
        judge_model_name: judge 模型名
        judge_mode: "auto"（推荐）/ "vlm"（强制视觉）/ "text"（强制纯文本）/ "skip"（关闭 judge）
        extra_info: 透传给 evaluate_task_on_device 的额外信息

    Returns:
        {
            "success": bool,
            "attempts": int,           # 实际执行次数
            "stop_reason": str,        # 最后一次的 stop_reason
            "return_val": str,         # Agent COMPLETE 时的返回文本
            "judge": dict | None,      # 最后一次 VLM Judge 结果
            "all_attempts": list[dict] # 每次 attempt 的详情（含各自 judge 结果）
        }
    """
    device_id = device_info["device_id"]
    pass_count = max(1, pass_count)
    extra_info = extra_info or {}

    # 自动检测 task 是否属于"阅读全文"场景，若是则注入滑动 criteria 和 task 提示
    # 只在调用方没有传入 judge_criteria 时才自动推断，传入了就尊重调用方的设置
    _READ_TASK_KEYWORDS = ["阅读全文", "总结全文", "读完", "查看全文",
                           "公众号", "推文", "文章", "新闻", "博客", "帖子"]
    _READ_CRITERIA = (
        "如果任务涉及阅读文章/推文，必须多次 SLIDE 滑动到文章底部阅读全文，"
        "截图中应能看到文章末尾内容或评论区入口，否则判定为 fail。"
    )
    _READ_HINT = "【重要】进入文章页后，必须多次向上滑动（SLIDE）直到页面底部，看到评论区或文末标识后再总结全文内容。"

    if not judge_criteria:
        if any(kw in task for kw in _READ_TASK_KEYWORDS):
            judge_criteria = _READ_CRITERIA
            if _READ_HINT not in task:
                task = task + "\n" + _READ_HINT
            logger.info("[Runner] 检测到全文阅读场景，已自动注入滑动 criteria 和 task 提示")
    else:
        # 调用方显式传入了 criteria，沿用旧逻辑：若 criteria 含阅读全文关键词则追加 task 提示
        _READ_KEYWORDS = ["阅读全文", "滑动到底", "读完全文", "全文"]
        if any(kw in judge_criteria for kw in _READ_KEYWORDS):
            if _READ_HINT not in task:
                task = task + "\n" + _READ_HINT
                logger.info("[Runner] judge_criteria 含全文阅读要求，已自动追加滑动提示到 task")

    all_attempts: list[dict] = []
    final_judge: dict | None = None
    success = False
    last_stop_reason = "UNKNOWN"
    last_return_val = ""

    for attempt in range(1, pass_count + 1):
        sep = "=" * 50
        logger.info(sep)
        logger.info(f"Attempt {attempt}/{pass_count}  task={task!r}")
        logger.info(sep)

        # 每次 attempt 前重置环境
        _reset_device_env(device_id)

        # ---- 执行 Agent ----
        attempt_result: dict = {}
        try:
            attempt_result = evaluate_task_on_device(
                agent_server=agent_server,
                device_info=device_info,
                task=task,
                rollout_config=rollout_config,
                extra_info=extra_info,
                reflush_app=True,
                reset_environment=False,  # 已在上方手动重置
            )
        except Exception as e:
            logger.error(f"Attempt {attempt} 执行异常: {e}", exc_info=True)
            attempt_record = {"attempt": attempt, "error": str(e), "judge": None}
            all_attempts.append(attempt_record)
            if attempt < pass_count:
                logger.info("将在下一次 attempt 重试...")
                continue
            break

        stop_reason = attempt_result.get("stop_reason", "UNKNOWN")
        return_val = attempt_result.get("return_val", "")
        history_actions = attempt_result.get("history_actions", [])
        last_stop_reason = stop_reason
        last_return_val = return_val

        logger.info(f"Attempt {attempt}: stop_reason={stop_reason}  return_val={return_val!r}")

        # ---- 截图策略：优先用执行期 last_step_screenshot，去掉延迟补截 ----
        # last_step_screenshot 是 Agent 做出 COMPLETE/ABORT 决策时实际看到的那张图
        # 比延迟 5 秒补截更可信：设备状态尚未因 Agent 操作后的副作用改变
        final_screenshot_b64: str | None = None
        if stop_reason.upper() not in ("ABORT",):
            final_screenshot_b64 = attempt_result.get("last_step_screenshot")
            if final_screenshot_b64:
                logger.info("[Judge] 使用执行期 last_step_screenshot（COMPLETE 时 Agent 实际看到的画面）")
            else:
                logger.warning("[Judge] last_step_screenshot 不可用，降级到延迟截图")
                final_screenshot_b64 = _take_judge_screenshot(device_id)

        # ---- 运行 VLM Judge ----
        logger.info(f"[Judge] 运行 Judge（attempt {attempt}/{pass_count})...")
        judge_result = run_judge(
            task=task,
            return_val=return_val,
            stop_reason=stop_reason,
            history_actions=history_actions,
            final_screenshot_b64=final_screenshot_b64,
            judge_mode=judge_mode,
            judge_criteria=judge_criteria,
            judge_model_provider=judge_model_provider,
            judge_model_name=judge_model_name,
        )
        final_judge = judge_result

        judge_pass = judge_result.get("pass")
        logger.info(
            f"[Judge] verdict={judge_result['verdict']}  "
            f"confidence={judge_result['confidence']:.2f}  "
            f"reason={judge_result['reason']}"
        )

        attempt_record = {
            "attempt": attempt,
            "stop_reason": stop_reason,
            "return_val": return_val,
            "judge": judge_result,
        }
        all_attempts.append(attempt_record)

        if judge_pass is True:
            # Judge 确认通过
            success = True
            logger.info(f"✅ Judge 判定通过，共用 {attempt} 次 attempt")
            break
        elif judge_pass is False:
            # Judge 确认失败
            logger.warning(f"❌ Judge 判定失败（attempt {attempt}/{pass_count}）")
            if attempt < pass_count:
                logger.info("将重置环境后重试...")
                continue
        else:
            # judge_pass is None → Judge 跳过（error / skip 模式），以 stop_reason 兜底
            logger.warning(f"[Judge] 判定结果为 None，以 stop_reason={stop_reason} 兜底")
            success = stop_reason.upper() == "COMPLETE"
            break

    if not success:
        logger.warning(f"所有 {pass_count} 次 attempt 均未通过 Judge。")

    return {
        "success": success,
        "attempts": len(all_attempts),
        "stop_reason": last_stop_reason,
        "return_val": last_return_val,
        "judge": final_judge,
        "all_attempts": all_attempts,
    }
