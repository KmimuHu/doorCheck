# 智能设备产测工具 v3.0

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/PyQt5-5.15+-green.svg)](https://pypi.org/project/PyQt5/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

统一的智能设备产测平台，支持智能门控和智能音箱两种产测模式。

## 🎯 核心特性

### 🚪 智能门控产测
- 设备自动发现（mDNS + 网络扫描）
- MAC地址烧写
- 遥控器配对测试
- 应急开关测试
- 无线检测（WiFi/BLE/SLE）
- OTA固件升级
- 标签打印
- 测试记录管理

### 🔊 智能音箱产测
- 4窗口并行测试
- 室内/室外音箱类型切换
- MAC地址烧录
- 音麦测试
- 无线检测（WiFi/蓝牙/星闪）
- 红外/微波测试
- RTSP视频流显示（室外音箱）
- 固件升级
- 测试日志管理

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行程序

```bash
python main.py
```

程序启动后会显示选择对话框，选择需要的产测模式即可。

### ���行测试

```bash
python test_integration.py
```

## 📦 项目结构

```
doorCheck/
├── main.py                    # 统一启动入口
├── config/config.yaml         # 配置文件
├── src/
│   ├── ui/                    # UI界面
│   │   ├── startup_dialog.py  # 启动选择对话框
│   │   ├── main_window.py     # 门控主窗口
│   │   └── speaker_test_window.py  # 音箱主窗口
│   ├── core/                  # 门控核心逻辑
│   ├── testing/               # 音箱测试逻辑
��   ├── communication/         # 通信模块
│   ├── network/               # 网络服务
│   ├── hardware/              # 硬件控制
│   ├── utils/                 # 工具类
│   └── data/                  # 数据存储
├── requirements.txt           # 依赖列表
├── test_integration.py        # 集成测试
└── MERGE_GUIDE.md            # 详细使用说明
```

## 🔧 配置说明

编辑 `config/config.yaml` 进行配置：

```yaml
app:
  name: "智能设备产测工具"
  version: "3.0"

device:
  psk: "weidian_24h"
  product_id: "1696"

mqtt:
  broker: "127.0.0.1"
  port: 1881

test:
  ir_strict_verify: true  # 红外强校验

ui:
  speaker_type: indoor    # indoor | outdoor
```

## 📖 使用说明

### 启动流程

1. **运行程序**
   ```bash
   python main.py
   ```

2. **选择模式**
   - 点击 "🚪 智能门控产测工具" → 门控测试模式
   - 点击 "🔊 智能音箱产测工具" → 音箱测试模式

3. **开始测试**
   - 门控模式：选择设备 → 自动测试 → 打印标签
   - 音箱模式：设备自动分配 → 一键检测 → 打印标签

详细说明请参考 [MERGE_GUIDE.md](MERGE_GUIDE.md)

## 🔍 测试验证

所有核心功能已通过集成测试：

```bash
$ python test_integration.py
==================================================
测试模块导入
==================================================
✅ 启动对话框: 成功
✅ 门控主窗口: 成功
✅ 音箱主窗口: 成功
✅ 配置管理: 成功
✅ 日志管理: 成功

总计: 5 成功, 0 失败

==================================================
测试配置文件
==================================================
应用名称: 智能设备产测工具
应用版本: 3.0
音箱类型: indoor
红外强校验: True
✅ 配置加载成功

==================================================
✅ 所有测试通过！
==================================================
```

## 🛠️ 技术架构

- **UI框架**: PyQt5
- **设备发现**: mDNS (Zeroconf) + IP扫描
- **通信协议**: MQTT + HTTP + TFTP
- **数据存储**: SQLite
- **日志管理**: Python logging
- **标签打印**: ZPL/TSPL协议

## 📋 依赖项

- PyQt5 >= 5.15.0
- paho-mqtt >= 1.6.0
- amqtt >= 0.11.0
- zeroconf >= 0.131.0
- requests >= 2.32.0
- PyYAML >= 6.0
- Flask >= 3.0.0
- Pillow >= 11.0.0
- qrcode >= 7.0
- reportlab >= 4.0.0
- imageio-ffmpeg >= 0.6.0
- pyserial >= 3.5
- pywin32 >= 306 (仅Windows)
- pyinstaller >= 6.0.0

## 💻 系统要求

- Python 3.8+
- Windows / macOS / Linux
- 建议内存：4GB+
- 网络要求：与测试设备在同一局域网

## 📝 变更日志

### v3.0 (2026-07-14) - 重大重构
- ✨ UI风格完全统一（音箱采用门控配色和样式）
- ✨ 代码结构规范化（按5层架构重组：core/network/hardware/data/utils）
- ✨ 启动对话框按钮间距优化
- ♻️ 音箱模块统一命名（speaker_前缀）
- 🐛 修复crypto模块冲突
- 📝 完善文档和测试
- 🎯 保持两个工具所有原有功能

### v2.7 (门控项目)
- 实现测试记录按日期筛选导出
- 实现Zebra ZPL打印机识别和配置
- 清理废弃的label_config配置项

### v2.0 (音箱项目)
- 实现4窗口并行测试
- 支持室内/室外音箱类型切换
- 添加视频流显示功能
- 实现固件升级功能

## 🤝 开发团队

- **项目负责人**: 微店IoT团队
- **合并完成**: 2026-07-14
- **基础项目**: doorCheck (门控产测工具)
- **集成项目**: hornCheck (音箱产测工具)

## 📄 许可证

本项目为专有软件，版权归属微店IoT团队。未经授权不得复制、修改或分发。

## 🙏 致谢

感谢所有参与门控产测工具和音箱产测工具开发的团队成员。

---

**注意**: 本工具用于生产环境设备测试，请确保在授权的网络环境中使用。
