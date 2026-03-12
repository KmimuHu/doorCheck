import sys
from PyQt5.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.utils.logger import logger


def main():
    logger.info("=" * 50)
    logger.info("智能门锁产测工具启动")
    logger.info("=" * 50)
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
