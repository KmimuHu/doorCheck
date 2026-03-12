import threading
import time

from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QMessageBox, QFileDialog, QSplitter, QDialog,
                             QLabel, QAction)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QFont
from zeroconf import Zeroconf, ServiceBrowser
import uuid

from .device_list_panel import DeviceListPanel
from .device_detail_panel import DeviceDetailPanel
from .test_record_panel import TestRecordPanel
from ..network.mdns_discovery import DeviceInfo, DeviceDiscoveryListener, MasterMdnsService
from ..network.mqtt_client import MQTTClient
from ..core.test_engine import TestEngine
from ..core.test_result import TestStatus
from ..hardware.label_printer import LabelPrinter
from ..network.http_server import ConfigServer
from ..network.mqtt_broker import MQTTBrokerManager
from ..core.protocol_message import DiscoverMessage
from ..network.tftp_server import TFTPServer
from ..data.test_record_storage import TestRecordStorage
from ..utils.config import Config
from ..utils.logger import logger


class CountdownDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('测试进行中')
        self.setModal(True)
        self.setFixedSize(400, 150)

        layout = QVBoxLayout()

        self.message_label = QLabel('正在测试...')
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setFont(QFont('Microsoft YaHei', 12))
        layout.addWidget(self.message_label)

        self.countdown_label = QLabel('')
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setFont(QFont('Microsoft YaHei', 24, QFont.Bold))
        self.countdown_label.setStyleSheet('color: #f44336;')
        layout.addWidget(self.countdown_label)

        self.setLayout(layout)

    def update_message(self, message: str, countdown: int = None):
        self.message_label.setText(message)
        if countdown is not None:
            self.countdown_label.setText(f'{countdown} 秒')
        else:
            self.countdown_label.setText('')


class TestThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(object)
    countdown_signal = pyqtSignal(str, int)

    def __init__(self, test_engine):
        super().__init__()
        self.test_engine = test_engine

    def _report_callback(self, event_type: str, countdown: int):
        if event_type == "emergency_countdown":
            self.countdown_signal.emit("请按应急开关", countdown)
        elif event_type == "transition":
            self.countdown_signal.emit("✅ 应急开关测试通过，请松开开关", countdown)
        elif event_type == "pairing_countdown":
            self.countdown_signal.emit("请按遥控器配对", countdown)
        elif event_type == "open_countdown":
            self.countdown_signal.emit("请按遥控器开门", countdown)
        elif event_type == "hide_dialog":
            self.countdown_signal.emit("__hide__", 0)

    def run(self):
        self.test_engine.set_progress_callback(lambda msg: self.progress_signal.emit(msg))
        result = self.test_engine.run_full_test(report_callback=self._report_callback)
        self.finished_signal.emit(result)


class OTAThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, test_engine, tftp_server_ip, tftp_port, firmware_name, file_size):
        super().__init__()
        self.test_engine = test_engine
        self.tftp_server_ip = tftp_server_ip
        self.tftp_port = tftp_port
        self.firmware_name = firmware_name
        self.file_size = file_size

    def run(self):
        try:
            success = self.test_engine.test_ota_upgrade(
                self.tftp_server_ip,
                self.tftp_port,
                self.firmware_name,
                self.file_size
            )
            if success:
                self.log_signal.emit("✅ OTA升级指令已接受，设备正在下载固件")
            else:
                self.log_signal.emit("❌ OTA升级失败")
            self.finished_signal.emit(success)
        except Exception as e:
            self.log_signal.emit(f"❌ OTA升级异常: {str(e)}")
            self.finished_signal.emit(False)


class SingleTestThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, test_engine, test_func):
        super().__init__()
        self.test_engine = test_engine
        self.test_func = test_func

    def run(self):
        self.test_engine.set_progress_callback(lambda msg: self.progress_signal.emit(msg))
        try:
            result = self.test_func()
            self.finished_signal.emit(result)
        except Exception as e:
            self.progress_signal.emit(f"❌ 测试异常: {str(e)}")
            self.finished_signal.emit(False)


class MainWindow(QMainWindow):
    device_found_signal = pyqtSignal(object)
    device_removed_signal = pyqtSignal(str)
    ota_progress_signal = pyqtSignal(str, int, int, int)
    ota_log_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.devices = {}                       # sn -> DeviceInfo
        self.selected_device_sn = None
        self.mqtt_client = None
        self.test_engine = None
        self.label_printer = LabelPrinter(self.config)
        self.test_record_storage = TestRecordStorage()
        self.zeroconf = None
        self.browser = None
        self.master_mdns = None
        self.config_server = None
        self.http_thread = None
        self.mqtt_broker = None
        self.broker_thread = None
        self.device_test_status = {}
        self.device_mqtt_clients = {}
        self.device_test_threads = {}
        self.broadcast_mqtt_client = None
        self.device_last_heartbeat = {}
        self.heartbeat_timeout = 90
        self.tftp_server = None
        self.device_ota_progress = {}
        self.device_ota_in_progress = set()
        self.current_firmware_path = None
        self.current_firmware_name = None
        self.device_ip_to_sn = {}
        self.countdown_dialog = None
        self.listener = None

        self.device_found_signal.connect(self._on_device_found_main_thread)
        self.device_removed_signal.connect(self._on_device_removed_main_thread)
        self.ota_progress_signal.connect(self._on_ota_progress_update)
        self.ota_log_signal.connect(self._emit_ota_log)

        self.init_ui()
        self.init_menu()
        self.connect_signals()
        self.start_mqtt_broker()
        self.start_http_server()
        self.start_device_discovery()
        self.init_broadcast_mqtt()
        self.start_heartbeat_monitor()
        self.start_tftp_server()

    def init_ui(self):
        self.setWindowTitle(f'{self.config.app_name} v{self.config.app_version}')
        self.setGeometry(100, 100, 1400, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout()

        splitter = QSplitter(Qt.Horizontal)

        self.device_list_panel = DeviceListPanel()
        self.device_list_panel.setMinimumWidth(300)
        splitter.addWidget(self.device_list_panel)

        self.device_detail_panel = DeviceDetailPanel()
        splitter.addWidget(self.device_detail_panel)

        splitter.setStretchFactor(0, 35)
        splitter.setStretchFactor(1, 65)
        splitter.setSizes([490, 910])

        main_layout.addWidget(splitter)
        central_widget.setLayout(main_layout)

        self.statusBar().showMessage("就绪")

    def init_menu(self):
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)  # 在窗口内显示菜单栏

        tools_menu = menubar.addMenu('工具')

        view_records_action = QAction('查看测试记录', self)
        view_records_action.triggered.connect(self.open_test_records)
        tools_menu.addAction(view_records_action)

    def open_test_records(self):
        """打开测试记录窗口"""
        dialog = QDialog(self)
        dialog.setWindowTitle('测试记录')
        dialog.setMinimumSize(1200, 700)

        layout = QVBoxLayout()
        record_panel = TestRecordPanel()
        layout.addWidget(record_panel)
        dialog.setLayout(layout)

        dialog.exec_()

    def connect_signals(self):
        # Device list signals
        self.device_list_panel.device_selected.connect(self._on_device_selected)
        self.device_list_panel.device_deleted.connect(self._on_device_deleted)
        self.device_list_panel.refresh_btn.clicked.connect(self.refresh_devices)

        # Device detail signals
        self.device_detail_panel.auto_test_clicked.connect(self._on_auto_test)
        self.device_detail_panel.test_clicked.connect(self._on_test_item)
        self.device_detail_panel.upload_firmware_clicked.connect(self.upload_firmware)
        self.device_detail_panel.ota_clicked.connect(self.start_ota_upgrade)
        self.device_detail_panel.print_label_clicked.connect(self.print_label)
        self.device_detail_panel.reset_config_clicked.connect(self.start_reset_config)

    # ---------------------------------------------------------------
    # Device selection
    # ---------------------------------------------------------------
    def _on_device_selected(self, sn: str):
        device = self.devices.get(sn)
        if not device:
            return

        self.selected_device_sn = sn
        self.device_detail_panel.set_device(device.sn, device.ip, device.model)

        # Restore previous test status
        status = self.device_test_status.get(sn, '')
        if status:
            if '通过' in status:
                self.device_detail_panel.update_auto_test_status("passed")
            elif '失败' in status:
                self.device_detail_panel.update_auto_test_status("failed")

        self.statusBar().showMessage(f"已选择设备: {sn} ({device.ip})")
        logger.info(f"选中设备: {sn} ({device.ip})")

    def _on_device_deleted(self, sn: str):
        reply = QMessageBox.question(
            self, '确认删除',
            f'确定要删除设备 {sn} 吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.device_removed_signal.emit(sn)

    # ---------------------------------------------------------------
    # Auto test (full test)
    # ---------------------------------------------------------------
    def _on_auto_test(self, sn: str):
        device = self.devices.get(sn)
        if not device:
            return

        self.device_detail_panel.update_auto_test_status("testing")
        self.device_detail_panel.set_testing(True)
        self.device_detail_panel.append_log(f"开始测试设备: {device.sn}")

        try:
            mqtt_client = self._ensure_mqtt_client(device)
            if not mqtt_client:
                return

            test_engine = TestEngine(mqtt_client, self.config)

            self.countdown_dialog = CountdownDialog(self)

            test_thread = TestThread(test_engine)
            test_thread.progress_signal.connect(self.device_detail_panel.append_log)
            test_thread.countdown_signal.connect(self._on_countdown_update)
            test_thread.finished_signal.connect(lambda result: self._on_test_finished(result, device))
            test_thread.start()

            self.device_test_threads[device.sn] = test_thread

        except Exception as e:
            self.device_detail_panel.set_testing(False)
            QMessageBox.critical(self, '错误', f'测试启动失败: {str(e)}')

    def _on_countdown_update(self, message: str, countdown: int):
        if message == "__hide__":
            if self.countdown_dialog:
                self.countdown_dialog.hide()
            return
        if self.countdown_dialog:
            self.countdown_dialog.update_message(message, countdown)
            if not self.countdown_dialog.isVisible():
                self.countdown_dialog.show()

    def _on_test_finished(self, result, device):
        if self.countdown_dialog:
            self.countdown_dialog.close()
            self.countdown_dialog = None

        self.device_detail_panel.set_testing(False)

        # 保存测试记录
        import uuid
        from datetime import datetime
        record = {
            'id': str(uuid.uuid4()),
            'device_sn': device.sn,
            'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'test_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'test_type': '一键测试',
            'status': 'passed' if result.status == TestStatus.PASSED else 'failed',
            'duration': result.duration,
            'steps': [{'name': s['name'], 'success': s['success'], 'message': s['message']} for s in result.steps]
        }
        self.test_record_storage.save_record(record)

        if result.status == TestStatus.PASSED:
            self.device_detail_panel.append_log("✅ 测试通过！")
            self.device_detail_panel.update_auto_test_status("passed")
            self.device_test_status[device.sn] = '✅ 通过'
            self.device_list_panel.update_device_status(device.sn, '✅ 通过')
        else:
            self.device_detail_panel.append_log(f"❌ 测试失败: {result.error_message}")
            self.device_detail_panel.update_auto_test_status("failed")
            status_text = f'❌ 失败'
            self.device_test_status[device.sn] = status_text
            self.device_list_panel.update_device_status(device.sn, status_text)
            QMessageBox.critical(self, '失败', f'测试失败:\n{result.error_message}')

    # ---------------------------------------------------------------
    # Individual test items
    # ---------------------------------------------------------------
    def _on_test_item(self, test_name: str, sn: str):
        device = self.devices.get(sn)
        if not device:
            return

        if test_name == "burn_mac":
            self.start_burn_mac(device)
        elif test_name == "remote_pairing":
            self.start_remote_pairing(device)
        elif test_name == "emergency_switch":
            self.start_emergency_switch_test(device)

    def start_burn_mac(self, device):
        self.device_detail_panel.update_test_result("burn_mac", "testing")
        self.device_detail_panel.append_log(f"开始烧写MAC地址: {device.sn}")

        try:
            mqtt_client = self._ensure_mqtt_client(device)
            if not mqtt_client:
                return

            test_engine = TestEngine(mqtt_client, self.config)

            success, message = test_engine.burn_mac_addresses(
                device.sn,
                lambda msg: self.device_detail_panel.append_log(msg)
            )

            if success:
                self.device_detail_panel.append_log(f"✅ {message}")
                self.device_detail_panel.update_test_result("burn_mac", "passed", message)
                QMessageBox.information(self, '成功', message)
            else:
                self.device_detail_panel.append_log(f"❌ {message}")
                self.device_detail_panel.update_test_result("burn_mac", "failed", message)
                QMessageBox.critical(self, '失败', message)

        except Exception as e:
            self.device_detail_panel.append_log(f"❌ 烧写MAC失败: {str(e)}")
            self.device_detail_panel.update_test_result("burn_mac", "failed")
            QMessageBox.critical(self, '错误', f'烧写MAC失败: {str(e)}')

    def start_remote_pairing(self, device):
        self.device_detail_panel.update_test_result("remote_pairing", "testing")
        self.device_detail_panel.append_log(f"开始遥控器配对: {device.sn}")

        try:
            mqtt_client = self._ensure_mqtt_client(device)
            if not mqtt_client:
                return

            test_engine = TestEngine(mqtt_client, self.config)

            QMessageBox.information(
                self,
                '遥控器配对测试',
                '即将进行遥控器配对测试\n\n'
                '1. 门锁将上锁\n'
                '2. 设备进入配对模式，请按遥控器配对按键\n'
                '3. 配对完成后，请按遥控器开门按键\n'
                '4. 系统将检测门锁是否开启\n\n'
                '请点击确定开始测试'
            )

            start_time = time.time()
            thread = SingleTestThread(test_engine, lambda: test_engine.test_remote_pairing())
            thread.progress_signal.connect(self.device_detail_panel.append_log)
            thread.finished_signal.connect(lambda success, st=start_time, te=test_engine: self._on_remote_pairing_finished(success, time.time() - st, te))
            thread.start()
            self._single_test_thread = thread

        except Exception as e:
            self.device_detail_panel.append_log(f"❌ 遥控器配对失败: {str(e)}")
            self.device_detail_panel.update_test_result("remote_pairing", "failed")
            QMessageBox.critical(self, '错误', f'遥控器配对失败: {str(e)}')

    def _on_remote_pairing_finished(self, success: bool, duration: float, test_engine):
        import uuid
        from datetime import datetime

        # 保存测试记录
        steps = [{'name': s['name'], 'success': s['success'], 'message': s['message']} for s in test_engine.result.steps]
        record = {
            'id': str(uuid.uuid4()),
            'device_sn': self.selected_device_sn,
            'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'test_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'test_type': '遥控器配对测试',
            'status': 'passed' if success else 'failed',
            'duration': round(duration, 2),
            'steps': steps
        }
        self.test_record_storage.save_record(record)

        if success:
            self.device_detail_panel.append_log("✅ 遥控器配对成功")
            self.device_detail_panel.update_test_result("remote_pairing", "passed")
            QMessageBox.information(self, '成功', '遥控器配对成功')
        else:
            self.device_detail_panel.append_log("❌ 遥控器配对失败")
            self.device_detail_panel.update_test_result("remote_pairing", "failed")
            QMessageBox.critical(self, '错误', '遥控器配对失败')

    def start_emergency_switch_test(self, device):
        self.device_detail_panel.update_test_result("emergency_switch", "testing")
        self.device_detail_panel.append_log(f"开始应急开关测试: {device.sn}")

        try:
            mqtt_client = self._ensure_mqtt_client(device)
            if not mqtt_client:
                return

            test_engine = TestEngine(mqtt_client, self.config)

            QMessageBox.information(
                self,
                '应急开关测试',
                '即将进行应急开关测试\n\n'
                '1. 门锁将上锁\n'
                '2. 请按应急开关\n'
                '3. 系统将在10秒内检测门锁是否开启\n\n'
                '请点击确定开始测试'
            )

            start_time = time.time()
            thread = SingleTestThread(test_engine, lambda: test_engine.test_emergency_switch(timeout=10))
            thread.progress_signal.connect(self.device_detail_panel.append_log)
            thread.finished_signal.connect(lambda success, st=start_time, te=test_engine: self._on_emergency_switch_finished(success, time.time() - st, te))
            thread.start()
            self._single_test_thread = thread

        except Exception as e:
            self.device_detail_panel.append_log(f"❌ 应急开关测试失败: {str(e)}")
            self.device_detail_panel.update_test_result("emergency_switch", "failed")
            QMessageBox.critical(self, '错误', f'应急开关测试失败: {str(e)}')

    def _on_emergency_switch_finished(self, success: bool, duration: float, test_engine):
        import uuid
        from datetime import datetime

        # 保存测试记录
        steps = [{'name': s['name'], 'success': s['success'], 'message': s['message']} for s in test_engine.result.steps]
        record = {
            'id': str(uuid.uuid4()),
            'device_sn': self.selected_device_sn,
            'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'test_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'test_type': '应急开关测试',
            'status': 'passed' if success else 'failed',
            'duration': round(duration, 2),
            'steps': steps
        }
        self.test_record_storage.save_record(record)

        if success:
            self.device_detail_panel.append_log("✅ 应急开关测试成功")
            self.device_detail_panel.update_test_result("emergency_switch", "passed")
            QMessageBox.information(self, '成功', '应急开关测试成功')
        else:
            self.device_detail_panel.append_log("❌ 应急开关测试失败")
            self.device_detail_panel.update_test_result("emergency_switch", "failed")
            QMessageBox.critical(self, '错误', '应急开关测试失败')

    # ---------------------------------------------------------------
    # Firmware & OTA
    # ---------------------------------------------------------------
    def upload_firmware(self):
        firmware_path, _ = QFileDialog.getOpenFileName(
            self,
            '选择固件文件',
            '',
            '固件文件 (*.fwpkg *.bin);;所有文件 (*.*)'
        )

        if not firmware_path:
            return

        if not self.tftp_server:
            QMessageBox.critical(self, '错误', 'TFTP服务器未启动')
            return

        try:
            import os
            self.tftp_server.set_firmware_file(firmware_path)
            self.current_firmware_path = firmware_path
            self.current_firmware_name = os.path.basename(firmware_path)

            file_size = os.path.getsize(firmware_path)
            size_mb = file_size / (1024 * 1024)

            self.device_detail_panel.update_firmware_status(self.current_firmware_name, size_mb)

            logger.info(f"固件已上传: {self.current_firmware_name}, 大小: {size_mb:.2f} MB")
            QMessageBox.information(self, '成功', f'固件已上传成功\n\n文件: {self.current_firmware_name}\n大小: {size_mb:.2f} MB')
        except Exception as e:
            logger.error(f"上传固件失败: {e}")
            QMessageBox.critical(self, '错误', f'上传固件失败: {str(e)}')

    def start_ota_upgrade(self, sn: str):
        device = self.devices.get(sn)
        if not device:
            return

        if not self.current_firmware_path:
            QMessageBox.warning(self, '警告', '请先上传固件文件')
            return

        if not self.tftp_server:
            QMessageBox.critical(self, '错误', 'TFTP服务器未启动\n\n请使用sudo运行程序')
            return

        if not self.tftp_server.firmware_data:
            QMessageBox.critical(self, '错误', '固件未加载到TFTP服务器\n\n请重新上传固件')
            return

        try:
            tftp_server_ip = self.tftp_server.host
            tftp_port = self.tftp_server.port

            self.device_detail_panel.append_log(f"开始OTA升级: {device.sn}")
            self.device_detail_panel.append_log(f"固件文件: {self.current_firmware_name}")
            self.device_detail_panel.append_log(f"TFTP服务器: {tftp_server_ip}:{tftp_port}")
            self.device_detail_panel.append_log(f"固件大小: {len(self.tftp_server.firmware_data)} 字节")

            logger.info(f"OTA升级 - 设备: {device.sn}, IP: {device.ip}")
            logger.info(f"OTA升级 - TFTP: {tftp_server_ip}:{tftp_port}/{self.current_firmware_name}")
            logger.info(f"OTA升级 - 固件大小: {len(self.tftp_server.firmware_data)} 字节")

            mqtt_client = self._ensure_mqtt_client(device)
            if not mqtt_client:
                return

            test_engine = TestEngine(mqtt_client, self.config)

            self.device_detail_panel.append_log("正在发送OTA升级指令...")
            file_size = len(self.tftp_server.firmware_data)

            self.device_ota_in_progress.add(device.sn)
            self.device_detail_panel.progress_bar.setVisible(True)
            self.device_detail_panel.progress_bar.setValue(0)

            ota_thread = OTAThread(test_engine, tftp_server_ip, tftp_port, self.current_firmware_name, file_size)
            ota_thread.log_signal.connect(lambda msg: self._emit_ota_log(device.sn, msg))
            ota_thread.finished_signal.connect(lambda success: self._on_ota_finished(device.sn, success))
            ota_thread.start()

            QMessageBox.information(self, '提示', 'OTA升级已启动\n设备正在下载固件')

        except Exception as e:
            self.device_detail_panel.append_log(f"❌ OTA升级异常: {str(e)}")
            QMessageBox.critical(self, '错误', f'OTA升级异常: {str(e)}')
            self.device_ota_in_progress.discard(device.sn)

    # ---------------------------------------------------------------
    # Print & Reset
    # ---------------------------------------------------------------
    def print_label(self, sn: str):
        device = self.devices.get(sn)
        if not device:
            return

        self.device_detail_panel.append_log(f"打印标签: {sn}")

        try:
            success = self.label_printer.print_label(sn, "PASSED")
            if success:
                self.device_detail_panel.append_log("标签打印成功")
            else:
                QMessageBox.warning(self, '警告', '标签打印失败')
        except Exception as e:
            QMessageBox.critical(self, '错误', f'打印失败: {str(e)}')

    def start_reset_config(self, sn: str):
        device = self.devices.get(sn)
        if not device:
            return

        reply = QMessageBox.warning(
            self,
            '确认重置',
            f'确定要重置设备 {sn} 的NV配置吗？\n\n'
            '此操作将清除NV区域的所有配置，包括：\n'
            '- MQTT配置\n'
            '- WiFi配置\n'
            '- 设备信息等\n\n'
            '操作后需要重启设备才能生效。',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.device_detail_panel.append_log(f"开始重置NV配置: {sn}")

        try:
            mqtt_client = self._ensure_mqtt_client(device)
            if not mqtt_client:
                return

            test_engine = TestEngine(mqtt_client, self.config)

            success, message = test_engine.reset_config(
                lambda msg: self.device_detail_panel.append_log(msg)
            )

            if success:
                self.device_detail_panel.append_log(f"✅ {message}")
                QMessageBox.information(self, '成功', f'{message}\n\n请重启设备使配置生效。')
            else:
                self.device_detail_panel.append_log(f"❌ {message}")
                QMessageBox.critical(self, '失败', message)

        except Exception as e:
            self.device_detail_panel.append_log(f"❌ 重置配置失败: {str(e)}")
            QMessageBox.critical(self, '错误', f'重置配置失败: {str(e)}')

    # ---------------------------------------------------------------
    # MQTT helper
    # ---------------------------------------------------------------
    def _ensure_mqtt_client(self, device):
        if device.sn not in self.device_mqtt_clients:
            mqtt_client = MQTTClient(
                self.config.mqtt_broker,
                self.config.mqtt_port,
                self.config.product_id,
                device.sn
            )

            if not mqtt_client.connect():
                QMessageBox.critical(self, '错误', 'MQTT连接失败')
                return None

            self.device_mqtt_clients[device.sn] = mqtt_client

        return self.device_mqtt_clients[device.sn]

    # ---------------------------------------------------------------
    # Network services
    # ---------------------------------------------------------------
    def start_mqtt_broker(self):
        try:
            self.mqtt_broker = MQTTBrokerManager(
                host='0.0.0.0',
                port=self.config.mqtt_port,
                ssl_enabled=True
            )
            self.broker_thread = threading.Thread(
                target=self.mqtt_broker.start,
                daemon=True
            )
            self.broker_thread.start()
            logger.info(f"MQTT Broker启动中: 0.0.0.0:{self.config.mqtt_port}")
        except Exception as e:
            logger.error(f"MQTT Broker启动失败: {e}")

    def start_http_server(self):
        try:
            self.config_server = ConfigServer(
                host='0.0.0.0',
                port=self.config.http_port,
                mqtt_broker=self.config.mqtt_broker,
                mqtt_port=self.config.mqtt_port,
                secret_key=self.config.device_psk
            )
            self.http_thread = threading.Thread(
                target=self.config_server.start,
                daemon=True
            )
            self.http_thread.start()
            logger.info(f"HTTP配置服务已启动: 0.0.0.0:{self.config.http_port}")
        except Exception as e:
            logger.error(f"HTTP配置服务启动失败: {e}")

    def start_tftp_server(self):
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()

            self.tftp_server = TFTPServer(host=local_ip, port=69)
            self.tftp_server.set_progress_callback(self._on_tftp_progress)
            self.tftp_server.start()
            logger.info(f"TFTP服务器已启动: {local_ip}:69")
        except Exception as e:
            logger.error(f"TFTP服务器启动失败: {e}")
            logger.warning("TFTP端口69需要管理员权限，请使用sudo运行")

    def init_broadcast_mqtt(self):
        try:
            self.broadcast_mqtt_client = MQTTClient(
                self.config.mqtt_broker,
                self.config.mqtt_port,
                self.config.product_id,
                "broadcast"
            )
            if self.broadcast_mqtt_client.connect():
                logger.info("广播MQTT客户端已连接")
                self.broadcast_mqtt_client.register_callback("heartbeat_monitor", self._on_heartbeat_received)
            else:
                logger.warning("广播MQTT客户端连接失败")
                self.broadcast_mqtt_client = None
        except Exception as e:
            logger.error(f"初始化广播MQTT客户端失败: {e}")
            self.broadcast_mqtt_client = None

    # ---------------------------------------------------------------
    # Device discovery
    # ---------------------------------------------------------------
    def start_device_discovery(self):
        logger.info("启动设备发现...")
        try:
            self.zeroconf = Zeroconf()

            self.master_mdns = MasterMdnsService(self.zeroconf, port=self.config.http_port)
            self.master_mdns.register()

            self.listener = DeviceDiscoveryListener(self.on_device_found, self.on_device_removed)
            self.browser = ServiceBrowser(self.zeroconf, self.config.mdns_service_type, self.listener)
        except Exception as e:
            logger.error(f"设备发现启动失败: {e}")

    def on_device_found(self, device: DeviceInfo):
        self.device_found_signal.emit(device)

    def on_device_removed(self, device_sn: str):
        self.device_removed_signal.emit(device_sn)

    # ---------------------------------------------------------------
    # Heartbeat
    # ---------------------------------------------------------------
    def start_heartbeat_monitor(self):
        self.heartbeat_timer = QTimer()
        self.heartbeat_timer.timeout.connect(self._check_device_heartbeat)
        self.heartbeat_timer.start(10000)
        logger.info("心跳监控已启动，检查间隔: 10秒")

    def _on_heartbeat_received(self, topic: str, message: dict):
        try:
            if "status" in topic:
                header = message.get("header", {})
                action = header.get("action", "")

                if action == "heartbeat":
                    device_info = header.get("device", {})
                    device_sn = device_info.get("sn", "")

                    if device_sn:
                        self.device_last_heartbeat[device_sn] = time.time()
                        logger.debug(f"收到设备 {device_sn} 心跳")
        except Exception as e:
            logger.error(f"处理心跳消息失败: {e}")

    def _check_device_heartbeat(self):
        current_time = time.time()
        offline_devices = []

        for device_sn, last_heartbeat in list(self.device_last_heartbeat.items()):
            if device_sn in self.device_ota_in_progress:
                continue
            if current_time - last_heartbeat > self.heartbeat_timeout:
                offline_devices.append(device_sn)
                logger.warning(f"设备 {device_sn} 心跳超时，已离线")

        for device_sn in offline_devices:
            self.device_removed_signal.emit(device_sn)

    def _check_offline_devices(self):
        current_time = time.time()
        offline_devices = []

        for sn, device in self.devices.items():
            last_heartbeat = self.device_last_heartbeat.get(sn, 0)
            if last_heartbeat > 0 and current_time - last_heartbeat > self.heartbeat_timeout:
                offline_devices.append(sn)
                logger.warning(f"刷新检测: 设备 {sn} 不在线，移除")

        for device_sn in offline_devices:
            self.device_removed_signal.emit(device_sn)

    # ---------------------------------------------------------------
    # Device found/removed handlers (main thread)
    # ---------------------------------------------------------------
    def _on_device_found_main_thread(self, device: DeviceInfo):
        existing = self.devices.get(device.sn)
        if existing:
            self.devices[device.sn] = device
            logger.info(f"更新设备: {device.get_display_name()} ({device.ip})")
        else:
            self.devices[device.sn] = device
            self.device_list_panel.add_device(device)
            logger.info(f"发现设备: {device.get_display_name()} ({device.ip})")

        self.device_last_heartbeat[device.sn] = time.time()
        self.device_ip_to_sn[device.ip] = device.sn

        if device.sn in self.device_ota_in_progress:
            self.device_ota_in_progress.discard(device.sn)
            logger.info(f"设备 {device.sn} OTA完成，重新上线")

        # Restore status on card
        status = self.device_test_status.get(device.sn)
        if status:
            self.device_list_panel.update_device_status(device.sn, status)

        self.statusBar().showMessage(f"发现设备: {device.sn}")

    def _on_device_removed_main_thread(self, device_sn: str):
        if device_sn not in self.devices:
            return

        del self.devices[device_sn]
        self.device_list_panel.remove_device(device_sn)

        if self.selected_device_sn == device_sn:
            self.selected_device_sn = None
            self.device_detail_panel.clear_device()

        if device_sn in self.device_mqtt_clients:
            self.device_mqtt_clients[device_sn].disconnect()
            del self.device_mqtt_clients[device_sn]

        if device_sn in self.device_test_threads:
            del self.device_test_threads[device_sn]

        if device_sn in self.device_test_status:
            del self.device_test_status[device_sn]

        if device_sn in self.device_last_heartbeat:
            del self.device_last_heartbeat[device_sn]

        if device_sn in self.device_ota_progress:
            del self.device_ota_progress[device_sn]

        for ip, sn in list(self.device_ip_to_sn.items()):
            if sn == device_sn:
                del self.device_ip_to_sn[ip]

        self.statusBar().showMessage(f"设备离线: {device_sn}")
        logger.info(f"设备离线: {device_sn}")

    # ---------------------------------------------------------------
    # OTA progress
    # ---------------------------------------------------------------
    def _on_tftp_progress(self, transfer_id: str, progress: int, sent_bytes: int, total_bytes: int):
        self.ota_progress_signal.emit(transfer_id, progress, sent_bytes, total_bytes)

    def _on_ota_progress_update(self, transfer_id: str, progress: int, sent_bytes: int, total_bytes: int):
        client_ip = transfer_id.split(':')[0]
        device_sn = self.device_ip_to_sn.get(client_ip)

        if not device_sn:
            return

        last_progress = self.device_ota_progress.get(device_sn, -1)
        if progress != last_progress and progress % 5 == 0:
            self.device_ota_progress[device_sn] = progress

            # Only update UI if this device is currently selected
            if device_sn == self.selected_device_sn:
                size_mb = total_bytes / (1024 * 1024)
                sent_mb = sent_bytes / (1024 * 1024)
                self.device_detail_panel.update_ota_progress(progress, sent_mb, size_mb)

            logger.info(f"设备 {device_sn} OTA进度: {progress}%")

        if progress >= 100 and device_sn in self.device_ota_in_progress:
            self.device_ota_in_progress.discard(device_sn)
            self.device_ota_progress.pop(device_sn, None)
            size_mb = total_bytes / (1024 * 1024)
            logger.info(f"设备 {device_sn} 固件传输完成，共 {size_mb:.2f} MB")

            if device_sn == self.selected_device_sn:
                self.device_detail_panel.append_log(f"✅ 固件传输完成，共 {size_mb:.2f} MB，请等待设备重启")
                self.device_detail_panel.hide_progress_bar()

            QMessageBox.information(self, 'OTA升级', f'固件传输完成\n\n设备: {device_sn}\n大小: {size_mb:.2f} MB\n\n请等待设备重启')

    def _emit_ota_log(self, device_sn: str, message: str):
        if device_sn == self.selected_device_sn:
            self.device_detail_panel.append_log(message)

    def _on_ota_finished(self, device_sn: str, success: bool):
        if not success:
            self.device_ota_in_progress.discard(device_sn)

    # ---------------------------------------------------------------
    # Refresh devices
    # ---------------------------------------------------------------
    def refresh_devices(self):
        logger.info("开始刷新设备列表...")

        self._check_offline_devices()

        if self.broadcast_mqtt_client and self.broadcast_mqtt_client.connected:
            try:
                discover_msg = DiscoverMessage(self.config.device_psk)
                payload = discover_msg.to_json()

                if len(self.devices) == 0:
                    logger.info("当前没有已发现的设备，使用mDNS刷新")
                    if self.listener and self.zeroconf:
                        self.listener.refresh_all_devices(self.zeroconf, self.config.mdns_service_type)
                        logger.info("已触发mDNS设备刷新")
                    return

                for sn, device in self.devices.items():
                    try:
                        topic = f"{self.config.product_id}/{device.sn}/command"
                        self.broadcast_mqtt_client.client.publish(topic, payload, qos=1)
                        logger.info(f"向设备 {device.sn} 发送discover命令")
                    except Exception as e:
                        logger.error(f"向设备 {device.sn} 发送discover命令失败: {e}")

                logger.info(f"已向 {len(self.devices)} 个设备发送discover命令")

            except Exception as e:
                logger.error(f"广播discover命令失败: {e}")
        else:
            logger.warning("广播MQTT客户端未连接，使用mDNS刷新")
            if self.listener and self.zeroconf:
                try:
                    self.listener.refresh_all_devices(self.zeroconf, self.config.mdns_service_type)
                    logger.info("已触发mDNS设备刷新")
                except Exception as e:
                    logger.error(f"刷新设备失败: {e}")

    # ---------------------------------------------------------------
    # Close
    # ---------------------------------------------------------------
    def closeEvent(self, event):
        for mqtt_client in self.device_mqtt_clients.values():
            mqtt_client.disconnect()

        if self.broadcast_mqtt_client:
            self.broadcast_mqtt_client.disconnect()

        if self.mqtt_broker:
            self.mqtt_broker.stop()
        if self.tftp_server:
            self.tftp_server.stop()
        if self.master_mdns:
            self.master_mdns.unregister()
        if self.zeroconf:
            self.zeroconf.close()
        event.accept()
