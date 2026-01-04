#!/usr/bin/env python3
"""
启动AutoGLM Web UI
"""

import os
import sys
import subprocess

def check_dependencies():
    """检查依赖是否安装"""
    try:
        import gradio as gr
        print("OK - Gradio已安装")
    except ImportError:
        print("ERROR - Gradio未安装，请运行: pip install -r requirements.txt")
        return False

    try:
        import PIL
        print("OK - Pillow已安装")
    except ImportError:
        print("ERROR - Pillow未安装，请运行: pip install -r requirements.txt")
        return False

    return True

def main():
    print("启动AutoGLM Web UI...")

    # 检查依赖
    if not check_dependencies():
        sys.exit(1)

    # 检查ADB
    print("检查ADB连接...")
    try:
        result = subprocess.run(["adb", "version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("OK - ADB已安装")
        else:
            print("WARNING - ADB未正确安装，请确保ADB已添加到系统PATH")
    except:
        print("WARNING - ADB未找到，请确保ADB已安装并添加到系统PATH")

    # 检查web_ui目录是否存在
    web_ui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_ui")
    if not os.path.exists(web_ui_dir):
        print("ERROR - web_ui目录不存在")
        sys.exit(1)

    # 将web_ui目录添加到Python路径
    sys.path.insert(0, web_ui_dir)

    # 启动Gradio应用
    print("\n正在启动Web界面...")
    print("正在尝试可用端口...")

    # 强制尝试清理端口 8866
    target_port = 8866
    print(f"\n检查端口 {target_port} 占用情况...")
    try:
        # Windows下查找占用端口的进程
        cmd_find = f"netstat -ano | findstr :{target_port}"
        result = subprocess.run(cmd_find, shell=True, capture_output=True, text=True)
        
        if result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    try:
                        # 排除自身进程
                        if int(pid) != os.getpid():
                            print(f"发现占用端口 {target_port} 的进程 PID: {pid}，正在尝试终止...")
                            subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                            print(f"进程 {pid} 已终止")
                    except ValueError:
                        pass
    except Exception as e:
        print(f"清理端口时出错: {e}")

    try:
        from app import create_ui
        
        demo, css, head = create_ui()
        
        print(f"访问地址: http://localhost:{target_port}")
        demo.launch(
            server_name="0.0.0.0",
            server_port=target_port,
            share=False,
            inbrowser=True,
            show_error=True,
            quiet=False,
            css=css,
            head=head
        )
    except Exception as e:
        print(f"ERROR - 启动失败: {e}")
        print("请确保已安装所有依赖：pip install -r requirements.txt")
        sys.exit(1)

if __name__ == "__main__":
    main()