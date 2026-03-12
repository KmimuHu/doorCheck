from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QLineEdit, QComboBox, QPushButton,
                             QLabel, QHeaderView, QMessageBox, QDialog, QTextEdit)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from datetime import datetime
from ..data.test_record_storage import TestRecordStorage


class TestRecordDetailDialog(QDialog):
    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.setWindowTitle('测试记录详情')
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout()

        # 基本信息
        info_text = f"""设备SN: {record.get('device_sn', 'N/A')}
测试类型: {record.get('test_type', 'N/A')}
测试时间: {record.get('test_time', 'N/A')}
测试结果: {record.get('status_text', 'N/A')}
耗时: {record.get('duration', 'N/A')}秒
"""
        info_label = QLabel(info_text)
        info_label.setStyleSheet('font-size: 12pt; padding: 10px;')
        layout.addWidget(info_label)

        # 测试步骤详情
        steps_label = QLabel('测试步骤详情:')
        steps_label.setStyleSheet('font-weight: bold; font-size: 11pt;')
        layout.addWidget(steps_label)

        steps_text = QTextEdit()
        steps_text.setReadOnly(True)

        steps_content = ""
        for step in record.get('steps', []):
            status_icon = "✅" if step.get('success') else "❌"
            steps_content += f"{status_icon} {step.get('name')}\n"
            if step.get('message'):
                steps_content += f"   {step.get('message')}\n"
            steps_content += "\n"

        steps_text.setPlainText(steps_content)
        layout.addWidget(steps_text)

        # 关闭按钮
        close_btn = QPushButton('关闭')
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.setLayout(layout)


class TestRecordPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.storage = TestRecordStorage()
        self.init_ui()
        self.load_records()

    def init_ui(self):
        layout = QVBoxLayout()

        # 搜索栏
        search_layout = QHBoxLayout()

        search_layout.addWidget(QLabel('SN查询:'))
        self.sn_input = QLineEdit()
        self.sn_input.setPlaceholderText('输入设备SN进行模糊查询')
        self.sn_input.textChanged.connect(self.on_search)
        search_layout.addWidget(self.sn_input)

        search_layout.addWidget(QLabel('测试结果:'))
        self.status_combo = QComboBox()
        self.status_combo.addItems(['全部', '通过', '失败'])
        self.status_combo.currentTextChanged.connect(self.on_search)
        search_layout.addWidget(self.status_combo)

        refresh_btn = QPushButton('刷新')
        refresh_btn.clicked.connect(self.load_records)
        search_layout.addWidget(refresh_btn)

        clear_btn = QPushButton('清空记录')
        clear_btn.clicked.connect(self.clear_all_records)
        search_layout.addWidget(clear_btn)

        layout.addLayout(search_layout)

        # 记录表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(['设备SN', '测试类型', '测试时间', '测试结果', '耗时(秒)', '操作'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def load_records(self):
        """加载所有记录"""
        records = self.storage.load_all_records()
        self.display_records(records)

    def on_search(self):
        """执行搜索"""
        sn_keyword = self.sn_input.text().strip()
        status_text = self.status_combo.currentText()

        status_map = {'全部': 'all', '通过': 'passed', '失败': 'failed'}
        status_filter = status_map.get(status_text, 'all')

        records = self.storage.search_records(sn_keyword, status_filter)
        self.display_records(records)

    def display_records(self, records):
        """显示记录列表"""
        self.table.setRowCount(len(records))

        for row, record in enumerate(records):
            self.table.setItem(row, 0, QTableWidgetItem(record.get('device_sn', '')))
            self.table.setItem(row, 1, QTableWidgetItem(record.get('test_type', '')))
            self.table.setItem(row, 2, QTableWidgetItem(record.get('test_time', '')))

            status_item = QTableWidgetItem(record.get('status_text', ''))
            if record.get('status') == 'passed':
                status_item.setForeground(QColor(76, 175, 80))
            else:
                status_item.setForeground(QColor(244, 67, 54))
            self.table.setItem(row, 3, status_item)

            self.table.setItem(row, 4, QTableWidgetItem(str(record.get('duration', 0))))

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(5, 2, 5, 2)

            detail_btn = QPushButton('详情')
            detail_btn.clicked.connect(lambda checked, r=record: self.show_detail(r))
            btn_layout.addWidget(detail_btn)

            delete_btn = QPushButton('删除')
            delete_btn.clicked.connect(lambda checked, r=record: self.delete_record(r))
            btn_layout.addWidget(delete_btn)

            btn_widget.setLayout(btn_layout)
            self.table.setCellWidget(row, 5, btn_widget)

    def show_detail(self, record):
        """显示记录详情"""
        dialog = TestRecordDetailDialog(record, self)
        dialog.exec_()

    def delete_record(self, record):
        """删除记录"""
        reply = QMessageBox.question(
            self, '确认删除',
            f'确定要删除设备 {record.get("device_sn")} 的测试记录吗？',
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.storage.delete_record(record.get('id')):
                QMessageBox.information(self, '成功', '记录已删除')
                self.load_records()

    def clear_all_records(self):
        """清空所有记录"""
        reply = QMessageBox.warning(
            self, '确认清空',
            '确定要清空所有测试记录吗？此操作不可恢复！',
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.storage.clear_all_records():
                QMessageBox.information(self, '成功', '所有记录已清空')
                self.load_records()
