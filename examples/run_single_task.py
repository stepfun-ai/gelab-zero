import os
import sys
import time
if "." not in sys.path:
    sys.path.append(".")

from copilot_agent_client.pu_client import evaluate_task_on_device
from copilot_front_end.mobile_action_helper import list_devices, get_device_wm_size
from copilot_agent_server.local_server import LocalServer

tmp_server_config = {
    "log_dir": "running_log/server_log/os-copilot-local-eval-logs/traces",
    "image_dir": "running_log/server_log/os-copilot-local-eval-logs/images",
    "debug": False
}


local_model_config = {
    # "task_type": "parser_0922_summary",
    # "task_type": "parser_0920",
    "task_type": "parser_0920_summary_adv",
    "model_config": {
        # "model_name": "gelab-zero-4b-preview:latest",
        # "model_provider": "local",

        "model_name": "step-gui-1",
        "model_provider": "step",

        # "model_name": 'peqwen10b-20251231',
        # "model_provider": "eval",


        "args": {
            "temperature": 0.1,
            "top_p": 0.95,
            "frequency_penalty": 0.0,
            "max_tokens": 4096,
        },
        
        # optional to resize image
        # "resize_config": {
            # "is_resize": True,
            # "target_image_size": (728, 728)
        # }
    },

    "max_steps": 400,
    "delay_after_capture": 3,
    "debug": False
}


# ===== 新增：用于记录每步耗时 =====
_step_times = []


# ===== 新增：包装 automate_step 方法 =====
def wrap_automate_step_with_timing(server_instance):
    original_method = server_instance.automate_step

    def timed_automate_step(payload):
        step_start = time.time()
        try:
            result = original_method(payload)
        finally:
            duration = time.time() - step_start
            _step_times.append(duration)
            print(f"Step {len(_step_times)} took: {duration:.2f} seconds")
        return result

    # 替换实例方法
    server_instance.automate_step = timed_automate_step

if __name__ == "__main__":

    # The device ID you want to use
    device_id = list_devices()[0]
    device_wm_size = get_device_wm_size(device_id)
    device_info = {
        "device_id": device_id,
        "device_wm_size": device_wm_size
    }

    task_list = [

    "去小红书找一个能让我在上海玩四天的攻略，向我报告主要内容，浏览3-5个帖子。"
    ]

    for task in task_list:

        print(f"Using device {device_id} with wm size {device_wm_size} to execute task: {task}")

        tmp_rollout_config = local_model_config
        l2_server = LocalServer(tmp_server_config)

        # 注入计时逻辑
        wrap_automate_step_with_timing(l2_server)
        # 执行任务并计总时间
        total_start = time.time()
        # Disable auto reply
        evaluate_task_on_device(l2_server, device_info, task, tmp_rollout_config, reflush_app=True)
        total_time = time.time() - total_start

        # 在最后加一行总时间
        print(f"总计执行时间为 {total_time} 秒")
    


    pass
