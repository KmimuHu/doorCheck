import time
import threading
from enum import Enum
from typing import Callable, Optional
from ..communication.mqtt_client import MQTTClient
from ..protocol.message import OpenDoorMessage, CloseDoorMessage, QueryStatusMessage
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

    def add_step(self, step_name: str, success: bool, message: str = ""):
        self.steps.append({
            "name": step_name,
            "success": success,
            "message": message,
            "timestamp": time.time()
        })

    def set_passed(self):
        self.status = TestStatus.PASSED
        self.end_time = time.time()

    def set_failed(self, error: str):
        self.status = TestStatus.FAILED
        self.error_message = error
        self.end_time = time.time()
