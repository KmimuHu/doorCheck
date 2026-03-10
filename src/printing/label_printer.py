from PIL import Image, ImageDraw, ImageFont
import qrcode
import os
import sys
from datetime import datetime
from typing import Dict
from ..utils.logger import logger
from ..utils.config import Config
from ..utils.paths import get_app_dir

try:
    import win32print
    import win32ui
    from PIL import ImageWin
    WINDOWS_PRINT_AVAILABLE = True
except ImportError:
    WINDOWS_PRINT_AVAILABLE = False

# Windows 系统常见字体回退列表
_FALLBACK_FONTS = [
    'msyh.ttc',      # 微软雅黑
    'simhei.ttf',    # 黑体
    'simsun.ttc',    # 宋体
    'arial.ttf',     # Arial
]


def _resolve_font(font_family: str, font_size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """按配置字体 -> 系统常见字体 -> 默认字体的顺序尝试加载"""
    candidates = []
    if font_family:
        candidates.append(font_family)
    candidates.extend(_FALLBACK_FONTS)

    for name in candidates:
        try:
            font = ImageFont.truetype(name, font_size)
            return font
        except (OSError, IOError):
            continue

    # 全部失败，用默认字体但放大到接近目标尺寸
    logger.warning(f"无法加载任何字体，使用默认字体 (目标大小: {font_size})")
    return ImageFont.load_default(size=font_size)


class LabelPrinter:
    def __init__(self, config: Config):
        self.config = config
        self.printer_config = config.printer_config
        self.label_config = self.printer_config.get('label_config', {})

        self.dpi = self.printer_config.get('dpi', 600)
        self.paper_width_mm = self.printer_config.get('paper_width', 50)
        self.paper_height_mm = self.printer_config.get('paper_height', 30)

        self.width_px = int(self.label_config.get('labelWidth', 1181))
        self.height_px = int(self.label_config.get('labelHeight', 708))

    def _mm_to_px(self, mm: float) -> int:
        return int(mm * self.dpi / 25.4)

    def create_label_image(self, device_sn: str, test_result: str) -> Image.Image:
        image = Image.new('RGB', (self.width_px, self.height_px), 'white')
        draw = ImageDraw.Draw(image)

        if self.label_config.get('drawBorder', True):
            draw.rectangle([(0, 0), (self.width_px-1, self.height_px-1)], outline='black', width=3)

        self._draw_sn_text(draw, device_sn)
        self._draw_date_text(draw)
        self._draw_qrcode(image, device_sn)

        return image

    def _draw_sn_text(self, draw: ImageDraw, device_sn: str):
        sn_config = self.label_config.get('snTextConfig', {})
        x = sn_config.get('x', 115)
        y = sn_config.get('y', 503)
        font_size = sn_config.get('fontSize', 34)
        font_family = sn_config.get('fontFamily', '')
        bold = sn_config.get('fontBold', False)

        font = _resolve_font(font_family, font_size, bold)
        stroke_w = max(1, font_size // 15) if bold else 0
        draw.text((x, y), f"SN: {device_sn}", fill='black', font=font, stroke_width=stroke_w, stroke_fill='black')

    def _draw_date_text(self, draw: ImageDraw):
        date_config = self.label_config.get('dateConfig', {})
        x = date_config.get('x', 371)
        y = date_config.get('y', 344)
        font_size = date_config.get('fontSize', 32)
        font_family = date_config.get('fontFamily', '')
        bold = date_config.get('fontBold', False)

        date_str = datetime.now().strftime('%Y/%m/%d')

        font = _resolve_font(font_family, font_size, bold)
        stroke_w = max(1, font_size // 15) if bold else 0
        draw.text((x, y), date_str, fill='black', font=font, stroke_width=stroke_w, stroke_fill='black')

    def _draw_qrcode(self, image: Image.Image, device_sn: str):
        qr_config = self.label_config.get('qrCodeConfig', {})
        x = qr_config.get('x', 740)
        y = qr_config.get('y', 181)
        size = qr_config.get('width', 441)

        qr = qrcode.QRCode(version=1, box_size=10, border=1)
        qr.add_data(device_sn)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img = qr_img.resize((size, size))

        image.paste(qr_img, (x, y))

    def print_label(self, device_sn: str, test_result: str = "PASSED") -> bool:
        if not self.printer_config.get('enabled', True):
            logger.info("打印功能未启用")
            return True

        try:
            logger.info(f"开始打印标签: {device_sn}")

            label_image = self.create_label_image(device_sn, test_result)

            if os.name == 'nt':
                return self._print_windows(label_image, device_sn)
            else:
                logger.warning("当前系统不支持打印，仅保存图片")
                return self._save_image(label_image, device_sn)

        except Exception as e:
            logger.error(f"打印失败: {e}")
            return False

    def _print_windows(self, image: Image.Image, device_sn: str = "temp") -> bool:
        if not WINDOWS_PRINT_AVAILABLE:
            logger.warning("Windows打印模块未安装(pywin32)，保存图片代替")
            return self._save_image(image, device_sn)

        try:
            import win32con

            printer_name = win32print.GetDefaultPrinter()
            logger.info(f"使用打印机: {printer_name}")

            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)

            # 获取打印机真实 DPI
            printer_dpi_x = hdc.GetDeviceCaps(win32con.LOGPIXELSX)
            printer_dpi_y = hdc.GetDeviceCaps(win32con.LOGPIXELSY)
            logger.info(f"打印机DPI: {printer_dpi_x}x{printer_dpi_y}")

            # 按打印机真实 DPI 计算纸张输出区域（设备单位）
            paper_w = int(self.paper_width_mm / 25.4 * printer_dpi_x)
            paper_h = int(self.paper_height_mm / 25.4 * printer_dpi_y)
            logger.info(f"输出区域: {paper_w}x{paper_h} dots")

            hdc.StartDoc("Label Print")
            hdc.StartPage()

            dib = ImageWin.Dib(image)
            dib.draw(hdc.GetHandleOutput(), (0, 0, paper_w, paper_h))

            hdc.EndPage()
            hdc.EndDoc()
            hdc.DeleteDC()

            logger.info("打印成功")
            return True
        except Exception as e:
            logger.error(f"Windows打印失败: {e}")
            return False

    def _save_image(self, image: Image.Image, device_sn: str) -> bool:
        try:
            output_dir = os.path.join(get_app_dir(), 'reports')
            os.makedirs(output_dir, exist_ok=True)

            filename = f"label_{device_sn}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = os.path.join(output_dir, filename)

            image.save(filepath)
            logger.info(f"标签图片已保存: {filepath}")
            return True
        except Exception as e:
            logger.error(f"保存图片失败: {e}")
            return False
