from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTextEdit, QScrollArea,
                             QProgressBar, QFrame)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont


SECTION_TITLE_STYLE = (
    "font-family: 'Microsoft YaHei'; font-size: 13px; font-weight: bold; "
    "color: #333; padding: 2px 0px;"
)

SECTION_FRAME_STYLE = (
    "QFrame#sectionFrame { "
    "  border: 1px solid #dcdcdc; border-radius: 6px; "
    "  background-color: #fafafa; "
    "}"
)


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
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.test_btn = QPushButton(self.display_name)
        self.test_btn.setMinimumWidth(100)
        self.test_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color};
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
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
        self.status_label.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px; color: #999;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Hidden label kept for API compatibility
        self.message_label = QLabel("")
        self.message_label.setVisible(False)

        self.setLayout(layout)

    def update_result(self, status: str, message: str = ""):
        if status == "passed":
            self.status_label.setText("✓ 通过")
            self.status_label.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px; color: #4caf50; font-weight: bold;")
        elif status == "failed":
            self.status_label.setText("✗ 失败")
            self.status_label.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px; color: #f44336; font-weight: bold;")
        elif status == "testing":
            self.status_label.setText("⟳ 测试中")
            self.status_label.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px; color: #ff9800; font-weight: bold;")
        else:
            self.status_label.setText("未测试")
            self.status_label.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px; color: #999;")

        if message:
            self.status_label.setToolTip(message)
        else:
            self.status_label.setToolTip("")

    def set_enabled(self, enabled: bool):
        self.test_btn.setEnabled(enabled)


def _create_section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(SECTION_TITLE_STYLE)
    return label


def _create_section_frame() -> QFrame:
    frame = QFrame()
    frame.setObjectName("sectionFrame")
    frame.setStyleSheet(SECTION_FRAME_STYLE)
    return frame


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
        layout.setSpacing(0)

        header = QLabel("设备详情")
        header.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        header.setStyleSheet("padding: 10px; background-color: #2196F3; color: white;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #f0f0f0; }")

        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #f0f0f0;")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(12, 8, 12, 8)
        content_layout.setSpacing(6)

        # ---- Device info ----
        self.device_info_label = QLabel("请选择设备")
        self.device_info_label.setFont(QFont("Microsoft YaHei", 10))
        self.device_info_label.setStyleSheet(
            "padding: 8px; background-color: white; border-radius: 6px; "
            "border: 1px solid #e0e0e0; color: #333;"
        )
        content_layout.addWidget(self.device_info_label)

        # ---- 检测项目 ----
        content_layout.addWidget(_create_section_title("检测项目"))

        test_frame = _create_section_frame()
        test_layout = QHBoxLayout()
        test_layout.setSpacing(8)
        test_layout.setContentsMargins(8, 8, 8, 8)

        # Auto-test button (vertical: button + status)
        auto_test_container = QVBoxLayout()
        auto_test_container.setSpacing(4)

        self.auto_test_btn = QPushButton("一键测试")
        self.auto_test_btn.setMinimumWidth(100)
        self.auto_test_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF5722;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
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
        auto_test_container.addWidget(self.auto_test_btn)

        self.auto_test_status = QLabel("")
        self.auto_test_status.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px;")
        self.auto_test_status.setAlignment(Qt.AlignCenter)
        auto_test_container.addWidget(self.auto_test_status)

        test_layout.addLayout(auto_test_container)

        # Vertical separator
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setStyleSheet("color: #dcdcdc;")
        test_layout.addWidget(separator)

        # Individual test items (horizontal)
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

        test_layout.addStretch()
        test_frame.setLayout(test_layout)
        content_layout.addWidget(test_frame)

        # ---- 固件升级 ----
        content_layout.addWidget(_create_section_title("固件升级"))

        ota_frame = _create_section_frame()
        ota_layout = QVBoxLayout()
        ota_layout.setContentsMargins(8, 8, 8, 8)
        ota_layout.setSpacing(8)

        # Buttons row
        ota_btn_row = QHBoxLayout()
        ota_btn_row.setSpacing(10)

        self.upload_firmware_btn = QPushButton("上传固件")
        self.upload_firmware_btn.setMinimumWidth(100)
        self.upload_firmware_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e68900;
            }
        """)
        self.upload_firmware_btn.clicked.connect(self.upload_firmware_clicked.emit)
        ota_btn_row.addWidget(self.upload_firmware_btn)

        self.firmware_status_label = QLabel("固件: 未上传")
        self.firmware_status_label.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px; color: #999;")
        ota_btn_row.addWidget(self.firmware_status_label)

        self.ota_btn = QPushButton("OTA升级")
        self.ota_btn.setMinimumWidth(100)
        self.ota_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
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
        ota_btn_row.addWidget(self.ota_btn)

        self.ota_status_label = QLabel("")
        self.ota_status_label.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px;")
        ota_btn_row.addWidget(self.ota_status_label)

        ota_btn_row.addStretch()
        ota_layout.addLayout(ota_btn_row)

        # Progress bar
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

        ota_frame.setLayout(ota_layout)
        content_layout.addWidget(ota_frame)

        # ---- Control buttons ----
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.print_btn = QPushButton("打印标签")
        self.print_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-family: 'Microsoft YaHei';
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
                font-family: 'Microsoft YaHei';
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

        # ---- 测试日志 ----
        content_layout.addWidget(_create_section_title("测试日志"))

        log_frame = _create_section_frame()
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(8, 8, 8, 8)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setMinimumHeight(120)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 8px;
                selection-background-color: #264f78;
            }
        """)
        log_layout.addWidget(self.log_text)

        log_frame.setLayout(log_layout)
        content_layout.addWidget(log_frame, 1)

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
        self.firmware_status_label.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px; color: #4caf50; font-weight: bold;")

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
            self.auto_test_status.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px; color: #4caf50; font-weight: bold;")
        elif status == "failed":
            self.auto_test_status.setText("✗ 失败")
            self.auto_test_status.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px; color: #f44336; font-weight: bold;")
        elif status == "testing":
            self.auto_test_status.setText("⟳ 测试中")
            self.auto_test_status.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px; color: #ff9800; font-weight: bold;")
        else:
            self.auto_test_status.setText("")
            self.auto_test_status.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px;")

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
        self.auto_test_status.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 13px;")
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
