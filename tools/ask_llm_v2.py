import sys
if "." not in sys.path:
    sys.path.append(".")

from megfile import smart_open
import base64

import openai
import yaml

import json
import time

def ask_llm_anything(model_provider, model_name, messages, args= {
    "max_tokens": 256,
    "temperature": 0.5,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
}, resize_config=None):

    with smart_open("model_config.yaml", "r") as f:
        model_config = yaml.safe_load(f)
    

    if model_provider in model_config:
        openai.api_base = model_config[model_provider]["api_base"]
        openai.api_key = model_config[model_provider]["api_key"]


    else:
        raise ValueError(f"Unknown model provider: {model_provider}")
    
    # preprocess
    def preprocess_messages(messages):
        # Implement any necessary preprocessing steps for the messages
        # return messages
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
                    # to check if the image is already in base64 format
                    if url.startswith("data:image/"):
                        continue
                    else:
                        image_bytes = smart_open(url, mode="rb").read()
                        b64 = base64.b64encode(image_bytes).decode('utf-8')

                        # to judge the image format
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


        return messages
    messages = preprocess_messages(messages)

    # current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    start_time = time.time()
    completion = openai.ChatCompletion.create(
        api_key=openai.api_key,
        api_base = openai.api_base,
        model=model_name,
        messages=messages,
        temperature=args.get("temperature", 0.5),
        top_p=args.get("top_p", 1.0),
        frequency_penalty=args.get("frequency_penalty", 0.0),
        max_tokens=args.get("max_tokens", 100), 
        # enable_thinking = False,
        # timeout=300,
    )
    end_time = time.time()
    print(f"LLM {model_name} inference time: {end_time - start_time:.2f} seconds")
    # token cost
    print(f"LLM {model_name} prompt tokens: {completion['usage']['prompt_tokens']}, completion tokens: {completion['usage']['completion_tokens']}, total tokens: {completion['usage']['total_tokens']}")
    
    result = completion.choices[0].message['content']

    print("llm ask id:", completion['id'])

    reasoning = completion.choices[0].message.get("reasoning_content", "")
    if reasoning is not None and len(reasoning) > 0:
        result = "<think>" + reasoning + "</think>" + "\n" + result

    print(f"LLM {model_name} says:\n--------------start--------------\n{result}\n---------------end---------------")

    return result


if __name__ == "__main__":
    while True:
        #         "model_name": "step3p5v-sftv1-128k-it8949-reason",
        # "model_provider": "stepcast",

        try:
            response = ask_llm_anything(
                model_provider="stepcast",
                model_name="step3p5v-sftv1-128k-it8949-reason",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请问现在的时间是几点？"
                            }
                        ]
                    }
                ],
                args={
                    "temperature": 0.1,
                    "top_p": 0.95,
                    "frequency_penalty": 0.0,
                    "max_tokens": 4096,
                },
            )
            print("LLM response:", response)
        except Exception as e:
            print("Error during LLM interaction:", str(e))
        
        time.sleep(1)