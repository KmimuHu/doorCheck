"""
循环开关门测试工具
通过MQTT向门锁发送开门/关门指令，验证门锁状态，记录每次操作的结果和耗时。
"""
import os
import sys
import json
import time
import hmac
import hashlib
import uuid
import secrets
import base64
import logging
import threading
from datetime import datetime
from typing import Optional, Dict

import yaml
import paho.mqtt.client as mqtt

# ============================================================
# 路径 & 配置
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(PROJECT_DIR, "config", "config.yaml")
LOG_DIR = os.path.join(PROJECT_DIR, "logs")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============================================================
# 日志
# ============================================================
def setup_logger() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"door_cycle_{datetime.now():%Y%m%d_%H%M%S}.log")

    lg = logging.getLogger("DoorCycleTest")
    lg.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    lg.addHandler(fh)
    lg.addHandler(ch)

    lg.info(f"日志文件: {log_file}")
    return lg


logger = setup_logger()

# ============================================================
# 消息签名 (复用 src/protocol/crypto.py 逻辑)
# ============================================================

def _generate_nonce(length: int = 16) -> str:
    return secrets.token_hex(length // 2)


def _generate_message_id() -> str:
    return uuid.uuid4().hex


def _build_sign_data(ver, mid, ts, action, body, nonce, psk) -> str:
    return f"{ver}{mid}{ts}{action}{body}{nonce}{psk}"


def _calculate_hmac(data: str, key: str) -> str:
    sig = hmac.new(key.encode(), data.encode(), hashlib.sha256).digest()
    return base64.b64encode(sig).decode()


def build_message(action: str, body: dict, psk: str) -> str:
    ver = "1.0"
    mid = _generate_message_id()
    ts = int(time.time())
    nonce = _generate_nonce()
    body_json = json.dumps(body, separators=(", ", ": "), ensure_ascii=False)
    sign_data = _build_sign_data(ver, mid, ts, action, body_json, nonce, psk)
    sig = _calculate_hmac(sign_data, psk)

    msg = {
        "header": {
            "ver": ver,
            "mid": mid,
            "ts": ts,
            "nonce": nonce,
            "type": "req",
            "action": action,
            "device": {"sn": "master-001", "model": "MASTER"},
            "sig": sig,
        },
        "body": body,
    }
    return json.dumps(msg, ensure_ascii=False)


# ============================================================
# MQTT 客户端封装
# ============================================================
class DoorMQTTClient:
    def __init__(self, broker: str, port: int, product_id: str, device_sn: str):
        self.broker = broker
        self.port = port
        self.product_id = product_id
        self.device_sn = device_sn

        self.command_topic = f"{product_id}/{device_sn}/command"
        self.reply_topic = f"{product_id}/{device_sn}/reply"
        self.status_topic = f"{product_id}/{device_sn}/status"

        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self._connect_event = threading.Event()
        self._response: Optional[Dict] = None
        self._response_event = threading.Event()

    def connect(self, timeout: int = 5) -> bool:
        self._connect_event.clear()
        client_id = f"door_cycle_{self.device_sn}_{int(time.time())}"
        self.client = mqtt.Client(client_id=client_id)

        if self.port in (1881, 8883):
            import ssl
            ca_cert = os.path.join(PROJECT_DIR, "certs", "ca.crt")
            if os.path.exists(ca_cert):
                self.client.tls_set(ca_certs=ca_cert, cert_reqs=ssl.CERT_NONE)
                self.client.tls_insecure_set(True)
                logger.info(f"SSL已启用: {ca_cert}")

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        logger.info(f"连接MQTT: {self.broker}:{self.port}")
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

        if self._connect_event.wait(timeout):
            return self.connected
        logger.error("MQTT连接超时")
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
            client.subscribe("+/+/reply", qos=1)
            client.subscribe("+/+/status", qos=1)
            logger.info("MQTT连接成功，已订阅 reply/status")
            self._connect_event.set()
        else:
            logger.error(f"MQTT连接失败，rc={rc}")
            self._connect_event.set()

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        logger.warning(f"MQTT断开，rc={rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            logger.debug(f"收到 [{msg.topic}]: {msg.payload.decode()}")
            if "reply" in msg.topic or "status" in msg.topic:
                self._response = payload
                self._response_event.set()
        except Exception as e:
            logger.error(f"解析消息失败: {e}")

    def publish(self, message: str) -> bool:
        if not self.connected:
            logger.error("MQTT未连接，无法发送")
            return False
        result = self.client.publish(self.command_topic, message, qos=1)
        result.wait_for_publish()
        return True

    def wait_response(self, timeout: int = 10) -> Optional[Dict]:
        self._response_event.clear()
        self._response = None
        if self._response_event.wait(timeout):
            return self._response
        return None


# ============================================================
# 循环开关门测试
# ============================================================
class DoorCycleTest:
    def __init__(self, client: DoorMQTTClient, psk: str, open_duration: int = 5000,
                 response_timeout: int = 30, interval: float = 1.0):
        self.client = client
        self.psk = psk
        self.open_duration = open_duration
        self.timeout = response_timeout
        self.interval = interval
        self.results = []

    def _send_and_verify(self, action: str, body: dict, expected_state: str) -> dict:
        """发送指令 -> 等待回复 -> 查询状态验证，返回单次结果"""
        record = {
            "action": action,
            "expected_state": expected_state,
            "send_ok": False,
            "reply_ok": False,
            "state_verified": False,
            "actual_state": None,
            "success": False,
            "duration_ms": 0,
            "error": None,
        }

        t0 = time.time()

        # 1. 发送指令
        msg = build_message(action, body, self.psk)
        if not self.client.publish(msg):
            record["error"] = "发送失败"
            record["duration_ms"] = int((time.time() - t0) * 1000)
            return record
        record["send_ok"] = True

        # 2. 等待回复
        reply = self.client.wait_response(self.timeout)
        if not reply:
            record["error"] = "等待回复超时"
            record["duration_ms"] = int((time.time() - t0) * 1000)
            return record
        record["reply_ok"] = True

        # 3. 查询状态验证
        time.sleep(0.5)
        query_msg = build_message("query", {
            "query_type": "status",
            "fields": ["status", "battery", "temperature"]
        }, self.psk)
        self.client.publish(query_msg)
        status_reply = self.client.wait_response(5)

        if status_reply:
            actual = status_reply.get("body", {}).get("status", "")
            record["actual_state"] = actual
            state_map = {
                "opened": ["opened", "unlocked"],
                "closed": ["closed", "locked"],
            }
            if actual in state_map.get(expected_state, [expected_state]):
                record["state_verified"] = True
                record["success"] = True
            else:
                record["error"] = f"状态不匹配: 期望={expected_state}, 实际={actual}"
        else:
            record["error"] = "查询状态超时"

        record["duration_ms"] = int((time.time() - t0) * 1000)
        return record

    def open_door(self) -> dict:
        return self._send_and_verify("open", {"duration": self.open_duration}, "opened")

    def close_door(self) -> dict:
        return self._send_and_verify("close", {}, "closed")

    def run(self, cycles: int):
        logger.info("=" * 60)
        logger.info(f"开始循环开关门测试: {cycles} 次")
        logger.info(f"MQTT: {self.client.broker}:{self.client.port}")
        logger.info(f"设备: {self.client.product_id}/{self.client.device_sn}")
        logger.info(f"开门时长: {self.open_duration}ms, 响应超时: {self.timeout}s, 间隔: {self.interval}s")
        logger.info("=" * 60)

        total_start = time.time()
        open_ok = close_ok = open_fail = close_fail = 0

        for i in range(1, cycles + 1):
            logger.info(f"\n--- 第 {i}/{cycles} 轮 ---")

            # 开门
            logger.info(f"[{i}] 发送开门指令...")
            open_result = self.open_door()
            self.results.append(open_result)
            if open_result["success"]:
                open_ok += 1
                logger.info(f"[{i}] 开门成功 | 状态={open_result['actual_state']} | 耗时={open_result['duration_ms']}ms")
            else:
                open_fail += 1
                logger.error(f"[{i}] 开门失败 | {open_result['error']} | 耗时={open_result['duration_ms']}ms")

            time.sleep(self.interval)

            # 关门
            logger.info(f"[{i}] 发送关门指令...")
            close_result = self.close_door()
            self.results.append(close_result)
            if close_result["success"]:
                close_ok += 1
                logger.info(f"[{i}] 关门成功 | 状态={close_result['actual_state']} | 耗时={close_result['duration_ms']}ms")
            else:
                close_fail += 1
                logger.error(f"[{i}] 关门失败 | {close_result['error']} | 耗时={close_result['duration_ms']}ms")

            if i < cycles:
                time.sleep(self.interval)

        total_ms = int((time.time() - total_start) * 1000)
        self._print_summary(cycles, open_ok, open_fail, close_ok, close_fail, total_ms)

    def _print_summary(self, cycles, open_ok, open_fail, close_ok, close_fail, total_ms):
        open_times = [r["duration_ms"] for r in self.results if r["action"] == "open" and r["success"]]
        close_times = [r["duration_ms"] for r in self.results if r["action"] == "close" and r["success"]]

        def _stat(times):
            if not times:
                return "N/A"
            return f"avg={sum(times)//len(times)}ms, min={min(times)}ms, max={max(times)}ms"

        logger.info("\n" + "=" * 60)
        logger.info("测试结果汇总")
        logger.info("=" * 60)
        logger.info(f"总轮次: {cycles}")
        logger.info(f"开门: 成功={open_ok}, 失败={open_fail}, 成功率={open_ok}/{cycles}")
        logger.info(f"关门: 成功={close_ok}, 失败={close_fail}, 成功率={close_ok}/{cycles}")
        logger.info(f"开门耗时: {_stat(open_times)}")
        logger.info(f"关门耗时: {_stat(close_times)}")
        logger.info(f"总耗时: {total_ms}ms")
        logger.info("=" * 60)


# ============================================================
# 入口
# ============================================================
def main(device_sn: str, cycles: int = 10):
    """
    循环开关门测试入口

    Args:
        device_sn: 设备SN
        cycles: 开关门循环次数
    """
    cfg = load_config()
    broker = cfg.get("mqtt", {}).get("broker", "127.0.0.1")
    port = cfg.get("mqtt", {}).get("port", 1883)
    product_id = cfg.get("device", {}).get("product_id", "1696")
    psk = cfg.get("device", {}).get("psk", "weidian_24h")
    open_duration = cfg.get("test", {}).get("open_duration", 5000)
    response_timeout = cfg.get("test", {}).get("test_timeout", 30)

    client = DoorMQTTClient(broker, port, product_id, device_sn)
    if not client.connect():
        logger.error("MQTT连接失败，退出")
        sys.exit(1)

    try:
        tester = DoorCycleTest(client, psk, open_duration, response_timeout, interval=3.0)
        tester.run(cycles)
    except KeyboardInterrupt:
        logger.info("\n用户中断测试")
    finally:
        client.disconnect()


if __name__ == "__main__":
    # 使用示例: 直接修改下面的设备SN和次数即可
    main(device_sn="E466E512A914", cycles=10)
