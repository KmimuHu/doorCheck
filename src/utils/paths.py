import os
import sys


def get_app_dir() -> str:
    """获取应用根目录：打包后返回 exe 所在目录，开发时返回项目根目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
