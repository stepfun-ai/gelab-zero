"""Local server with periodic rolling state compression."""

import time
from collections import OrderedDict
from copy import deepcopy

from copilot_agent_server.base_server import BaseCopilotServer, DEFAULT_MAX_RETRY
from copilot_agent_server.local_server_logger import LocalServerLogger
from copilot_agent_server.parser_factory import get_parser
from copilot_front_end.pu_frontend_executor import uiTars_to_frontend_action
from tools.ask_llm_v2 import ask_llm_anything
from tools.image_tools import make_b64_url, read_from_url
from copilot_tools.web_search import WebSearchError, ask_with_web_search, resolve_search_config


class LocalStateCompressServer(BaseCopilotServer):
    """Local parser server with a rolling compressed-history block."""

    def __init__(self, server_config: dict):
        super().__init__()

        self.server_config = server_config
        assert "log_dir" in server_config, "server_config must contain 'log_dir'"
        assert "image_dir" in server_config, "server_config must contain 'image_dir'"

        self.debug = server_config.get("debug", False)

    def get_session(self, payload: dict) -> str:
        import uuid

        session_id = str(uuid.uuid4())

        logger = LocalServerLogger(
            {
                "log_dir": self.server_config["log_dir"],
                "image_dir": self.server_config["image_dir"],
                "session_id": session_id,
            }
        )

        assert "task" in payload, "payload must contain 'task'"

        rollout_config = payload.get("rollout_config", None)
        if rollout_config is None:
            assert "task_type" in payload, "payload must contain 'task_type' indicating different parsers"
            assert "model_config" in payload, "payload must contain 'model_config'"
            rollout_config = {
                "task_type": payload["task_type"],
                "model_config": payload["model_config"],
            }

        assert "task_type" in rollout_config, "rollout_config must contain 'task_type'"
        assert "model_config" in rollout_config, "rollout_config must contain 'model_config'"
        assert "model_name" in rollout_config["model_config"], "model_config must contain 'model_name'"

        extra_info = payload.get("extra_info", {})
        config = payload.get("config", rollout_config.get("config", {}))
        skill = payload.get("skill", "")

        logger.log_str(
            {
                "log_type": "session_start",
                "task": payload["task"],
                "task_type": rollout_config["task_type"],
                "model_config": rollout_config["model_config"],
                "web_search_config": resolve_search_config(
                    self.server_config.get("web_search"), payload.get("web_search")
                ),
                "rollout_config": rollout_config,
                "skill": skill,
                "config": config,
                "extra_info": extra_info,
            },
            is_print=self.debug,
        )

        return session_id

    @staticmethod
    def _get_envs_acts_from_logs(logs):
        environments = []
        actions = []
        for log in logs[1:]:
            msg = log["message"]
            assert "environment" in msg, "log message must contain 'environment'"
            assert "action" in msg, "log message must contain 'action'"
            environments.append(msg["environment"])
            actions.append(msg["action"])
        return environments, actions

    @staticmethod
    def _strip_think(text: str) -> str:
        if not isinstance(text, str):
            return ""
        text = text.replace("<THINK>", "<think>").replace("</THINK>", "</think>")
        if "</think>" not in text:
            return text.strip()
        return text.split("</think>", 1)[-1].strip()

    @staticmethod
    def _dedup_preserve_order(items):
        deduped = []
        seen = set()
        for item in items:
            item = str(item).strip()
            if len(item) == 0:
                continue
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def _resolve_compression_config(self, config_dict):
        state_compression = deepcopy(config_dict.get("state_compression", {}))
        enabled = state_compression.get(
            "enabled",
            config_dict.get("enable_state_compression", True),
        )
        interval = int(
            state_compression.get(
                "interval",
                config_dict.get("state_compression_interval", 10),
            )
        )
        recent_window = int(
            state_compression.get(
                "recent_window",
                config_dict.get("state_compression_recent_window", 10),
            )
        )
        max_field_items = int(
            state_compression.get(
                "max_field_items",
                config_dict.get("state_compression_max_field_items", 8),
            )
        )
        compression_args = deepcopy(state_compression.get("args", {}))

        assert interval > 0, "state compression interval must be positive"
        assert recent_window > 0, "state compression recent window must be positive"
        assert max_field_items > 0, "state compression max_field_items must be positive"

        return {
            "enabled": bool(enabled),
            "interval": interval,
            "recent_window": recent_window,
            "max_field_items": max_field_items,
            "args": compression_args,
        }

    def _get_latest_compressed_state(self, logs):
        for log in reversed(logs[1:]):
            msg = log["message"]
            compression_info = msg.get("state_compression")
            if not isinstance(compression_info, dict):
                continue
            if not compression_info.get("triggered", False):
                continue
            compressed_state = compression_info.get("compressed_state")
            compressed_upto_step = int(compression_info.get("compressed_upto_step", 0))
            if isinstance(compressed_state, str) and len(compressed_state.strip()) > 0:
                return compressed_state, compressed_upto_step
        return None, 0

    def _compute_compression_target(self, current_step, last_compressed_upto_step, interval, recent_window):
        compressible_steps = current_step - recent_window
        if compressible_steps < interval:
            return 0
        candidate_upto_step = (compressible_steps // interval) * interval
        if candidate_upto_step <= last_compressed_upto_step:
            return 0
        return candidate_upto_step

    def _truncate_items(self, items, max_items):
        items = self._dedup_preserve_order(items)
        if len(items) <= max_items:
            return items
        return items[-max_items:]

    def _step_record2text(self, step_idx, env, action):
        lines = [f"[STEP {step_idx}]"]
        lines.append(f"user_comment: {env.get('user_comment', '').strip() or 'none'}")
        lines.append(f"image_reference: {env.get('image', 'none')}")
        lines.append(f"action: {action.get('action', action.get('action_type', 'none'))}")
        lines.append(f"verify: {action.get('verify', 'none')}")
        lines.append(f"note: {action.get('note', 'none')}")
        lines.append(f"explain: {action.get('explain', 'none')}")
        lines.append(f"key_process: {action.get('key_process', action.get('summary', 'none'))}")
        if "value" in action:
            lines.append(f"value: {action.get('value', 'none')}")
        if "return" in action:
            lines.append(f"return: {action.get('return', 'none')}")
        lines.append(f"[/STEP {step_idx}]")
        return "\n".join(lines)

    def _build_compression_messages(
        self,
        task,
        previous_compressed_state,
        chunk_start_step,
        chunk_end_step,
        chunk_records_text,
    ):
        previous_state_text = previous_compressed_state.strip() if isinstance(previous_compressed_state, str) else ""
        if len(previous_state_text) == 0:
            previous_state_text = "none"

        compression_prompt = f"""
你是一个 GUI Agent 历史状态压缩器。你的任务不是预测动作，而是把较早历史压缩成一段结构化状态，供后续 parser 继续使用。

压缩要求：
1. 你只能输出一个压缩块，不要输出额外解释，不要输出 JSON，不要输出动作指令。
2. 必须保留关键的原始输入信息：用户任务、用户补充回复、关键页面观察、关键进展、当前子目标、风险点、最后有效状态。
3. 字段必须清晰、稳定，严格使用下面模板，缺失内容写 `- none` 或 `none`。
4. 你需要把旧的压缩状态和本轮新增步骤合并成一份新的压缩状态。
5. 输出中必须保留开始和结束标记，确保系统后续可以稳定解析。

请严格输出以下格式：
<<<STATE_COMPRESSION>>>
covered_steps: 1-{chunk_end_step}
task: {task}
important_user_inputs:
- ...
important_observations:
- ...
completed_progress:
- ...
current_subgoal:
...
pending_risks:
- ...
last_effective_state:
...
<<<END_STATE_COMPRESSION>>>

以下是已有压缩状态：
{previous_state_text}

以下是本轮需要新增压缩的原始步骤（第{chunk_start_step}步到第{chunk_end_step}步）：
{chunk_records_text}
""".strip()

        return [{"role": "user", "content": [{"type": "text", "text": compression_prompt}]}]

    def _listify_text_field(self, value):
        value = str(value).strip()
        if len(value) == 0 or value == "none":
            return []
        lines = []
        for line in value.splitlines():
            line = line.strip()
            if len(line) == 0 or line == "none":
                continue
            if line.startswith("- "):
                line = line[2:].strip()
            lines.append(line)
        return lines

    def _build_fallback_compressed_state(
        self,
        parser,
        task,
        previous_compressed_state,
        chunk_step_records,
        chunk_end_step,
        max_field_items,
    ):
        merged_state = OrderedDict(
            {
                "covered_steps": f"1-{chunk_end_step}",
                "task": task,
                "important_user_inputs": [],
                "important_observations": [],
                "completed_progress": [],
                "current_subgoal": "none",
                "pending_risks": [],
                "last_effective_state": "none",
            }
        )

        if previous_compressed_state:
            try:
                previous_state_dict = parser.compressed_state_text2dict(previous_compressed_state)
                merged_state["important_user_inputs"].extend(
                    self._listify_text_field(previous_state_dict.get("important_user_inputs", "none"))
                )
                merged_state["important_observations"].extend(
                    self._listify_text_field(previous_state_dict.get("important_observations", "none"))
                )
                merged_state["completed_progress"].extend(
                    self._listify_text_field(previous_state_dict.get("completed_progress", "none"))
                )
                merged_state["pending_risks"].extend(
                    self._listify_text_field(previous_state_dict.get("pending_risks", "none"))
                )
                previous_subgoal = str(previous_state_dict.get("current_subgoal", "none")).strip()
                if len(previous_subgoal) > 0:
                    merged_state["current_subgoal"] = previous_subgoal
                previous_last_state = str(previous_state_dict.get("last_effective_state", "none")).strip()
                if len(previous_last_state) > 0:
                    merged_state["last_effective_state"] = previous_last_state
            except Exception:
                pass

        last_note = "none"
        last_explain = "none"
        for step_idx, env, action in chunk_step_records:
            user_comment = env.get("user_comment", "").strip()
            if len(user_comment) > 0:
                merged_state["important_user_inputs"].append(f"step {step_idx}: {user_comment}")

            note = str(action.get("note", "")).strip()
            if len(note) > 0 and note != "none":
                merged_state["important_observations"].append(f"step {step_idx}: {note}")
                last_note = f"step {step_idx}: {note}"

            key_process = str(action.get("key_process", action.get("summary", ""))).strip()
            if len(key_process) > 0 and key_process != "none":
                merged_state["completed_progress"].append(f"step {step_idx}: {key_process}")

            explain = str(action.get("explain", "")).strip()
            if len(explain) > 0 and explain != "none":
                merged_state["current_subgoal"] = f"step {step_idx}: {explain}"
                last_explain = f"step {step_idx}: {explain}"

            verify = str(action.get("verify", "")).strip()
            if len(verify) > 0 and "不符合" in verify:
                merged_state["pending_risks"].append(f"step {step_idx}: {verify}")

            action_type = action.get("action", action.get("action_type", ""))
            if action_type in ["INFO", "ABORT", "CALL_USER"]:
                reason_value = action.get("value", action.get("return", "none"))
                merged_state["pending_risks"].append(
                    f"step {step_idx}: action={action_type}, detail={reason_value}"
                )

        merged_state["important_user_inputs"] = self._truncate_items(
            merged_state["important_user_inputs"], max_field_items
        )
        merged_state["important_observations"] = self._truncate_items(
            merged_state["important_observations"], max_field_items
        )
        merged_state["completed_progress"] = self._truncate_items(
            merged_state["completed_progress"], max_field_items
        )
        merged_state["pending_risks"] = self._truncate_items(
            merged_state["pending_risks"], max_field_items
        )

        if merged_state["current_subgoal"] == "none" and last_explain != "none":
            merged_state["current_subgoal"] = last_explain

        if last_note != "none":
            merged_state["last_effective_state"] = last_note
        elif last_explain != "none":
            merged_state["last_effective_state"] = last_explain

        for field_name in [
            "important_user_inputs",
            "important_observations",
            "completed_progress",
            "pending_risks",
        ]:
            if len(merged_state[field_name]) == 0:
                merged_state[field_name] = ["- none"]

        return parser.compressed_state_dict2text(merged_state)

    def _run_state_compression(
        self,
        parser,
        task,
        model_provider,
        model_name,
        base_args,
        previous_compressed_state,
        logs,
        chunk_start_step,
        chunk_end_step,
        max_field_items,
        compression_args_override=None,
    ):
        chunk_step_records = []
        chunk_records_text_list = []
        for step_idx in range(chunk_start_step, chunk_end_step + 1):
            log_message = logs[step_idx]["message"]
            env = log_message["environment"]
            action = log_message["action"]
            chunk_step_records.append((step_idx, env, action))
            chunk_records_text_list.append(self._step_record2text(step_idx, env, action))

        chunk_records_text = "\n\n".join(chunk_records_text_list)
        compression_messages = self._build_compression_messages(
            task=task,
            previous_compressed_state=previous_compressed_state,
            chunk_start_step=chunk_start_step,
            chunk_end_step=chunk_end_step,
            chunk_records_text=chunk_records_text,
        )

        compression_args = deepcopy(base_args)
        compression_args["max_tokens"] = min(int(compression_args.get("max_tokens", 4096)), 4096)
        if compression_args_override:
            compression_args.update(deepcopy(compression_args_override))

        raw_response = ""
        compression_error = None
        compression_start_time = time.time()

        for retry_idx in range(DEFAULT_MAX_RETRY):
            try:
                raw_response = ask_llm_anything(
                    model_provider=model_provider,
                    model_name=model_name,
                    messages=compression_messages,
                    args=compression_args,
                )
                normalized_state = parser.normalize_compressed_state(
                    compressed_state=self._strip_think(raw_response),
                    fallback_task=task,
                    fallback_covered_steps=f"1-{chunk_end_step}",
                )
                break
            except Exception as exc:
                compression_error = str(exc)
                print(f"Error when compressing history: {exc}")
                if retry_idx == DEFAULT_MAX_RETRY - 1:
                    normalized_state = self._build_fallback_compressed_state(
                        parser=parser,
                        task=task,
                        previous_compressed_state=previous_compressed_state,
                        chunk_step_records=chunk_step_records,
                        chunk_end_step=chunk_end_step,
                        max_field_items=max_field_items,
                    )
                else:
                    print(f"Retrying state compression... ({retry_idx + 1}/{DEFAULT_MAX_RETRY})")
                    time.sleep(1)

        compression_end_time = time.time()

        return {
            "triggered": True,
            "chunk_start_step": chunk_start_step,
            "chunk_end_step": chunk_end_step,
            "compressed_upto_step": chunk_end_step,
            "compressed_state": normalized_state,
            "compression_messages": compression_messages,
            "compression_raw_response": raw_response,
            "compression_error": compression_error,
            "compression_cost": {
                "llm_time": compression_end_time - compression_start_time,
                "llm_start_time": compression_start_time,
                "llm_end_time": compression_end_time,
            },
        }

    def automate_step(self, payload: dict) -> dict:
        assert "session_id" in payload, "payload must contain 'session_id'"
        session_id = payload["session_id"]

        logger = LocalServerLogger(
            {
                "log_dir": self.server_config["log_dir"],
                "image_dir": self.server_config["image_dir"],
                "session_id": session_id,
            }
        )

        logs = logger.read_logs()
        assert len(logs) > 0, f"No logs found for session_id {session_id}"
        current_ste = len(logs) - 1

        config_dict = logs[0]["message"]
        rollout_config = config_dict.get("rollout_config", None)
        if rollout_config is None:
            rollout_config = {
                "task_type": config_dict["task_type"],
                "model_config": config_dict["model_config"],
            }

        task_type = rollout_config["task_type"]
        model_config = rollout_config["model_config"]
        task = config_dict["task"]
        skill = config_dict.get("skill", "")
        session_runtime_config = config_dict.get("config", {})
        compression_config = self._resolve_compression_config(session_runtime_config)

        assert "observation" in payload, "payload must contain 'observation'"
        observation = payload["observation"]
        image_url = observation["screenshot"]["image_url"]["url"]
        image = read_from_url(image_url)
        image_inner_url = logger.save_image(image, f"step_{current_ste + 1}")
        query = observation.get("query", "")

        environments, actions = self._get_envs_acts_from_logs(logs)
        current_env = {
            "image": image_inner_url,
            "user_comment": query,
        }
        environments.append(current_env)
        current_step = len(environments)

        parser = get_parser(task_type)
        if compression_config["enabled"] and not hasattr(parser, "normalize_compressed_state"):
            assert task_type in [
                "parser_0920_summary_adv",
                "parser_0920_summary_adv_state_compress",
            ], (
                "LocalStateCompressServer currently expects a parser derived from "
                "parser_0920_summary_adv so it can inject compressed history."
            )
            parser = get_parser("parser_0920_summary_adv_state_compress")

        model_name = model_config["model_name"]
        model_provider = model_config.get("model_provider", "eval")
        args = model_config.get(
            "args",
            {
                "temperature": 0.1,
                "top_p": 1.0,
                "frequency_penalty": 0.0,
                "max_tokens": 512,
            },
        )
        image_preprocess = model_config.get("image_preprocess", None)

        compressed_state, compressed_upto_step = self._get_latest_compressed_state(logs)
        compression_info = {
            "triggered": False,
            "compressed_upto_step": compressed_upto_step,
        }

        if compression_config["enabled"]:
            compression_target = self._compute_compression_target(
                current_step=current_step,
                last_compressed_upto_step=compressed_upto_step,
                interval=compression_config["interval"],
                recent_window=compression_config["recent_window"],
            )
            if compression_target > 0:
                compression_info = self._run_state_compression(
                    parser=parser,
                    task=task,
                    model_provider=model_provider,
                    model_name=model_name,
                    base_args=args,
                    previous_compressed_state=compressed_state,
                    logs=logs,
                    chunk_start_step=compressed_upto_step + 1,
                    chunk_end_step=compression_target,
                    max_field_items=compression_config["max_field_items"],
                    compression_args_override=compression_config["args"],
                )
                compressed_state = compression_info["compressed_state"]
                compressed_upto_step = compression_info["compressed_upto_step"]

        recent_environments = environments[compressed_upto_step:]
        recent_actions = actions[compressed_upto_step:]

        if compressed_state is not None or compressed_upto_step > 0:
            messages_to_ask = parser.env2messages4ask(
                task=task,
                environments=recent_environments,
                actions=recent_actions,
                extra_skill=skill,
                compressed_state=compressed_state,
                compressed_upto_step=compressed_upto_step,
                history_step_offset=compressed_upto_step,
            )
        else:
            messages_to_ask = parser.env2messages4ask(
                task=task,
                environments=recent_environments,
                actions=recent_actions,
                extra_skill=skill,
            )
        asked_messages = deepcopy(messages_to_ask)

        if image_preprocess is not None and "target_image_size" in image_preprocess:
            target_image_size = image_preprocess["target_image_size"]

            def resize_image_in_messages(messages, target_size):
                for msg in messages:
                    if isinstance(msg["content"], str):
                        continue
                    for content in msg["content"]:
                        if content["type"] == "text":
                            continue
                        assert content["type"] == "image_url"
                        resized_image_url = make_b64_url(
                            content["image_url"]["url"],
                            resize_config={
                                "is_resize": True,
                                "target_image_size": target_size,
                            },
                        )
                        content["image_url"]["url"] = resized_image_url

            resize_image_in_messages(messages_to_ask, target_image_size)
            print(f"Resized images to {target_image_size} for model {model_name}")

        llm_start_time = time.time()

        for retry_idx in range(DEFAULT_MAX_RETRY):
            try:
                response, action, web_search, asked_messages = ask_with_web_search(
                    parser=parser,
                    messages=messages_to_ask,
                    ask_model=lambda messages: ask_llm_anything(
                        model_provider=model_provider,
                        model_name=model_name,
                        messages=messages,
                        args=args,
                        resize_config=model_config.get("resize_config", None),
                    ),
                    config=resolve_search_config(
                        self.server_config.get("web_search"), config_dict.get("web_search_config")
                    ),
                    session_id=session_id,
                    model_name=model_name,
                    logs=logs,
                )
                # assert (
                #     action["action"] != "CALL_USER"
                # ), "If the model responds with CALL_USER, it means the model cannot understand the current situation and needs to ask for user's help. Please check the model response and adjust the prompt or provide more information to the model."
                try:
                    action = uiTars_to_frontend_action(action)
                except Exception as exc:
                    if web_search:
                        raise WebSearchError("Invalid device action after web research") from exc
                    raise
                break
            except WebSearchError:
                raise
            except Exception as exc:
                print(f"Error when asking LLM: {exc}")
                if retry_idx == DEFAULT_MAX_RETRY - 1:
                    raise exc
                print(f"Retrying... ({retry_idx + 1}/{DEFAULT_MAX_RETRY})")
                time.sleep(1)

        llm_end_time = time.time()

        state_context = {
            "enabled": compression_config["enabled"],
            "interval": compression_config["interval"],
            "recent_window": compression_config["recent_window"],
            "current_step": current_step,
            "compressed_upto_step": compressed_upto_step,
            "raw_history_start_step": compressed_upto_step + 1,
            "raw_history_end_step": current_step,
            "used_compressed_state": bool(compressed_state),
        }

        log_message = {
            "environment": current_env,
            "action": action,
            "asked_messages": asked_messages,
            "model_response": response,
            "model_config": model_config,
            "web_search": web_search,
            "state_context": state_context,
            "llm_cost": {
                "llm_time": llm_end_time - llm_start_time,
                "llm_start_time": llm_start_time,
                "llm_end_time": llm_end_time,
            },
        }

        if compression_info.get("triggered", False):
            log_message["state_compression"] = compression_info

        logger.log_str(log_message, is_print=self.debug)

        return {
            "action": action,
            "current_step": current_step,
            "llm_cost": {
                "llm_time": llm_end_time - llm_start_time,
                "llm_start_time": llm_start_time,
                "llm_end_time": llm_end_time,
            },
            "state_context": state_context,
        }
