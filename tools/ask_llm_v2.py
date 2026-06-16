"""Utilities for calling OpenAI-compatible chat models with optional images."""

import sys
if "." not in sys.path:
    sys.path.append(".")

from megfile import smart_open
import base64

# import openai
# to support 2.28.0
from openai import OpenAI

import yaml

import json
import time

def ask_llm_anything(model_provider, model_name, messages, args= {
    "max_tokens": 256,
    "temperature": 0.5,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
}, resize_config=None, timeout=30):
    """Send a chat request to a configured model provider.

    This helper reads ``model_config.yaml`` to resolve API credentials, normalizes
    multimodal message content (including image payload conversion), and sends the
    request through ``openai.ChatCompletion.create``.

    Args:
        model_provider (str): Provider key defined in ``model_config.yaml``.
        model_name (str): Model identifier used by the provider.
        messages (list[dict]): Chat messages following OpenAI-style schema.
        args (dict): Sampling and generation parameters such as ``temperature``,
            ``top_p``, ``frequency_penalty``, and ``max_tokens``.
        resize_config (dict | None): Optional image resize config. Expected keys:
            ``is_resize`` (bool) and ``target_image_size`` (tuple[int, int]).

    Returns:
        str: Assistant response content. If provider returns reasoning content, it
        is prefixed with ``<think>...</think>``.

    Raises:
        ValueError: If ``model_provider`` is not found in ``model_config.yaml``.
    """

    with open("model_config.yaml", "r") as f:
        model_config = yaml.safe_load(f)
    

    if model_provider in model_config:
        # openai.api_base = model_config[model_provider]["api_base"]
        # to support 2.28.0
        api_base = model_config[model_provider]["api_base"]
        # openai.api_key = model_config[model_provider]["api_key"]
        api_key = model_config[model_provider]["api_key"]


    else:
        raise ValueError(f"Unknown model provider: {model_provider}")
    
    def preprocess_messages(messages):
        """Normalize image inputs to OpenAI-compatible ``image_url`` entries.

        Supported image payload forms:
        - ``image_url`` with a local/remote path
        - ``image_url`` with an existing data URL
        - ``image_b64`` with raw base64 content
        """
        for msg in messages:
            if type(msg['content']) == str:
                continue
            assert type(msg['content']) == list
            for content in msg['content']:
                if content['type'] == "text":
                    continue
                assert content['type'] == "image_url" or content['type'] == "image_b64"
                if content['type'] == "image_url":
                    url = content['image_url']['url']
                    # Skip conversion if the payload is already a data URL.
                    if url.startswith("data:image/"):
                        continue
                    else:

                        image_bytes = smart_open(url, mode="rb").read()

                        b64 = base64.b64encode(image_bytes).decode('utf-8')

                        # Detect basic image type by signature bytes.
                        if image_bytes[0:4] == b"\x89PNG":
                            content['image_url']['url'] = "data:image/png;base64," + b64
                        elif image_bytes[0:2] == b"\xff\xd8":
                            content['image_url']['url'] = "data:image/jpeg;base64," + b64
                        else:
                            content['image_url']['url'] = "data:image/png;base64," + b64

                else:
                    assert content['type'] == "image_b64"
                    b64 = content['image_b64']['b64_json']
                    del content['image_b64']
                    content['image_url'] = {"url": "data:image/png;base64," + b64}
                    content['type'] = "image_url"
                
                if resize_config is not None and resize_config.get("is_resize", False) == True:
                    # Optionally resize image data URLs to reduce payload size.
                    print(f"Resizing image in message for model {model_name} to {resize_config['target_image_size']}...", flush=True)
                    image_url = content['image_url']['url']
                    image_b64_url = image_url.split(",", 1)[1]
                    image_data = base64.b64decode(image_b64_url)
                    from PIL import Image
                    import io
                    image = Image.open(io.BytesIO(image_data))
                    image = image.resize(size= resize_config['target_image_size'])
                    image_data = io.BytesIO()
                    image = image.convert('RGB')
                    image.save(image_data, format="JPEG", quality=85)
                    image_data = image_data.getvalue()
                    b64_image = base64.b64encode(image_data).decode('utf-8')
                    content['image_url']['url'] = f"data:image/jpeg;base64,{b64_image}"
                else:
                    print(f"No resizing for image in message for model {model_name}.", flush=True)

        return messages
    messages = preprocess_messages(messages)

    # Measure API latency for observability.
    start_time = time.time()

    default_headers = {
    }

    # to support 2.28.0
    client = OpenAI(
        api_key=api_key,
        base_url=api_base,
    )

    completion = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=args.get("temperature", 0.5),
        top_p=args.get("top_p", 1.0),
        frequency_penalty=args.get("frequency_penalty", 0.0),
        max_tokens=args.get("max_tokens", 100), 

        extra_headers=default_headers,

        timeout=timeout,

        # reasoning_effort = "high", # for step_stage, can be "none", "medium", "full"

        # stream=False,
        # enable_thinking = False,
        # timeout=300,
    )
    end_time = time.time()
    print(f"LLM {model_name} inference time: {end_time - start_time:.2f} seconds")
    print(f"LLM Args: {json.dumps(args, ensure_ascii=False)}", flush=True)
    # Log token usage to track request cost.
    # print(f"LLM {model_name} prompt tokens: {completion['usage']['prompt_tokens']}, completion tokens: {completion['usage']['completion_tokens']}, total tokens: {completion['usage']['total_tokens']}")
    # to support 2.28.0
    print(f"LLM {model_name} prompt tokens: {completion.usage.prompt_tokens}, completion tokens: {completion.usage.completion_tokens}, total tokens: {completion.usage.total_tokens}", flush=True)

    
    # result = completion.choices[0].message['content']
    # to support 2.28.0
    # result = completion.choices[0].message.content


    # print("llm ask id:", completion['id'])
    # to support 2.28.0
    print("llm ask id:", completion.id)

    # Some providers return reasoning content in a dedicated field.
    # We log it for debugging but do NOT prepend it to the result.
    # Prepending reasoning_content as a <think> block causes issues when the
    # model's content already contains <THINK> tags (required by the parser prompt),
    # resulting in two layers of THINK tags that confuse str2action().
    # The parser only needs the model's content output, which already follows
    # the <THINK>...</THINK>\texplain:...\taction:...\tsummary:... format.

    llm_content = completion.choices[0].message.content
    result = llm_content
    if llm_content is None or len(llm_content) == 0:
        llm_content = ""
        result = ""
        print(f"Warning: LLM {model_name} returned empty content.", flush=True)
    
    reasoning_debug = None
    try:
        reasoning_debug = completion.choices[0].message.reasoning_content
    except Exception:
        pass
    if reasoning_debug is None:
        try:
            reasoning_debug = completion.choices[0].message.reasoning
        except Exception:
            pass

    if reasoning_debug and len(reasoning_debug) > 0:
        print(f"[Reasoning] {reasoning_debug[:200]}...", flush=True)
    else:
        print(f"Warning: LLM {model_name} returned response without reasoning content.", flush=True)


    print(f"LLM {model_name} says:\n--------------start--------------\n{result}\n---------------end---------------",flush=True)

    return result


if __name__ == "__main__":

    # Example usage
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}}
        ]},
    ]
    response = ask_llm_anything("model_proxy", "gpt-5.4", messages)
    print("LLM Response:", response)
