from flask import Flask, jsonify, request
from typing import Dict
import socket
from ..utils.logger import logger


class ConfigServer:
    def __init__(self, host: str, port: int, mqtt_broker: str, mqtt_port: int, secret_key: str):
        self.app = Flask(__name__)
        self.host = host
        self.port = port
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.secret_key = secret_key
        self._setup_routes()
    
    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return socket.gethostbyname(socket.gethostname())
    
    def _setup_routes(self):
        @self.app.route('/api/device/config', methods=['GET'])
        def get_device_config():
            sn = request.args.get('sn')
            product_id = request.args.get('productId', '1696')
            
            if not sn:
                logger.warning("配置请求缺少sn参数")
                return jsonify({"code": 400, "message": "缺少sn参数"}), 400
            
            logger.info(f"设备请求配置: sn={sn}, productId={product_id}")
            
            broker_ip = self._get_local_ip() if self.mqtt_broker == '127.0.0.1' else self.mqtt_broker
            
            config = {
                "code": 0,
                "message": "success",
                "data": {
                    "mqtt": {
                        "broker": broker_ip,
                        "port": self.mqtt_port,
                        "username": "",
                        "password": "",
                        "clientId": f"device_{sn}",
                        "keepAlive": 60,
                        "cleanSession": True,
                        "ssl": True,
                        "protocol": "ssl",
                        "verifyCert": False
                    },
                    "topics": {
                        "command": f"{product_id}/{sn}/command",
                        "reply": f"{product_id}/{sn}/reply",
                        "status": f"{product_id}/{sn}/status",
                        "event": f"{product_id}/{sn}/event"
                    },
                    "secretKey": self.secret_key,
                    "heartbeatInterval": 30
                }
            }
            logger.info(f"返回MQTT配置: broker={broker_ip}:{self.mqtt_port}")
            return jsonify(config)
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            return jsonify({"status": "ok"})
    
    def start(self):
        logger.info(f"HTTP配置服务启动: {self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, threaded=True, debug=False)
