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

# ===== 配置变量定义 (全局作用域) =====
tmp_rollout_config = local_model_config

# ===== 中央配置：设备能力与任务队列=====
DEVICE_CAPABILITIES = {
    "FIRST_DEVICE": {"tag": "SHOPPING_CONSUMPTION"}, 
    "SECOND_DEVICE": {"tag": "VIDEO_STREAMING"}, 
}

JOB_QUEUE = [
    {"task": "在淘宝上搜索并下单一个键盘", "required_tag": "SHOPPING_CONSUMPTION"},
    {"task": "打开爱奇艺，播放《疯狂动物城》", "required_tag": "VIDEO_STREAMING"},
    {"task": "检查微信是否有未读消息", "required_tag": "SOCIAL_MEDIA"}, 
]

# ===== 用于记录每步耗时 =====
_step_times = []

# 全局字典，用于存储 scrcpy 的实际 PID (而非 Shell/CMD 的 PID)
scrcpy_pids_to_kill = {} 


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

# ===== 在单个设备上运行任务的封装（移除线程内清理，仅执行任务） =====
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
        
        print(f"\n>>>> 任务开始在设备: {device_id} 上执行 (任务: {task[:10]}...) <<<<")
        evaluate_task_on_device(l2_server, device_info, task, tmp_rollout_config, reflush_app=True)
        print(f">>>> 任务执行完毕 (设备: {device_id}) <<<<\n")
        
    except Exception as e:
        print(f"任务执行过程中发生错误 (设备: {device_id}): {e}")
        
    finally:
        pass


# ===== scrcpy 基础路径定义 =====
SCRCPY_BASE_DIR = os.path.join("copilot_tools", "scrcpy")


# ===== 动态获取 scrcpy 路径  =====
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

# ===== 【新增】获取当前所有 scrcpy 进程的 PID 集合 (跨平台) =====
def get_scrcpy_pids(scrcpy_path):
    system = platform.system()
    pids = set()
    
    if system == "Windows":
        try:
            # 查找所有名为 scrcpy.exe 的进程
            result = subprocess.run('tasklist /FI "IMAGENAME eq scrcpy.exe" /NH', capture_output=True, text=True, shell=True, check=False)
            
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split()
                    try:
                        pids.add(int(parts[1]))
                    except (ValueError, IndexError):
                        continue
        except Exception:
            pass
            
    elif system in ["Darwin", "Linux"]:
        try:
            # 查找所有包含 scrcpy 路径的进程
            result = subprocess.run(f'pgrep -f "{scrcpy_path}"', capture_output=True, text=True, shell=True, check=False)
            
            for pid_str in result.stdout.strip().split('\n'):
                if pid_str.strip():
                    try:
                        pids.add(int(pid_str))
                    except ValueError:
                        continue
        except Exception:
            pass
            
    return pids


# ===== 通过端口查找并终止 PID (跨平台兼容) =====
def terminate_process_by_port(port):
    """使用 Windows 的 netstat/taskkill 或 macOS/Linux 的 lsof/kill 终止占用指定端口的进程"""
    system = platform.system()
    
    if system == "Windows":
        # Windows 逻辑 (使用 netstat 和 taskkill)
        try:
            command = f'netstat -ano | findstr LISTEN | findstr :{port}'
            result = subprocess.run(command, capture_output=True, text=True, shell=True, check=False)
            
            if result.returncode != 0 or not result.stdout.strip():
                return
                
            pid_match = re.search(r'\s+(\d+)\s*$', result.stdout.strip().split('\n')[0])
            
            if pid_match:
                pid = pid_match.group(1)
                print(f"    -> [保险清理] 终止 PID {pid} (端口 {port})...")
                # 使用 taskkill /F /T 终止进程树
                subprocess.run(f"taskkill /PID {pid} /F /T", shell=True, check=False, capture_output=True)
                return
                
        except Exception as e:
            print(f"    -> [保险清理] 终止端口 {port} 失败 (Windows): {e}")
            
    elif system in ["Darwin", "Linux"]:
        # macOS/Linux 逻辑 (使用 lsof 和 kill)
        try:
            command = f'lsof -i tcp:{port} | grep LISTEN'
            result = subprocess.run(command, capture_output=True, text=True, shell=True, check=False)
            
            if not result.stdout.strip():
                return
                
            pid_match = re.search(r'\s+(\d+)\s+', result.stdout.strip().split('\n')[0])
            
            if pid_match:
                pid = pid_match.group(1)
                print(f"    -> [保险清理] 终止 PID {pid} (端口 {port})...")
                subprocess.run(f"kill -9 {pid}", shell=True, check=False, capture_output=True)
                return
                
        except Exception as e:
            print(f"    -> [保险清理] 终止端口 {port} 失败 (macOS/Linux): {e}")
        
# =============================================================

if __name__ == "__main__":
    # 1. 获取所有设备信息
    all_device_ids = list_devices()
    if not all_device_ids:
        print("未检测到任何 ADB 设备，请检查设备连接！")
        sys.exit(1)
        
    
    # 构建动态设备能力映射，并获取需要启动 scrcpy 的设备列表
    devices_to_start_scrcpy = []
    
    temp_device_map = DEVICE_CAPABILITIES.copy()
    DEVICE_CAPABILITIES = {}
    
    # 将配置中的占位符ID替换为实际的在线设备ID
    if len(all_device_ids) >= 1:
        DEVICE_CAPABILITIES[all_device_ids[0]] = temp_device_map.pop("FIRST_DEVICE")
        devices_to_start_scrcpy.append(all_device_ids[0])
    if len(all_device_ids) >= 2:
        DEVICE_CAPABILITIES[all_device_ids[1]] = temp_device_map.pop("SECOND_DEVICE")
        devices_to_start_scrcpy.append(all_device_ids[1])
        
    
    scrcpy_ports = {} 
    # 使用全局的 scrcpy_pids_to_kill 字典
    
    total_start = time.time()
    task_threads = [] 
    
    START_X = 50 
    
    try:
        # 2. 动态获取 scrcpy 路径
        SCRCPY_PATH = get_scrcpy_path()
        SCRCPY_DIR = os.path.dirname(SCRCPY_PATH)
        print(f"scrcpy 路径确定为: {SCRCPY_PATH}")
        
        system = platform.system()

        # 3. 循环启动所有设备的 scrcpy 进程
        print(f"检测到 {len(devices_to_start_scrcpy)} 个配置的设备，正在启动 scrcpy 窗口...")
        
        #在启动前记录所有 scrcpy 进程的 PID
        initial_scrcpy_pids = get_scrcpy_pids(SCRCPY_PATH)
        
        start_port = 27183 
        offset_y = 50 
        OFFSET_STEP = 65 
        
        for i, device_id in enumerate(devices_to_start_scrcpy):
            window_position_arg = f"--window-x {START_X} --window-y {offset_y}"
            port_arg = f"-p {start_port}"
            
            # 跨平台启动命令的构建
            command_args = f'"{SCRCPY_PATH}" -s {device_id} {port_arg} {window_position_arg}'
            
            if system == "Windows":
                # 使用 start "" 来分离子进程
                scrcpy_command_str = f'start "" {command_args}'
            else:
                # 使用 nohup ... & 来分离子进程
                scrcpy_command_str = f'nohup {command_args} > /dev/null 2>&1 &' 
            
            # 启动 Shell/CMD 进程
            subprocess.Popen(
                scrcpy_command_str,
                shell=True,             
            )
            
            # 等待 scrcpy 窗口启动，并找到其真实的 PID
            time.sleep(1.5) # 给予 scrcpy 足够的启动时间
            
            current_scrcpy_pids = get_scrcpy_pids(SCRCPY_PATH)
            new_pids = current_scrcpy_pids - initial_scrcpy_pids
            
            if new_pids:
                # 找到新启动的 PID (通常只有一个)
                actual_pid = list(new_pids)[0] 
                # 记录实际 PID 用于后续终止
                scrcpy_pids_to_kill[device_id] = actual_pid
                initial_scrcpy_pids = current_scrcpy_pids # 更新初始列表供下一个设备使用
                print(f"设备 {device_id} 的 scrcpy 进程已启动 (端口: {start_port}, 实际PID: {actual_pid})...")
            else:
                print(f"警告: 未能找到设备 {device_id} 的 scrcpy 进程的实际 PID!")

            scrcpy_ports[device_id] = start_port

            offset_y += OFFSET_STEP 
            start_port += 1 
            
            if len(devices_to_start_scrcpy) > 1:
                 time.sleep(0.5) 

        # 4. 在执行任务前，等待 ADB 稳定
        if not wait_for_device_stability(devices_to_start_scrcpy):
            raise Exception("部分 ADB 连接未能稳定，任务终止。")
        
        # 5. 任务分配与并发执行
        assignment_batch = []
        available_devices = set(devices_to_start_scrcpy) 
        
        for job in JOB_QUEUE:
            required_tag = job['required_tag']
            assigned_now = None
            
            for device_id in available_devices:
                if DEVICE_CAPABILITIES.get(device_id, {}).get('tag') == required_tag:
                    
                    assignment_batch.append({
                        "device_id": device_id,
                        "task": job['task'],
                        "port": scrcpy_ports[device_id] 
                    })
                    assigned_now = device_id
                    break 
            
            if assigned_now:
                available_devices.remove(assigned_now) 
                
        
        if not assignment_batch:
            print("\n没有找到匹配的任务和设备上下文，跳过任务执行。")
        else:
            print(f"\n>>>> 正在 {len(assignment_batch)} 个设备上并发执行任务 (精确匹配模式) <<<<")
            
            for assignment in assignment_batch:
                device_id = assignment['device_id']
                task = assignment['task']
                
                thread = threading.Thread(
                    target=run_task_on_device,
                    args=(device_id, tmp_server_config, task) 
                )
                task_threads.append(thread)
                thread.start()
                
            for thread in task_threads:
                thread.join()
                
            print("\n>>>> 所有并发任务执行完毕 <<<<")
        
    except FileNotFoundError as e:
        print(f"致命错误: {e}")
        
    except Exception as e:
        print(f"任务执行过程中发生错误: {e}")
        
    finally:
        # 6. 终止所有 scrcpy 进程和计时
        total_time = time.time() - total_start
        print(f"总计执行时间为 {total_time:.2f} 秒")
        
        print("\n正在执行最终清理...")
        
        # 通过真实的 scrcpy PID 终止进程 (最可靠的方式)
        for device_id, pid in scrcpy_pids_to_kill.items():
             print(f"    -> 尝试通过实际 PID 终止设备 {device_id} 的 scrcpy 进程 (PID: {pid})...")
             try:
                 if platform.system() == "Windows":
                     # Windows 上使用 taskkill /F /T 来终止进程树
                     subprocess.run(f"taskkill /PID {pid} /F /T", shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 else:
                     # macOS/Linux 上使用 kill -9 终止进程
                     subprocess.run(f"kill -9 {pid}", shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 
                 print(f"    -> 设备 {device_id} 的 scrcpy 进程已终止。")
             except Exception as e:
                 print(f"    -> 终止 scrcpy 进程失败 ({device_id}): {e}")
        
        # 保险措施：通过端口终止残留进程
        print("\n    -> 执行端口进程的二次保险清理...")
        for port in scrcpy_ports.values():
            terminate_process_by_port(port)

    pass
