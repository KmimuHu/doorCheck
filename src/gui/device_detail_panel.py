from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTextEdit, QGroupBox, QScrollArea,
                             QProgressBar)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont


class TestItemWidget(QWidget):

    test_clicked = pyqtSignal(str)

    def __init__(self, test_name: str, display_name: str, color: str, hover_color: str, parent=None):
        super().__init__(parent)
        self.test_name = test_name
        self.display_name = display_name
        self.color = color
        self.hover_color = hover_color
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        self.test_btn = QPushButton(self.display_name)
        self.test_btn.setFixedWidth(100)
        self.test_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color};
                color: white;
                border: none;
                padding: 4px;
                border-radius: 3px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {self.hover_color};
            }}
            QPushButton:disabled {{
                background-color: #BDBDBD;
                color: #757575;
            }}
        """)
        self.test_btn.clicked.connect(lambda: self.test_clicked.emit(self.test_name))
        layout.addWidget(self.test_btn)

        self.status_label = QLabel("未测试")
        self.status_label.setFont(QFont("Arial", 9))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFixedWidth(60)
        layout.addWidget(self.status_label)

        self.message_label = QLabel("")
        self.message_label.setFont(QFont("Arial", 8))
        layout.addWidget(self.message_label)

        layout.addStretch()

        self.setLayout(layout)

    def update_result(self, status: str, message: str = ""):
        if status == "passed":
            self.status_label.setText("✓ 通过")
            self.status_label.setStyleSheet("color: #4caf50; font-weight: bold;")
        elif status == "failed":
            self.status_label.setText("✗ 失败")
            self.status_label.setStyleSheet("color: #f44336; font-weight: bold;")
        elif status == "testing":
            self.status_label.setText("⟳ 测试中")
            self.status_label.setStyleSheet("color: #ff9800; font-weight: bold;")
        else:
            self.status_label.setText("未测试")
            self.status_label.setStyleSheet("color: #999;")

        self.message_label.setText(message)

    def set_enabled(self, enabled: bool):
        self.test_btn.setEnabled(enabled)


class DeviceDetailPanel(QWidget):

    test_clicked = pyqtSignal(str, str)       # test_name, device_sn
    auto_test_clicked = pyqtSignal(str)        # device_sn
    upload_firmware_clicked = pyqtSignal()
    ota_clicked = pyqtSignal(str)              # device_sn
    print_label_clicked = pyqtSignal(str)      # device_sn
    reset_config_clicked = pyqtSignal(str)     # device_sn

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_device_sn = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("设备详情")
        header.setFont(QFont("Arial", 14, QFont.Bold))
        header.setStyleSheet("padding: 10px; background-color: #2196F3; color: white;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(15, 15, 15, 15)

        # Device info
        self.device_info_label = QLabel("请选择设备")
        self.device_info_label.setFont(QFont("Arial", 12))
        self.device_info_label.setStyleSheet("padding: 10px; background-color: #f5f5f5; border-radius: 5px;")
        content_layout.addWidget(self.device_info_label)

        # Test items group
        test_group = QGroupBox("检测项目")
        test_group.setFont(QFont("Arial", 11, QFont.Bold))
        test_layout = QVBoxLayout()
        test_layout.setSpacing(4)

        # Auto-test button
        auto_test_layout = QHBoxLayout()
        auto_test_layout.setContentsMargins(5, 5, 5, 5)

        self.auto_test_btn = QPushButton("一键测试")
        self.auto_test_btn.setFixedWidth(100)
        self.auto_test_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF5722;
                color: white;
                border: none;
                padding: 4px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #E64A19;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #757575;
            }
        """)
        self.auto_test_btn.setEnabled(False)
        self.auto_test_btn.clicked.connect(self._on_auto_test_clicked)
        auto_test_layout.addWidget(self.auto_test_btn)

        self.auto_test_status = QLabel("")
        self.auto_test_status.setFont(QFont("Arial", 9))
        self.auto_test_status.setAlignment(Qt.AlignCenter)
        self.auto_test_status.setFixedWidth(60)
        auto_test_layout.addWidget(self.auto_test_status)

        auto_test_layout.addStretch()
        test_layout.addLayout(auto_test_layout)

        # Individual test items
        self.test_widgets = {}
        test_items = [
            ("burn_mac", "烧写MAC", "#16a085", "#138d75"),
            ("remote_pairing", "遥控器配对", "#9b59b6", "#8e44ad"),
            ("emergency_switch", "应急开关", "#e74c3c", "#c0392b"),
        ]

        for test_name, display_name, color, hover_color in test_items:
            widget = TestItemWidget(test_name, display_name, color, hover_color)
            widget.test_clicked.connect(self._on_test_item_clicked)
            test_layout.addWidget(widget)
            self.test_widgets[test_name] = widget

        test_group.setLayout(test_layout)
        content_layout.addWidget(test_group)

        # OTA group
        ota_group = QGroupBox("固件升级")
        ota_group.setFont(QFont("Arial", 11, QFont.Bold))
        ota_layout = QVBoxLayout()

        firmware_layout = QHBoxLayout()

        self.upload_firmware_btn = QPushButton("上传固件")
        self.upload_firmware_btn.setFixedWidth(100)
        self.upload_firmware_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 4px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #e68900;
            }
        """)
        self.upload_firmware_btn.clicked.connect(self.upload_firmware_clicked.emit)
        firmware_layout.addWidget(self.upload_firmware_btn)

        self.firmware_status_label = QLabel("固件: 未上传")
        self.firmware_status_label.setFont(QFont("Arial", 9))
        self.firmware_status_label.setStyleSheet("color: #999;")
        firmware_layout.addWidget(self.firmware_status_label)

        firmware_layout.addStretch()
        ota_layout.addLayout(firmware_layout)

        ota_btn_layout = QHBoxLayout()

        self.ota_btn = QPushButton("OTA升级")
        self.ota_btn.setFixedWidth(100)
        self.ota_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                padding: 4px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #757575;
            }
        """)
        self.ota_btn.setEnabled(False)
        self.ota_btn.clicked.connect(self._on_ota_clicked)
        ota_btn_layout.addWidget(self.ota_btn)

        self.ota_status_label = QLabel("")
        self.ota_status_label.setFont(QFont("Arial", 9))
        ota_btn_layout.addWidget(self.ota_status_label)

        ota_btn_layout.addStretch()
        ota_layout.addLayout(ota_btn_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #34495e;
                border-radius: 3px;
                background-color: #2c3e50;
                height: 24px;
                color: #ecf0f1;
                font-weight: bold;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 2px;
            }
        """)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setVisible(False)
        ota_layout.addWidget(self.progress_bar)

        ota_group.setLayout(ota_layout)
        content_layout.addWidget(ota_group)

        # Log group
        log_group = QGroupBox("测试日志")
        log_group.setFont(QFont("Arial", 11, QFont.Bold))
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 8))
        self.log_text.setMaximumHeight(200)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: none;
                padding: 8px;
            }
        """)
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        content_layout.addWidget(log_group)

        # Bottom control buttons
        button_layout = QHBoxLayout()

        self.print_btn = QPushButton("打印标签")
        self.print_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e68900;
            }
        """)
        self.print_btn.clicked.connect(self._on_print_label)
        self.print_btn.setEnabled(False)
        button_layout.addWidget(self.print_btn)

        self.reset_btn = QPushButton("重置配置")
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #7B1FA2;
            }
        """)
        self.reset_btn.clicked.connect(self._on_reset_config)
        self.reset_btn.setEnabled(False)
        button_layout.addWidget(self.reset_btn)

        button_layout.addStretch()

        content_layout.addLayout(button_layout)
        content_layout.addStretch()

        content_widget.setLayout(content_layout)
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        self.setLayout(layout)

    def set_device(self, sn: str, ip: str, model: str):
        self.current_device_sn = sn
        self.device_info_label.setText(f"SN: {sn}\nIP: {ip}\n型号: {model}")
        self.auto_test_btn.setEnabled(True)
        self.ota_btn.setEnabled(True)
        self.print_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        for widget in self.test_widgets.values():
            widget.set_enabled(True)
        self.clear_results()

    def clear_device(self):
        self.current_device_sn = None
        self.device_info_label.setText("请选择设备")
        self.auto_test_btn.setEnabled(False)
        self.ota_btn.setEnabled(False)
        self.print_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        for widget in self.test_widgets.values():
            widget.set_enabled(False)
        self.clear_results()

    def update_firmware_status(self, name: str, size_mb: float):
        self.firmware_status_label.setText(f"固件: {name} ({size_mb:.2f} MB)")
        self.firmware_status_label.setStyleSheet("color: #4caf50; font-weight: bold;")

    def update_ota_progress(self, progress: int, sent_mb: float, total_mb: float):
        if not self.progress_bar.isVisible():
            self.progress_bar.setVisible(True)
        self.progress_bar.setValue(progress)
        self.append_log(f"OTA升级进度: {progress}% ({sent_mb:.2f}/{total_mb:.2f} MB)")

    def hide_progress_bar(self):
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)

    def update_test_result(self, test_name: str, status: str, message: str = ""):
        if test_name in self.test_widgets:
            self.test_widgets[test_name].update_result(status, message)

    def update_auto_test_status(self, status: str):
        if status == "passed":
            self.auto_test_status.setText("✓ 通过")
            self.auto_test_status.setStyleSheet("color: #4caf50; font-weight: bold;")
        elif status == "failed":
            self.auto_test_status.setText("✗ 失败")
            self.auto_test_status.setStyleSheet("color: #f44336; font-weight: bold;")
        elif status == "testing":
            self.auto_test_status.setText("⟳ 测试中")
            self.auto_test_status.setStyleSheet("color: #ff9800; font-weight: bold;")
        else:
            self.auto_test_status.setText("")
            self.auto_test_status.setStyleSheet("")

    def set_testing(self, is_testing: bool):
        self.auto_test_btn.setEnabled(not is_testing)
        for widget in self.test_widgets.values():
            widget.set_enabled(not is_testing)
        self.ota_btn.setEnabled(not is_testing)

    def append_log(self, message: str):
        self.log_text.append(message)

    def clear_log(self):
        self.log_text.clear()

    def clear_results(self):
        for widget in self.test_widgets.values():
            widget.update_result("not_tested")
        self.auto_test_status.setText("")
        self.auto_test_status.setStyleSheet("")
        self.clear_log()
        self.hide_progress_bar()

    def _on_auto_test_clicked(self):
        if self.current_device_sn:
            self.auto_test_clicked.emit(self.current_device_sn)

    def _on_test_item_clicked(self, test_name: str):
        if self.current_device_sn:
            self.test_clicked.emit(test_name, self.current_device_sn)

    def _on_ota_clicked(self):
        if self.current_device_sn:
            self.ota_clicked.emit(self.current_device_sn)

    def _on_print_label(self):
        if self.current_device_sn:
            self.print_label_clicked.emit(self.current_device_sn)

    def _on_reset_config(self):
        if self.current_device_sn:
            self.reset_config_clicked.emit(self.current_device_sn)
