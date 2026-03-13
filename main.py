import sys
import os
import ctypes
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from src.ui.main_window import MainWindow
from src.utils.logger import logger


def get_icon_path():
    """获取图标路径，兼容开发环境和打包环境"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'vdian.ico')
    else:
        return os.path.join(os.path.dirname(__file__), 'src', 'ui', 'icon', 'vdian.ico')


def main():
    logger.info("=" * 50)
    logger.info("智能门锁产测工具启动")
    logger.info("=" * 50)

    # Windows下设置AppUserModelID，使任务栏显示自定义图标而非Python图标
    if sys.platform == 'win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('vdian.doorcheck.tool')

    app = QApplication(sys.argv)

    # 在QApplication级别设置图标
    icon_path = get_icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
