import os
import sys

if "." not in sys.path:
    sys.path.append(".")

import json

from PIL import Image
import io

from tools.image_tools import make_b64_url

from copilot_front_end.mobile_action_helper import capture_screenshot, dectect_screen_on, press_home_key

from copilot_front_end.mobile_action_helper import init_device, open_screen
from copilot_front_end.pu_frontend_executor import act_on_device, uiTars_to_frontend_action
from copilot_front_end.mobile_action_helper import get_device_wm_size
from fastmcp.utilities.types import Image as MCPImage


from megfile import smart_remove

import time

from tools.ask_llm_v2 import ask_llm_anything

import threading

# 暂停信号文件路径 - 使用绝对路径基于项目根目录
def get_pause_signal_file():
    """获取暂停信号文件的绝对路径"""
    # 从 copilot_agent_client 目录向上一级找到项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "tmp_screenshot", "pause_signal.txt")

def check_pause_signal():
    """
    检查是否有外部暂停信号。
    如果存在暂停信号文件，删除文件并返回 True (should_pause).
    Returns: should_pause: bool
    """
    pause_file = get_pause_signal_file()
    if os.path.exists(pause_file):
        try:
            # 仅检测文件存在，不需要读取内容
            os.remove(pause_file)
            print(f"[DEBUG] 检测到暂停信号: {pause_file}")
            return True
        except Exception as e:
            print(f"[WARNING] 读取/删除暂停信号文件失败: {e}")
            return False
    return False

def clear_pause_signal():
    """清除暂停信号文件（如果存在）"""
    pause_file = get_pause_signal_file()
    if os.path.exists(pause_file):
        try:
            os.remove(pause_file)
            print(f"[DEBUG] 已清除暂停信号: {pause_file}")
        except:
            pass


def auto_reply(current_image_url, task, info_action, model_provider, model_name):
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

def caption_current_screenshot(current_task, current_image_url, model_config, result_container=None):
    """
    Caption the current screenshot using the caption model specified in model_config.
    """

    model_name = model_config['model_name']
    model_provider = model_config.get('model_provider', 'eval')

    messages_to_ask = [
        {
            "role": "user",
            "content": [
                {
                    'type': "image_url",
                    'image_url': {
                        'url': current_image_url
                    }
                },
                {
                    "type": "text",
                    "text": f"当前的任务是：{current_task}。\n请根据任务需求，详细描述出当前截图和任务相关的部分。如果有列表，请列出所有选项。"
                },
            ]
        }
    ]

    response = ask_llm_anything(
        model_provider=model_provider,
        model_name=model_name,
        messages=messages_to_ask,
        args={
            "max_tokens": 256,
            "temperature": 0.5,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
        },
        resize_config=model_config.get('image_preprocess', None)
    )

    if result_container is not None:
        result_container['caption'] = response

    return response

def gui_agent_loop(
        # the agent server to interact with
        agent_server,

        # the detail config of agent loop
        agent_loop_config: dict,

        # device id
        device_id: str,

        # max steps
        max_steps: int,

        enable_intermediate_logs: bool = False,
        enable_intermediate_image_caption: bool = False,
        enable_intermediate_screenshots: bool = False,

        enable_final_screenshot: bool = False,
        enable_final_image_caption: bool = False,

        # whether to reset the environment before starting the task
        reset_environment: bool = True,

        # whether to reflush app when awake
        reflush_app: bool = True,

        # When the INFO action is called, how to handle it.
        # 1. "auto_reply": the INFO action will be handled automatically by calling the caption model to generate image captions.
        # 2. "no_reply": the INFO action will be ignored. THE AGENT MAY GET STUCK IF THE INFO ACTION IS IGNORED.
        # 3. "manual_reply": the INFO action will cause an interruption, and the user needs to provide the reply manually by input things in server's console.
        # 4. "pass_to_client": the INFO action will be returned to the MCP client to handle it.
        reply_mode: str = "pass_to_client",  # options: "auto_reply", "pass_to_client", 

        # task: the task to execute, if None, the session id must be provided, meaning to continue an existing session
        task: str = None,

        # if session_id is provided, continue the existing session, happens only when last action in this session is INFO, and need reply from client
        session_id: str = None, 

        # optional you can provide extra infomation to pass to the agent and log it
        extra_info: dict = {},

        reply_from_client: str = None,
        # agent_server, device_info, task, rollout_config, extra_info = {}, reflush_app=True, auto_reply = False, reset_environment=True
        ):
    """
    Evaluate a task on a device using the provided frontend action converter and action function.
    
    """

    # to check task and session_id
    assert (task is not None and session_id is None) or (task is None and session_id is not None), "Either task or session_id must be provided, but not both. task: {}, session_id: {}".format(task, session_id)

    if enable_intermediate_logs == False:
        enable_intermediate_image_caption = False
        enable_intermediate_screenshots = False


    device_wm_size = get_device_wm_size(device_id)

    # init device for the first time
    open_screen(device_id)
    init_device(device_id)

    # if reset_environment, press home key before starting the task
    if reset_environment and session_id is None and task is not None:
        press_home_key(device_id, print_command=True)

    # task, task_type = task, rollout_config['task_type']
    task_type = agent_loop_config['task_type']

    if session_id is None:
        session_id = agent_server.get_session({
            "task": task,
            "task_type": task_type,
            "model_config": agent_loop_config['model_config'],
            "extra_info": extra_info  
        })

        print(f"New Session ID: {session_id}")

        return_log = {
            "session_id": session_id,
            "device_info": {
                "device_id": device_id,
                "device_wm_size": device_wm_size
            },
            "task": task,

            # "rollout_config": rollout_config,
            # "extra_info": extra_info
        }
    else:
        print(f"Continue Session ID: {session_id}")

        return_log = {
            "session_id": session_id,
            "device_info": {
                "device_id": device_id,
                "device_wm_size": device_wm_size
            },
            "reply_from_client": reply_from_client,

            # "rollout_config": rollout_config,
            # "extra_info": extra_info
        }

    delay_after_capture = agent_loop_config.get('delay_after_capture', 2)

    history_actions = []
    

    # The log will contain interleaved: 
    # 1. {agent predicted action}
    # 2. {screenshot if enabled}
    # 3. {image caption (if enabled)}
    # at least, the final action will be returned

    # TODO: to support intermidiate logs and screenshots
    intermidiate_logs = []

    stop_reason = "NOT_STARTED"


    if reply_from_client is not None:
        reply_info = reply_from_client
    else:
        reply_info = None

    action = None

    global_step_idx = 0
    # restart the steps from 0, even continuing an existing session
    for step_idx in range(max_steps):

        # >>> 检查外部暂停信号 <<<
        # >>> 检查外部暂停信号 <<<
        should_pause = check_pause_signal()
        if should_pause:
            print(f"[PAUSED] 检测到暂停信号，暂停任务...")
            stop_reason = "USER_PAUSED"
            break

        if not dectect_screen_on(device_id):
            print("Screen is off, turn on the screen first")
            stop_reason = "MANUAL_STOP_SCREEN_OFF"
            break

        image_path = capture_screenshot(device_id, "tmp_screenshot", print_command=False)

        # current step log use to store intermediate logs if enabled
        current_step_log = {

        }

        image_b64_url = make_b64_url(image_path)

        current_step_log["screenshot_b64_url"] = image_b64_url
        
        if enable_intermediate_image_caption:
            # to start a thread to caption the image while the agent is thinking
            caption_result_container = {}
            caption_thread = threading.Thread(
                target=lambda: caption_current_screenshot(
                    current_task=task,
                    current_image_url=image_b64_url,
                    model_config=agent_loop_config['caption_config'].get('model_config', agent_loop_config['model_config']),
                    result_container=caption_result_container
                )
            )
            caption_thread.start()


        smart_remove(image_path)
        
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

        # assume when reply info is provided, it must be used for current step
        if reply_info is not None:
            print(f"Using reply from client: {reply_info}")
            # 增强提示，确保LLM优先执行用户干预指令，不要继续完成原任务
            payload['observation']['query'] = f"""【紧急用户干预 - 最高优先级】
用户要求：{reply_info}

重要提示：
1. 立即停止当前正在执行的任务
2. 优先执行用户的新指令
3. 不要输出 COMPLETE，除非新指令已完成
4. 根据当前屏幕状态，执行用户的新要求"""
            reply_info = None  # reset after use

        server_return = agent_server.automate_step(payload)
        action, global_step_idx = server_return['action'], server_return['current_step']

        if enable_intermediate_image_caption:
            # wait for caption thread to finish
            caption_thread.join()
            caption_text = caption_result_container.get('caption', '')
            current_step_log['screenshot_caption'] = caption_text
        
        current_step_log['agent_action'] = action
        current_step_log['global_step_idx'] = global_step_idx

        intermidiate_logs.append(current_step_log)

        # check screen status before acting on device
        if not dectect_screen_on(device_id):
            print("Screen is off, turn on the screen first")
            stop_reason = "MANUAL_STOP_SCREEN_OFF"
            break

        #TODO: to replace with the new function
        action = uiTars_to_frontend_action(action)

        if action['action_type'].upper() == "INFO":
            if reply_mode == "auto_reply":
                print(f"AUTO REPLY INFO FROM MODEL!")
                reply_info = auto_reply(image_b64_url, task, action, model_provider=agent_loop_config['model_config']['model_provider'], model_name=agent_loop_config['model_config']['model_name'])
                print(f"info: {reply_info}")

            elif reply_mode == "no_reply":
                print(f"INFO action ignored as per reply_mode=no_reply. Agent may get stuck.")
                reply_info = "Please follow the task and continue. Don't ask further questions."
                # do nothing, agent may get stuck

            elif reply_mode == "manual_reply":
                print(f"EN: Agent asks: {action['value']} Please Reply: ")
                print(f"ZH: Agent 问你: {action['value']} 回复一下：")

                reply_info = input("Your reply:")

                print(f"Replied info action: {reply_info}")

            elif reply_mode == "pass_to_client":
                print(f"Passing INFO action to client for reply.")
                # break the loop and return to client for handling
                stop_reason = "INFO_ACTION_NEEDS_REPLY"
                break

            else:
                raise ValueError(f"Unknown reply_mode: {reply_mode}")

        act_on_device(action, device_id, device_wm_size, print_command=True, reflush_app=reflush_app)

        history_actions.append(action)

        print(f"Step {step_idx+1}/{max_steps} done.\nAction Type: {action['action_type']}, cot: {action.get('cot', '')}\nSession ID: {session_id}\n")

        # print(f"local:{step_idx+1}/global:{global_step_idx}/{max_steps} done. Action: {action}")

        if action['action_type'].upper() in ['COMPLETE', "ABORT"]:
            stop_reason = action['action_type'].upper()
            break

        time.sleep(delay_after_capture)
    
    # if intermediate caption is not enabled, but final caption is enabled, caption the final screenshot
    if enable_final_image_caption and not enable_intermediate_image_caption:
        last_image_b64_url = intermidiate_logs[-1]['screenshot_b64_url']
        caption_text = caption_current_screenshot(
            current_task=task,
            current_image_url=last_image_b64_url,
            model_config=agent_loop_config['caption_config'].get('model_config', agent_loop_config['model_config']),
        )
        intermidiate_logs[-1]['screenshot_caption'] = caption_text
    
    final_action_log = intermidiate_logs[-1] if len(intermidiate_logs) > 0 else {}
    final_action_log = final_action_log.copy()

    if not enable_final_screenshot:
        if 'screenshot_b64_url' in final_action_log:
            del final_action_log['screenshot_b64_url']
    if not enable_final_image_caption:
        if 'screenshot_caption' in final_action_log:
            del final_action_log['screenshot_caption']
    return_log['final_action'] = final_action_log

    new_intermediate_logs = []
    if enable_intermediate_logs:
        for log in intermidiate_logs[:-1]:
            new_log = {}
            if enable_intermediate_screenshots and 'screenshot_b64_url' in log:
                new_log['screenshot_b64_url'] = log['screenshot_b64_url']
            if enable_intermediate_image_caption and 'screenshot_caption' in log:
                new_log['screenshot_caption'] = log['screenshot_caption']
            new_log['agent_action'] = log['agent_action']
            new_log['global_step_idx'] = log['global_step_idx']
            new_intermediate_logs.append(new_log)
    else:
        new_intermediate_logs = None
    
    if new_intermediate_logs and len(new_intermediate_logs) > 1:
        return_log['intermediate_logs'] = new_intermediate_logs  # exclude the last one which is final action
    else:
        if enable_intermediate_logs:
            return_log['intermediate_logs'] = []
        pass

    if stop_reason in ['MANUAL_STOP_SCREEN_OFF', 'INFO_ACTION_NEEDS_REPLY', "NOT_STARTED", "USER_PAUSED"]:
        pass
    elif action is None:
        pass
    elif action['action_type'].upper() == 'COMPLETE':
        stop_reason = "TASK_COMPLETED_SUCCESSFULLY"
    elif action['action_type'].upper() == 'ABORT':
        stop_reason = "TASK_ABORTED_BY_AGENT"
    elif step_idx == max_steps - 1:
        stop_reason = "MAX_STEPS_REACHED"


    return_log['stop_reason'] = stop_reason
    return_log['local_step_idx'] = step_idx + 1
    return_log['global_step_idx'] = global_step_idx

    # return_log['intermediate_logs'] = intermidiate_logs

    # TODO: to support last screenshot and image caption
    # return_log['last_logs'] = 

    print(f"Session {session_id} done. Stop reason: {stop_reason} in {len(history_actions)} steps.")
    # print(f"Task {task} done in {len(history_actions)} steps. Session ID: {session_id}")

    return return_log


