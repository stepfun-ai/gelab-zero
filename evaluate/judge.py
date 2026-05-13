"""
judge.py — VLM Judge for gelab-zero task evaluation.

分级判定策略（按 judge_mode）：
  - "auto"      : 根据 stop_reason 和截图是否存在自动选择 skip / text / vlm
  - "vlm"       : 强制走全量 VLM（截图 + 历史）
  - "text"      : 强制纯文本判定（无截图，只看历史和 return_val）
  - "skip"      : 跳过 Judge，直接以 stop_reason 兜底

auto 模式决策表：
  ABORT                          → 直接 fail，0 次 LLM
  return_val 含失败关键词         → 直接 fail，0 次 LLM
  COMPLETE + 有截图               → vlm（全量，最深度）
  COMPLETE + 无截图               → text（降级）
  MAX_STEPS_REACHED + 有截图     → vlm（可能跑完了但没 COMPLETE）
  MAX_STEPS_REACHED + 无截图     → skip（直接判 fail，省 LLM 调用）
"""

import json
import logging
import re
from typing import Literal

from tools.ask_llm_v2 import ask_llm_anything

logger = logging.getLogger("evaluate.judge")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 快速过滤：含以下词的 return_val 直接判 fail，节省 LLM 调用
_FAILURE_KEYWORDS = [
    "无法完成", "失败", "不能", "错误", "超时", "未完成",
    "cannot", "failed", "failure", "unable", "error", "timeout",
]

# Judge provider key（对应 model_config.yaml 中的节名）
# 只暴露 provider，model_name 从配置文件读取，不在代码中硬编码
DEFAULT_JUDGE_PROVIDER = "judge"


def get_judge_model_name(provider: str = DEFAULT_JUDGE_PROVIDER) -> str:
    """
    从 model_config.yaml 读取 judge 模型名。

    设计意图：model_name 集中维护在配置文件，不在代码里硬编码。
    要切换 judge 模型（如从 StepFun 换成 Claude / Qwen / 本地模型），
    只需修改 model_config.yaml 中对应 provider 节的 model_name，代码无需改动。

    Args:
        provider: model_config.yaml 中的 provider key，默认 "judge"

    Returns:
        模型名字符串；配置缺失时抛出 ValueError

    Raises:
        ValueError: provider 不存在或未配置 model_name
    """
    import yaml

    with open("model_config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if provider not in config:
        raise ValueError(
            f"Judge provider '{provider}' not found in model_config.yaml. "
            f"Available providers: {list(config.keys())}"
        )

    provider_cfg = config[provider]
    model_name = provider_cfg.get("model_name", "")
    if not model_name:
        raise ValueError(
            f"model_config.yaml [{provider}] is missing 'model_name'. "
            f"Add 'model_name: your-model-name' under the [{provider}] section."
        )

    return model_name

_JUDGE_SYSTEM_PROMPT = """你是一个专业的移动端 AI Agent 测试评估员。

## 核心判定原则
**截图是判定 pass/fail 的最高优先级依据。此截图是 Agent 做出 COMPLETE 决策时实际看到的画面。**

判定规则（按优先级）：
1. **截图与 Agent 返回值交叉核验**：若任务要求提取屏幕内容（如"第一名是什么"、"告诉我XXX"），必须对比截图中实际显示的内容与 Agent 的返回值是否一致。**返回值与截图不符 → fail**，即使截图页面正确。
2. 截图清楚显示任务目标状态（目标页面已打开/操作已完成/内容已展示）且与返回值一致 → **pass**，不论过程是否低效
3. 截图明确显示任务未完成（停在错误页/目标未出现）→ **fail**
4. 无截图时：综合 verify/note/key_process 字段判断，更严格

## 执行历史字段说明
执行历史中的每一步除动作类型外，还包含 Agent 自身的认知记录：
- **verify结论**：Agent 对上一步动作是否生效的自我评估，"符合预期"表示该步成功
- **note**：Agent 对当前截图的关键信息提取，包含 UI 状态、文字内容、控件状态
- **key_process**：Agent 认为已完成的关键进展里程碑

note 字段记录了 Agent 对每步截图的语义理解，可用于发现 Agent 读图幻觉（note 描述与截图实际内容不符的情况）。

**过程质量（process_score）与任务完成（verdict）是两个独立维度，互不影响。**

## 输出格式（严格 JSON，不输出任何其他内容）
{
  "verdict": "pass 或 fail",
  "confidence": 0.0到1.0,
  "reason": "一句话，30字以内，聚焦最终状态或不一致原因",
  "process_score": 0.0到1.0,
  "process_comment": "执行过程简评（效率/决策合理性/verify符合率/冗余步骤）",
  "analysis": {
    "failure_summary": "失败原因概述，pass时填null",
    "root_cause": "UI变更/网络超时/登录异常/元素定位失败/任务理解偏差/读图幻觉/返回值与截图不符/其他",
    "suggestions": ["改进建议1", "改进建议2"]
  }
}"""

_JUDGE_USER_TEMPLATE = """## 任务描述
{task}

## 执行历史（最后 {history_len} 步）
{history_summary}

## Agent 最终状态
- stop_reason: {stop_reason}
- return_val: {return_val}

{screenshot_section}请对本次执行进行评估。"""


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _build_history_summary(history_actions: list[dict], max_steps: int = 25) -> tuple[str, int]:
    """
    从 history_actions 提取结构化摘要供 Judge 使用。

    除了动作类型和坐标，还提取 Agent 自身的认知字段：
      - note:        Agent 对当前截图的关键信息提取（文字/控件状态/进度）
      - verify:      Agent 对上一步动作是否生效的自我评估
      - key_process: Agent 认为当前完成了哪些关键进展

    这三个字段来自 parser 的输出格式，是 Agent 在执行时对每张截图的
    语义理解，Judge 结合这些信息可以做更深度的判断，而不只是看最终截图。

    Returns:
        (summary_text, actual_steps_shown)
    """
    if not history_actions:
        return "(无历史数据)", 0

    tail = history_actions[-max_steps:]
    lines = []
    if len(history_actions) > max_steps:
        lines.append(f"...(前 {len(history_actions) - max_steps} 步已省略)...")

    offset = len(history_actions) - len(tail)
    for i, action in enumerate(tail, start=offset + 1):
        action_type = action.get("action_type", "UNKNOWN")
        value = action.get("value", "")
        # 截断过长的 value（避免带入截图 base64 等大字段）
        if isinstance(value, str) and len(value) > 150:
            value = value[:150] + "...[truncated]"
        coordinate = action.get("coordinate", "")
        coord_str = f"  coord={coordinate}" if coordinate else ""

        lines.append(f"Step {i}: [{action_type}]{coord_str}  value={value!r}")

        # Agent 对本步截图的语义理解：verify / note / key_process
        # 这些字段来自 parser 输出，代表 Agent 自己对 UI 状态的判断
        verify = action.get("verify", "").strip()
        note = action.get("note", "").strip()
        key_process = action.get("key_process", "").strip()

        if verify and verify.lower() not in ("", "none"):
            # 只保留 verify 结论句，去掉冗长描述（节省 token）
            # 格式约定："因此我判断（符合｜不符合）上一步预期"
            if "因此我判断" in verify:
                verdict_line = verify[verify.rfind("因此我判断"):]
                lines.append(f"  ↳ verify结论: {verdict_line[:80]}")
            else:
                lines.append(f"  ↳ verify: {verify[:80]}")

        if note and note.lower() not in ("", "none"):
            # note 可能很长（要求记录全文），截断到合理长度
            note_preview = note[:200] + "..." if len(note) > 200 else note
            lines.append(f"  ↳ note: {note_preview}")

        if key_process and key_process.lower() not in ("", "none"):
            lines.append(f"  ↳ key_process: {key_process[:120]}")

    return "\n".join(lines), len(tail)


def _check_scroll_requirement(
    history_actions: list[dict],
    judge_criteria: str,
) -> dict | None:
    """
    若 judge_criteria 要求阅读全文，检查 history_actions 中是否有滑动操作。
    有滑动 → 返回 None（继续走 VLM Judge）。
    无滑动 → 直接返回 fail，不调 LLM。
    """
    READ_KEYWORDS = ["阅读全文", "滑动到底", "滑动到文章底部", "读完全文", "全文"]
    needs_scroll = any(kw in judge_criteria for kw in READ_KEYWORDS)
    if not needs_scroll:
        return None

    has_scroll = any(
        str(a.get("action_type", "")).upper() in ("SLIDE", "SCROLL")
        for a in history_actions
    )
    if has_scroll:
        return None

    return _make_result(
        passed=False,
        verdict="fail",
        confidence=0.95,
        reason="任务要求阅读全文但 Agent 全程未滑动页面",
        process_score=0.1,
        process_comment="未执行任何滑动操作即 COMPLETE，未完成全文阅读",
        root_cause="missing_scroll",
        suggestions=["在 COMPLETE 前应多次 SLIDE 滑动文章页直到底部"],
    )


def _quick_check(return_val: str, stop_reason: str) -> dict | None:
    """
    快速判定：不需要 LLM 调用就能确定结果的情况。

    Returns:
        判定结果 dict，或 None（表示需要继续走 LLM Judge）。
    """
    # ABORT：Agent 主动放弃，直接 fail
    if stop_reason.upper() == "ABORT":
        return _make_result(
            passed=False,
            verdict="fail",
            confidence=1.0,
            reason="Agent 主动 ABORT",
            process_score=0.3,
            process_comment="Agent 诚实放弃",
            root_cause="agent_abort",
        )

    # return_val 含失败关键词
    if return_val:
        for kw in _FAILURE_KEYWORDS:
            if kw.lower() in return_val.lower():
                return _make_result(
                    passed=False,
                    verdict="fail",
                    confidence=0.9,
                    reason=f"Agent 返回含失败关键词「{kw}」",
                    process_score=0.0,
                    process_comment="",
                    root_cause="agent_reported_failure",
                )

    return None


def _make_result(
    *,
    passed: bool | None,
    verdict: str,
    confidence: float,
    reason: str,
    process_score: float,
    process_comment: str,
    root_cause: str = "",
    suggestions: list[str] | None = None,
) -> dict:
    """统一构造 judge 结果 dict。"""
    return {
        "pass": passed,
        "verdict": verdict,
        "confidence": confidence,
        "reason": reason,
        "process_score": process_score,
        "process_comment": process_comment,
        "analysis": {
            "failure_summary": None if passed else reason,
            "root_cause": root_cause,
            "suggestions": suggestions or [],
        },
    }


# ---------------------------------------------------------------------------
# 核心 Judge 函数
# ---------------------------------------------------------------------------

def run_judge(
    task: str,
    return_val: str,
    stop_reason: str,
    history_actions: list[dict],
    final_screenshot_b64: str | None = None,
    judge_mode: Literal["auto", "vlm", "text", "skip"] = "auto",
    judge_criteria: str = "",
    judge_model_provider: str = DEFAULT_JUDGE_PROVIDER,
    judge_model_name: str | None = None,
) -> dict:
    """
    运行 VLM Judge，返回判断结果。

    judge_criteria: 额外验收标准，追加到 prompt 中让 Judge 额外考量。
    例如："需要滑动到文章底部，截图应能看到文章末尾或评论区入口"

    Args:
        task: 任务描述字符串
        return_val: Agent COMPLETE/ABORT 时的 value 文本
        stop_reason: COMPLETE / ABORT / MAX_STEPS_REACHED / MANUAL_STOP
        history_actions: evaluate_task_on_device 返回的 history_actions 列表
        final_screenshot_b64: 延迟截取的最终截图，格式为 data:image/jpeg;base64,...
                              为 None 时不做视觉判断
        judge_mode: 判定策略，"auto" 时根据 stop_reason + 截图自动选择
        judge_model_provider: model_config.yaml 中的 provider key
        judge_model_name: judge 使用的模型名

    Returns:
        {
            "pass": bool | None,      # None 表示 judge 跳过
            "verdict": str,           # "pass" / "fail" / "skip" / "error"
            "confidence": float,
            "reason": str,
            "process_score": float,   # 0~1，独立于 verdict
            "process_comment": str,
            "analysis": {
                "failure_summary": str | None,
                "root_cause": str,
                "suggestions": list[str],
            },
        }
    """
    # ---- 第一层：快速判定（0 次 LLM）----
    quick = _quick_check(return_val, stop_reason)
    if quick is not None:
        logger.info(f"[Judge] 快速判定: {quick['verdict']}  reason={quick['reason']}")
        return quick

    # ---- 第一层补充：滑动行为检查（0 次 LLM）----
    scroll_check = _check_scroll_requirement(history_actions, judge_criteria)
    if scroll_check is not None:
        logger.info(f"[Judge] 滑动检查未通过: {scroll_check['reason']}")
        return scroll_check

    # ---- 解析 judge model name（None 时从 model_config.yaml 读取）----
    if judge_model_name is None:
        judge_model_name = get_judge_model_name(judge_model_provider)
    logger.info(f"[Judge] provider={judge_model_provider}  model={judge_model_name}")

    # ---- 确定实际执行模式 ----
    has_screenshot = bool(final_screenshot_b64)

    if judge_mode == "skip":
        effective_mode = "skip"
    elif judge_mode == "vlm":
        effective_mode = "vlm"
    elif judge_mode == "text":
        effective_mode = "text"
    else:
        # auto：根据 stop_reason 和截图决定
        if has_screenshot:
            # 有截图时都走 vlm，充分利用 StepFun 的 GUI 理解能力
            effective_mode = "vlm"
        else:
            # 无截图：COMPLETE 降级到 text，MAX_STEPS 直接 skip（大概率失败）
            if stop_reason.upper() == "COMPLETE":
                effective_mode = "text"
            else:
                effective_mode = "skip"

    logger.info(
        f"[Judge] mode={judge_mode} → effective={effective_mode}  "
        f"stop={stop_reason}  has_screenshot={has_screenshot}"
    )

    # ---- skip 模式：以 stop_reason 兜底 ----
    if effective_mode == "skip":
        passed = stop_reason.upper() == "COMPLETE"
        return _make_result(
            passed=passed,
            verdict="pass" if passed else "fail",
            confidence=0.5,
            reason=f"Judge 跳过，以 stop_reason={stop_reason} 兜底",
            process_score=0.5,
            process_comment="",
            root_cause="judge_skipped",
        )

    # ---- 构建 LLM 请求 ----
    history_summary, history_len = _build_history_summary(history_actions)

    # 额外验收标准：追加到 screenshot_section 之后
    criteria_section = f"## 额外验收标准\n{judge_criteria}\n\n" if judge_criteria.strip() else ""

    if effective_mode == "vlm" and has_screenshot:
        screenshot_section = "## 最终截图\n（已附带，请结合截图判断）\n\n" + criteria_section
        user_text = _JUDGE_USER_TEMPLATE.format(
            task=task,
            history_len=history_len,
            history_summary=history_summary,
            stop_reason=stop_reason,
            return_val=return_val or "(Agent 未返回任何文本)",
            screenshot_section=screenshot_section,
        )
        messages = [
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": final_screenshot_b64}},
                ],
            },
        ]
    else:
        # text 模式：无截图
        screenshot_section = "## 最终截图\n（无截图，请仅依据执行历史和返回值判断，不得因缺少截图判定失败）\n\n" + criteria_section
        user_text = _JUDGE_USER_TEMPLATE.format(
            task=task,
            history_len=history_len,
            history_summary=history_summary,
            stop_reason=stop_reason,
            return_val=return_val or "(Agent 未返回任何文本)",
            screenshot_section=screenshot_section,
        )
        messages = [
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

    # ---- 调用 LLM（最多重试 2 次，应对空响应或 JSON 解析失败）----
    last_exc: Exception | None = None
    for _attempt in range(3):
        try:
            raw = ask_llm_anything(
                model_provider=judge_model_provider,
                model_name=judge_model_name,
                messages=messages,
                args={
                    "max_tokens": 1024,
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "frequency_penalty": 0.0,
                },
            )
            # 去掉 <think>...</think> 推理段落
            if "</think>" in raw:
                raw = raw.split("</think>")[-1].strip()

            if not raw.strip():
                raise ValueError("Judge LLM 返回了空内容（仅有 think 段落，正文为空）")

            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not json_match:
                raise ValueError(f"Judge LLM 返回内容中未找到 JSON：{raw[:200]!r}")
            parsed = json.loads(json_match.group())

            verdict = str(parsed.get("verdict", "fail")).lower()
            analysis = parsed.get("analysis") or {}
            result = {
                "pass": verdict == "pass",
                "verdict": verdict,
                "confidence": float(parsed.get("confidence", 0.5)),
                "reason": parsed.get("reason", ""),
                "process_score": float(parsed.get("process_score", 0.5)),
                "process_comment": parsed.get("process_comment", ""),
                "analysis": {
                    "failure_summary": analysis.get("failure_summary"),
                    "root_cause": analysis.get("root_cause", ""),
                    "suggestions": analysis.get("suggestions") or [],
                },
            }
            logger.info(
                f"[Judge] verdict={result['verdict']}  "
                f"confidence={result['confidence']:.2f}  "
                f"reason={result['reason']}"
            )
            return result

        except Exception as e:
            last_exc = e
            logger.warning(f"[Judge] 第 {_attempt + 1} 次调用失败: {e}，{'重试中...' if _attempt < 2 else '已达最大重试次数'}")

    # 所有重试均失败
    logger.error(f"[Judge] LLM 调用全部失败: {last_exc}", exc_info=True)
    return _make_result(
        passed=None,
        verdict="error",
        confidence=0.0,
        reason=f"Judge 调用异常: {last_exc}",
        process_score=0.0,
        process_comment="",
        root_cause="judge_error",
    )
