from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame, QScrollArea)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from ..network.mdns_discovery import DeviceInfo


class DeviceCard(QFrame):

    clicked = pyqtSignal(str)
    delete_clicked = pyqtSignal(str)

    def __init__(self, device: DeviceInfo, parent=None):
        super().__init__(parent)
        self.device = device
        self.selected = False
        self.test_status = '未测试'
        self.init_ui()

    def init_ui(self):
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(2)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(80)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        sn_label = QLabel(f"SN: {self.device.get_display_name()}")
        sn_label.setFont(QFont("Microsoft YaHei", 9))
        sn_label.setWordWrap(True)
        sn_label.setStyleSheet("color: #333;")
        layout.addWidget(sn_label)

        ip_label = QLabel(f"IP: {self.device.ip}")
        ip_label.setFont(QFont("Microsoft YaHei", 9))
        ip_label.setWordWrap(True)
        ip_label.setStyleSheet("color: #333;")
        layout.addWidget(ip_label)

        model_label = QLabel(f"型号: {self.device.model}")
        model_label.setFont(QFont("Microsoft YaHei", 9))
        model_label.setWordWrap(True)
        model_label.setStyleSheet("color: #333;")
        layout.addWidget(model_label)

        status_layout = QHBoxLayout()
        self.status_label = QLabel("状态: 未测试")
        self.status_label.setFont(QFont("Microsoft YaHei", 8))
        self.status_label.setStyleSheet("color: #333333;")
        status_layout.addWidget(self.status_label)

        delete_btn = QPushButton("删除")
        delete_btn.setFixedWidth(50)
        delete_btn.setStyleSheet("background-color: #ff6b6b; color: white; border-radius: 3px;")
        delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.device.sn))
        status_layout.addWidget(delete_btn)

        layout.addLayout(status_layout)

        self.setLayout(layout)
        self.update_style()

    def update_style(self):
        if self.selected:
            self.setStyleSheet("""
                DeviceCard {
                    background-color: #e3f2fd;
                    border: 2px solid #2196F3;
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                DeviceCard {
                    background-color: white;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                }
                DeviceCard:hover {
                    background-color: #f5f5f5;
                    border: 1px solid #2196F3;
                }
            """)

    def set_selected(self, selected: bool):
        self.selected = selected
        self.update_style()

    def update_status(self, status: str):
        self.test_status = status
        self.status_label.setText(f"状态: {status}")

        if '通过' in status:
            self.status_label.setStyleSheet("color: #4caf50; font-weight: bold;")
        elif '失败' in status:
            self.status_label.setStyleSheet("color: #f44336; font-weight: bold;")
        elif '测试中' in status:
            self.status_label.setStyleSheet("color: #ff9800; font-weight: bold;")
        else:
            self.status_label.setStyleSheet("color: #666;")

    def mousePressEvent(self, event):
        self.clicked.emit(self.device.sn)
        super().mousePressEvent(event)


class DeviceListPanel(QWidget):

    device_selected = pyqtSignal(str)
    device_deleted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.device_cards = {}
        self.current_selected_card = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("设备列表")
        header.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        header.setStyleSheet("padding: 10px; background-color: #2196F3; color: white;")
        layout.addWidget(header)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(10, 5, 10, 5)

        self.refresh_btn = QPushButton("刷新发现")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-family: 'Microsoft YaHei';
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        button_layout.addWidget(self.refresh_btn)

        layout.addLayout(button_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout()
        self.cards_layout.setSpacing(10)
        self.cards_layout.setContentsMargins(10, 10, 10, 10)
        self.cards_layout.addStretch()
        self.cards_container.setLayout(self.cards_layout)

        scroll_area.setWidget(self.cards_container)
        layout.addWidget(scroll_area)

        self.setLayout(layout)

    def add_device(self, device: DeviceInfo):
        if device.sn in self.device_cards:
            return

        card = DeviceCard(device)
        card.clicked.connect(self.on_device_clicked)
        card.delete_clicked.connect(self.on_device_delete)

        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self.device_cards[device.sn] = card

    def remove_device(self, sn: str):
        if sn in self.device_cards:
            card = self.device_cards.pop(sn)
            if self.current_selected_card is card:
                self.current_selected_card = None
            self.cards_layout.removeWidget(card)
            card.deleteLater()

    def on_device_clicked(self, sn: str):
        if self.current_selected_card:
            self.current_selected_card.set_selected(False)

        card = self.device_cards.get(sn)
        if card:
            card.set_selected(True)
            self.current_selected_card = card

        self.device_selected.emit(sn)

    def on_device_delete(self, sn: str):
        self.device_deleted.emit(sn)

    def update_device_status(self, sn: str, status: str):
        if sn in self.device_cards:
            self.device_cards[sn].update_status(status)

    def clear_devices(self):
        for card in list(self.device_cards.values()):
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.device_cards.clear()
        self.current_selected_card = None
