import sys
import time

if "." not in sys.path:
    sys.path.append(".")

from copilot_front_end.mobile_action_helper import list_devices, get_device_wm_size
from copilot_agent_server.local_state_compress_server import LocalStateCompressServer
from evaluate.runner import run_task_pass_at_n

tmp_server_config = {
    "log_dir": "running_log/server_log/os-copilot-local-eval-logs/traces",
    "image_dir": "running_log/server_log/os-copilot-local-eval-logs/images",
    "debug": False
}

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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_single_task.py \"your task\"")
        sys.exit(1)

    task = ' '.join(sys.argv[1:])

    device_id = list_devices()[0]
    device_wm_size = get_device_wm_size(device_id)
    device_info = {
        "device_id": device_id,
        "device_wm_size": device_wm_size,
    }

    print(f"Device: {device_id}  wm_size: {device_wm_size}")
    print(f"Task: {task}")
    print("=" * 60)

    l2_server = LocalStateCompressServer(tmp_server_config)

    total_start = time.time()
    result = run_task_pass_at_n(
        agent_server=l2_server,
        device_info=device_info,
        task=task,
        rollout_config=local_model_config,
        pass_count=3,
        judge_mode="auto",
        # judge_criteria 留空，由 runner 根据 task 内容自动判断是否需要滑动检查
        judge_criteria="",
    )
    total_time = time.time() - total_start

    # ── 最终报告（独立分区，与 LLM 执行日志隔开）──────────────────────────
    W = 60
    print(f"\n{'#' * W}")
    print(f"#{'EVALUATION REPORT':^{W-2}}#")
    print(f"{'#' * W}")

    # 基本信息
    status_icon = "✅ SUCCESS" if result['success'] else "❌  FAIL  "
    print(f"  状态      : {status_icon}")
    print(f"  耗时      : {total_time:.1f}s  ({result['attempts']}/3 次 attempt)")
    print(f"  stop      : {result['stop_reason']}")

    # Agent 输出
    print(f"\n  {'─'*54}")
    print(f"  📤 Agent 输出")
    print(f"  {'─'*54}")
    agent_out = result['return_val'] or "(无)"
    for line in agent_out.splitlines():
        print(f"  {line}")

    # Judge 判定
    if result['judge']:
        j = result['judge']
        verdict_icon = "✅ pass" if j['verdict'] == "pass" else ("❌ fail" if j['verdict'] == "fail" else f"⚠️  {j['verdict']}")
        print(f"\n  {'─'*54}")
        print(f"  🔍 Judge 判定")
        print(f"  {'─'*54}")
        print(f"  verdict       : {verdict_icon}  (confidence={j['confidence']:.0%})")
        print(f"  reason        : {j['reason']}")
        print(f"  process_score : {j['process_score']:.1f}/1.0  {j['process_comment']}")
        if j['analysis'].get('root_cause'):
            print(f"  root_cause    : {j['analysis']['root_cause']}")
        if j['analysis'].get('suggestions'):
            for i, s in enumerate(j['analysis']['suggestions'], 1):
                print(f"  suggestion {i}  : {s}")

    print(f"{'#' * W}\n")
