import os
import sys

if "." not in sys.path:
    sys.path.append(".")

import json

from PIL import Image
import io

from tools.image_tools import draw_points, make_b64_url

from copilot_front_end.mobile_action_helper import capture_screenshot, dectect_screen_on, press_home_key

from copilot_front_end.mobile_action_helper import init_device, open_screen
from copilot_front_end.pu_frontend_executor import act_on_device, uiTars_to_frontend_action

from megfile import smart_remove

import time

from tools.ask_llm_v2 import ask_llm_anything

def reply_info_action(current_image_url, task, info_action, model_provider, model_name):
    """
    Reply with information action.
    """
    messages_to_ask = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text":  f"""# 角色
你将扮演一个正在使用GUI Agent完成任务的用户。

# 任务
阅读下方提供的所有背景信息，针对[Agent的澄清问题]，生成一个提供关键信息的、简短直接的回答。

# 背景信息
- **任务目标:** {task}
- **agent 问的问题:** {json.dumps(info_action, ensure_ascii=False)}

# 输出要求
- 你的回答必须极其简短和明确。
- 你的回答应直接命中问题的核心，解决Agent的疑惑。
- 不要进行任何额外的解释、对话或使用礼貌用语。
- 只输出回答本身，不要添加任何引号或其他修饰。

以下是当前页面内容:
                """,
                },
                {
                    'type': "image_url",
                    'image_url': {
                        'url': current_image_url
                    }
                },
                {
                    "type": "text",
                    "text": '请基于以上信息，简洁直接地回答Agent的问题。'
                }
            ]
        }
    ]

    response = ask_llm_anything(
        model_provider=model_provider,
        model_name=model_name,
        messages=messages_to_ask,
        args={
            "max_tokens": 1024,
            "temperature": 0.5,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
        }
    )

    if "</think>" in response:
        response = response.split("</think>")[-1].strip()

    return response

# delay after act on device
# rollout config
# device info
# def evaluate_task_on_device(agent_server, device_info, task, frontend_action_converter, ask_action_function_func, max_steps = 40, delay_after_capture = 2):
def evaluate_task_on_device(agent_server, device_info, task, rollout_config, extra_info = {}, reflush_app=True, auto_reply = False, reset_environment=True):
    """
    Evaluate a task on a device using the provided frontend action converter and action function.

    """

    # init device for the first time
    device_id = device_info['device_id']
    open_screen(device_id)
    init_device(device_id)


    if reset_environment:
        press_home_key(device_id, print_command=True)

    task, task_type = task, rollout_config['task_type']

    session_id = agent_server.get_session({
        "task": task,
        "task_type": task_type,
        "model_config": rollout_config['model_config'],
        "extra_info": extra_info
        
    })

    print(f"Session ID: {session_id}")

    return_log = {
        "session_id": session_id,
        "device_info": device_info,
        "task": task,
        "rollout_config": rollout_config,
        "extra_info": extra_info
    }

    device_id, device_wm_size = device_info['device_id'], device_info['device_wm_size']

    max_steps = rollout_config.get('max_steps', 40)
    delay_after_capture = rollout_config.get('delay_after_capture', 2)

    history_actions = []
    # 保留执行期截图的 base64，供 Judge 使用
    # 只保留最后 JUDGE_SCREENSHOT_KEEP 张，避免内存占用过大
    # key = step_idx（0-based），value = base64 url
    JUDGE_SCREENSHOT_KEEP = 5
    step_screenshots: dict[int, str] = {}

    for step_idx in range(max_steps):

        if not dectect_screen_on(device_id):
            print("Screen is off, turn on the screen first")
            break

        image_path = capture_screenshot(device_id, "tmp_screenshot", print_command=False)

        image_b64_url = make_b64_url(image_path, resize_config=rollout_config['model_config'].get("resize_config", None))
        smart_remove(image_path)

        # 分叉：同一张截图保存一份给 Judge，不影响 Agent 处理路径
        step_screenshots[step_idx] = image_b64_url
        # 只保留最后 K 步，滚动丢弃更早的
        if len(step_screenshots) > JUDGE_SCREENSHOT_KEEP:
            oldest_key = min(step_screenshots)
            del step_screenshots[oldest_key]
        
        payload = {
            "session_id": session_id,
            "observation": {
                "screenshot": {
                    "type": "image_url",
                    "image_url": {
                        "url": image_b64_url
                    }
                },
            }
        }
        if history_actions[-1]['action_type'] == "INFO" if len(history_actions) > 0 else False:
            info_action = history_actions[-1]

            if auto_reply:
                print(f"AUTO REPLY INFO FROM MODEL!")
                reply_info = reply_info_action(image_b64_url, task, info_action, model_provider=rollout_config['model_config']['model_provider'], model_name=rollout_config['model_config']['model_name'])
                print(f"info: {reply_info}")
            
            else:
                print(f"EN: Agent asks: {history_actions[-1]['value']} Please Reply: ")
                print(f"ZH: Agent 问你: {history_actions[-1]['value']} 回复一下：")

                reply_info = input("Your reply:")

            print(f"Replied info action: {reply_info}")

            payload['observation']['query'] = reply_info


        action = agent_server.automate_step(payload)['action']

        #TODO: to replace with the new function
        action = uiTars_to_frontend_action(action)

        act_on_device(action, device_id, device_wm_size, print_command=True, reflush_app=reflush_app)

        history_actions.append(action)


        print(f"Step {step_idx+1}/{max_steps} done. Action: {action}")

        if action['action_type'].upper() in ['COMPLETE', "ABORT"]:
            stop_reason = action['action_type'].upper()
            break

        time.sleep(delay_after_capture)
    
    if action['action_type'] in ['COMPLETE', "ABORT"]:
        stop_reason = action['action_type']
    elif step_idx == max_steps - 1:
        stop_reason = "MAX_STEPS_REACHED"
    else:
        stop_reason = "MANUAL_STOP"

    # return_log['session_id'] = session_id
    return_log['stop_reason'] = stop_reason
    return_log['stop_steps'] = step_idx + 1
    # judge 需要的字段：最终动作返回文本 + 完整历史
    # 注意：COMPLETE 的消息字段名是 'return'（协议格式：action:COMPLETE\treturn:...）
    #       ABORT   的消息字段名是 'value' （协议格式：action:ABORT\tvalue:...）
    if stop_reason == 'COMPLETE':
        return_log['return_val'] = action.get('return') or action.get('value') or ''
    elif stop_reason == 'ABORT':
        return_log['return_val'] = action.get('value') or action.get('return') or ''
    else:
        return_log['return_val'] = ''
    return_log['history_actions'] = history_actions
    # 执行期截图（最后 JUDGE_SCREENSHOT_KEEP 步），Judge 直接用这些，不再延迟补截
    # last_step_screenshot：COMPLETE/ABORT 那一步 Agent 实际看到的画面，最高优先级
    return_log['step_screenshots'] = step_screenshots
    return_log['last_step_screenshot'] = step_screenshots.get(step_idx)

    print(f"Task {task} done in {len(history_actions)} steps. Session ID: {session_id}")

    return return_log


