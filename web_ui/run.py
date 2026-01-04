#!/usr/bin/env python3
"""
直接运行Web UI的脚本
"""

if __name__ == "__main__":
    import sys
    import os

    # 将当前目录添加到Python路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)

    try:
        from app import create_ui
        demo = create_ui()
        print("启动AutoGLM Web UI...")
        demo.launch(
            server_name="0.0.0.0",
            server_port=7861,  # 使用不同的端口
            share=False,
            inbrowser=True,
            show_error=True
        )
    except Exception as e:
        print(f"启动失败: {e}")
        print("请确保已安装所有依赖：pip install -r requirements.txt")