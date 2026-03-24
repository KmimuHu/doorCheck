import paho.mqtt.client as mqtt
import json
import threading
import ssl
import os
import time
from typing import Callable, Optional
from ..utils.logger import logger
from ..utils.config import Config
from ..utils.paths import get_app_dir


class MQTTClient:
    def __init__(self, broker: str, port: int, product_id: str, device_sn: str):
        self.broker = broker
        self.port = port
        self.product_id = product_id
        self.device_sn = device_sn
        self.client = None
        self.connected = False
        self.message_callbacks = {}
        self._lock = threading.Lock()
        self._connect_event = threading.Event()
        
        self.command_topic = f"{product_id}/{device_sn}/command"
        self.reply_topic = f"{product_id}/{device_sn}/reply"
        self.status_topic = f"{product_id}/{device_sn}/status"
        self.event_topic = f"{product_id}/{device_sn}/event"

    def connect(self, timeout: int = 5) -> bool:
        try:
            self._connect_event.clear()
            
            client_id = f"doorcheck_{self.device_sn}"
            self.client = mqtt.Client(client_id=client_id)
            
            if self.port == 1881 or self.port == 8883:
                ca_cert = os.path.join(get_app_dir(), 'certs', 'ca.crt')
                
                if os.path.exists(ca_cert):
                    self.client.tls_set(ca_certs=ca_cert, cert_reqs=ssl.CERT_NONE)
                    self.client.tls_insecure_set(True)
                    logger.info(f"MQTT SSL已启用: {ca_cert}")
            
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            logger.info(f"连接MQTT Broker: {self.broker}:{self.port}")
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            
            if self._connect_event.wait(timeout):
                logger.info(f"MQTT连接已建立: {self.device_sn}")
                return True
            else:
                logger.error(f"MQTT连接超时: {self.device_sn}")
                return False
                
        except Exception as e:
            logger.error(f"MQTT连接失败: {e}")
            return False

    def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("MQTT已断开")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            logger.info("MQTT连接成功")

            if self.device_sn == "broadcast":
                self.client.subscribe("+/+/reply", qos=1)
                self.client.subscribe("+/+/status", qos=1)
                self.client.subscribe("+/+/event", qos=1)
                logger.info("订阅主题: +/+/reply, +/+/status, +/+/event")
            else:
                self.client.subscribe(self.reply_topic, qos=1)
                self.client.subscribe(self.status_topic, qos=1)
                self.client.subscribe(self.event_topic, qos=1)
                logger.info(f"订阅主题: {self.reply_topic}, {self.status_topic}, {self.event_topic}")

            self._connect_event.set()
        else:
            logger.error(f"MQTT连接失败，错误码: {rc}")
            self._connect_event.set()

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        logger.warning(f"MQTT断开连接，错误码: {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8')
            logger.debug(f"收到消息 [{msg.topic}]: {payload}")
            
            message = json.loads(payload)
            
            with self._lock:
                for callback in self.message_callbacks.values():
                    callback(msg.topic, message)
        except Exception as e:
            logger.error(f"处理消息失败: {e}")

    def publish(self, message: str) -> bool:
        if not self.connected:
            logger.error("MQTT未连接")
            return False

        try:
            logger.debug(f"准备发送消息: {message[:200]}...")
            result = self.client.publish(self.command_topic, message, qos=1)
            result.wait_for_publish(timeout=5)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"消息发送成功到 {self.command_topic}")
                return True
            else:
                logger.error(f"消息发送失败，错误码: {result.rc}")
                return False
        except Exception as e:
            logger.error(f"发送消息异常: {e}")
            return False

    def register_callback(self, name: str, callback: Callable):
        with self._lock:
            self.message_callbacks[name] = callback

    def unregister_callback(self, name: str):
        with self._lock:
            if name in self.message_callbacks:
                del self.message_callbacks[name]
