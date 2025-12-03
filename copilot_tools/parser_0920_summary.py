import sys
import json
import os
import re

from collections import OrderedDict

import jsonlines
from megfile import smart_open

current_file = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file)
sys.path.append(current_dir)

if "." not in sys.path:
    sys.path.append(".")

# from tools.prompt_tools import messages2sft

from copy import deepcopy


task_define_prompt = """你是一个手机 GUI-Agent 操作专家，你需要根据用户下发的任务、手机屏幕截图和交互操作的历史记录，借助既定的动作空间与手机进行交互，从而完成用户的任务。
请牢记，手机屏幕坐标系以左上角为原点，x轴向右，y轴向下，取值范围均为 0-1000。

在 Android 手机的场景下，你的动作空间包含以下9类操作，所有输出都必须遵守对应的参数要求：
1. CLICK：点击手机屏幕坐标，需包含点击的坐标位置 point。
例如：action:CLICK\tpoint:x,y
2. TYPE：在手机输入框中输入文字，需包含输入内容 value、输入框的位置 point。
例如：action:TYPE\tvalue:输入内容\tpoint:x,y
3. COMPLETE：任务完成后向用户报告结果，需包含报告的内容 value。
例如：action:COMPLETE\treturn:完成任务后向用户报告的内容
4. WAIT：等待指定时长，需包含等待时间 value（秒）。
例如：action:WAIT\tvalue:等待时间
5. AWAKE：唤醒指定应用，需包含唤醒的应用名称 value。
例如：action:AWAKE\tvalue:应用名称
6. INFO：询问用户问题或详细信息，需包含提问内容 value。
例如：action:INFO\tvalue:提问内容
7. ABORT：终止当前任务，仅在当前任务无法继续执行时使用，需包含 value 说明原因。
例如：action:ABORT\tvalue:终止任务的原因
8. SLIDE：在手机屏幕上滑动，滑动的方向不限，需包含起点 point1 和终点 point2。
例如：action:SLIDE\tpoint1:x1,y1\tpoint2:x2,y2
9. LONGPRESS：长按手机屏幕坐标，需包含长按的坐标位置 point。
例如：action:LONGPRESS\tpoint:x,y
"""

def make_status_prompt(task, current_image, hints, summary_history="", user_comment=""):

    if len(hints) == 0:
        hint_str = ""
    else:
        hint_str = "\n".join([f"- {hint}" for hint in hints])
        hint_str = f"### HINT：\n{hint_str}\n"

    if user_comment == "":
        history_display = summary_history if summary_history.strip() else "暂无历史操作"
    else:
        history_display = summary_history + user_comment if summary_history.strip() else "暂无历史操作"

    
    status_conversation = [
        {
            "type": "text",
            "text": f'''
已知用户任务为：{task}
已知已经执行过的历史动作如下：{history_display}
当前手机屏幕截图如下：
'''
        },
        {
            "type": "image_url",
            "image_url": {"url": current_image}
        },
        {
            "type": "text",
            "text": f'''
在执行操作之前，请务必回顾你的历史操作记录和限定的动作空间，先进行思考和解释然后输出动作空间和对应的参数：
1. 思考（THINK）：在 <THINK> 和 </THINK> 标签之间。
2. 解释（explain）：在动作格式中，使用 explain: 开头，简要说明当前动作的目的和执行方式。
在执行完操作后，请输出执行完当前步骤后的新历史总结。
输出格式示例：
<THINK> 思考的内容 </THINK>
explain:解释的内容\taction:动作空间和对应的参数\tsummary:执行完当前步骤后的新历史总结
'''
        }
    ]

    return status_conversation


class Parser0920Summary():
    def __init__(self, *args, **kwargs):
        # super().__init__(*args, **kwargs)
        pass

    def action2action(self, action):
        # assert single actions
        assert "action" in action or "action_type" in action, f"action {action} should have action or action_type field"
        assert "explain" in action, f"action {action} should have explain field"
        assert "cot" in action, f"action {action} should have cot field"

        explain = action['explain']
        cot = action['cot']
        summary = action.get('summary', '')  
        action_type = action.get('action_type', action.get('action', None))

        return_action = OrderedDict(
            {
                "cot": cot,
                "explain": explain,
                "action": action_type,
                "summary": summary
            }
        )


        if action_type == "TYPE":
            # assert "is_keyboard" in action or "keyboard_exists" in action, f"action {action} should have is_keyboard or keyboard_exists field"
            assert "value" in action, f"action {action} should have value field"
            # assert "point" in action, f"action {action} should have point field"
            
            keyboard_exists = action.get("is_keyboard", action.get("keyboard_exists", False))
            if type(keyboard_exists) == str:
                keyboard_exists = keyboard_exists.lower() == "true"

            # point = action['point'] 
            value = action['value']

            return_action.update({
                "value": value, 
                # "point": point, 
                # "keyboard_exists": keyboard_exists
            })

        elif action_type == "CLICK":
            assert "point" in action, f"action {action} should have point field"
            point = action['point']
            
            return_action.update({
                "point": point
            })

        elif action_type == "AWAKE":
            assert "value" in action, f"action {action} should have value field"
            value = action['value']

            return_action.update({
                "value": value
            })

        elif action_type == "INFO":
            assert "value" in action, f"action {action} should have value field"
            value = action['value']

            return_action.update({
                "value": value
            })

        elif action_type == "WAIT":
            assert "value" in action, f"action {action} should have value field"
            value = action['value']

            return_action.update({
                "value": value
            })

        elif action_type == "COMPLETE":
            assert "return" in action, f"action {action} should have return field"
            return_value = action['return']

            return_action.update({
                "return": return_value
            })

        
        elif action_type == "ABORT":

            pass

        
        elif action_type == "SLIDE":
            assert "point1" in action, f"action {action} should have point1 field"
            assert "point2" in action, f"action {action} should have point2 field"
            point1 = action['point1']
            point2 = action['point2']

            return_action.update({
                "point1": point1, 
                "point2": point2
            })


        elif action_type == "LONGPRESS":
            assert "point" in action, f"action {action} should have point field"
            point = action['point']

            return_action.update({
                "point": point
            })
        
        else:
            raise ValueError(f"Unknown action type {action_type} in action {action}")

        return return_action

    def action2str(self, actions):
        assert (type(actions) == list and len(actions) == 0) or type(actions) == dict or type(actions) == OrderedDict, f"actions {actions} should be a list or a dict; only one action is supported"

        if type(actions) == dict or type(actions) == OrderedDict:
            actions = [actions]
        # action = actions[0]
        action = deepcopy(actions[0])

        # assert action type field
        if "action" in action and "action_type" in action:
            assert action['action'] == action['action_type'], f"action {action} should have same action and action_type field"
            assert len(action['action']) > 0, f"action {action} should have non-empty action and action_type field"
            del action['action_type']

        action = self.action2action(action)

        kvs = []
        for key, value in action.items():
            key = key.strip()

            if key in ['cot']:
                continue
        
            if type(value) == list:
                value = ",".join([str(v).strip() for v in value])
            elif type(value) == bool:
                value = str(value).lower()
            elif type(value) == int or type(value) == float:
                value = str(value)
            else:
                value = value.replace("\n", "").replace("\t", "").strip()

            kvs.append(f"{key}:{value}")

        action_str = f"<THINK> {action['cot']} </THINK>\n" + "\t".join(kvs) + "\n"
        return action_str
    

    def str2action(self, command_str):
        command_str = command_str.strip()
        
        # Normalize THINK tags: fix typos, case, and spacing
        command_str = (
            command_str
            .replace("<TINK>", "<THINK>").replace("</TINK>", "</THINK>")
            .replace("<think>", "<THINK>").replace("</think>", "</THINK>")
        )
        command_str = re.sub(r"<\s*/?THINK\s*>", lambda m: "<THINK>" if "/" not in m.group() else "</THINK>", command_str, flags=re.IGNORECASE)
        
        # Extract CoT and key-value parts
        # Expected format: <THINK> cot </THINK>\nexplain:xxx\taction:xx\tvalue:xxx\tsummary:xxx
        try:
            cot_part = command_str.split("<THINK>")[1].split("</THINK>")[0].strip()
            kv_part = command_str.split("</THINK>")[1].strip()
        except IndexError:
            print(f"[Parser Warning] Missing <THINK> tags, treating entire response as kv")
            kv_part = command_str
            cot_part = ""

        action = OrderedDict()
        action['cot'] = cot_part
        
        # FIX:issue 13
        # Error split by \n, should split by tab separator 
        kvs = [kv.strip() for kv in kv_part.split("\t") if kv.strip()]

        for kv in kvs:
            if ":" not in kv:
                continue

            key = kv.split(":", 1)[0].strip()
            value = kv.split(":", 1)[1].strip()

            if key == "action":
                action['action'] = value
            elif key == "summary":
                action['summary'] = value
            elif "point" in key:
                # Parse point format: "x,y" or "x y"
                try:
                    # Replace comma with space for unified processing
                    coords = value.replace(",", " ").split()
                    if len(coords) < 2:
                        raise ValueError(f"Expected 2 coordinates, got {len(coords)}")
                    
                    x, y = int(coords[0]), int(coords[1])
                    action[key] = [x, y]
                    
                except (ValueError, IndexError) as e:
                    raise ValueError(
                        f"[Parser Error] Failed to parse point '{value}' for key '{key}': {str(e)}. "
                        f"Expected format: 'x,y' or 'x y' with integer values"
                    ) from e
            else:
                action[key] = value

        return action

    def env2messages4ask(self, task, environments, actions, markov_mode=False, return_sft = False, hints = [], ) -> list:

        assert len(environments) > 0, f"environments {environments} should not be empty"
        assert len(environments) - 1 == len(actions), f"environments {environments} should be one more than actions {actions}"
        
        # Use the summary of the last action as the historical summary
        summary_history = ""
        if len(actions) > 0:
            last_action = self.action2action(actions[-1])
            summary_history = last_action.get('summary', '')

        current_env = environments[-1]

        user_comment = ""
        if len(current_env['user_comment']) > 0:
            user_comment = "用户回复说： "+ current_env['user_comment'].strip()

        conversations = [
            {
                "type": "text",
                "text": task_define_prompt
            }
        ] + make_status_prompt(
            task, 
            current_env['image'], 
            hints,
            summary_history,
            user_comment
        )

        messages = [
            {
                "role": "user",
                "content": conversations
            }
        ]
        # print(f"=============================================messages: \n\n{messages}\n=============================================")
        print(f"{'='*45}\nmessages:\n{messages}\n{'='*45}")

        if return_sft:
            sft = messages2sft(messages)
            return messages, sft
        else:
            return messages

def tkj_action_transformer(action, width: int, height: int):
    ret_dict = {}

    assert "action_type" in action or "action" in action, f"action {action} should have action_type or action field"

    if "action_type" in action:
        action_type = action['action_type']
    if "action" in action:
        action_type = action['action']
    
    action['action_type'] = action_type
    action['action'] = action_type
        
    # try:
    if True:
        ret_dict['explain'] = action['explain']
        ret_dict['cot'] = action.get('cot', '')
        
        # compatible with new and old field names
        ret_dict['action_type'] = action.get('action_type') or action.get('action')
        if "search_type" in action:
            ret_dict['search_type'] = action['search_type']

        # compatible with different field names of keyboard
        if "keyboard_exists" in action:
            ret_dict['keyboard_exists'] = action['keyboard_exists']
        elif "is_keyboard" in action:
            ret_dict['keyboard_exists'] = action['is_keyboard']

        if "is_auto_close" in action:
            ret_dict["is_auto_close"] = action["is_auto_close"]

        if "point" in action:
            ret_dict['coordinates'] = action['point']

        for key in ["point", "point1", "point2"]:
            if key in action:
                ret_dict[key] = action[key]

        if "value" in action:
            ret_dict['text'] = action['value']
        if action['action_type'] == "WAIT":
            ret_dict['duration'] = action['value']
            if "功能类" in action['explain']:
                ret_dict["is_auto_close"] = True

            if "close_reasons" in action:
                ret_dict["close_reasons"] = [{
                    "reason": reason["reason"],
                    "bbox": reason["bbox"],
                } for reason in action["close_reasons"]]
            else:
                ret_dict["close_reasons"] = []
        if action['action_type'] == "TYPE":
            if "point" in action:
                ret_dict['coordinates'] = action['point']
            else:
                ret_dict['coordinates'] = action['point']
        # if ['action_type'] == "SCROLL":
        #     ret_dict['point1'] = denormalize_point(action['point1'], width, height)
        #     ret_dict['point2'] = denormalize_point(action['point2'], width, height)
        # if action['action_type'] == "LONGPRESS":
        #     ret_dict['point'] = denormalize_point(action['point'], width, height)
    # except Exception as e:
        # ret_dict["action_type"] = "ABORT"
        # ret_dict["abort_reason"] = "operation parameter parsing exception"

    return ret_dict


if __name__ == "__main__":
    # test_case = [
    #     "<think>xxx</think>",
    #     "<think>xxx</think>\nexplain:xxx\taction:xx\tvalue:xxx\tsummary:xxx",
    #     "<think>xxx</think>\nexplain:xxx\taction:xx\tvalue:xxx\tsummary:xxx",
    #     "<think>xxx</think>\nexplain:xxx\taction:xx\tvalue:xxx\tsummary:xxx",
    #     "< think>xxx</think>\nexplain:xxx\taction:xx\tvalue:xxx\tsummary:xxx",
    #     "</THINK>xxx</THINK>\nexplain:xxx\taction:xx\tvalue:xxx\tsummary:xxx",
    #     "<THINK>xxx</THINK>\nexplain:xxx\taction:xx\tvalue:xxx\tsummary:xxx",
    # ]
    # for command_str in test_case:
    #     action = str2action(command_str)
    #     print(f"action: {action}")
    pass
            
