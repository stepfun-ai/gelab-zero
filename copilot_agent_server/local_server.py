import json
import sys
import os

from copilot_agent_server.base_server import BaseCopilotServer

from copilot_agent_server.local_server_logger import LocalServerLogger

from tools.image_tools import read_from_url, make_b64_url

from copilot_agent_server.parser_factory import get_parser

from tools.ask_llm_v2 import ask_llm_anything

from copy import deepcopy

import time

class LocalServer(BaseCopilotServer):
    
    def __init__(self, server_config: dict):
        super().__init__()


        self.server_config = server_config

        # assert log related config
        assert "log_dir" in server_config, "server_config must contain 'log_dir'"
        assert "image_dir" in server_config, "server_config must contain 'image_dir'"

        self.debug = server_config.get("debug", False)
        

    
    def get_session(self, payload: dict) -> str:
        """
        Get a new session ID.
        """
        # For local server, we can generate a random session ID or use a timestamp-based ID.
        import uuid
        session_id = str(uuid.uuid4())

        logger = LocalServerLogger({
            "log_dir": self.server_config["log_dir"],
            "image_dir": self.server_config["image_dir"],
            "session_id": session_id
        })

        assert "task" in payload, "payload must contain 'task'"
        assert "task_type" in payload, "payload must contain 'task_type' indicating different parsers"
        assert "model_config" in payload, "payload must contain 'model_config'"

        model_config = payload["model_config"]
        assert "model_name" in model_config, "model_config must contain 'model_name'"

        extra_info = payload.get('extra_info', {})

        message_to_log = {
            "log_type": "session_start",
            "task": payload["task"],
            "task_type": payload["task_type"],
            "model_config": payload["model_config"],

            "extra_info": extra_info
        }

        logger.log_str(message_to_log, is_print=self.debug)

        return session_id

    def automate_step(self, payload: dict) -> dict:
        """
        Automate a step in the Copilot service.
        """

        assert "session_id" in payload, "payload must contain 'session_id'"
        session_id = payload["session_id"]

        logger = LocalServerLogger({
            "log_dir": self.server_config["log_dir"],
            "image_dir": self.server_config["image_dir"],
            "session_id": session_id
        })

        logs = logger.read_logs()
        assert len(logs) > 0, f"No logs found for session_id {session_id}"
        current_ste = len(logs) - 1

        config_log = logs[0]
        config_dict = config_log['message']


        task_type = config_dict['task_type']
        model_config = config_dict['model_config']
        task = config_dict['task']

        # current image 
        assert "observation" in payload, "payload must contain 'observation'"
        observation = payload['observation']

        image_url = observation['screenshot']['image_url']['url']
        image = read_from_url(image_url)
        image_inner_url = logger.save_image(image, f"step_{current_ste+1}")

        query = observation.get('query', '')


        def get_envs_acts_from_logs(logs):
            environments = []
            actions = []
            for log in logs[1:]:
                msg = log['message']
                assert "environment" in msg, "log message must contain 'environment'"
                assert "action" in msg, "log message must contain 'action'"
                environments.append(msg['environment'])
                actions.append(msg['action'])

            return environments, actions

        environments, actions = get_envs_acts_from_logs(logs)

        current_env = {
            "image": image_inner_url,
            "user_comment": query
        }
        environments.append(current_env)

        
        parser = get_parser(task_type)

        messages_to_ask = parser.env2messages4ask(
            task = task,
            environments = environments,
            actions = actions,
        )

        asked_messages = deepcopy(messages_to_ask)

        model_name = model_config['model_name']
        model_provider = model_config.get('model_provider', 'eval')

        args = model_config.get('args', {
            "temperature": 0.1,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "max_tokens": 512,
        })

        image_preprocess = model_config.get('image_preprocess', None)

        if image_preprocess is not None:
            if "target_image_size" in image_preprocess:
                target_image_size = image_preprocess["target_image_size"]
                
                def resize_image_in_messages(messages, target_size):
                    for msg in messages:
                        if type(msg['content']) == str:
                            continue
                        assert type(msg['content']) == list
                        for content in msg['content']:
                            if content['type'] == "text":
                                continue
                            assert content['type'] == "image_url" 

                            image_url = content['image_url']['url']

                            image_resize_url = make_b64_url(image_url, resize_config={
                                "is_resize": True,
                                "target_image_size": target_size
                            })

                            content['image_url']['url'] = image_resize_url
                    
                resize_image_in_messages(messages_to_ask, target_image_size)
                print(f"Resized images to {target_image_size} for model {model_name}")

        
        llm_start_time = time.time()

        for i in range(3):
            try:
                response = ask_llm_anything(
                    model_provider=model_provider,
                    model_name=model_name,
                    messages=messages_to_ask,
                    args=args
                )
                break
            except Exception as e:
                print(f"Error when asking LLM: {e}")
                if i == 2:
                    raise e
                else:
                    print(f"Retrying... ({i+1}/3)")
                    time.sleep(1)

        llm_end_time = time.time()

        print(f"LLM response: \n-----------------\n{response}\n-----------------")

        action = parser.str2action(response)


        log_message = {
            "environment": current_env,
            "action": action,

            "asked_messages": asked_messages,
            "model_response": response,
            "model_config": model_config,


            "llm_cost": {
                "llm_time": llm_end_time - llm_start_time,
                "llm_start_time": llm_start_time,
                "llm_end_time": llm_end_time
            },
        }

        logger.log_str(log_message, is_print=self.debug)

        return {
            "action": action,
            "current_step": current_ste + 1,
            "llm_cost": {
                "llm_time": llm_end_time - llm_start_time,
                "llm_start_time": llm_start_time,
                "llm_end_time": llm_end_time
            },
        }
        
    