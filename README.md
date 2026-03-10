# 智能门锁产测工具

门锁工厂质检自动化测试软件，支持设备发现、功能测试、标签打印。

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

## 功能特性

- 设备自动发现（mDNS）
- MQTT通信与自动化测试
- 标签打印（50x30mm）
- 图形界面（PyQt5）

## 配置

编辑 `config/config.yaml`：

```yaml
device:
  psk: "weidian_24h"
  product_id: "1696"

mqtt:
  broker: "22.0.0.10"
  port: 1883
```

## 测试流程

1. 设备接入网络（22.0.0.10网段）
2. 自动发现设备
3. 选择设备并开始测试
4. 查看结果并打印标签

## 项目结构

```
doorCheck/
├── src/
│   ├── discovery/       # 设备发现
│   ├── communication/   # MQTT通信
│   ├── protocol/        # 协议层
│   ├── testing/         # 测试引擎
│   ├── printing/        # 标签打印
│   ├── gui/             # GUI界面
│   ├── http_server/     # HTTP配置服务
│   ├── mqtt_broker/     # MQTT代理
│   ├── tftp_server/     # TFTP服务
│   └── utils/           # 工具类
├── config/              # 配置文件
├── tools/               # 门锁模拟器
├── build.py             # 构建脚本
└── main.py              # 入口
```

## 打包部署

Windows打包：
```bash
python build.py
```

## 故障排查

- 设备无法发现：检查网络连接和IP段
- MQTT连接失败：确认broker地址 22.0.0.10:1883
- 查看日志：`logs/doorcheck_YYYYMMDD.log`

## 技术栈

Python 3.14 | PyQt5 | paho-mqtt | zeroconf | Pillow
