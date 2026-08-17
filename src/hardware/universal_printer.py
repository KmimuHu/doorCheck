import sys
import logging
from datetime import datetime
from typing import Optional

# 只在Windows平台导入win32print
if sys.platform == 'win32':
    import win32print
else:
    win32print = None

# 使用统一的 logger，确保日志能被记录
from ..utils.logger import logger


class UniversalPrinter:
    """
    通用标签打印机，支持 ZPL (Zebra) 和 TSPL (Xprinter/TSC) 协议
    根据打印机名称自动检测协议，或手动指定
    """

    # 协议检测规则（与配置对话框保持一致）
    _PROTOCOL_RULES = [
        ('zpl',  ['zdesigner', 'zebra', 'zpl']),
        ('tspl', ['xprinter', 'xp-t', 'xp-n', 'xp-d', 'tsc', 'tspl']),
    ]

    def __init__(self, config=None):
        """
        初始化打印机
        
        Args:
            config: Config对象或字典，包含printer配置
        """
        self.printer_name = None
        self.dpi = 600
        self.protocol = None
        self.paper_width = 50
        self.paper_height = 30
        self.tspl_layout = {}
        self.zpl_layout = {}

        # 从配置加载参数
        if config is not None:
            self._load_config(config)

        # 如果没有配置打印机名称，使用系统默认
        if not self.printer_name:
            try:
                self.printer_name = win32print.GetDefaultPrinter()
                logger.info(f"使用系统默认打印机: {self.printer_name}")
            except Exception as e:
                logger.error(f"获取默认打印机失败: {e}")
                self.printer_name = ""

        # 自动检测协议
        if not self.protocol or self.protocol == 'auto':
            self.protocol = self._detect_protocol()

        logger.info(f"打印机初始化: name={self.printer_name}, protocol={self.protocol}, dpi={self.dpi}")

    def _load_config(self, config):
        """从 Config 对象或字典加载配置"""
        # 区分 Config 对象和普通字典
        if hasattr(config, 'load_config') or hasattr(config, 'printer_config'):
            # Config 对象 - 使用点号路径
            self.printer_name = config.get('printer.printer_name', None)
            self.dpi = config.get('printer.dpi', 600)
            self.protocol = config.get('printer.protocol', None)
            self.paper_width = config.get('printer.paper_width', 50)
            self.paper_height = config.get('printer.paper_height', 30)
            self.tspl_layout = config.get('printer.tspl_layout', {})
            self.zpl_layout = config.get('printer.zpl_layout', {})
        elif isinstance(config, dict):
            # 普通字典
            printer_cfg = config.get('printer', {})
            self.printer_name = printer_cfg.get('printer_name', None)
            self.dpi = printer_cfg.get('dpi', 600)
            self.protocol = printer_cfg.get('protocol', None)
            self.paper_width = printer_cfg.get('paper_width', 50)
            self.paper_height = printer_cfg.get('paper_height', 30)
            self.tspl_layout = printer_cfg.get('tspl_layout', {})
            self.zpl_layout = printer_cfg.get('zpl_layout', {})

    def _detect_protocol(self) -> str:
        """根据打印机名称检测协议"""
        if self.printer_name:
            name_lower = self.printer_name.lower()
            for protocol, keywords in self._PROTOCOL_RULES:
                for kw in keywords:
                    if kw in name_lower:
                        logger.info(f"检测到 {protocol.upper()} 协议（关键字: '{kw}'）")
                        return protocol
        logger.warning(f"无法检测协议（打印机: '{self.printer_name}'），默认使用 ZPL")
        return 'zpl'

    def print_label(self, sn: str, capacity: str = '', status: str = None) -> bool:
        """
        打印标签
        
        Args:
            sn: 设备序列号
            capacity: 容量信息（可选）
            status: 状态（可选）
            
        Returns:
            打印是否成功
        """
        try:
            if self.protocol == 'zpl':
                return self._print_zpl(sn, capacity)
            else:
                return self._print_tspl(sn, capacity)
        except Exception as e:
            logger.error(f"打印失败: {e}")
            return False

    def _build_tspl_commands(self, sn: str, capacity: str = '') -> str:
        """构建 TSPL 打印指令"""
        tspl = "CLS\n"
        tspl += f"SIZE {self.paper_width} mm, {self.paper_height} mm\n"
        tspl += "GAP 2 mm, 0 mm\n"
        tspl += "DIRECTION 1\n"
        tspl += "SPEED 4\n"
        tspl += "DENSITY 10\n"
        tspl += "REFERENCE 0,0\n"
        tspl += "SET TEAR ON\n"
        tspl += "CLS\n"

        # 从配置读取布局
        date_cfg = self.tspl_layout.get('date', {})
        date_x = date_cfg.get('x', 120)
        date_y = date_cfg.get('y', 124)
        date_font = date_cfg.get('font', '1')
        date_rotation = date_cfg.get('rotation', 0)
        date_x_scale = date_cfg.get('x_scale', 1)
        date_y_scale = date_cfg.get('y_scale', 1)

        sn_cfg = self.tspl_layout.get('sn', {})
        sn_x = sn_cfg.get('x', 34)
        sn_y = sn_cfg.get('y', 178)
        sn_font = sn_cfg.get('font', '1')
        sn_rotation = sn_cfg.get('rotation', 0)
        sn_x_scale = sn_cfg.get('x_scale', 1)
        sn_y_scale = sn_cfg.get('y_scale', 1)

        qr_cfg = self.tspl_layout.get('qrcode', {})
        qr_x = qr_cfg.get('x', 245)
        qr_y = qr_cfg.get('y', 69)
        
        # QR码尺寸计算：目标15mm
        if 'cell_width' in qr_cfg:
            qr_cell_width = qr_cfg['cell_width']
        else:
            target_dots = int(15 * self.dpi / 25.4)
            qr_cell_width = max(1, (target_dots + 24) // 25)

        # 日期
        date_str = datetime.now().strftime("%Y/%m/%d")
        tspl += f'TEXT {date_x},{date_y},"{date_font}",{date_rotation},{date_x_scale},{date_y_scale},"{date_str}"\n'

        # 序列号
        tspl += f'TEXT {sn_x},{sn_y},"{sn_font}",{sn_rotation},{sn_x_scale},{sn_y_scale},"SN:{sn}"\n'

        # QR码
        tspl += f'QRCODE {qr_x},{qr_y},M,{qr_cell_width},A,0,M2,S7,"{sn}"\n'

        tspl += "PRINT 1,1\n"
        
        return tspl

    def _build_zpl_commands(self, sn: str, capacity: str = '') -> str:
        """构建 ZPL 打印指令"""
        zpl = "^XA\n"  # 标签开始
        zpl += "^PW" + str(int(self.paper_width * self.dpi / 25.4)) + "\n"  # 标签宽度（点数）
        zpl += "^LL" + str(int(self.paper_height * self.dpi / 25.4)) + "\n"  # 标签长度（点数）

        # 从配置读取布局
        qr_cfg = self.zpl_layout.get('qrcode', {})
        qr_x = qr_cfg.get('x', 723)
        qr_y = qr_cfg.get('y', 204)
        
        # QR码放大倍数：目标15mm
        if 'magnification' in qr_cfg:
            qr_mag = qr_cfg['magnification']
        else:
            target_dots = int(15 * self.dpi / 25.4)
            qr_mag = max(1, (target_dots + 24) // 25)

        date_cfg = self.zpl_layout.get('date', {})
        date_x = date_cfg.get('x', 354)
        date_y = date_cfg.get('y', 366)
        date_font_h = date_cfg.get('font_height', 80)
        date_font_w = date_cfg.get('font_width', 80)

        sn_cfg = self.zpl_layout.get('sn', {})
        sn_x = sn_cfg.get('x', 100)
        sn_y = sn_cfg.get('y', 605)
        sn_font_h = sn_cfg.get('font_height', 80)
        sn_font_w = sn_cfg.get('font_width', 80)

        # 日期
        date_str = datetime.now().strftime("%Y/%m/%d")
        zpl += f"^FO{date_x},{date_y}\n"
        zpl += f"^CF0,{date_font_h},{date_font_w}\n"
        zpl += f"^FD{date_str}^FS\n"

        # 序列号
        zpl += f"^FO{sn_x},{sn_y}\n"
        zpl += f"^CF0,{sn_font_h},{sn_font_w}\n"
        zpl += f"^FDSN:{sn}^FS\n"

        # QR码
        zpl += f"^FO{qr_x},{qr_y}\n"
        zpl += f"^BQN,2,{qr_mag}\n"
        zpl += f"^FDQA,{sn}^FS\n"

        # 容量信息（如果提供且配置中有）
        if capacity:
            disk_cfg = self.zpl_layout.get('disk_size', {})
            if disk_cfg:
                disk_x = disk_cfg.get('x', 827)
                disk_y = disk_cfg.get('y', 649)
                disk_font_h = disk_cfg.get('font_height', 75)
                disk_font_w = disk_cfg.get('font_width', 75)
                zpl += f"^FO{disk_x},{disk_y}\n"
                zpl += f"^CF0,{disk_font_h},{disk_font_w}\n"
                zpl += f"^FD{capacity}^FS\n"

        zpl += "^XZ\n"  # 标签结束
        return zpl

    def _print_tspl(self, sn: str, capacity: str = '') -> bool:
        """TSPL 协议打印"""
        tspl = self._build_tspl_commands(sn, capacity)
        logger.info(f"TSPL 指令:\n{tspl}")
        return self._send_raw(tspl)

    def _print_zpl(self, sn: str, capacity: str = '') -> bool:
        """ZPL 协议打印"""
        zpl = self._build_zpl_commands(sn, capacity)
        logger.info(f"ZPL 指令:\n{zpl}")
        return self._send_raw(zpl)

    def _send_raw(self, commands: str) -> bool:
        """发送原始打印指令"""
        if not self.printer_name:
            logger.error("打印机名称未设置")
            return False

        try:
            data = commands.encode('utf-8')
            hPrinter = win32print.OpenPrinter(self.printer_name)
            try:
                win32print.StartDocPrinter(hPrinter, 1, ("Label", None, "RAW"))
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, data)
                win32print.EndPagePrinter(hPrinter)
                win32print.EndDocPrinter(hPrinter)
                logger.info(f"打印成功: {self.printer_name}")
                return True
            finally:
                win32print.ClosePrinter(hPrinter)
        except Exception as e:
            logger.error(f"打印失败: {e}")
            return False
