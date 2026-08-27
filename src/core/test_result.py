import time
import threading
from enum import Enum
from typing import Callable, Optional
from ..network.mqtt_client import MQTTClient
from .protocol import OpenDoorMessage, CloseDoorMessage, QueryStatusMessage
from ..utils.logger import logger
from ..utils.config import Config


class TestStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


class TestResult:
    def __init__(self):
        self.status = TestStatus.IDLE
        self.steps = []
        self.error_message = ""
        self.start_time = None
        self.end_time = None
        self.sub_results = []

    def add_step(self, step_name: str, success: bool, message: str = ""):
        self.steps.append({
            "name": step_name,
            "success": success,
            "message": message,
            "timestamp": time.time()
        })
        # 失败步骤必须落盘：此前只入内存 list，导致排查时日志里没有任何失败记录，
        # 只能靠设备侧事件反推失败原因
        if not success:
            logger.warning(f"步骤失败 [{step_name}]" + (f": {message}" if message else ""))

    def set_passed(self):
        self.status = TestStatus.PASSED
        self.end_time = time.time()

    @property
    def duration(self):
        if self.start_time and self.end_time:
            return round(self.end_time - self.start_time, 2)
        return 0

    def set_failed(self, error: str):
        self.status = TestStatus.FAILED
        self.error_message = error
        self.end_time = time.time()
