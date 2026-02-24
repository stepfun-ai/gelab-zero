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

from datetime import datetime

if "." not in sys.path:
    sys.path.append(".")

# from tools.prompt_tools import messages2sft

from copy import deepcopy

default_skill = '''
# Role: 手机 GUI-Agent 操作专家
Version: 1.8

你是一个手机 GUI-Agent 操作专家，你需要根据用户下发的任务、手机屏幕截图和交互操作的历史记录，借助既定的动作空间与手机进行交互，从而完成用户的任务。

## 基础设定
请牢记，手机屏幕坐标系以左上角为原点：
- x轴向右，取值范围 0-1000
- y轴向下，取值范围 0-1000

## 行动原则

1. **【最高优先级】强制屏幕状态朗读**：
   - 在进行思考（Thought）时，**必须**用明确的语言“读出来”当前屏幕的状态。
   - **强调一：首先必须识别并读出当前页面的标题（Title）或顶部导航栏文字，确认我在哪。**
   - **强调二：不要忽略页面标题！思考的第一步就是确认页面标题是什么。**
   - **强调三：请务必在思考中写下“当前页面标题是：[标题内容]”，以此作为环境感知的基点。**

2. **独立状态验证与预期偏差检查（新增）**：
   - 页面随时可能因**弹窗广告、人类意外干预、工程异常**等原因发生意外变化。
   - **切勿假设**当前页面就是你上一步操作后的自然结果。
   - 在思考（Thought）的**开头**，你必须进行验证：
     1. **判断**：当前页面状态是否符合上一步操作的预期？
     2. **决策**：如果遇到突发弹窗或页面被意外切换，必须优先处理异常（如关闭弹窗、返回正确页面），而不是盲目继续执行原定计划。

3. **重要信息记录（Take Note）**：
   - **必须善用 Note 字段**。在完成当前步骤的 Summary 之后，你必须检查屏幕上是否有对后续任务有用的关键信息（如：搜索到的具体商品名、价格、订单号、会议时间、联系人姓名等）。
   - 如果有，**必须**将这些信息提取并记录在 `note` 字段中，以便后续步骤查阅，防止信息丢失。

4. **输入前置条件检查**：
   - **键盘未唤醒时禁止打字**。如果你想输入文字，首先检查屏幕下方是否有键盘弹起。
   - 如果没有键盘，你必须先**点击（Tap）目标输入框**，等待键盘唤醒后，再在下一步进行输入操作。

5. **明确操作意图描述**：
   - 在解释（Explain）或描述你的下一步行动时，**必须明确指出你想点击或操作的具体对象是什么**。
   - 例如：要说“点击‘xx’按钮”或“点击标题为‘yy’的区域”。

6. **任务流转与状态重置**：
   - 在 APP 内部执行任务时，如果某个子任务（Sub-task）已经执行完毕，**请尽量操作返回到该 APP 的首页/主界面**，然后再开始执行下一个子任务。这有助于避免页面层级过深导致的路径混乱。

7. **操作对象锁定**：
   - 如果输入包含多张屏幕截图，你**必须且只能**基于**最后一张图**（即最新的屏幕状态）进行分析和操作。

8. **操作生效判断（失败检测）**：
   - 在思考时，必须对比当前截图与上一张截图。
   - **如果最后两张图完全一样（或高度相似）**，说明上一步操作可能未生效或指令失败。
   - 此时必须在思考中显式判断：“检测到画面未变化，上一步动作可能失败”，并尝试调整策略或重试。

9. **记录追踪**：你需要明确记录自己上一次的 action。如果是滑动操作，连续滑动不能超过 5 次。

10. **指令优先级**：你需要严格遵循用户的指令。如果你和用户进行过多轮对话，必须优先遵守最后一轮的指令。

11. **安全边界**：绝对禁止给用户直接下单支付。

## 指令格式
User 会在后续交互中告诉你需要遵循的具体指令格式。

'''

task_define_prompt = """

# 用户给你的任务：
{task}

当前时间是{current_time}

# Action Space:

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



class Parser0920SummaryAdv():
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

        action_str = json.dumps(actions, ensure_ascii=False)

        return action_str
    

    def str2action(self, command_str):
        command_str = command_str.strip()
        
        # assert  "</think>" in command_str, f"command_str {command_str} should contain <think> and </think> tags"
        # assert "<THINK>" in command_str and "</THINK>" in command_str, f"command_str {command_str} should contain <THINK> and </THINK> tags"

        if "</think>" not in command_str:
            cot_small = ""
            # raise ValueError(f"command_str {command_str} should contain <think> and </think> tags")
        else:
            cot_small = command_str.split("<think>")[-1].split("</think>")[0].strip()
        
        # cot_big = command_str.split("<THINK>")[1].split("</THINK>")[0].strip()



        action = OrderedDict()
        # action['cot'] = cot_part
        
        action['cot'] = cot_small
        # action['cot'] = cot_big

        kv_part = command_str.split("</think>")[-1].strip()
        
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

    def env2messages4ask(self, task, environments, actions, skill = default_skill, keep_last_k_images = 1) -> list:

        assert len(environments) > 0, f"environments {environments} should not be empty"
        assert len(environments) - 1 == len(actions), f"environments {environments} should be one more than actions {actions}"
        
        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": skill
                    }
                ]
            },
        ]


        history_content = [
            {
                "type": "text",
                "text": task_define_prompt.format(task=task, current_time=datetime.now().strftime("%Y年%m月%d日")) + "\n\n" + "以下是你之前的操作历史回顾："
            }
        ]

        for idx, (env, act) in enumerate(zip(environments, actions + [None])):
            
            # environment_content = f"这是第{idx}步的环境信息："

            if act is not None: 
                if"cot" in act:
                    del act['cot']

                if "point" in act:
                    del act['point']
                if "point1" in act:
                    del act['point1']
                if "point2" in act:
                    del act['point2']

                if "action_type" in act:
                    del act['action_type']

            user_comment = env.get('user_comment', '').strip()
            if len(user_comment) > 0:
                user_comment = f"用户回复说：\n---------\n{user_comment}\n---------\n用户回复结束\n\n"
            else:
                user_comment = ""
                # user_comment = "用户没有回复任何内容。"   
            
            pic_comment = f"当前手机屏幕截图如下：\n" if idx >= len(environments) - keep_last_k_images else ""

            history_content.append(
                {
                    "type": "text",
                    "text": f"这是第{idx}步的环境信息：\n" + user_comment + pic_comment
                }
            )

            if idx >= len(environments) - keep_last_k_images:
                history_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": env['image']}
                    }
                )

            if act is not None:
                action_comment = f"这一步的动作是：{json.dumps(act, ensure_ascii=False)}\n\n"
            else:
                action_comment = "\n\n"

            history_content.append(
                {
                    "type": "text",
                    "text": f"这是第{idx}步的环境信息结束。" + action_comment
                }
            )

        history_content.append(
            {
                "type": "text",
                "text": '''
在执行操作之前，请务必回顾你的历史操作记录和限定的动作空间，先进行思考和解释然后输出动作空间和对应的参数：
1. 思考：你得想。我需要你验证、指认，当前操作是否符合你上一次操作的预期。是否没达成目标？
2. 解释（explain）：在动作格式中，使用 explain: 开头，简要说明当前动作的目的和执行方式。

思考中体现：
上一步（如有），预期屏幕发生xx 变化，我确认｜否认，发生了xx变化。我要做xx 动作，预期屏幕变化是xx。
并写到explain 字段中。

在执行完操作后，请输出执行完当前步骤后的新历史总结。
输出格式示例：
note:当前页面总结出的关键信息，你看到了什么？所有信息都应该写在这里，要详细，得多写。\texplain:解释的内容\taction:动作空间和对应的参数\n


思考完之后以note 开头。

'''
            }
        )
        messages.append(
            {
                "role": "user",
                "content": history_content
            }
        )

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
            
