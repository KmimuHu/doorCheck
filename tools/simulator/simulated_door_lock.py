"""
模拟门锁 - 完整实现设计文档流程
用于测试主控的交互功能
"""
import time
import json
import socket
import requests
import paho.mqtt.client as mqtt
from zeroconf import Zeroconf, ServiceBrowser, ServiceListener, ServiceInfo
from typing import Optional, Dict


class SimulatedDoorLock:
    def __init__(self, device_sn: str, device_model: str = "DC-DOOR-3.0", product_id: str = "1696"):
        self.device_sn = device_sn
        self.device_model = device_model
        self.product_id = product_id
        
        self.master_ip = None
        self.master_port = None
        self.mqtt_config = None
        self.topics = None
        self.secret_key = None
        
        self.zeroconf = None
        self.mqtt_client = None
        self.service_info = None
        
        self.state = "IDLE"
        
        print(f"[门锁] 初始化: SN={device_sn}, Model={device_model}")
    
    def start(self):
        """启动门锁，按照设计文档流程"""
        print("\n" + "="*60)
        print("模拟门锁启动流程")
        print("="*60)
        
        try:
            # 步骤1: 发现主控
            if not self._discover_master():
                print("[门锁] ❌ 未发现主控，退出")
                return False
            
            # 步骤2: 获取配置
            if not self._get_config():
                print("[门锁] ❌ 获取配置失败，退出")
                return False
            
            # 步骤3: 连接MQTT
            if not self._connect_mqtt():
                print("[门锁] ❌ MQTT连接失败，退出")
                return False
            
            # 步骤4: 注册mDNS
            if not self._register_mdns():
                print("[门锁] ❌ mDNS注册失败，退出")
                return False
            
            # 步骤5: 发送上线消息
            self._send_online_message()
            
            print("\n" + "="*60)
            print("[门锁] ✅ 启动完成，等待主控命令...")
            print("="*60)
            
            self.state = "ONLINE"
            return True
            
        except Exception as e:
            print(f"[门锁] ❌ 启动失败: {e}")
            return False
    
    def _discover_master(self) -> bool:
        """步骤1: 通过mDNS发现主控"""
        print("\n[步骤1] 发现主控...")
        
        class MasterListener(ServiceListener):
            def __init__(self, parent):
                self.parent = parent
                self.found = False
            
            def add_service(self, zc, type_, name):
                info = zc.get_service_info(type_, name)
                if info:
                    addresses = info.parsed_addresses()
                    if addresses:
                        self.parent.master_ip = addresses[0]
                        self.parent.master_port = info.port
                        self.found = True
                        print(f"[门锁] ✅ 发现主控: {self.parent.master_ip}:{self.parent.master_port}")
        
        try:
            self.zeroconf = Zeroconf()
            listener = MasterListener(self)
            browser = ServiceBrowser(self.zeroconf, "_master._tcp.local.", listener)
            
            timeout = 10
            for i in range(timeout):
                if listener.found:
                    return True
                time.sleep(1)
            
            print(f"[门锁] ❌ {timeout}秒内未发现主控")
            return False
            
        except Exception as e:
            print(f"[门锁] ❌ mDNS发现失败: {e}")
            return False
    
    def _get_config(self) -> bool:
        """步骤2: 从主控获取MQTT配置"""
        print("\n[步骤2] 获取配置...")
        
        try:
            url = f"http://{self.master_ip}:{self.master_port}/api/device/config"
            params = {
                "sn": self.device_sn,
                "productId": self.product_id
            }
            
            print(f"[门锁] 请求: {url}?sn={self.device_sn}&productId={self.product_id}")
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code != 200:
                print(f"[门锁] ❌ HTTP错误: {response.status_code}")
                return False
            
            data = response.json()
            if data.get("code") != 0:
                print(f"[门锁] ❌ 配置错误: {data.get('message')}")
                return False
            
            config = data.get("data", {})
            self.mqtt_config = config.get("mqtt", {})
            self.topics = config.get("topics", {})
            self.secret_key = config.get("secretKey", "")
            
            print(f"[门锁] ✅ 获取配置成功")
            print(f"       MQTT Broker: {self.mqtt_config.get('broker')}:{self.mqtt_config.get('port')}")
            print(f"       Command Topic: {self.topics.get('command')}")
            return True
            
        except Exception as e:
            print(f"[门锁] ❌ 获取配置失败: {e}")
            return False
    
    def _connect_mqtt(self) -> bool:
        """步骤3: 连接主控的MQTT Broker"""
        print("\n[步骤3] 连接MQTT...")
        
        try:
            client_id = self.mqtt_config.get("clientId", f"device_{self.device_sn}")
            self.mqtt_client = mqtt.Client(client_id=client_id)
            
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_message = self._on_mqtt_message
            self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
            
            broker = self.mqtt_config.get("broker")
            port = self.mqtt_config.get("port")
            
            print(f"[门锁] 连接到: {broker}:{port}")
            self.mqtt_client.connect(broker, port, 60)
            self.mqtt_client.loop_start()
            
            time.sleep(2)
            
            if self.state == "MQTT_CONNECTED":
                print(f"[门锁] ✅ MQTT连接成功")
                return True
            else:
                print(f"[门锁] ❌ MQTT连接超时")
                return False
                
        except Exception as e:
            print(f"[门锁] ❌ MQTT连接失败: {e}")
            return False
    
    def _register_mdns(self) -> bool:
        """步骤4: 注册mDNS服务"""
        print("\n[步骤4] 注册mDNS...")
        
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            
            self.service_info = ServiceInfo(
                "_mqtt._tcp.local.",
                f"{self.device_sn}._mqtt._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=1883,
                properties={
                    b'sn': self.device_sn.encode(),
                    b'model': self.device_model.encode()
                }
            )
            
            self.zeroconf.register_service(self.service_info)
            print(f"[门锁] ✅ mDNS注册成功: {self.device_sn}._mqtt._tcp.local.")
            return True
            
        except Exception as e:
            print(f"[门锁] ❌ mDNS注册失败: {e}")
            return False
    
    def _send_online_message(self):
        """步骤5: 发送上线消息"""
        print("\n[步骤5] 发送上线消息...")
        
        try:
            status_topic = self.topics.get("status")
            message = {
                "header": {
                    "ver": "1.0",
                    "mid": f"msg_{int(time.time())}",
                    "ts": int(time.time()),
                    "type": "event",
                    "action": "online",
                    "device": {
                        "sn": self.device_sn,
                        "model": self.device_model
                    }
                },
                "body": {
                    "status": "online",
                    "timestamp": int(time.time())
                }
            }
            
            self.mqtt_client.publish(status_topic, json.dumps(message), qos=1)
            print(f"[门锁] ✅ 上线消息已发送到: {status_topic}")
            
        except Exception as e:
            print(f"[门锁] ⚠️  发送上线消息失败: {e}")
    
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT连接回调"""
        if rc == 0:
            self.state = "MQTT_CONNECTED"
            command_topic = self.topics.get("command")
            client.subscribe(command_topic, qos=1)
            print(f"[门锁] MQTT已连接，订阅: {command_topic}")
        else:
            print(f"[门锁] MQTT连接失败，错误码: {rc}")
    
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT断开回调"""
        print(f"[门锁] MQTT断开连接，错误码: {rc}")
        self.state = "DISCONNECTED"
    
    def _on_mqtt_message(self, client, userdata, msg):
        """MQTT消息回调"""
        try:
            payload = msg.payload.decode('utf-8')
            print(f"\n[门锁] 收到命令: {msg.topic}")
            print(f"       内容: {payload}")
            
            message = json.loads(payload)
            action = message.get("header", {}).get("action")
            
            if action == "open":
                self._handle_open_command(message)
            elif action == "close":
                self._handle_close_command(message)
            elif action == "query":
                self._handle_query_command(message)
            else:
                print(f"[门锁] ⚠️  未知命令: {action}")
                
        except Exception as e:
            print(f"[门锁] ❌ 处理消息失败: {e}")
    
    def _handle_open_command(self, message):
        """处理开门命令"""
        print("[门锁] 🚪 执行开门...")
        time.sleep(0.5)
        print("[门锁] ✅ 门已打开")
        self._send_reply(message, "success", {"status": "opened"})
    
    def _handle_close_command(self, message):
        """处理关门命令"""
        print("[门锁] 🔒 执行关门...")
        time.sleep(0.5)
        print("[门锁] ✅ 门已关闭")
        self._send_reply(message, "success", {"status": "closed"})
    
    def _handle_query_command(self, message):
        """处理查询命令"""
        print("[门锁] 📊 查询状态...")
        status_data = {
            "status": "online",
            "battery": 85,
            "signal": "good"
        }
        self._send_reply(message, "success", status_data)
    
    def _send_reply(self, request_message, result, data):
        """发送回复消息"""
        try:
            reply_topic = self.topics.get("reply")
            reply = {
                "header": {
                    "ver": "1.0",
                    "mid": f"reply_{int(time.time())}",
                    "ts": int(time.time()),
                    "type": "resp",
                    "action": request_message.get("header", {}).get("action"),
                    "device": {
                        "sn": self.device_sn,
                        "model": self.device_model
                    }
                },
                "body": {
                    "result": result,
                    "data": data
                }
            }
            
            self.mqtt_client.publish(reply_topic, json.dumps(reply), qos=1)
            print(f"[门锁] 📤 回复已发送到: {reply_topic}")
            
        except Exception as e:
            print(f"[门锁] ❌ 发送回复失败: {e}")
    
    def stop(self):
        """停止门锁"""
        print("\n[门锁] 正在停止...")
        
        if self.service_info and self.zeroconf:
            self.zeroconf.unregister_service(self.service_info)
            print("[门锁] mDNS已注销")
        
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            print("[门锁] MQTT已断开")
        
        if self.zeroconf:
            self.zeroconf.close()
        
        print("[门锁] ✅ 已停止")


def main():
    """主程序入口"""
    import sys
    
    device_sn = "SIM001" if len(sys.argv) < 2 else sys.argv[1]
    
    door_lock = SimulatedDoorLock(device_sn)
    
    try:
        if door_lock.start():
            print("\n按 Ctrl+C 停止模拟门锁...")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n收到停止信号")
    finally:
        door_lock.stop()


if __name__ == "__main__":
    main()
