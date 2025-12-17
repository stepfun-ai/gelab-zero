import sys
import os
import subprocess

from uuid import uuid4

if "." not in sys.path:
    sys.path.append(".")
from copilot_front_end.package_map import find_package_name

import time
from tqdm import tqdm

from megfile import smart_copy

def _get_adb_command(device_id=None):
    """
    Get the ADB command for the specified device ID.
    """
    if device_id is None:
        adb_command = "adb "
    else:
        assert device_id in list_devices(), f"Device {device_id} not found in connected devices."
        adb_command = f"adb -s {device_id} "
    return adb_command

def get_adb_command(device_id=None):
    """
    Get the ADB command for the specified device ID.
    """
    adb_command = _get_adb_command(device_id)
    return adb_command

def local_str_grep(input_str, pattern):
    """
    A simple local grep function that searches for a pattern in a string.
    :param input_str: The input string to search within.
    :param
    pattern: The pattern to search for.
    :return: True if the pattern is found, False otherwise.
    """
    return_lines = []
    for line in input_str.splitlines():
        if pattern in line:
            return_lines.append(line)
    
    return "\n".join(return_lines) if return_lines else None


def close_app_on_device(device_id, app_name, print_command = False):
    """
    Close the specified app on the device.
    """
    adb_command = _get_adb_command(device_id)
    
    package_name = find_package_name(app_name)
    if package_name is None:
        raise ValueError(f"App {app_name} not found in package map.")
    
    command = f"{adb_command} shell am force-stop {package_name}"
    if print_command:
        print(f"Executing command: {command}")
    
    subprocess.run(command, shell=True, capture_output=True, text=True)

def press_home_key(device_id, print_command = False):
    """
    Press the home key on the device.
    """
    adb_command = _get_adb_command(device_id)
    
    command = f"{adb_command} shell input keyevent 3"
    if print_command:
        print(f"Executing command: {command}")
    
    subprocess.run(command, shell=True, capture_output=True, text=True)

def init_device(device_id, print_command = False):
    """
    Initialize the device by checking if yadb is installed.
    """
    adb_command = _get_adb_command(device_id)
    
    # adb -s DEVICE_ID shell ls /data/local/tmp 
    # except yadb 
    command = f"{adb_command} shell md5sum /data/local/tmp/yadb"
    if print_command:
        print(f"Executing command: {command}")
    
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if "29a0cd3b3adea92350dd5a25594593df" not in result.stdout:
        # to push yadb into the device
        command = f"{adb_command} push yadb /data/local/tmp"
        print(f"YADB is not installed on the device. Installing now...")

        if print_command:
            # print(f"Executing command: {command}")
            print(f"Executing command: {command}")

        subprocess.run(command, shell=True, capture_output=True, text=True)
    else:
        print("yadb is already installed on the device.")

    # press_home_key(device_id, print_command=print_command)

def init_all_devices():
    """
    Initialize all devices by listing them and setting up the environment.
    """
    devices = list_devices()
    for device_id in tqdm(devices):
        init_device(device_id)
        print(f"Initialized device: {device_id}")

def dectect_screen_on(device_id, print_command = False):
    """
    Detect whether the screen is on for the specified device.
    """
    adb_command = _get_adb_command(device_id)
    
    # adb shell dumpsys display | grep mScreenState

    #duplicate the command, support win platform
    # command = f"{adb_command} shell dumpsys display | grep mScreenState"
    # if print_command:
    #     print(f"Executing command: {command}")
    
    # result = subprocess.run(command, shell=True, capture_output=True, text=True)
    # screen_state = result.stdout.strip()


    if sys.platform == "win32":
        # On Windows, we need to decode the output
        command = f"{adb_command} shell dumpsys display"
        if print_command:
            print(f"Executing command: {command}")
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        result.stdout = result.stdout.encode('utf-8').decode('utf-8')
        screen_state = local_str_grep(result.stdout, "mScreenState").strip()
    else:
        command = f"{adb_command} shell dumpsys display | grep mScreenState"
        if print_command:
            print(f"Executing command: {command}")
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        screen_state = result.stdout.strip()
    
    if "ON" in screen_state:
        return True
    else:
        return False

def press_power_key(device_id, print_command = False):
    """
    Press the power key on the specified device.
    """
    adb_command = _get_adb_command(device_id)
    
    command = f"{adb_command} shell input keyevent 26"
    if print_command:
        print(f"Executing command: {command}")
    
    subprocess.run(command, shell=True, capture_output=True, text=True)

def swipe_up_to_unlock(device_id, wm_size=(1000,2000), print_command = False):
    """
    Swipe up on the specified device to unlock the screen.
    """
    adb_command = _get_adb_command(device_id)

    x = wm_size[0] // 2
    y_start = int(wm_size[1] * 0.9)
    y_end = int(wm_size[1] * 0.2)

    command = f"{adb_command} shell input swipe {x} {y_start} {x} {y_end}"
    if print_command:
        print(f"Executing command: {command}")
    subprocess.run(command, shell=True, capture_output=True, text=True)

def get_manufacturer(device_id):
    """
    Get the manufacturer of the specified device.
    """
    adb_command = _get_adb_command(device_id)
    command = f"{adb_command} shell getprop ro.product.manufacturer"
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    manufacturer = result.stdout.strip().lower()
    return manufacturer

def _open_screen(device_id, print_command = False):
    """
    Open the screen of the specified device.
    """
    
    is_screen_on = dectect_screen_on(device_id, print_command=print_command)
    if is_screen_on:
        if print_command:
            print(f"Screen is already on for device {device_id}.")
        return
    
    
    press_power_key(device_id, print_command=print_command)
    time.sleep(0.2)
    maunfacturer = get_manufacturer(device_id)
    if "vivo" in maunfacturer:
        # to swipe up to unlock the screen
        swipe_up_to_unlock(device_id, wm_size=get_device_wm_size(device_id), print_command=print_command)
        time.sleep(0.2)

        

def open_screen(device_id, print_command = False):
    """
    Open the screen of the specified device.
    """
    _open_screen(device_id, print_command=print_command)


def list_devices():
    """
    List all connected mobile devices.
    """
    try:
        result = subprocess.run(['adb', 'devices'], capture_output=True, text=True)
        devices = result.stdout.splitlines()[1:]
        devices = [line.split()[0].strip() for line in devices if line.strip() and 'device' in line]
        return devices
    except Exception as e:
        print(f"Error listing devices: {e}")
        return []

def _capture_save_screenshot(device_id, tmp_file_dir="tmp_screenshot", image_name = None, print_command = False):
    if not os.path.exists(tmp_file_dir):
        os.makedirs(tmp_file_dir)
        print(f"Created temporary directory: {tmp_file_dir}")
    
    adb_command = _get_adb_command(device_id)
    
    if image_name is None:
        screen_shot_pic_name = f"uuid_{uuid4()}.png"
    
    screen_shot_pic_path = os.path.join(tmp_file_dir, screen_shot_pic_name)
    try:
        # result = subprocess.run([adb_command, 'shell', 'screencap', '-p'], capture_output=True, text=True)
        command = f"{adb_command} shell screencap -p /sdcard/{screen_shot_pic_name}"
        if print_command:   
            print(f"Executing command: {command}")
        subprocess.run(command, shell=True, capture_output=True, text=True)

        # time.sleep(0.2)

        command = f"{adb_command} pull /sdcard/{screen_shot_pic_name} {screen_shot_pic_path}"
        if print_command:
            print(f"Executing command: {command}")
        subprocess.run(command, shell=True, capture_output=True, text=True)

        remove_command = f"{adb_command} shell rm /sdcard/{screen_shot_pic_name}"
        if print_command:
            print(f"Executing command: {remove_command}")
        subprocess.run(remove_command, shell=True, capture_output=True, text=True)

        return screen_shot_pic_path
    except Exception as e:
        print(f"Error capturing screenshot: {e}")
        return None

def capture_screenshot(device_id, tmp_file_dir="tmp_screenshot", image_name = None, print_command = False):
    """
    Capture a screenshot of the specified device and save it to the specified directory.
    """
    screen_shot_pic_path = _capture_save_screenshot(device_id, tmp_file_dir, image_name, print_command)
    if screen_shot_pic_path is None:
        raise ValueError(f"Error capturing screenshot for device {device_id}.")
    
    return screen_shot_pic_path    

def get_device_wm_size(device_id):
    """
    Get the screen size of the specified device.
    """
    

    adb_command = _get_adb_command(device_id)
    try:
        # result = subprocess.run([adb_command, 'shell', 'wm', 'size'], capture_output=True, text=True)
        command = f"{adb_command} shell wm size"

        # print(f"Getting device {device_id} wm size with command: {command}")

        result = subprocess.run(command, shell=True, capture_output=True, text=True)

        result_str = result.stdout.strip()
        
        assert "Physical size:" in result_str or "Override size:" in result_str, f"Unexpected wm size output: {result_str}"

        if "override size" in result_str.lower():
            size = result_str.split('Override size:')[1].strip()
        else:
            size = result_str.split('Physical size:')[1].strip()

        size = size.split('x')
        if "\n" in size[1]:
            size[1] = size[1].split("\n")[0]
        size = (int(size[0]), int(size[1]))
        return size
    except Exception as e:
        print(f"Error getting device size: {e}")
        return None

# convert model action from api to a front-end action
def model_act2front_act(act, wm_size):
    """
    Convert model action to front-end action.
    """
    # to parse the action and convert it to front-end action
    model_action_type_list = ['CLICK', "TYPE", "COMPLETE", "WAIT", "AWAKE", "INFO", "ABORT", "SWIPE", "LONGPRESS"]

    action_type_map = {
        "CLICK": "Click",
        "TYPE": "Type",
        "COMPLETE": "Complete",
        "INFO": "Pop",
        "WAIT": "Wait",
        "AWAKE": "Awake",
        "ABORT": "Abort",
        "SWIPE": "Scroll",
        "LONGPRESS": "LongPress",
    }

    if "action" in act:
        act['action_type'] = act['action']

    assert act['action_type'] in model_action_type_list, f"Invalid action type: {act['action_type']}"

    # action unrelated parameters
    status = act.get('status', None)
    payload_dict = act.get('payload', {})
    plan, summary = payload_dict.get('plan', None), payload_dict.get('summary', None)

    explain = act['explain']


    down_stream_action = {
        "action_type": action_type_map[act['action_type']],
        "args": {
            "status": status,
            "plan": plan,
            "summary": summary,

            "explain": explain,
        }
    }

    if act['action_type'] == 'CLICK':
        # <STATUS>xxx<ACTION>explain:xxx\taction:CLICK\tpoint:x,y\tsearch_type:app|keyboard|none<PAYLOAD>plan:xxx\tsummary:xxx\t
        assert "point" in act, f"Point not found in CLICK action: {act}"

        search_type = act.get('search_type', "none")

        point = act['point']

        zero_one_point = ((float(point[0])) / 1000, (float(point[1])) / 1000)
        real_coordinate = (int(zero_one_point[0] * wm_size[0]), int(zero_one_point[1] * wm_size[1]))

        # click point for several versions
        down_stream_action['args']['coordinate'] = real_coordinate + real_coordinate
        down_stream_action['args']['point'] = real_coordinate
        down_stream_action['args']['normalized_point'] = zero_one_point

        down_stream_action['args']['search_type'] = search_type

    elif act['action_type'] == 'TYPE':
        # <STATUS>xxx<ACTION>explain:xxx\taction:TYPE\tvalue:xxxx\tpoint:x,y\tkeyboard:true|alse<PAYLOAD>plan:xxx\tsummary:xxx\t
        assert "value" in act, f"Value not found in TYPE action: {act}"

        value = act['value'].replace(" ", "_")
        # point = act['point']
        # point can be optional
        point = act.get('point', None)

        # to set the keyboard exists default to True, for point is None
        keyboard_exists = act.get('keyboard', True)

        if point is not None:        
            zero_one_point = ((float(point[0])) / 1000, (float(point[1])) / 1000)
            real_coordinate = (int(zero_one_point[0] * wm_size[0]), int(zero_one_point[1] * wm_size[1]))
        else:
            zero_one_point = None
            real_coordinate = [None]

        # click point for several versions
        down_stream_action['args']['coordinate'] = real_coordinate + real_coordinate
        down_stream_action['args']['point'] = real_coordinate
        down_stream_action['args']['normalized_point'] = zero_one_point

        down_stream_action['args']['text'] = value

        down_stream_action['args']['keyboard_exists'] = keyboard_exists

    elif act['action_type'] == "INFO": 
        # <STATUS>xxx<ACTION>explain:xxx\taction:INFO\tvalue:xxxx\t<PAYLOAD>plan:xxx\tsummary:xxx\t
        assert "value" in act, f"Value not found in INFO action: {act}"

        value = act['value']
        down_stream_action['args']['text'] = value


    elif act['action_type'] == "WAIT":
        #<STATUS>xxx<ACTION>explain:xxx\taction:WAIT\tvalue:5\tis_auto_close:true|false\tr1:xxx\tp1:x1,y1\tr2:xxx\tp2:x2,y2\t<PAYLOAD>plan:xxx\tsummary:xxx\t

        assert "value" in act, f"Value not found in WAIT action: {act}"
        value = act['value']
        is_auto_close = act.get('is_auto_close', False)

        clickable_regions = []
        close_reasons = act.get('close_reasons', [])
        for click_area in close_reasons:

            point, reason = click_area['point'], click_area['reason']
            bbox = click_area.get('bbox', None)

            zero_one_point = ((float(point[0])) / 1000, (float(point[1])) / 1000)
            real_coordinate = (int(zero_one_point[0] * wm_size[0]), int(zero_one_point[1] * wm_size[1]))
            
            if bbox is not None:
                zero_one_bbox = ((float(bbox[0])) / 1000, (float(bbox[1])) / 1000, 
                                 (float(bbox[2])) / 1000, (float(bbox[3])) / 1000)
                real_bbox = (int(zero_one_bbox[0] * wm_size[0]), int(zero_one_bbox[1] * wm_size[1]),
                              int(zero_one_bbox[2] * wm_size[0]), int(zero_one_bbox[3] * wm_size[1]))
                
            else:
                zero_one_bbox = (zero_one_point[0], zero_one_point[1], zero_one_point[0], zero_one_point[1])
                real_bbox = (real_coordinate[0], real_coordinate[1], real_coordinate[0], real_coordinate[1])
            
                
            clickable_regions.append({
                "reason": reason,

                "point": real_coordinate,
                "region": real_bbox,

                "normalized_point": zero_one_point,
                "normalized_region": zero_one_bbox,
            })

        # for reason, point in act['']

        down_stream_action['args']['duration'] = value
        down_stream_action['args']['closability'] = {
            "auto_closable": is_auto_close,
            "type": explain,
            "regions": clickable_regions,
        }

    elif act['action_type'] == "AWAKE":
        # <STATUS>xxx<ACTION>explain:xxx\taction:AWAKE\tvalue:xxxx\t<PAYLOAD>plan:xxx\tsummary:xxx\t
        assert "value" in act, f"Value not found in AWAKE action: {act}"

        value = act['value']
        down_stream_action['args']['text'] = value

    elif act['action_type'] == "ABORT":
        # <STATUS>xxx<ACTION>explain:xxx\taction:ABORT\t<PAYLOAD>plan:xxx\tsummary:xxx\t

        down_stream_action['args']['abort_reason'] = explain
    
    elif act['action_type'] == "COMPLETE":
        # <STATUS>xxx<ACTION>explain:xxx\taction:COMPLETE\t<PAYLOAD>plan:xxx\tsummary:xxx\t

        # nothing to add
        pass

    elif act['action_type'] == "SWIPE":
        # <STATUS>xxx<ACTION>explain:xxx\taction:SWIPE\tpoint1:x,y\tpoint2:x,y\t<PAYLOAD>plan:xxx\tsummary:xxx\t  

        point1 = act['point1']
        zero_one_point1 = ((float(point1[0])) / 1000, (float(point1[1])) / 1000)
        real_coordinate1 = (int(zero_one_point1[0] * wm_size[0]), int(zero_one_point1[1] * wm_size[1]))

        point2 = act['point2']
        zero_one_point2 = ((float(point2[0])) / 1000, (float(point2[1])) / 1000)
        real_coordinate2 = (int(zero_one_point2[0] * wm_size[0]), int(zero_one_point2[1] * wm_size[1]))

        path = [(real_coordinate1[0], real_coordinate1[1]), (real_coordinate2[0], real_coordinate2[1])]
        normalized_path = [(zero_one_point1[0], zero_one_point1[1]), (zero_one_point2[0], zero_one_point2[1])]

        down_stream_action['args']['path'] = path
        down_stream_action['args']['normalized_path'] = normalized_path

    elif act['action_type'] == "LONGPRESS":
        # <STATUS>xxx<ACTION>explain:xxx\taction:LONGPRESS\tpoint:x,y\t<PAYLOAD>plan:xxx\tsummary:xxx\t

        point = act['point']
        zero_one_point = ((float(point[0])) / 1000, (float(point[1])) / 1000)
        real_coordinate = (int(zero_one_point[0] * wm_size[0]), int(zero_one_point[1] * wm_size[1]))

        # click point for several versions
        down_stream_action['args']['coordinate'] = real_coordinate + real_coordinate
        down_stream_action['args']['point'] = real_coordinate
        down_stream_action['args']['normalized_point'] = zero_one_point

    else:
        raise ValueError(f"Invalid action type: {act['action_type']}")
    
    return down_stream_action

def normlize_point(point, wm_size):
    """
    Normalize a point based on the window manager size.
    """
    real_world_point = ((float(point[0])) / wm_size[0], (float(point[1])) / wm_size[1])
    return real_world_point


def act_on_device(device_id, action, print_command = False, refush_app = True, device_wm_size = None):
    """
    Perform an action on a specific device.
    """
    adb_command = _get_adb_command(device_id)

    if action['action_type'] == "Click":

        if device_wm_size is None:
            real_point = action['args']['point']
        else:
            normalized_point = action['args']['normalized_point']
            real_point = (int(normalized_point[0] * device_wm_size[0]), int(normalized_point[1] * device_wm_size[1]))
        adb_command += f" shell input tap {real_point[0]} {real_point[1]}"

    
        # print(f"Executing command: {adb_command}")
    elif action['action_type'] == "Awake":
        app_name = action['args']['text']

        package_name = find_package_name(app_name)
        
        if package_name is None:
            raise ValueError(f"App {app_name} not found in package map.")
        # adb shell monkey -p com.sankuai.meituan -c android.intent.category.LAUNCHER 1

        if refush_app:
            refush_command = f"{adb_command} shell am force-stop {package_name}"
            if print_command:
                print(f"Executing command: {refush_command}")
            subprocess.run(refush_command, shell=True, capture_output=True, text=True)

        # else:
        adb_command = f"{adb_command} shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1"
        time.sleep(2)

        # adb_command += f" shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1"

    elif action['action_type'] == "Type":
        text = action['args']['text']
        # adb_command += f" shell input text '{text}'"
        # adb shell app_process -Djava.class.path=/data/local/tmp/yadb /data/local/tmp com.ysbing.yadb.Main -keyboard 你好，世界

        if device_wm_size is None:
            point = action['args']['point']
        else:
            normalized_point = action['args']['normalized_point']
            point = (int(normalized_point[0] * device_wm_size[0]), int(normalized_point[1] * device_wm_size[1]))
            
        if "keyboard_exists" in action['args'] and not action['args']['keyboard_exists']:
            click_commmand = f"{adb_command} shell input tap {point[0]} {point[1]}"
            subprocess.run(click_commmand, shell=True, capture_output=True, text=True)


        adb_command += f' shell app_process -Djava.class.path=/data/local/tmp/yadb /data/local/tmp com.ysbing.yadb.Main -keyboard "{text}"'

    elif action['action_type'] == "Pop":
        if print_command:
            print("Pop action received; no device command executed.")
        return

    elif action['action_type'] == "Wait":
        wait_time = action['args']['duration']
        time.sleep(float(wait_time))

        return
    
    elif action['action_type'] == "Scroll":
        path = action['args']['path']

        if device_wm_size is not None:  
            normalized_path = action['args']['normalized_path']
            path = [(int(normalized_path[0][0] * device_wm_size[0]), int(normalized_path[0][1] * device_wm_size[1])),
                    (int(normalized_path[1][0] * device_wm_size[0]), int(normalized_path[1][1] * device_wm_size[1]))]

        adb_command += f" shell input swipe {path[0][0]} {path[0][1]} {path[1][0]} {path[1][1]} 1000"

    elif action['action_type'] == "LongPress":
        # adb shell app_process -Djava.class.path=/data/local/tmp/yadb /data/local/tmp com.ysbing.yadb.Main -touch 500 500 2000

        if device_wm_size is None:
            point = action['args']['point']
        else:
            normalized_point = action['args']['normalized_point']
            point = (int(normalized_point[0] * device_wm_size[0]), int(normalized_point[1] * device_wm_size[1]))

        adb_command += f" shell app_process -Djava.class.path=/data/local/tmp/yadb /data/local/tmp com.ysbing.yadb.Main -touch {point[0]} {point[1]} 2000"

    elif action['action_type'] == "Abort":
        if print_command:
            abort_reason = action.get('args', {}).get('abort_reason')
            if abort_reason:
                print(f"Abort action received: {abort_reason}")
            else:
                print("Abort action received.")
        return

    elif action['action_type'] == "Complete":
        if print_command:
            print("Complete action received.")
        return

    else:
        raise ValueError(f"Invalid action type: {action['action_type']}")

    if print_command:
        print(f"Executing command: {adb_command}")

    result = subprocess.run(adb_command, shell=True, capture_output=True, text=True)

    if print_command:
        print(f"Command output: {result.stdout}")


def default_reply_method(task, envs, actions, question):
    """
    Default reply method for the evaluation.
    :param task: The task to evaluate.
    :param envs: The environments to evaluate the task on.
    :param actions: The actions taken during the evaluation.
    :param question: The question to ask the model.
    :return: The model's reply.
    """
    

    return "Choose the second one."

class BaseMoboleActionHelper:
    def __init__(self, device_id = None):
        self.device_id = device_id
        self.wm_size = get_device_wm_size(self.device_id)
        if self.device_id is not None:
            init_device(self.device_id, print_command=True)
            # _open_screen(self.device_id, print_command=True)

        pass

    def set_device_id(self, device_id):
        """
        Set the device ID for the mobile action helper.
        """
        self.device_id = device_id
        self.wm_size = get_device_wm_size(self.device_id)
    
    def get_device_id(self):
        """
        Get the device ID for the mobile action helper.
        """
        return self.device_id
    
    def step_interaction(self, action, capture_duration = 0.5, image_full_path = None, user_comment = None):
        """
        Perform a step interaction on the device, and get the observation.
        """

        # to make sure the screen is on
        _open_screen(self.device_id)
        
        user_comment = ""
        if action is not None and action['action_type'] not in ['INFO', 'COMPLETE', 'ABORT']:
            # to convert vthe action to front-end action
            front_end_action = model_act2front_act(action, self.wm_size)

            # to perform the action
            act_on_device(self.device_id, front_end_action) 

        elif action is not None and action['action_type'] == "INFO":
            # to convert the action to front-end action
            front_end_action = model_act2front_act(action, self.wm_size)

            value = front_end_action['args']['text']
            
            # to ask the user to input the value
            if user_comment is None:
                user_comment = input(f"Please answer the model's question: {value}: ")

        
        elif action is not None and action['action_type'] in ["COMPLETE", "ABORT"]:
            
            return None

        # to wait for the action to be completed
        time.sleep(capture_duration)

        is_screenshot = False

        # to get the observation
        for i in range(3):
            try:
                screen_shot_pic_path = _capture_save_screenshot(self.device_id, tmp_file_dir="tmp_screenshot", print_command=True)
                is_screenshot = True
                break
            except Exception as e:
                print(f"Error capturing screenshot: {e}")
                time.sleep(0.5)


        if not is_screenshot:
            raise ValueError(f"Error capturing screenshot: {e}")
        # to check if the screenshot is valid

        if image_full_path is not None:
            # to copy the image to the full path
            smart_copy(screen_shot_pic_path, image_full_path)
            screen_shot_pic_path = image_full_path
            

        observation = {
            "image": screen_shot_pic_path,
            "user_comment": user_comment,
        }

        return observation
        





    

if __name__ == "__main__":

    print(get_device_wm_size("bc23727a"))
    
    open_screen(None, print_command=True)
    pass