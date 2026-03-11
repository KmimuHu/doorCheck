# 智能门锁产测工具

门锁工厂质检自动化测试软件，支持设备发现、功能测试、OTA升级、标签打印。

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

## 功能特性

- 设备自动发现（mDNS）与心跳监控
- MQTT加密通信与自动化测试
- 一键全流程测试（MAC烧写、遥控器配对、应急开关）
- OTA固件升级（TFTP传输，实时进度显示）
- 标签打印（50x30mm，二维码）
- 设备NV配置重置
- 图形界面（PyQt5，左右分栏布局）

## 测试流程

1. 启动程序，自动发现设备（mDNS）
2. 在左侧设备列表选择目标设备
3. 在右侧详情面板执行操作：
   - **一键测试**：完整产测流程
   - **烧写MAC**：单独烧写MAC地址
   - **遥控器配对**：单独测试遥控器配对
   - **应急开关**：单独测试应急开关
   - **OTA升级**：上传固件后升级设备
4. 测试通过后打印标签

## 项目结构

```
doorCheck/
├── src/
│   ├── gui/               # GUI界面
│   │   ├── main_window.py          # 主窗口与业务逻辑
│   │   ├── device_list_panel.py    # 左侧设备列表面板
│   │   └── device_detail_panel.py  # 右侧设备详情面板
│   ├── discovery/         # mDNS设备发现
│   ├── communication/     # MQTT通信
│   ├── protocol/          # 协议层（加密/消息）
│   ├── testing/           # 测试引擎
│   ├── printing/          # 标签打印
│   ├── http_server/       # HTTP配置服务
│   ├── mqtt_broker/       # 内嵌MQTT代理
│   ├── tftp_server/       # TFTP固件传输服务
│   └── utils/             # 工具类（配置、日志、路径）
├── config/                # 配置文件
├── certs/                 # SSL证书
├── tools/                 # 辅助工具（门锁模拟器、压测脚本）
├── build.py               # 打包构建脚本
└── main.py                # 入口
```

## 打包部署

Windows打包：
```bash
python build.py
```

## 故障排查

- 设备无法发现：检查网络连接，确认设备与主机在同一网段
- MQTT连接失败：确认broker地址和端口配置（默认 127.0.0.1:1881）
- TFTP启动失败：端口69需要管理员权限，使用 `sudo python main.py`
- 查看日志：`logs/doorcheck_YYYYMMDD.log`

## 技术栈

Python 3.8+ | PyQt5 | paho-mqtt | amqtt | zeroconf | Flask | Pillow
