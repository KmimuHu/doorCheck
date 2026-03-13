from zeroconf import ServiceBrowser, ServiceListener, Zeroconf, ServiceInfo
from typing import Callable, Dict, List, Optional
import threading
import socket
import json
from ..utils.logger import logger


class DeviceInfo:
    def __init__(self, sn: str, model: str, ip: str, port: int, properties: Dict = None):
        self.sn = sn
        self.model = model
        self.ip = ip
        self.port = port
        self.properties = properties or {}
        
        self.hw_ver = None
        self.fw_ver = None
        
        if 'device' in self.properties:
            try:
                device_data = json.loads(self.properties['device'])
                self.hw_ver = device_data.get('hw_ver', '')
                self.fw_ver = device_data.get('fw_ver', '')
                logger.debug(f"解析设备 {self.sn} 版本信息: hw_ver={self.hw_ver}, fw_ver={self.fw_ver}")
            except Exception as e:
                logger.warning(f"解析设备 {self.sn} 版本信息失败: {e}")
                pass

    def get_display_name(self):
        """获取设备的显示名称，格式：sn(hw_ver=x,fw_ver=y)"""
        if self.hw_ver and self.fw_ver:
            return f"{self.sn}(hw_ver={self.hw_ver},fw_ver={self.fw_ver})"
        elif self.hw_ver:
            return f"{self.sn}(hw_ver={self.hw_ver})"
        elif self.fw_ver:
            return f"{self.sn}(fw_ver={self.fw_ver})"
        else:
            return self.sn

    def __repr__(self):
        return f"Device(sn={self.sn}, model={self.model}, ip={self.ip}, port={self.port})"


class DeviceDiscoveryListener(ServiceListener):
    def __init__(self, on_device_found: Callable[[DeviceInfo], None], on_device_removed: Optional[Callable[[str], None]] = None):
        self.on_device_found = on_device_found
        self.on_device_removed = on_device_removed
        self.discovered_devices: Dict[str, DeviceInfo] = {}
        self._lock = threading.Lock()

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            self._process_service(info)

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            self._process_service(info)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        with self._lock:
            if name in self.discovered_devices:
                device = self.discovered_devices.pop(name)
                logger.info(f"设备离线: {device}")
                if self.on_device_removed:
                    self.on_device_removed(device.sn)
    
    def refresh_all_devices(self, zc: Zeroconf, service_type: str) -> None:
        with self._lock:
            device_names = list(self.discovered_devices.keys())

        logger.info(f"刷新 {len(device_names)} 个已知设备...")
        for name in device_names:
            info = zc.get_service_info(service_type, name)
            if info:
                self._process_service(info)

    def _process_service(self, info):
        try:
            addresses = info.parsed_addresses()
            if not addresses:
                return

            ip = addresses[0]
            port = info.port
            properties = {k.decode('utf-8'): v.decode('utf-8') for k, v in info.properties.items()}
            
            sn = properties.get('sn', '')
            model = properties.get('model', '')
            
            if not sn and 'device' in properties:
                try:
                    import json
                    device_info = json.loads(properties['device'])
                    sn = device_info.get('sn', '')
                    model = device_info.get('model', '')
                except:
                    pass
            
            if not sn and info.name:
                name_parts = info.name.split('.')
                if name_parts and name_parts[0].startswith('lock-'):
                    sn = name_parts[0]
            
            if sn:
                device = DeviceInfo(sn, model or 'Unknown', ip, port, properties)
                is_new = info.name not in self.discovered_devices
                self.discovered_devices[info.name] = device
                
                if is_new:
                    logger.info(f"发现新设备: {device.get_display_name()} ({device.ip})")
                else:
                    logger.info(f"更新设备: {device.get_display_name()} ({device.ip})")
                
                if self.on_device_found:
                    self.on_device_found(device)
        except Exception as e:
            logger.error(f"处理设备信息失败: {e}")


class MasterMdnsService:
    def __init__(self, zeroconf: Zeroconf, port: int = 8080):
        self.zeroconf = zeroconf
        self.port = port
        self.service_info = None
    
    def register(self):
        try:
            local_ip = self._get_local_ip()
            hostname = socket.gethostname()
            
            device_info = {"sn": "master-001", "model": "MASTER"}
            
            self.service_info = ServiceInfo(
                "_master._tcp.local.",
                f"master-{hostname}._master._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    b'device': json.dumps(device_info, separators=(',', ':')).encode('utf-8')
                }
            )
            self.zeroconf.register_service(self.service_info)
            logger.info(f"主控mDNS服务已注册: {local_ip}:{self.port}, device: {json.dumps(device_info, separators=(',', ':'))}")
        except Exception as e:
            logger.error(f"注册主控mDNS服务失败: {e}")
    
    def _get_local_ip(self):
        """获取局域网IP地址"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return socket.gethostbyname(socket.gethostname())
    
    def unregister(self):
        if self.service_info:
            try:
                self.zeroconf.unregister_service(self.service_info)
                logger.info("主控mDNS服务已注销")
            except Exception as e:
                logger.error(f"注销主控mDNS服务失败: {e}")
