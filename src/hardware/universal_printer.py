import os
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
        """构建 ZPL 打印指令

        支持两种渲染模式（由 zpl_layout.render_mode 决定）：
        - bitmap: 用 PIL 在电脑端渲染日期/SN(指定字体)和二维码为位图，
                  转 ^GFA 发送。字体和二维码完全可控，不受打印机内置字体限制。
        - native: 使用打印机内置字体(^A/^BQN)，兼容旧行为。
        """
        render_mode = self.zpl_layout.get('render_mode', 'native')
        if render_mode == 'bitmap':
            return self._build_zpl_bitmap(sn, capacity)
        return self._build_zpl_native(sn, capacity)

    def _build_zpl_native(self, sn: str, capacity: str = '') -> str:
        """构建 ZPL 打印指令（打印机内置字体模式）"""
        label_w = int(self.paper_width * self.dpi / 25.4)
        label_h = int(self.paper_height * self.dpi / 25.4)

        zpl = "^XA\n"  # 标签开始
        zpl += f"^PW{label_w}\n"  # 标签宽度（点数）
        zpl += f"^LL{label_h}\n"  # 标签长度（点数）

        # 边框（与 TSPL 模板保持一致，绘制外框）
        border_cfg = self.zpl_layout.get('border', {})
        if border_cfg.get('enabled', False):
            b_thickness = border_cfg.get('thickness', 6)
            b_x = border_cfg.get('x', 6)
            b_y = border_cfg.get('y', 6)
            b_w = border_cfg.get('width', label_w - b_x * 2)
            b_h = border_cfg.get('height', label_h - b_y * 2)
            zpl += f"^FO{b_x},{b_y}\n"
            zpl += f"^GB{b_w},{b_h},{b_thickness}^FS\n"

        # 从配置读取布局
        qr_cfg = self.zpl_layout.get('qrcode', {})
        qr_x = qr_cfg.get('x', 724)
        qr_y = qr_cfg.get('y', 204)
        # 纠错等级（与 TSPL 模板的 M 级保持一致）
        qr_ecc = qr_cfg.get('error_correction', 'M')

        # QR码放大倍数：目标15mm
        if 'magnification' in qr_cfg:
            qr_mag = qr_cfg['magnification']
        else:
            target_dots = int(15 * self.dpi / 25.4)
            qr_mag = max(1, (target_dots + 24) // 25)

        date_cfg = self.zpl_layout.get('date', {})
        date_x = date_cfg.get('x', 354)
        date_y = date_cfg.get('y', 366)
        date_font = date_cfg.get('font', 'D')
        date_font_h = date_cfg.get('font_height', 35)
        date_font_w = date_cfg.get('font_width', 24)

        sn_cfg = self.zpl_layout.get('sn', {})
        sn_x = sn_cfg.get('x', 100)
        sn_y = sn_cfg.get('y', 526)
        sn_font = sn_cfg.get('font', 'D')
        sn_font_h = sn_cfg.get('font_height', 35)
        sn_font_w = sn_cfg.get('font_width', 24)

        # 日期
        # 使用 ^A<font> 指定内置点阵字体(A~H，非加粗)，避免 ^CF0 默认矢量字体
        # (CG Triumvirate Bold Condensed) 带来的加粗效果
        date_str = datetime.now().strftime("%Y/%m/%d")
        zpl += f"^FO{date_x},{date_y}\n"
        zpl += f"^A{date_font}N,{date_font_h},{date_font_w}\n"
        zpl += f"^FD{date_str}^FS\n"

        # 序列号
        zpl += f"^FO{sn_x},{sn_y}\n"
        zpl += f"^A{sn_font}N,{sn_font_h},{sn_font_w}\n"
        zpl += f"^FDSN: {sn}^FS\n"

        # QR码（^FD 首字符为纠错等级，与 TSPL 模板保持一致）
        zpl += f"^FO{qr_x},{qr_y}\n"
        zpl += f"^BQN,2,{qr_mag}\n"
        zpl += f"^FD{qr_ecc}A,{sn}^FS\n"

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

    def _resolve_font_path(self) -> Optional[str]:
        """解析字体文件路径（支持相对工程根目录或绝对路径）"""
        font_path = self.zpl_layout.get('font_path')
        if not font_path:
            return None
        if os.path.isabs(font_path) and os.path.exists(font_path):
            return font_path
        # 相对路径：以工程根目录(本文件上溯三级)为基准
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidate = os.path.join(project_root, font_path)
        if os.path.exists(candidate):
            return candidate
        logger.warning(f"字体文件未找到: {font_path} (已尝试 {candidate})")
        return None

    def _render_label_bitmap(self, sn: str):
        """用 PIL 渲染整张标签的可变内容(日期/SN/二维码)为 1-bit 位图

        返回 PIL Image(模式 '1')；坐标系与 ZPL 点坐标一致(600dpi)。
        仅渲染可变字段，预印内容由标签纸自带。
        """
        from PIL import Image, ImageDraw, ImageFont
        import qrcode

        label_w = int(self.paper_width * self.dpi / 25.4)
        label_h = int(self.paper_height * self.dpi / 25.4)

        # 白底(1-bit: 255=白/不打印, 0=黑/打印)
        img = Image.new('1', (label_w, label_h), 1)
        draw = ImageDraw.Draw(img)

        font_path = self._resolve_font_path()

        def load_font(size):
            if font_path:
                try:
                    return ImageFont.truetype(font_path, size)
                except Exception as e:
                    logger.error(f"加载字体失败({font_path}): {e}")
            return ImageFont.load_default()

        # 日期
        date_cfg = self.zpl_layout.get('date', {})
        date_str = datetime.now().strftime("%Y/%m/%d")
        dfont = load_font(date_cfg.get('font_size', 40))
        draw.text((date_cfg.get('x', 300), date_cfg.get('y', 388)),
                  date_str, font=dfont, fill=0)

        # SN
        sn_cfg = self.zpl_layout.get('sn', {})
        sfont = load_font(sn_cfg.get('font_size', 40))
        draw.text((sn_cfg.get('x', 77), sn_cfg.get('y', 512)),
                  f"SN: {sn}", font=sfont, fill=0)

        # 二维码
        qr_cfg = self.zpl_layout.get('qrcode', {})
        ecc_map = {
            'L': qrcode.constants.ERROR_CORRECT_L,
            'M': qrcode.constants.ERROR_CORRECT_M,
            'Q': qrcode.constants.ERROR_CORRECT_Q,
            'H': qrcode.constants.ERROR_CORRECT_H,
        }
        qr = qrcode.QRCode(
            error_correction=ecc_map.get(qr_cfg.get('error_correction', 'M'),
                                         qrcode.constants.ERROR_CORRECT_M),
            box_size=qr_cfg.get('box_size', 9),
            border=0,
        )
        qr.add_data(sn)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color='black', back_color='white').convert('1')
        img.paste(qr_img, (qr_cfg.get('x', 770), qr_cfg.get('y', 300)))

        return img

    @staticmethod
    def _bitmap_to_gfa(img) -> str:
        """把 1-bit PIL 位图转成 ZPL ^GFA 指令(ASCII hex)"""
        width, height = img.size
        bytes_per_row = (width + 7) // 8
        total_bytes = bytes_per_row * height

        # ZPL: 0 bit = 不打印, 1 bit = 打印(黑)。PIL '1' 模式 0=黑,需取反
        pixels = img.load()
        rows_hex = []
        for y in range(height):
            row = bytearray(bytes_per_row)
            for x in range(width):
                if pixels[x, y] == 0:  # 黑点 -> 需要打印
                    row[x // 8] |= (0x80 >> (x % 8))
            rows_hex.append(row.hex().upper())
        data = ''.join(rows_hex)

        return f"^GFA,{total_bytes},{total_bytes},{bytes_per_row},{data}"

    def _build_zpl_bitmap(self, sn: str, capacity: str = '') -> str:
        """构建 ZPL 打印指令（位图渲染模式）"""
        label_w = int(self.paper_width * self.dpi / 25.4)
        label_h = int(self.paper_height * self.dpi / 25.4)

        img = self._render_label_bitmap(sn)
        gfa = self._bitmap_to_gfa(img)

        zpl = "^XA\n"
        zpl += f"^PW{label_w}\n"
        zpl += f"^LL{label_h}\n"
        zpl += "^FO0,0\n"
        zpl += gfa + "^FS\n"
        zpl += "^XZ\n"
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
