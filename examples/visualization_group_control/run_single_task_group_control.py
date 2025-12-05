import os
import sys
import time
import subprocess 
import platform 
import re 
import threading 

if "." not in sys.path:
    sys.path.append(".")

from copilot_agent_client.pu_client import evaluate_task_on_device
from copilot_front_end.mobile_action_helper import list_devices, get_device_wm_size
from copilot_agent_server.local_server import LocalServer

tmp_server_config = {
    "log_dir": "running_log/server_log/os-copilot-local-eval-logs/traces",
    "image_dir": "running_log/server_server/os-copilot-local-eval-logs/images",
    "debug": False
}


local_model_config = {
    "task_type": "parser_0922_summary",
    "model_config": {
        "model_name": "gelab-zero-4b-preview",
        "model_provider": "local",
        "args": {
            "temperature": 0.1,
            "top_p": 0.95,
            "frequency_penalty": 0.0,
            "max_tokens": 4096,
        },
    },

    "max_steps": 400,
    "delay_after_capture": 2,
    "debug": False
}

# ===== 将配置变量定义移到全局作用域 =====
tmp_rollout_config = local_model_config

# ===== 用于记录每步耗时=====
_step_times = []


# ===== 包装 automate_step 方法 =====
def wrap_automate_step_with_timing(server_instance):
    original_method = server_instance.automate_step

    def timed_automate_step(payload):
        step_start = time.time()
        try:
            result = original_method(payload)
        finally:
            duration = time.time() - step_start
            _step_times.append(duration)
            print(f"[Thread {threading.get_ident()}] Step {len(_step_times)} took: {duration:.2f} seconds") 
        return result

    server_instance.automate_step = timed_automate_step

# ===== 等待目标设备重新稳定上线 =====
def wait_for_device_stability(target_device_ids, timeout=10, interval=0.5):
    print(f"\n等待 {len(target_device_ids)} 个设备在 ADB 中稳定...")
    start_time = time.time()
    
    devices_to_wait_for = set(target_device_ids)
    
    while time.time() - start_time < timeout and devices_to_wait_for:
        try:
            connected_devices = list_devices()
            
            stable_now = devices_to_wait_for.intersection(set(connected_devices))
            if stable_now:
                print(f"  -> 设备 {list(stable_now)} 已稳定连接。")
                devices_to_wait_for -= stable_now
                
        except Exception:
            pass 
            
        if devices_to_wait_for:
            time.sleep(interval)
        
    if devices_to_wait_for:
        print(f"错误：等待设备 {list(devices_to_wait_for)} 超时 ({timeout}秒)，任务终止。")
        return False
        
    print("所有目标设备已稳定连接。")
    return True

# ===== 在单个设备上运行任务的封装 =====
def run_task_on_device(device_id, tmp_server_config, task):
    global tmp_rollout_config 
    
    l2_server = LocalServer(tmp_server_config)
    wrap_automate_step_with_timing(l2_server)
    
    try:
        device_wm_size = get_device_wm_size(device_id)
        device_info = {
            "device_id": device_id,
            "device_wm_size": device_wm_size
        }
        
        print(f"\n>>>> 任务开始在设备: {device_id} 上执行 <<<<")
        evaluate_task_on_device(l2_server, device_info, task, tmp_rollout_config, reflush_app=True)
        print(f">>>> 任务执行完毕 (设备: {device_id}) <<<<\n")
        
    except Exception as e:
        print(f"任务执行过程中发生错误 (设备: {device_id}): {e}")
        
# ===== scrcpy 基础路径定义=====
SCRCPY_BASE_DIR = os.path.join("copilot_tools", "scrcpy")


# ===== 动态获取 scrcpy 路径=====
def get_scrcpy_path():
    """根据操作系统，返回 SCRCPY_BASE_DIR 文件夹中的 scrcpy 可执行文件路径"""
    
    system = platform.system()
    
    if system == "Windows":
        path = os.path.join(SCRCPY_BASE_DIR, "win", "scrcpy.exe")
    elif system == "Darwin": # macOS
        path = os.path.join(SCRCPY_BASE_DIR, "mac", "scrcpy")
    elif system == "Linux":
        path = os.path.join(SCRCPY_BASE_DIR, "linux", "scrcpy")
    else:
        raise OSError(f"不支持的操作系统: {system}")
        
    
    if not os.path.exists(path):
        if system == "Linux":
            try:
                subprocess.run(["scrcpy", "-h"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "scrcpy"
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        
        raise FileNotFoundError(f"scrcpy 可执行文件未找到，请检查路径: {os.path.abspath(path)}")

    return os.path.abspath(path)

# ===== 通过端口查找并终止 PID (Windows Only) =====
def terminate_process_by_port(port):
    """使用 netstat 和 taskkill 终止占用指定端口的进程"""
    if platform.system() != "Windows":
        return 
        
    try:
        command = f'netstat -ano | findstr LISTEN | findstr :{port}'
        result = subprocess.run(command, capture_output=True, text=True, shell=True, check=False)
        
        if result.returncode != 0 or not result.stdout.strip():
            return
            
        pid_match = re.search(r'\s+(\d+)\s*$', result.stdout.strip().split('\n')[0])
        
        if pid_match:
            pid = pid_match.group(1)
            print(f"    -> 终止 PID {pid} (端口 {port})...")
            subprocess.run(f"taskkill /PID {pid} /F", shell=True, check=True, capture_output=True)
            return
            
    except Exception as e:
        print(f"    -> 终止端口 {port} 失败: {e}")
        
# =============================================================

if __name__ == "__main__":
    # 1. 获取所有设备信息
    all_device_ids = list_devices()
    if not all_device_ids:
        print("未检测到任何 ADB 设备，请检查设备连接！")
        sys.exit(1)
        
    devices_to_task = all_device_ids 
    
    # task = "去淘宝帮我买本书"
    task = "打开爱奇艺，播放《疯狂动物城》"

    scrcpy_ports = [] 
    total_start = time.time()
    task_threads = [] 
    
    START_X = 50 
    
    try:
        # 2. 动态获取 scrcpy 路径
        SCRCPY_PATH = get_scrcpy_path()
        SCRCPY_DIR = os.path.dirname(SCRCPY_PATH)
        print(f"scrcpy 路径确定为: {SCRCPY_PATH}")

        # 3. 循环启动所有设备的 scrcpy 进程
        print(f"检测到 {len(devices_to_task)} 个设备，正在为每个设备启动 scrcpy 窗口...")
        
        start_port = 27183 
        offset_y = 50 
        OFFSET_STEP = 65 
        
        for i, device_id in enumerate(devices_to_task):
            window_position_arg = f"--window-x {START_X} --window-y {offset_y}"
            port_arg = f"-p {start_port}"
            
            scrcpy_command_str = (
                f'start "" "{SCRCPY_PATH}" -s {device_id} '
                f'{port_arg} '
                f'{window_position_arg}' 
            )
            
            subprocess.Popen(
                scrcpy_command_str,
                shell=True,             
            )
            
            scrcpy_ports.append(start_port) 
            
            print(f"设备 {device_id} 的 scrcpy 进程已启动 (端口: {start_port})...")

            offset_y += OFFSET_STEP 
            start_port += 1 
            
            if len(devices_to_task) > 1:
                 time.sleep(1) 

        # 4. 在执行任务前，等待 ADB 稳定
        if not wait_for_device_stability(devices_to_task):
            raise Exception("部分 ADB 连接未能稳定，任务终止。")
        
        # 5. 并发执行任务
        print(f"\n>>>> 正在 {len(devices_to_task)} 个设备上并发执行任务 (独立 Server 模式) <<<<")
        
        for device_id in devices_to_task:
            thread = threading.Thread(
                target=run_task_on_device,
                # 【修改】移除 tmp_rollout_config 参数
                args=(device_id, tmp_server_config, task) 
            )
            task_threads.append(thread)
            thread.start()
            
        # 6. 等待所有任务线程完成
        for thread in task_threads:
            thread.join()
            
        print("\n>>>> 所有并发任务执行完毕 <<<<")
        
    except FileNotFoundError as e:
        print(f"致命错误: {e}")
        
    except Exception as e:
        print(f"任务执行过程中发生错误: {e}")
        
    finally:
        # 7. 终止所有 scrcpy 进程和计时
        total_time = time.time() - total_start
        print(f"总计执行时间为 {total_time:.2f} 秒")
        
        print("\n正在关闭所有 scrcpy 镜像窗口...")
        for port in scrcpy_ports:
            terminate_process_by_port(port)

    pass