from fastmcp import FastMCP

import sys
if "." not in sys.path:
    sys.path.append(".")

from copilot_front_end.mobile_action_helper import list_devices, get_device_wm_size
from copilot_agent_server.local_server import LocalServer

from copilot_agent_client.pu_client import evaluate_task_on_device

import yaml

from typing import Annotated
from pydantic import Field

from mcp_server.mcp_backend_implements import (
    get_device_list,
    get_screenshot,
    execute_task,
)

mcp = FastMCP(name="Gelab-MCP-Server", instructions="""
This MCP server provides tools to interact with connected mobile devices using a GUI agent.               
              """
            )


@mcp.tool
def list_connected_devices() -> list:
    """
        List all connected mobile devices.
        
        Returns:
            list: A list of connected device IDs.
    """
    devices = get_device_list()
    print("Connected devices:", devices)
    return devices


@mcp.tool
def ask_agent_start_new_task(

    device_id: Annotated[str, Field(description="ID of the device to perform the task on. listed by list_connected_devices tool.")],

    task: Annotated[str | None, Field(description="The task that the agent needs to perform on the mobile device. if this is not None, the agent will try to perform this task. if None, the session_id must be provided to continue the previous session.")],
    
    # reset_environment: Annotated[bool, Field(description="Whether to reset the environment before executing the task, close current app, and back to home screen. If you want to execute a independent task, set this to True will make it easy to execute. If you want to continue the previous session, set this to False.")] = False,

    max_steps: Annotated[int, Field(description="Maximum number of steps the agent can take to complete the task.")] = 20,

    # session_id: Annotated[str | None, Field(description="Optional, session ID must provide when the last task endwith INFO action and you want to reply, the session id and device id and the reply from client must be provided.")] = None,

    # When the INFO action is called, how to handle it.
    # 1. "auto_reply": the INFO action will be handled automatically by calling the caption model to generate image captions.
    # 2. "no_reply": the INFO action will be ignored. THE AGENT MAY GET STUCK IF THE INFO ACTION IS IGNORED.
    # 3. "manual_reply": the INFO action will cause an interruption, and the user needs to provide the reply manually by input things in server's console.
    # 4. "pass_to_client": the INFO action will be returned to the MCP client to handle it. 
#     reply_mode: Annotated[str, Field(description='''
#         How to handle the INFO action during task execution.
        
#         Options:
#             - "auto_reply": Automatically generate image captions for INFO actions.
#             - "no_reply": Ignore INFO actions (may cause the agent to get stuck).
#             - "manual_reply": Interrupt and require user input for INFO actions.
#             - "pass_to_client": Pass INFO actions to the MCP client for handling.
# ''')] = "auto_reply",

    # reply_from_client: Annotated[str | None, Field(description="If the last task is ended with INFO action, and you want to give GUI agent a reply, provide the reply here. If you do so, you must provide last session id and last device id.")] = None,
) -> dict:

    """
# Ask GUI Agent to start performing a new task on a connected device.

Ask the GUI agent to perform the specified task on a connected device.
The GUI Agent can be able to understand natural language instructions and interact with the device accordingly.
The agent will be able to execute a high-level task description，if you have any additional requirements, write them down in detail at tast string.
This function will reset the environment before executing the task, close current app, and back to home screen.

if you have 

## The agent has the below limited capabilities:

1. The task must be related to an app that is already installed on the device. for example, "打开微信，帮我发一条消息给张三，说今天下午三点开会"; "帮我在淘宝上搜索一款性价比高的手机，并加入购物车"; "to purchase an ea on Amazon".

2. The task must be simple and specific. for example, "do yyy in xxx app"; "find xxx information in xxx app". ONE THING AT ONE APP AT A TIME.

3. The agent may not be able to handle complex tasks that require multi-step reasoning or planning. for example. You may need to break down complex tasks into simpler sub-tasks and ask the agent to perform them sequentially. For example, instead of asking the agent to "plan a trip to Paris for xxx", you can ask it to "search for flights to Paris on xxx app", "find hotels in Paris on xxx app", make the plan yourself and ask agent to "sent the plan to xxx via IM app like wechat".

4. The agent connot accept multimodal inputs now. if you want to provide additional information like screenshot captions, please include them in the task description.

## Usage guidance：

1. you should never directly ask an Agent to pay or order anything. If user want to make a purchase, you should ask agent to stop brfore ordering/paying, and let user to order/pay.

2. tell the agent, if human verification is appeared during the task execution, the agent should ask Client. when the you see the INFO, you should ask user to handle the verification manually. after user says "done", you can continue the task with the session_id and device_id and ask the agent to continue in reply_from_client.

3. IF the last agentic call is failed or you want to perform a new task in different app, you should always use this function to start a new task, so that the environment will be reset before executing the task.

Returns:
    dict: Execution log containing details of the task execution.
    with keys including
        - device_info: Information about the device used for task execution.
        - final_action: The final action taken by the agent to complete the task.
        - global_step_idx: The total number of steps taken during the task execution.
        - local_step_idx: The number of steps taken in the current session.
        - session_id: The session ID for maintaining context across multiple tasks.
        - stop_reason: The reason for stopping the task execution (e.g., TASK_COMPLETED_SUCCESSFULLY).
        - task: The original task description provided to the agent.
    """

    reply_mode = "pass_to_client"

    # if task is not None:
    #     assert session_id is None, "If task is provided, session_id must be None."
    #     # New task, so reset_environment is True
    #     reset_environment = True
    # else:
    #     assert session_id is not None, "If task is None, session_id must be provided to continue the previous session."
    #     # Continuing previous session, so reset_environment is False
    #     reset_environment = False

    reset_environment = True
    

    return_log = execute_task(
        device_id=device_id,

        task=task,

        reset_environment=reset_environment,
        max_steps=max_steps,

        # enable_intermediate_logs=False,
        # enable_intermediate_image_caption=False,
# 
        enable_intermediate_logs=True,
        # enable_intermediate_image_caption=False,
        enable_intermediate_image_caption=True,

        enable_intermediate_screenshots=False,

        enable_final_screenshot=False,
        # enable_final_image_caption=False,
        enable_final_image_caption=True,

        reply_mode=reply_mode,

        session_id=None,
        # session_id=session_id,
        reply_from_client=None,
        # reply_from_client=reply_from_client,


    )

    return return_log


# @mcp.tool
# def ask_agent_continue(

#     device_id: Annotated[str, Field(description="ID of the device to perform the task on. listed by list_connected_devices tool.")],

#     task: Annotated[str | None, Field(description="The task that the agent needs to perform on the mobile device. if this is not None, the agent will try to perform this task. if None, the session_id must be provided to continue the previous session.")],
    
#     # reset_environment: Annotated[bool, Field(description="Whether to reset the environment before executing the task, close current app, and back to home screen. If you want to execute a independent task, set this to True will make it easy to execute. If you want to continue the previous session, set this to False.")] = False,

#     max_steps: Annotated[int, Field(description="Maximum number of steps the agent can take to complete the task.")] = 20,

#     session_id: Annotated[str | None, Field(description="Optional, session ID must provide when the last task endwith INFO action and you want to reply, the session id and device id and the reply from client must be provided.")] = None,

#     # When the INFO action is called, how to handle it.
#     # 1. "auto_reply": the INFO action will be handled automatically by calling the caption model to generate image captions.
#     # 2. "no_reply": the INFO action will be ignored. THE AGENT MAY GET STUCK IF THE INFO ACTION IS IGNORED.
#     # 3. "manual_reply": the INFO action will cause an interruption, and the user needs to provide the reply manually by input things in server's console.
#     # 4. "pass_to_client": the INFO action will be returned to the MCP client to handle it. 
# #     reply_mode: Annotated[str, Field(description='''
# #         How to handle the INFO action during task execution.
        
# #         Options:
# #             - "auto_reply": Automatically generate image captions for INFO actions.
# #             - "no_reply": Ignore INFO actions (may cause the agent to get stuck).
# #             - "manual_reply": Interrupt and require user input for INFO actions.
# #             - "pass_to_client": Pass INFO actions to the MCP client for handling.
# # ''')] = "auto_reply",

#     # reply_from_client: Annotated[str | None, Field(description="If the last task is ended with INFO action, and you want to give GUI agent a reply, provide the reply here. If you do so, you must provide last session id and last device id.")] = None,
# ) -> dict:

#     """
# # Ask GUI Agent to continue performing a task on a connected device, using previous context.

# Ask the GUI agent to perform the specified task on a connected device.
# The GUI Agent can be able to understand natural language instructions and interact with the device accordingly.
# The agent will be able to execute a high-level task description，if you have any additional requirements, write them down in detail at tast string.
# This function will **NOT** reset the environment before executing the task, so that the agent can continue the previous session.

# if you have 

# ## The agent has the below limited capabilities:

# 1. The task must be related to an app that is already installed on the device. for example, "打开微信，帮我发一条消息给张三，说今天下午三点开会"; "帮我在淘宝上搜索一款性价比高的手机，并加入购物车"; "to purchase an ea on Amazon".

# 2. The task must be simple and specific. for example, "do yyy in xxx app"; "find xxx information in xxx app". ONE THING AT ONE APP AT A TIME.

# 3. The agent may not be able to handle complex tasks that require multi-step reasoning or planning. for example. You may need to break down complex tasks into simpler sub-tasks and ask the agent to perform them sequentially. For example, instead of asking the agent to "plan a trip to Paris for xxx", you can ask it to "search for flights to Paris on xxx app", "find hotels in Paris on xxx app", make the plan yourself and ask agent to "sent the plan to xxx via IM app like wechat".

# 4. The agent connot accept multimodal inputs now. if you want to provide additional information like screenshot captions, please include them in the task description.

# ## Usage guidance：

# 1. you should never directly ask an Agent to pay or order anything. If user want to make a purchase, you should ask agent to stop brfore ordering/paying, and let user to order/pay.

# 2. tell the agent, if human verification is appeared during the task execution, the agent should ask Client. when the you see the INFO, you should ask user to handle the verification manually. after user says "done", you can continue the task with the session_id and device_id and ask the agent to continue in reply_from_client.

# 3. IF the last agentic call is successful or the last action is INFO or the new task is related to the previous task, you can use this function to continue the task, so that the agent can finish the task faster by leveraging the previous context.
#     dict: Execution log containing details of the task execution.
#     with keys including
#         - device_info: Information about the device used for task execution.
#         - final_action: The final action taken by the agent to complete the task.
#         - global_step_idx: The total number of steps taken during the task execution.
#         - local_step_idx: The number of steps taken in the current session.
#         - session_id: The session ID for maintaining context across multiple tasks.
#         - stop_reason: The reason for stopping the task execution (e.g., TASK_COMPLETED_SUCCESSFULLY).
#         - task: The original task description provided to the agent.
#     """

#     reply_mode = "pass_to_client"

#     # if task is not None:
#     #     assert session_id is None, "If task is provided, session_id must be None."
#     #     # New task, so reset_environment is True
#     #     reset_environment = True
#     # else:
#     #     assert session_id is not None, "If task is None, session_id must be provided to continue the previous session."
#     #     # Continuing previous session, so reset_environment is False
#     #     reset_environment = False

#     reset_environment = False
    

#     return_log = execute_task(
#         device_id=device_id,

#         task=task,

#         reset_environment=reset_environment,
#         max_steps=max_steps,

#         # enable_intermediate_logs=False,
#         # enable_intermediate_image_caption=False,
# # 
#         enable_intermediate_logs=True,
#         enable_intermediate_image_caption=True,

#         enable_intermediate_screenshots=False,

#         enable_final_screenshot=False,
#         # enable_final_image_caption=False,
#         enable_final_image_caption=True,

#         reply_mode=reply_mode,

#         # session_id=None,
#         session_id=session_id,
#         reply_from_client=None,
#         # reply_from_client=reply_from_client,


#     )

#     return return_log


with open("mcp_server_config.yaml", "r") as f:
    mcp_server_config = yaml.safe_load(f)

mcp.run(transport="http", port=mcp_server_config['server_config'].get("mcp_server_port", 8702))