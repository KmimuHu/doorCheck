from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QLineEdit, QComboBox, QPushButton,
                             QLabel, QHeaderView, QMessageBox, QDialog, QTextEdit,
                             QFileDialog, QDateEdit, QCheckBox)
from PyQt5.QtCore import Qt, pyqtSignal, QDate
from PyQt5.QtGui import QColor
from datetime import datetime, timedelta
from ..data.test_record_storage import TestRecordStorage
from ..utils.logger import logger
import csv


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

        # 第一行搜索栏
        search_layout1 = QHBoxLayout()

        search_layout1.addWidget(QLabel('SN查询:'))
        self.sn_input = QLineEdit()
        self.sn_input.setPlaceholderText('输入设备SN进行模糊查询')
        self.sn_input.textChanged.connect(self.on_search)
        search_layout1.addWidget(self.sn_input)

        search_layout1.addWidget(QLabel('测试结果:'))
        self.status_combo = QComboBox()
        self.status_combo.addItems(['全部', '通过', '失败'])
        self.status_combo.currentTextChanged.connect(self.on_search)
        search_layout1.addWidget(self.status_combo)

        search_layout1.addStretch()

        refresh_btn = QPushButton('刷新')
        refresh_btn.clicked.connect(self.load_records)
        search_layout1.addWidget(refresh_btn)

        layout.addLayout(search_layout1)

        # 第二行日期筛选
        date_layout = QHBoxLayout()

        self.date_filter_checkbox = QCheckBox('日期筛选')
        self.date_filter_checkbox.stateChanged.connect(self.on_date_filter_changed)
        date_layout.addWidget(self.date_filter_checkbox)

        date_layout.addWidget(QLabel('起始日期:'))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat('yyyy-MM-dd')
        self.start_date_edit.setDate(QDate.currentDate().addDays(-7))  # 默认7天前
        self.start_date_edit.setEnabled(False)
        self.start_date_edit.dateChanged.connect(self.on_search)
        date_layout.addWidget(self.start_date_edit)

        date_layout.addWidget(QLabel('结束日期:'))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat('yyyy-MM-dd')
        self.end_date_edit.setDate(QDate.currentDate())  # 默认今天
        self.end_date_edit.setEnabled(False)
        self.end_date_edit.dateChanged.connect(self.on_search)
        date_layout.addWidget(self.end_date_edit)

        date_layout.addStretch()

        export_btn = QPushButton('导出CSV')
        export_btn.clicked.connect(self.export_csv)
        date_layout.addWidget(export_btn)

        clear_btn = QPushButton('清空记录')
        clear_btn.clicked.connect(self.clear_all_records)
        date_layout.addWidget(clear_btn)

        layout.addLayout(date_layout)

        # 记录表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(['设备SN', '测试类型', '测试时间', '测试结果', '耗时(秒)', '操作'])

        # 设置列宽模式
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 设备SN - 自动拉伸
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 测试类型 - 内容适配
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # 测试时�� - 自动拉伸
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 测试结果 - 内容适配
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 耗时 - 内容适配
        header.setSectionResizeMode(5, QHeaderView.Fixed)  # 操作 - 固定宽度
        header.resizeSection(5, 120)  # 操作列固定为120像素（容纳两个按钮）

        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def load_records(self):
        """加载所有记录"""
        records = self.storage.load_all_records()
        self.display_records(records)

    def on_date_filter_changed(self, state):
        """日期筛选复选框状态改变"""
        enabled = (state == Qt.Checked)
        self.start_date_edit.setEnabled(enabled)
        self.end_date_edit.setEnabled(enabled)
        self.on_search()

    def on_search(self):
        """执行搜索"""
        sn_keyword = self.sn_input.text().strip()
        status_text = self.status_combo.currentText()

        status_map = {'全部': 'all', '通过': 'passed', '失败': 'failed'}
        status_filter = status_map.get(status_text, 'all')

        # 获取日期筛选
        start_date = ''
        end_date = ''
        if self.date_filter_checkbox.isChecked():
            start_date = self.start_date_edit.date().toString('yyyy-MM-dd')
            end_date = self.end_date_edit.date().toString('yyyy-MM-dd')

        records = self.storage.search_records(sn_keyword, status_filter, start_date, end_date)
        self.display_records(records)

    def display_records(self, records):
        """显示记录列表"""
        # 清空表格并重新设置行数
        self.table.clearContents()
        self.table.setRowCount(0)
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
            btn_widget = QWidget(self.table)
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)

            detail_btn = QPushButton('详情')
            detail_btn.setFixedSize(50, 25)
            detail_btn.clicked.connect(lambda checked, r=record: self.show_detail(r))
            btn_layout.addWidget(detail_btn)

            delete_btn = QPushButton('删除')
            delete_btn.setFixedSize(50, 25)
            delete_btn.clicked.connect(lambda checked, r=record: self.delete_record(r))
            btn_layout.addWidget(delete_btn)

            btn_layout.addStretch()
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

    def export_csv(self):
        """导出当前显示的记录为CSV"""
        sn_keyword = self.sn_input.text().strip()
        status_text = self.status_combo.currentText()
        status_map = {'全部': 'all', '通过': 'passed', '失败': 'failed'}
        status_filter = status_map.get(status_text, 'all')
        
        # 获取日期筛选
        start_date = ''
        end_date = ''
        if self.date_filter_checkbox.isChecked():
            start_date = self.start_date_edit.date().toString('yyyy-MM-dd')
            end_date = self.end_date_edit.date().toString('yyyy-MM-dd')
        
        records = self.storage.search_records(sn_keyword, status_filter, start_date, end_date)

        if not records:
            QMessageBox.information(self, '提示', '当前无记录可导出')
            return

        # 生成文件名，包含日期范围信息
        date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'test_records_{date_str}'
        if start_date and end_date:
            filename = f'test_records_{start_date}_to_{end_date}'
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, '导出CSV', f'{filename}.csv', 'CSV Files (*.csv)'
        )

        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['设备SN', '测试类型', '测试时间', '测试结果', '耗时(秒)'])
                for r in records:
                    writer.writerow([
                        r.get('device_sn', ''),
                        r.get('test_type', ''),
                        r.get('test_time', ''),
                        '通过' if r.get('status') == 'passed' else '失败',
                        r.get('duration', 0),
                    ])
            QMessageBox.information(self, '成功', f'导出成功: {file_path}\n共 {len(records)} 条记录')
            logger.info(f"导出测试记录: {file_path}, 共{len(records)}条")
        except Exception as e:
            QMessageBox.critical(self, '错误', f'导出失败: {e}')
            logger.error(f"导出测试记录失败: {e}")
