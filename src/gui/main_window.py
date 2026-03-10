import sys
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QTextEdit, QTableWidget, QTableWidgetItem,
                             QLabel, QMessageBox, QHeaderView, QSplitter, QGroupBox,
                             QFrame, QTabWidget, QFileDialog, QInputDialog, QDialog,
                             QDialogButtonBox, QLineEdit, QFormLayout, QProgressBar)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette
import threading
import time
from zeroconf import Zeroconf, ServiceBrowser
from typing import List

from ..discovery.mdns_discovery import DeviceInfo, DeviceDiscoveryListener, MasterMdnsService
from ..communication.mqtt_client import MQTTClient
from ..testing.test_engine import TestEngine
from ..testing.test_result import TestStatus
from ..printing.label_printer import LabelPrinter
from ..http_server.config_server import ConfigServer
from ..mqtt_broker.broker_manager import MQTTBrokerManager
from ..protocol.message import DiscoverMessage
from ..tftp_server.tftp_server import TFTPServer
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
        self.countdown_label.setStyleSheet('color: #e74c3c;')
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


class MainWindow(QMainWindow):
    device_found_signal = pyqtSignal(object)
    device_removed_signal = pyqtSignal(str)
    ota_progress_signal = pyqtSignal(str, int, int, int)
    ota_log_signal = pyqtSignal(str, str)
    
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.devices = []
        self.selected_device = None
        self.mqtt_client = None
        self.test_engine = None
        self.label_printer = LabelPrinter(self.config)
        self.zeroconf = None
        self.browser = None
        self.master_mdns = None
        self.config_server = None
        self.http_thread = None
        self.mqtt_broker = None
        self.broker_thread = None
        self.device_test_status = {}
        self.device_log_widgets = {}
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
        
        self.device_found_signal.connect(self._on_device_found_main_thread)
        self.device_removed_signal.connect(self._on_device_removed_main_thread)
        self.ota_progress_signal.connect(self._on_ota_progress_update)
        self.ota_log_signal.connect(self._emit_ota_log)
        
        self.init_ui()
        self.start_mqtt_broker()
        self.start_http_server()
        self.start_device_discovery()
        self.init_broadcast_mqtt()
        self.start_heartbeat_monitor()
        self.start_tftp_server()
    
    def init_ui(self):
        self.setWindowTitle('智能门锁产测工具 v1.0')
        self.setGeometry(100, 100, 1400, 800)
        
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fa;
            }
            QLabel {
                color: #2c3e50;
            }
            QPushButton {
                background-color: #3498db;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
            QTableWidget {
                background-color: white;
                border: 1px solid #dfe6e9;
                border-radius: 6px;
                gridline-color: #ecf0f1;
            }
            QTableWidget::item {
                padding: 8px;
                color: #2c3e50;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: #2c3e50;
            }
            QHeaderView::section {
                background-color: #34495e;
                color: white;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
            QTextEdit {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: 1px solid #34495e;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
            QGroupBox {
                background-color: white;
                border: 2px solid #3498db;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 12px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 4px 10px;
                background-color: #3498db;
                color: white;
                border-radius: 4px;
                left: 10px;
            }
        """)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        central_widget.setLayout(main_layout)
        
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498db, stop:1 #2980b9);
                border-radius: 6px;
                padding: 8px 15px;
            }
        """)
        header_layout = QHBoxLayout()
        header_frame.setLayout(header_layout)
        
        title_label = QLabel('🔐 智能门锁产测工具')
        title_label.setFont(QFont('Microsoft YaHei', 14, QFont.Bold))
        title_label.setStyleSheet('color: white;')
        header_layout.addWidget(title_label)
        
        version_label = QLabel('v1.0')
        version_label.setFont(QFont('Microsoft YaHei', 9))
        version_label.setStyleSheet('color: rgba(255, 255, 255, 0.8);')
        header_layout.addWidget(version_label)
        
        header_layout.addStretch()
        
        main_layout.addWidget(header_frame)
        
        content_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(content_splitter)
        
        top_widget = QWidget()
        top_layout = QVBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_widget.setLayout(top_layout)
        self.setup_device_table(top_layout)
        self.setup_control_buttons(top_layout)
        content_splitter.addWidget(top_widget)
        
        log_group = QGroupBox('📋 测试日志')
        log_group.setFont(QFont('Microsoft YaHei', 11, QFont.Bold))
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(10, 15, 10, 10)
        log_group.setLayout(log_layout)
        
        self.log_tabs = QTabWidget()
        self.log_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #dfe6e9;
                background: white;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #ecf0f1;
                color: #2c3e50;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #3498db;
                color: white;
            }
            QTabBar::tab:hover {
                background: #bdc3c7;
            }
        """)
        log_layout.addWidget(self.log_tabs)
        content_splitter.addWidget(log_group)
        
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 2)
    
    def setup_device_table(self, layout):
        label = QLabel('📱 已发现设备列表')
        label.setFont(QFont('Microsoft YaHei', 11, QFont.Bold))
        label.setStyleSheet('color: #2c3e50; padding: 5px 0;')
        layout.addWidget(label)
        
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(12)
        self.device_table.setHorizontalHeaderLabels(['设备SN', '型号', 'IP地址', '端口', '测试状态', '测试', '烧写', '遥控器配对', '应急开关', 'OTA', '打印', '重置'])
        self.device_table.setAlternatingRowColors(True)
        self.device_table.verticalHeader().setDefaultSectionSize(70)
        self.device_table.setStyleSheet(self.device_table.styleSheet() + """
            QTableWidget {
                alternate-background-color: #f8f9fa;
            }
            QTableWidget::item {
                padding: 4px;
            }
        """)
        self.device_table.setWordWrap(True)
        header = self.device_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(10, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(11, QHeaderView.ResizeToContents)
        self.device_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.device_table.setSelectionMode(QTableWidget.SingleSelection)
        self.device_table.verticalHeader().setVisible(False)
        self.device_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.device_table)
    
    def setup_control_buttons(self, layout):
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.setContentsMargins(0, 5, 0, 5)
        
        self.refresh_btn = QPushButton('🔄 刷新设备')
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        self.refresh_btn.clicked.connect(self.refresh_devices)
        button_layout.addWidget(self.refresh_btn)
        
        self.upload_firmware_btn = QPushButton('📦 上传固件')
        self.upload_firmware_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        self.upload_firmware_btn.clicked.connect(self.upload_firmware)
        button_layout.addWidget(self.upload_firmware_btn)
        
        self.firmware_status_label = QLabel('固件: 未上传')
        self.firmware_status_label.setStyleSheet('color: #7f8c8d; font-size: 12px; padding: 0 10px;')
        button_layout.addWidget(self.firmware_status_label)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
    
    def create_device_log_widget(self, device_sn: str):
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setAlignment(Qt.AlignCenter)
        progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #34495e;
                border-radius: 3px;
                background-color: #2c3e50;
                height: 24px;
                margin: 5px;
                color: #ecf0f1;
                font-weight: bold;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 2px;
            }
        """)
        progress_bar.setVisible(False)
        progress_bar.setFormat("%p%")
        layout.addWidget(progress_bar)
        
        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setFont(QFont('Consolas', 9))
        log_text.setStyleSheet("""
            QTextEdit {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: none;
                padding: 8px;
            }
        """)
        layout.addWidget(log_text)
        
        container.setLayout(layout)
        
        self.log_tabs.addTab(container, f"📱 {device_sn}")
        
        self.device_log_widgets[device_sn] = {
            'log_text': log_text,
            'progress_bar': progress_bar,
            'tab_index': self.log_tabs.count() - 1
        }
        
        return log_text
    
    def remove_device_log_widget(self, device_sn: str):
        if device_sn in self.device_log_widgets:
            widget_info = self.device_log_widgets[device_sn]
            tab_index = widget_info['tab_index']
            self.log_tabs.removeTab(tab_index)
            
            for sn, info in self.device_log_widgets.items():
                if info['tab_index'] > tab_index:
                    info['tab_index'] -= 1
            
            del self.device_log_widgets[device_sn]
    
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
        
        for device in self.devices:
            last_heartbeat = self.device_last_heartbeat.get(device.sn, 0)
            if last_heartbeat > 0 and current_time - last_heartbeat > self.heartbeat_timeout:
                offline_devices.append(device.sn)
                logger.warning(f"刷新检测: 设备 {device.sn} 不在线，移除")
        
        for device_sn in offline_devices:
            self.device_removed_signal.emit(device_sn)
    
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
            
            if device_sn in self.device_log_widgets:
                try:
                    widget_info = self.device_log_widgets[device_sn]
                    log_widget = widget_info['log_text']
                    progress_bar = widget_info['progress_bar']
                    
                    size_mb = total_bytes / (1024 * 1024)
                    sent_mb = sent_bytes / (1024 * 1024)
                    
                    if progress_bar and progress_bar.isVisible():
                        progress_bar.setValue(progress)
                    
                    log_widget.append(f"OTA升级进度: {progress}% ({sent_mb:.2f}/{size_mb:.2f} MB)")
                    logger.info(f"设备 {device_sn} OTA进度: {progress}%")
                except Exception as e:
                    logger.warning(f"更新OTA进度失败: {e}")
    
    def on_device_found(self, device: DeviceInfo):
        self.device_found_signal.emit(device)
    
    def on_device_removed(self, device_sn: str):
        self.device_removed_signal.emit(device_sn)
    
    def _on_device_found_main_thread(self, device: DeviceInfo):
        existing = next((d for d in self.devices if d.sn == device.sn), None)
        if existing:
            idx = self.devices.index(existing)
            self.devices[idx] = device
            logger.info(f"更新设备: {device.get_display_name()} ({device.ip})")
        else:
            self.devices.append(device)
            logger.info(f"发现设备: {device.get_display_name()} ({device.ip})")
        
        self.device_last_heartbeat[device.sn] = time.time()
        self.device_ip_to_sn[device.ip] = device.sn
        
        if device.sn in self.device_ota_in_progress:
            self.device_ota_in_progress.discard(device.sn)
            logger.info(f"设备 {device.sn} OTA完成，重新上线")
        
        self.update_device_table()
    
    def _on_device_removed_main_thread(self, device_sn: str):
        self.devices = [d for d in self.devices if d.sn != device_sn]
        self.remove_device_log_widget(device_sn)
        
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
        
        self.update_device_table()
        logger.info(f"设备离线: {device_sn}")
    
    def update_device_table(self):
        self.device_table.setRowCount(len(self.devices))
        for i, device in enumerate(self.devices):
            self.device_table.setItem(i, 0, QTableWidgetItem(device.get_display_name()))
            self.device_table.setItem(i, 1, QTableWidgetItem(device.model))
            self.device_table.setItem(i, 2, QTableWidgetItem(device.ip))
            self.device_table.setItem(i, 3, QTableWidgetItem(str(device.port)))
            
            status = self.device_test_status.get(device.sn, '未测试')
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.device_table.setItem(i, 4, status_item)
            
            test_btn = QPushButton('开始测试')
            test_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2ecc71;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 3px;
                    border: 1px solid #27ae60;
                    max-height: 26px;
                }
                QPushButton:hover {
                    background-color: #27ae60;
                    border-color: #229954;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border-color: #7f8c8d;
                }
            """)
            
            is_testing = device.sn in self.device_test_threads and self.device_test_threads[device.sn].isRunning()
            test_btn.setEnabled(not is_testing)
            
            test_btn.clicked.connect(lambda checked, d=device, row=i: self.start_test(d, row))
            self.device_table.setCellWidget(i, 5, test_btn)
            
            burn_mac_btn = QPushButton('烧写')
            burn_mac_btn.setStyleSheet("""
                QPushButton {
                    background-color: #16a085;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 3px;
                    border: 1px solid #138d75;
                    max-height: 26px;
                }
                QPushButton:hover {
                    background-color: #138d75;
                    border-color: #117a65;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border-color: #7f8c8d;
                }
            """)
            burn_mac_btn.clicked.connect(lambda checked, d=device: self.start_burn_mac(d))
            self.device_table.setCellWidget(i, 6, burn_mac_btn)
            
            pairing_btn = QPushButton('遥控器配对')
            pairing_btn.setStyleSheet("""
                QPushButton {
                    background-color: #9b59b6;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 3px;
                    border: 1px solid #8e44ad;
                    max-height: 26px;
                }
                QPushButton:hover {
                    background-color: #8e44ad;
                    border-color: #7d3c98;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border-color: #7f8c8d;
                }
            """)
            pairing_btn.clicked.connect(lambda checked, d=device: self.start_remote_pairing(d))
            self.device_table.setCellWidget(i, 7, pairing_btn)
            
            emergency_btn = QPushButton('应急开关')
            emergency_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 3px;
                    border: 1px solid #c0392b;
                    max-height: 26px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                    border-color: #a93226;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border-color: #7f8c8d;
                }
            """)
            emergency_btn.clicked.connect(lambda checked, d=device: self.start_emergency_switch_test(d))
            self.device_table.setCellWidget(i, 8, emergency_btn)
            
            ota_btn = QPushButton('OTA升级')
            ota_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f39c12;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 3px;
                    border: 1px solid #e67e22;
                    max-height: 26px;
                }
                QPushButton:hover {
                    background-color: #e67e22;
                    border-color: #d35400;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border-color: #7f8c8d;
                }
            """)
            ota_btn.clicked.connect(lambda checked, d=device: self.start_ota_upgrade(d))
            self.device_table.setCellWidget(i, 9, ota_btn)
            
            print_btn = QPushButton('打印标签')
            print_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e67e22;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 3px;
                    border: 1px solid #d35400;
                    max-height: 26px;
                }
                QPushButton:hover {
                    background-color: #d35400;
                    border-color: #ba4a00;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border-color: #7f8c8d;
                }
            """)
            print_btn.setEnabled(True)
            print_btn.clicked.connect(lambda checked, d=device: self.print_label(d))
            self.device_table.setCellWidget(i, 10, print_btn)

            reset_btn = QPushButton('重置')
            reset_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 3px;
                    border: 1px solid #c0392b;
                    max-height: 26px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                    border-color: #a93226;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    border-color: #7f8c8d;
                }
            """)
            reset_btn.clicked.connect(lambda checked, d=device: self.start_reset_config(d))
            self.device_table.setCellWidget(i, 11, reset_btn)
    
    
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
                
                for device in self.devices:
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
            
            self.firmware_status_label.setText(f'固件: {self.current_firmware_name} ({size_mb:.2f} MB)')
            self.firmware_status_label.setStyleSheet('color: #27ae60; font-size: 12px; padding: 0 10px;')
            
            logger.info(f"固件已上传: {self.current_firmware_name}, 大小: {size_mb:.2f} MB")
            QMessageBox.information(self, '成功', f'固件已上传成功\n\n文件: {self.current_firmware_name}\n大小: {size_mb:.2f} MB')
        except Exception as e:
            logger.error(f"上传固件失败: {e}")
            QMessageBox.critical(self, '错误', f'上传固件失败: {str(e)}')
    
    def start_test(self, device, row=None):
        if device.sn not in self.device_log_widgets:
            log_widget = self.create_device_log_widget(device.sn)
        else:
            log_widget = self.device_log_widgets[device.sn]['log_text']
        
        log_widget.append(f"开始测试设备: {device.sn}")
        
        try:
            mqtt_client = MQTTClient(
                self.config.mqtt_broker,
                self.config.mqtt_port,
                self.config.product_id,
                device.sn
            )
            
            if not mqtt_client.connect():
                QMessageBox.critical(self, '错误', 'MQTT连接失败')
                return
            
            self.device_mqtt_clients[device.sn] = mqtt_client
            
            test_engine = TestEngine(mqtt_client, self.config)
            
            self.countdown_dialog = CountdownDialog(self)
            
            test_thread = TestThread(test_engine)
            test_thread.progress_signal.connect(lambda msg: log_widget.append(msg))
            test_thread.countdown_signal.connect(self._on_countdown_update)
            test_thread.finished_signal.connect(lambda result: self.on_test_finished(result, device))
            test_thread.start()
            
            self.device_test_threads[device.sn] = test_thread
            
            self.update_device_table()
            
        except Exception as e:
            QMessageBox.critical(self, '错误', f'测试启动失败: {str(e)}')
    
    def _on_countdown_update(self, message: str, countdown: int):
        if self.countdown_dialog:
            self.countdown_dialog.update_message(message, countdown)
            if not self.countdown_dialog.isVisible():
                self.countdown_dialog.show()
    
    def on_test_finished(self, result, device):
        if self.countdown_dialog:
            self.countdown_dialog.close()
            self.countdown_dialog = None
        
        if device.sn in self.device_log_widgets:
            log_widget = self.device_log_widgets[device.sn]['log_text']
        else:
            log_widget = None
        
        if result.status == TestStatus.PASSED:
            if log_widget:
                log_widget.append("✅ 测试通过！")
            self.device_test_status[device.sn] = '✅ 通过'
        else:
            if log_widget:
                log_widget.append(f"❌ 测试失败: {result.error_message}")
            
            status_text = f'❌ 失败\n{result.error_message}'
            self.device_test_status[device.sn] = status_text
            
            QMessageBox.critical(self, '失败', f'测试失败:\n{result.error_message}')
        
        self.update_device_table()
    
    def print_label(self, device):
        if device.sn in self.device_log_widgets:
            log_widget = self.device_log_widgets[device.sn]['log_text']
            log_widget.append(f"打印标签: {device.sn}")
        
        try:
            success = self.label_printer.print_label(device.sn, "PASSED")
            if success:
                if device.sn in self.device_log_widgets:
                    self.device_log_widgets[device.sn]['log_text'].append("标签打印成功")
                # QMessageBox.information(self, '成功', '标签打印成功！')
            else:
                QMessageBox.warning(self, '警告', '标签打印失败')
        except Exception as e:
            QMessageBox.critical(self, '错误', f'打印失败: {str(e)}')
    
    def start_reset_config(self, device):
        reply = QMessageBox.warning(
            self,
            '确认重置',
            f'确定要重置设备 {device.sn} 的NV配置吗？\n\n'
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

        if device.sn not in self.device_log_widgets:
            log_widget = self.create_device_log_widget(device.sn)
        else:
            log_widget = self.device_log_widgets[device.sn]['log_text']

        log_widget.append(f"开始重置NV配置: {device.sn}")

        try:
            if device.sn not in self.device_mqtt_clients:
                mqtt_client = MQTTClient(
                    self.config.mqtt_broker,
                    self.config.mqtt_port,
                    self.config.product_id,
                    device.sn
                )

                if not mqtt_client.connect():
                    QMessageBox.critical(self, '错误', 'MQTT连接失败')
                    return

                self.device_mqtt_clients[device.sn] = mqtt_client

            mqtt_client = self.device_mqtt_clients[device.sn]
            test_engine = TestEngine(mqtt_client, self.config)

            def progress_callback(msg):
                log_widget.append(msg)

            success, message = test_engine.reset_config(progress_callback)

            if success:
                log_widget.append(f"✅ {message}")
                QMessageBox.information(self, '成功', f'{message}\n\n请重启设备使配置生效。')
            else:
                log_widget.append(f"❌ {message}")
                QMessageBox.critical(self, '失败', message)

        except Exception as e:
            log_widget.append(f"❌ 重置配置失败: {str(e)}")
            QMessageBox.critical(self, '错误', f'重置配置失败: {str(e)}')

    def start_remote_pairing(self, device):
        if device.sn not in self.device_log_widgets:
            log_widget = self.create_device_log_widget(device.sn)
        else:
            log_widget = self.device_log_widgets[device.sn]['log_text']
        
        log_widget.append(f"开始遥控器配对: {device.sn}")
        
        try:
            if device.sn not in self.device_mqtt_clients:
                mqtt_client = MQTTClient(
                    self.config.mqtt_broker,
                    self.config.mqtt_port,
                    self.config.product_id,
                    device.sn
                )
                
                if not mqtt_client.connect():
                    QMessageBox.critical(self, '错误', 'MQTT连接失败')
                    return
                
                self.device_mqtt_clients[device.sn] = mqtt_client
            
            mqtt_client = self.device_mqtt_clients[device.sn]
            test_engine = TestEngine(mqtt_client, self.config)
            
            def progress_callback(msg):
                log_widget.append(msg)
            
            test_engine.set_progress_callback(progress_callback)
            
            success = test_engine.test_remote_pairing()
            
            if success:
                log_widget.append("✅ 遥控器配对成功")
                QMessageBox.information(self, '成功', '遥控器配对成功')
            else:
                log_widget.append("❌ 遥控器配对失败")
                QMessageBox.critical(self, '错误', '遥控器配对失败')
                
        except Exception as e:
            log_widget.append(f"❌ 遥控器配对失败: {str(e)}")
            QMessageBox.critical(self, '错误', f'遥控器配对失败: {str(e)}')
    
    def start_emergency_switch_test(self, device):
        if device.sn not in self.device_log_widgets:
            log_widget = self.create_device_log_widget(device.sn)
        else:
            log_widget = self.device_log_widgets[device.sn]['log_text']
        
        log_widget.append(f"开始应急开关测试: {device.sn}")
        
        try:
            if device.sn not in self.device_mqtt_clients:
                mqtt_client = MQTTClient(
                    self.config.mqtt_broker,
                    self.config.mqtt_port,
                    self.config.product_id,
                    device.sn
                )
                
                if not mqtt_client.connect():
                    QMessageBox.critical(self, '错误', 'MQTT连接失败')
                    return
                
                self.device_mqtt_clients[device.sn] = mqtt_client
            
            mqtt_client = self.device_mqtt_clients[device.sn]
            test_engine = TestEngine(mqtt_client, self.config)
            
            def progress_callback(msg):
                log_widget.append(msg)
            
            test_engine.set_progress_callback(progress_callback)
            
            QMessageBox.information(
                self, 
                '应急开关测试',
                '即将进行应急开关测试\n\n'
                '1. 门锁将上锁\n'
                '2. 请按应急开关\n'
                '3. 系统将在10秒内检测门锁是否开启\n\n'
                '请点击确定开始测试'
            )
            
            success = test_engine.test_emergency_switch(timeout=10)
            
            if success:
                log_widget.append("✅ 应急开关测试成功")
                QMessageBox.information(self, '成功', '应急开关测试成功')
            else:
                log_widget.append("❌ 应急开关测试失败")
                QMessageBox.critical(self, '错误', '应急开关测试失败')
                
        except Exception as e:
            log_widget.append(f"❌ 应急开关测试失败: {str(e)}")
            QMessageBox.critical(self, '错误', f'应急开关测试失败: {str(e)}')
    
    def start_burn_mac(self, device):
        if device.sn not in self.device_log_widgets:
            log_widget = self.create_device_log_widget(device.sn)
        else:
            log_widget = self.device_log_widgets[device.sn]['log_text']
        
        log_widget.append(f"开始烧写MAC地址: {device.sn}")
        
        try:
            if device.sn not in self.device_mqtt_clients:
                mqtt_client = MQTTClient(
                    self.config.mqtt_broker,
                    self.config.mqtt_port,
                    self.config.product_id,
                    device.sn
                )
                
                if not mqtt_client.connect():
                    QMessageBox.critical(self, '错误', 'MQTT连接失败')
                    return
                
                self.device_mqtt_clients[device.sn] = mqtt_client
            
            mqtt_client = self.device_mqtt_clients[device.sn]
            test_engine = TestEngine(mqtt_client, self.config)
            
            def progress_callback(msg):
                log_widget.append(msg)
            
            success, message = test_engine.burn_mac_addresses(device.sn, progress_callback)
            
            if success:
                log_widget.append(f"✅ {message}")
                QMessageBox.information(self, '成功', message)
            else:
                log_widget.append(f"❌ {message}")
                QMessageBox.critical(self, '失败', message)
                
        except Exception as e:
            log_widget.append(f"❌ 烧写MAC失败: {str(e)}")
            QMessageBox.critical(self, '错误', f'烧写MAC失败: {str(e)}')
    
    def start_ota_upgrade(self, device):
        if device.sn not in self.device_log_widgets:
            log_widget = self.create_device_log_widget(device.sn)
        else:
            log_widget = self.device_log_widgets[device.sn]['log_text']
        
        if not self.current_firmware_path:
            QMessageBox.warning(self, '警告', '请先上传固件文件\n\n点击"📦 上传固件"按钮选择固件')
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
            
            log_widget.append(f"开始OTA升级: {device.sn}")
            log_widget.append(f"固件文件: {self.current_firmware_name}")
            log_widget.append(f"TFTP服务器: {tftp_server_ip}:{tftp_port}")
            log_widget.append(f"固件大小: {len(self.tftp_server.firmware_data)} 字节")
            
            logger.info(f"OTA升级 - 设备: {device.sn}, IP: {device.ip}")
            logger.info(f"OTA升级 - TFTP: {tftp_server_ip}:{tftp_port}/{self.current_firmware_name}")
            logger.info(f"OTA升级 - 固件大小: {len(self.tftp_server.firmware_data)} 字节")
            
            if device.sn not in self.device_mqtt_clients:
                mqtt_client = MQTTClient(
                    self.config.mqtt_broker,
                    self.config.mqtt_port,
                    self.config.product_id,
                    device.sn
                )
                
                if not mqtt_client.connect():
                    QMessageBox.critical(self, '错误', 'MQTT连接失败')
                    return
                
                self.device_mqtt_clients[device.sn] = mqtt_client
            
            mqtt_client = self.device_mqtt_clients[device.sn]
            test_engine = TestEngine(mqtt_client, self.config)
            
            log_widget.append("正在发送OTA升级指令...")
            file_size = len(self.tftp_server.firmware_data)
            
            self.device_ota_in_progress.add(device.sn)
            
            if device.sn in self.device_log_widgets:
                progress_bar = self.device_log_widgets[device.sn]['progress_bar']
                progress_bar.setVisible(True)
                progress_bar.setValue(0)
            
            ota_thread = OTAThread(test_engine, tftp_server_ip, tftp_port, self.current_firmware_name, file_size)
            ota_thread.log_signal.connect(lambda msg: self._emit_ota_log(device.sn, msg))
            ota_thread.finished_signal.connect(lambda success: self._on_ota_finished(device.sn, success))
            ota_thread.start()
            
            QMessageBox.information(self, '提示', 'OTA升级已启动\n设备正在下载固件，请等待设备重启')
                
        except Exception as e:
            log_widget.append(f"❌ OTA升级异常: {str(e)}")
            QMessageBox.critical(self, '错误', f'OTA升级异常: {str(e)}')
            self.device_ota_in_progress.discard(device.sn)
    
    def _emit_ota_log(self, device_sn: str, message: str):
        if device_sn in self.device_log_widgets:
            log_widget = self.device_log_widgets[device_sn]['log_text']
            log_widget.append(message)
    
    def _on_ota_finished(self, device_sn: str, success: bool):
        if not success:
            self.device_ota_in_progress.discard(device_sn)
    
    
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
