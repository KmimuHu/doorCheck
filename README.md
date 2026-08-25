# 智能设备产测工具

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/PyQt5-5.15+-green.svg)](https://pypi.org/project/PyQt5/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

统一的智能设备产测平台，支持智能门控和智能音箱两种产测模式。

---

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

## 📦 项目结构

```
doorCheck/
├── main.py                         # 统一启动入口
├── build.py                        # 打包编译脚本
├── config/
│   └── config.yaml                 # 配置文件
├── certs/                          # SSL证书目录
├── assets/
│   └── fonts/                      # 字体资源
├── src/
│   ├── ui/                         # UI界面模块
│   │   ├── startup_dialog.py       # 启动模式选择对话框
│   │   ├── main_window.py          # 门控测试主窗口
│   │   ├── speaker_test_window.py  # 音箱测试主窗口
│   │   ├── device_list_panel.py    # 设备列表面板
│   │   ├── device_detail_panel.py  # 设备详情面板
│   │   ├── test_record_panel.py    # 测试记录面板
│   │   ├── test_logs_window.py     # 测试日志窗口
│   │   ├── test_results_window.py  # 测试结果窗口
│   │   ├── firmware_upgrade_dialog.py  # 固件升级对话框
│   │   ├── printer_config_dialog.py    # 打印机配置对话框
│   │   ├── broker_config_dialog.py     # MQTT Broker配置对话框
│   │   └── app_version_dialog.py       # 应用版本信息对话框
│   ├── core/                       # 核心测试引擎
│   │   ├── test_engine.py          # 门控测试引擎
│   │   ├── test_result.py          # 门控测试结果
│   │   ├── speaker_test_engine.py  # 音箱测试引擎
│   │   ├── speaker_test_result.py  # 音箱测试结果
│   │   ├── protocol.py             # 设备协议
│   │   ├── protocol_message.py     # 协议消息
│   │   └── crypto.py               # 加密工具
│   ├── network/                    # 网络通信模块
│   │   ├── mdns_discovery.py       # mDNS设备发现
│   │   ├── ip_scanner.py           # IP网络扫描
│   │   ├── mqtt_broker.py          # MQTT Broker服务
│   │   ├── mqtt_client.py          # MQTT客户端
│   │   ├── speaker_mqtt_datetime_sync.py  # 音箱时间同步
│   │   ├── http_server.py          # HTTP服务器
│   │   ├── speaker_http_client.py  # 音箱HTTP客户端
│   │   ├── tftp_server.py          # TFTP固件服务器
│   │   ├── firmware_server.py      # 固件升级服务器
│   │   └── device_info.py          # 设备信息模型
│   ├── hardware/                   # 硬件控制模块
│   │   ├── universal_printer.py    # 通用标签打印机（ZPL/TSPL）
│   │   ├── label_printer.py        # 门控标签打印
│   │   └── speaker_label_printer.py # 音箱标签打印
│   ├── data/                       # 数据存储模块
│   │   ├── test_record_storage.py  # 门控测试记录存储
│   │   └── speaker_test_database.py # 音箱测试数据库
│   └── utils/                      # 工具类模块
│       ├── config.py               # 配置管理
│       ├── logger.py               # 日志管理
│       ├── paths.py                # 路径工具
│       ├── mac_allocator.py        # MAC地址分配
│       ├── serial_reader.py        # 串口读取
│       ├── test_log_capture.py     # 测试日志捕获
│       └── upload_service.py       # 数据上传服务
├── tools/                          # 开发调试工具
│   ├── doortest.py                 # 门控测试工具
│   ├── door_ctl.py                 # 门控控制工具
│   ├── door_ctl2.py                # 门控控制工具v2
│   ├── door_stress.py              # 门控压力测试
│   ├── test_printer_detection.py   # 打印机检测测试
│   └── simulator/
│       └── simulated_door_lock.py  # 门控模拟器
├── data/                           # 数据文件目录（运行时生成）
├── logs/                           # 日志文件目录（运行时生成）
├── requirements.txt                # Python依赖列表
└── README.md                       # 项目说明文档
```

## 🛠️ 技术架构

| 技术栈 | 说明 |
|--------|------|
| **UI框架** | PyQt5 - 跨平台图形界面 |
| **设备发现** | mDNS (Zeroconf) + IP扫描 |
| **通信协议** | MQTT + HTTP + TFTP |
| **数据存储** | SQLite - 本地测试记录 |
| **日志管理** | Python logging - 分级日志 |
| **标签打印** | ZPL/TSPL - 支持Zebra/Xprinter |
| **固件升级** | TFTP - 固件传输服务 |
| **打包工具** | PyInstaller - 单文件可执行程序 |

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

- **Python版本**: 3.8 或更高
- **操作系统**: Windows / macOS / Linux
- **内存**: 建议 4GB 以上
- **网络**: 与测试设备在同一局域网
- **权限**: Windows需管理员权限（用于网络服务）

## 🚀 快速开始

### 开发环境运行

```bash
# 1. 克隆项目
git clone <repository-url>
cd doorCheck

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行程序
python main.py
```

### 打包编译

```bash
# 执行打包脚本
python build.py

# 打包产物在 dist/ 目录
# Windows: 智能设备产测工具_<版本号>.exe
# 需要同时包含 config/ 和 certs/ 目录
```

### 启动使用

1. **选择测试模式**: 启动后选择"门控产测"或"音箱产测"
2. **门控模式**: 选择设备 → 自动测试 → 打印标签
3. **音箱产测**: 配置参数 → 开始测试 → 查看结果

## 📝 开发说明

### 配置文件

配置文件位于 `config/config.yaml`，包含以下配置项：
- **app**: 应用基本信息（名称、版本）
- **device**: 设备通信参数
- **mqtt**: MQTT服务配置
- **printer**: 标签打印机配置
- **speaker**: 音箱测试参数

### 日志管理

- 日志文件位于 `logs/` 目录
- 文件命名格式: `smart_YYYYMMDD.log`
- 日志级别: DEBUG / INFO / WARNING / ERROR
- 自动按天切分

### 测试数据

- 门控测试记录: `test_records.db` (SQLite)
- 音箱测试数据: `data/speaker_tests.db` (SQLite)
- 支持历史查询和导出

## 🤝 开发团队

- **项目负责人**: 微店IoT团队
- **项目合并**: 2026-07-14
- **基础项目**: doorCheck (门控产测工具)
- **集成项目**: hornCheck (音箱产测工具)

## 📄 许可证

本项目为专有软件，版权归属微店IoT团队。未经授权不得复制、修改或分发。

## 🙏 致谢

感谢所有参与门控产测工具和音箱产测工具开发的团队成员。

---

**注意**: 本工具用于生产环境设备测试，请确保在授权的网络环境中使用。
