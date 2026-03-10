import yaml
import os
from typing import Dict, Any
from .paths import get_app_dir


class Config:
    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self.load_config()

    def load_config(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(get_app_dir(), 'config', 'config.yaml')
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)

    def get(self, key: str, default=None) -> Any:
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    @property
    def device_psk(self) -> str:
        return self.get('device.psk', 'weidian_24h')

    @property
    def product_id(self) -> str:
        return self.get('device.product_id', '1696')

    @property
    def mqtt_broker(self) -> str:
        return self.get('mqtt.broker', '22.0.0.10')

    @property
    def mqtt_port(self) -> int:
        return self.get('mqtt.port', 1883)

    @property
    def mdns_service_type(self) -> str:
        return self.get('mdns.service_type', '_mqtt._tcp.local.')

    @property
    def test_open_duration(self) -> int:
        return self.get('test.open_duration', 5000)

    @property
    def test_timeout(self) -> int:
        return self.get('test.test_timeout', 30)

    @property
    def http_port(self) -> int:
        return self.get('http.port', 8081)

    @property
    def printer_enabled(self) -> bool:
        return self.get('printer.enabled', True)

    @property
    def printer_config(self) -> Dict:
        return self.get('printer', {})
