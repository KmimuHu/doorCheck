import json
import time
from typing import Dict, Any
from .crypto import generate_nonce, generate_message_id, calculate_hmac_signature, build_sign_data


class Message:
    def __init__(self, action: str, body: Dict[str, Any], psk: str):
        self.ver = "1.0"
        self.mid = generate_message_id()
        self.ts = int(time.time() * 1000)
        self.nonce = generate_nonce()
        self.type = "req"
        self.action = action
        self.body = body
        self.psk = psk
        self.sig = self._generate_signature()

    def _generate_signature(self) -> str:
        body_json = json.dumps(self.body, separators=(', ', ': '), ensure_ascii=False)
        sign_data = build_sign_data(
            self.ver, self.mid, self.ts, self.action, body_json, self.nonce, self.psk
        )
        return calculate_hmac_signature(sign_data, self.psk)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "header": {
                "ver": self.ver,
                "mid": self.mid,
                "ts": self.ts,
                "nonce": self.nonce,
                "type": self.type,
                "action": self.action,
                "sig": self.sig
            },
            "body": self.body
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class OpenDoorMessage(Message):
    def __init__(self, psk: str, duration: int = 5000):
        body = {"duration": duration}
        super().__init__("open", body, psk)


class CloseDoorMessage(Message):
    def __init__(self, psk: str):
        body = {}
        super().__init__("close", body, psk)


class QueryStatusMessage(Message):
    def __init__(self, psk: str):
        body = {
            "query_type": "status",
            "fields": ["status", "battery", "temperature"]
        }
        super().__init__("query", body, psk)


class QueryDeviceSnMessage(Message):
    def __init__(self, psk: str):
        body = {}
        super().__init__("query_device_sn", body, psk)


class DiscoverMessage(Message):
    def __init__(self, psk: str):
        body = {}
        super().__init__("discover", body, psk)


class RemotePairingMessage(Message):
    def __init__(self, psk: str, duration: int = 100):
        body = {"duration": duration}
        super().__init__("remote_pairing", body, psk)


class OTAUpgradeMessage(Message):
    def __init__(self, psk: str, tftp_server: str, tftp_port: int = 69, firmware_file: str = "update.fwpkg", file_size: int = 0, md5: str = None):
        body = {
            "tftp_url": f"tftp://{tftp_server}:{tftp_port}/{firmware_file}",
            "file_size": file_size
        }
        if md5:
            body["md5"] = md5
        super().__init__("ota_upgrade", body, psk)


class WriteWifiBleMacMessage(Message):
    def __init__(self, psk: str, mac: str):
        body = {"mac": mac}
        super().__init__("write_wifi_ble_mac", body, psk)


class ReadWifiBleMaxMessage(Message):
    def __init__(self, psk: str):
        body = {}
        super().__init__("read_wifi_ble_mac", body, psk)


class WriteSleMaxMessage(Message):
    def __init__(self, psk: str, mac: str):
        body = {"mac": mac}
        super().__init__("write_sle_mac", body, psk)


class ReadSleMaxMessage(Message):
    def __init__(self, psk: str):
        body = {}
        super().__init__("read_sle_mac", body, psk)


class ResetConfigMessage(Message):
    def __init__(self, psk: str):
        body = {}
        super().__init__("reset_config", body, psk)
