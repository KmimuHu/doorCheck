# 模拟门锁

用于测试主控功能的门锁模拟器。

## 使用方法

```bash
# 默认SN (SIM001)
python simulator/simulated_door_lock.py

# 指定SN
python simulator/simulated_door_lock.py ABC123
```

## 测试流程

1. 启动主控：`python main.py`
2. 启动模拟器：`python simulator/simulated_door_lock.py`
3. 在主控GUI中选择设备并测试

## 实现流程

```
1. 发现主控 (mDNS查询 _master._tcp.local.)
2. 获取配置 (HTTP GET /api/device/config)
3. 连接MQTT (订阅command topic)
4. 注册mDNS (_mqtt._tcp.local.)
5. 发送上线消息 (status topic)
```

## 支持的命令

- `open` - 开门
- `close` - 关门
- `query` - 查询状态

## 故障排查

- 无法发现主控：确认主控已启动并注册mDNS
- 获取配置失败：检查HTTP服务端口8080
- MQTT连接失败：检查MQTT Broker端口1883
