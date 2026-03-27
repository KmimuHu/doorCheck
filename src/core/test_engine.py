import csv
import sys
import time
import threading
import requests
from typing import Callable, Optional, Dict
from .test_result import TestResult, TestStatus
from ..network.mqtt_client import MQTTClient
from .protocol_message import (OpenDoorMessage, CloseDoorMessage, QueryStatusMessage,
                               OTAUpgradeMessage, RemotePairingMessage,
                               WriteWifiBleMacMessage, ReadWifiBleMaxMessage,
                               WriteSleMaxMessage, ReadSleMaxMessage,
                               ResetConfigMessage)
from ..utils.logger import logger
from ..utils.config import Config
from ..utils.paths import get_app_dir


class TestEngine:
    def __init__(self, mqtt_client: MQTTClient, config: Config):
        self.mqtt_client = mqtt_client
        self.config = config
        self.result = TestResult()
        self.current_response = None
        self.response_event = threading.Event()
        self.emergency_event = threading.Event()
        self.on_progress_callback = None
        self.on_test_item_callback = None

        self.mqtt_client.register_callback("test_engine", self._on_message_received)

    def _on_message_received(self, topic: str, message: Dict):
        logger.debug(f"测试引擎收到消息: {topic}")
        if "event" in topic:
            action = message.get('header', {}).get('action', '')
            logger.debug(f"事件消息action: {action}")
            if action == "emergency_switch":
                emergency_status = message.get('body', {}).get('emergencyStatus', '')
                logger.info(f"收到应急开关事件通知: emergencyStatus={emergency_status}")
                if str(emergency_status) == "1":
                    self.emergency_event.set()
        elif "reply" in topic or "status" in topic:
            action = message.get('header', {}).get('action', '')
            logger.debug(f"消息action: {action}")
            self.current_response = message
            self.response_event.set()

    def _wait_for_response(self, timeout: int = 10) -> Optional[Dict]:
        self.response_event.clear()
        self.current_response = None

        if self.response_event.wait(timeout):
            return self.current_response
        return None

    def _query_door_state(self, timeout: int = 5) -> Optional[str]:
        query_msg = QueryStatusMessage(self.config.device_psk)
        self.mqtt_client.publish(query_msg.to_json())

        response = self._wait_for_response(timeout)
        if not response:
            logger.error("查询状态超时")
            return None

        body = response.get('body', {})
        actual_state = body.get('status', '')
        logger.info(f"当前状态: {actual_state}")
        return actual_state

    def _verify_door_state(self, expected_state: str, timeout: int = 5) -> bool:
        logger.info(f"验证门锁状态，期望: {expected_state}")
        actual_state = self._query_door_state(timeout)

        state_mapping = {
            "opened": ["opened", "unlocked"],
            "closed": ["closed", "locked"]
        }

        expected_states = state_mapping.get(expected_state, [expected_state])
        is_match = actual_state in expected_states

        if is_match:
            logger.info(f"✓ 状态验证通过: {actual_state} 匹配 {expected_state}")
        else:
            logger.error(f"✗ 状态验证失败: {actual_state} 不匹配 {expected_state}")

        return is_match

    def _report_progress(self, message: str):
        logger.info(message)
        if self.on_progress_callback:
            self.on_progress_callback(message)

    def _report_test_item(self, test_name: str, status: str, message: str = ""):
        if self.on_test_item_callback:
            self.on_test_item_callback(test_name, status, message)

    def test_open_door(self) -> bool:
        self._report_progress("【步骤1】测试开锁功能")

        open_msg = OpenDoorMessage(self.config.device_psk, self.config.test_open_duration)
        if not self.mqtt_client.publish(open_msg.to_json()):
            self.result.add_step("发送开锁指令", False, "发送失败")
            return False

        self.result.add_step("发送开锁指令", True)

        response = self._wait_for_response(self.config.test_timeout)
        if not response:
            self.result.add_step("等待开锁响应", False, "超时")
            return False

        self.result.add_step("等待开锁响应", True)

        time.sleep(1)

        if not self._verify_door_state("opened"):
            self.result.add_step("验证开锁状态", False, "状态不符合预期")
            return False

        self.result.add_step("验证开锁状态", True)
        return True

    def test_close_door(self) -> bool:
        self._report_progress("【步骤2】测试关锁功能")

        close_msg = CloseDoorMessage(self.config.device_psk)
        if not self.mqtt_client.publish(close_msg.to_json()):
            self.result.add_step("发送关锁指令", False, "发送失败")
            return False

        self.result.add_step("发送关锁指令", True)

        response = self._wait_for_response(self.config.test_timeout)
        if not response:
            self.result.add_step("等待关锁响应", False, "超时")
            return False

        self.result.add_step("等待关锁响应", True)

        time.sleep(1)

        if not self._verify_door_state("closed"):
            self.result.add_step("验证关锁状态", False, "状态不符合预期")
            return False

        self.result.add_step("验证关锁状态", True)
        return True

    def run_full_test(self, report_callback: Callable = None) -> TestResult:
        self.result = TestResult()
        self.result.status = TestStatus.RUNNING
        self.result.start_time = time.time()
        failed_tests = []

        try:
            self._report_progress("开始产测流程...")

            self._report_progress("【步骤1】烧写MAC地址")
            self._report_test_item("burn_mac", "testing")
            device_sn = self.mqtt_client.device_sn
            burn_success, burn_message = self.burn_mac_addresses(device_sn, self._report_progress)
            if not burn_success:
                failed_tests.append("MAC地址烧写")
                self._report_progress(f"⚠️ MAC地址烧写失败: {burn_message}，继续后续测试")
                self.result.add_step("烧写MAC地址", False, burn_message)
                self._report_test_item("burn_mac", "failed", burn_message)
            else:
                self._report_progress(f"✅ {burn_message}")
                self.result.add_step("烧写MAC地址", True, burn_message)
                self._report_test_item("burn_mac", "passed", burn_message)

            time.sleep(1)

            self._report_progress("【步骤2】查询当前门锁状态")
            current_state = self._query_door_state()
            if not current_state:
                self.result.set_failed("查询初始状态失败")
                return self.result

            self.result.add_step("查询初始状态", True, f"当前状态: {current_state}")

            if current_state in ["closed", "locked"]:
                self._report_progress("门锁当前为关闭状态，先测试开锁")
                if not self.test_open_door():
                    failed_tests.append("开锁测试")
                    self._report_progress("⚠️ 开锁测试失败，继续后续测试")

                time.sleep(1)

                if not self.test_close_door():
                    failed_tests.append("关锁测试")
                    self._report_progress("⚠️ 关锁测试失败，继续后续测试")
            else:
                self._report_progress("门锁当前为开启状态，先测试关锁")
                if not self.test_close_door():
                    failed_tests.append("关锁测试")
                    self._report_progress("⚠️ 关锁测试失败，继续后续测试")

                time.sleep(1)

                if not self.test_open_door():
                    failed_tests.append("开锁测试")
                    self._report_progress("⚠️ 开锁测试失败，继续后续测试")

            time.sleep(1)

            self._report_progress("【步骤3】测试应急开关")
            self._report_test_item("emergency_switch", "testing")
            emergency_start_time = time.time()
            emergency_step_start = len(self.result.steps)
            emergency_success = self.test_emergency_switch(timeout=10, report_callback=report_callback)
            emergency_end_time = time.time()
            emergency_steps = list(self.result.steps[emergency_step_start:])
            if not emergency_success:
                failed_tests.append("应急开关测试")
                self._report_progress("⚠️ 应急开关测试失败，继续后续测试")
                self._report_test_item("emergency_switch", "failed")
            else:
                self._report_progress("✅ 应急开关测试通过，请松开应急开关")
                self._report_test_item("emergency_switch", "passed")
                for i in range(3, 0, -1):
                    if report_callback:
                        report_callback("transition", i)
                    time.sleep(1)
                if report_callback:
                    report_callback("hide_dialog", 0)

            self.result.sub_results.append({
                'test_type': '应急开关测试',
                'status': 'passed' if emergency_success else 'failed',
                'duration': round(emergency_end_time - emergency_start_time, 2),
                'steps': emergency_steps,
            })

            self._report_progress("【步骤4】测试遥控器配对")
            self._report_test_item("remote_pairing", "testing")
            remote_start_time = time.time()
            remote_step_start = len(self.result.steps)
            remote_success = self.test_remote_pairing(pairing_duration=3000, open_timeout=8,
                                                      report_callback=report_callback)
            remote_end_time = time.time()
            remote_steps = list(self.result.steps[remote_step_start:])
            if not remote_success:
                failed_tests.append("遥控器配对测试")
                self._report_progress("⚠️ 遥控器配对测试失败")
                self._report_test_item("remote_pairing", "failed")
            else:
                if report_callback:
                    report_callback("hide_dialog", 0)
                self._report_test_item("remote_pairing", "passed")

            self.result.sub_results.append({
                'test_type': '遥控器配对测试',
                'status': 'passed' if remote_success else 'failed',
                'duration': round(remote_end_time - remote_start_time, 2),
                'steps': remote_steps,
            })

            if failed_tests:
                fail_message = "以下测试项未通过: " + ", ".join(failed_tests)
                self._report_progress(f"\n❌ {fail_message}")
                self.result.set_failed(fail_message)
            else:
                self._report_progress("\n✅ 所有测试通过！")
                self.result.set_passed()


        except Exception as e:
            logger.error(f"测试异常: {e}")
            self.result.set_failed(f"测试异常: {str(e)}")

        return self.result

    def set_progress_callback(self, callback: Callable):
        self.on_progress_callback = callback

    def set_test_item_callback(self, callback: Callable):
        self.on_test_item_callback = callback

    def test_remote_pairing(self, pairing_duration: int = 3000, open_timeout: int = 8,
                            report_callback: Callable = None) -> bool:
        self._report_progress("【步骤4】测试遥控器配对")

        current_state = self._query_door_state()
        if not current_state:
            self.result.add_step("检查初始门锁状态", False, "查询状态失败")
            return False

        logger.info(f"当前门锁状态: {current_state}")

        if current_state in ["opened", "unlocked"]:
            logger.info("门锁处于开启状态，执行上锁指令")
            self._report_progress("门锁处于开启状态，执行上锁指令")

            close_msg = CloseDoorMessage(self.config.device_psk)
            if not self.mqtt_client.publish(close_msg.to_json()):
                self.result.add_step("发送上锁指令", False, "发送失败")
                return False

            self.result.add_step("发送上锁指令", True)

            response = self._wait_for_response(self.config.test_timeout)
            if not response:
                self.result.add_step("等待上锁响应", False, "超时")
                return False

            self.result.add_step("等待上锁响应", True)

            time.sleep(1)

            if not self._verify_door_state("closed"):
                self.result.add_step("验证上锁状态", False, "上锁失败")
                return False

            self.result.add_step("验证上锁状态", True)
        else:
            self.result.add_step("检查初始门锁状态", True, "门锁已处于关闭状态")

        pairing_msg = RemotePairingMessage(self.config.device_psk, duration=pairing_duration)
        if not self.mqtt_client.publish(pairing_msg.to_json()):
            self.result.add_step("发送遥控器配对指令", False, "发送失败")
            return False

        self.result.add_step("发送遥控器配对指令", True)
        logger.info("遥控器配对命令已发送，等待设备响应")

        response = self._wait_for_response(self.config.test_timeout)
        if not response:
            self.result.add_step("等待配对响应", False, "超时")
            return False

        self.result.add_step("等待配对响应", True)

        logger.info("配对命令已响应，开始配对倒计时")
        self._report_progress("请按遥控器配对按键")

        if report_callback:
            pairing_start_time = time.time()
            pairing_timeout = pairing_duration / 1000.0
            while time.time() - pairing_start_time < pairing_timeout:
                remaining = pairing_timeout - (time.time() - pairing_start_time)
                if remaining > 0:
                    report_callback("pairing_countdown", int(remaining) + 1)
                time.sleep(0.1)
        else:
            time.sleep(pairing_duration / 1000.0)

        self._report_progress(f"请在{open_timeout}秒内按下遥控器开门")

        logger.info("配对命令已响应，循环查询锁状态...")
        self._report_progress("循环查询锁状态中...")

        start_time = time.time()
        pairing_success = False
        last_query_time = 0
        query_interval = 0.5

        while time.time() - start_time < open_timeout:
            current_time = time.time()

            if report_callback:
                remaining = open_timeout - (current_time - start_time)
                if remaining > 0:
                    report_callback("open_countdown", int(remaining) + 1)

            if current_time - last_query_time >= query_interval:
                actual_state = self._query_door_state(timeout=2)
                last_query_time = current_time

                if actual_state in ["opened", "unlocked"]:
                    logger.info(f"✓ 检测到开门状态: {actual_state}")
                    pairing_success = True
                    break

                logger.debug(f"当前状态: {actual_state}，继续查询...")

            time.sleep(0.1)

        if not pairing_success:
            self.result.add_step("验证遥控器配对", False, f"{open_timeout}秒内未检测到开门状态")
            return False

        self.result.add_step("验证遥控器配对", True)
        return True

    def test_emergency_switch(self, timeout: int = 10, report_callback: Callable = None) -> bool:
        self._report_progress("【步骤3】测试应急开关功能")

        current_state = self._query_door_state()
        if not current_state:
            self.result.add_step("检查初始门锁状态", False, "查询状态失败")
            return False

        logger.info(f"当前门锁状态: {current_state}")

        if current_state in ["opened", "unlocked"]:
            logger.info("门锁处于开启状态，执行上锁指令")
            self._report_progress("门锁处于开启状态，执行上锁指令")

            close_msg = CloseDoorMessage(self.config.device_psk)
            if not self.mqtt_client.publish(close_msg.to_json()):
                self.result.add_step("发送上锁指令", False, "发送失败")
                return False

            self.result.add_step("发送上锁指令", True)

            response = self._wait_for_response(self.config.test_timeout)
            if not response:
                self.result.add_step("等待上锁响应", False, "超时")
                return False

            self.result.add_step("等待上锁响应", True)

            time.sleep(1)

            if not self._verify_door_state("closed"):
                self.result.add_step("验证上锁状态", False, "上锁失败")
                return False

            self.result.add_step("验证上锁状态", True)
        else:
            self.result.add_step("检查初始门锁状态", True, "门锁已处于关闭状态")

        logger.info("门锁已上锁，等待用户按应急开关...")
        self._report_progress("请按应急开关进行测试，等待检测中...")

        # 清除之前可能残留的应急开关事件
        self.emergency_event.clear()

        start_time = time.time()
        emergency_success = False

        while time.time() - start_time < timeout:
            current_time = time.time()

            if report_callback:
                remaining = timeout - (current_time - start_time)
                if remaining > 0:
                    report_callback("emergency_countdown", int(remaining) + 1)

            # 等待应急开关事件通知（固件master在线时只发通知不开门，需主动下发开锁指令）
            if self.emergency_event.wait(timeout=0.3):
                logger.info("✓ 收到应急开关事件通知，下发开锁指令")
                self._report_progress("收到应急开关事件，正在下发开锁指令...")
                open_msg = OpenDoorMessage(self.config.device_psk, self.config.test_open_duration)
                if not self.mqtt_client.publish(open_msg.to_json()):
                    self.result.add_step("应急开关开锁", False, "发送开锁指令失败")
                    return False
                response = self._wait_for_response(self.config.test_timeout)
                if not response:
                    self.result.add_step("应急开关开锁", False, "等待开锁响应超时")
                    return False
                self.result.add_step("应急开关开锁", True)
                logger.info("✓ 应急开关开锁指令已执行，应急开关功能正常")
                emergency_success = True
                break

        if not emergency_success:
            self.result.add_step("验证应急开关", False, f"{timeout}秒内未收到应急开关事件通知")
            return False

        self.result.add_step("验证应急开关", True)
        return True

    def test_ota_upgrade(self, tftp_server: str, tftp_port: int = 69, firmware_file: str = "update.fwpkg",
                         file_size: int = 0, fw_ver: str = None) -> bool:
        self._report_progress(f"【OTA升级】开始固件升级: {tftp_server}:{tftp_port}/{firmware_file}")

        ota_msg = OTAUpgradeMessage(self.config.device_psk, tftp_server, tftp_port, firmware_file, file_size, fw_ver=fw_ver)
        if not self.mqtt_client.publish(ota_msg.to_json()):
            logger.error("发送OTA升级指令失败")
            return False

        logger.info("OTA升级指令已发送，等待设备响应...")

        start_time = time.time()
        timeout = 1000

        while time.time() - start_time < timeout:
            response = self._wait_for_response(timeout=5)
            if response:
                header = response.get('header', {})
                action = header.get('action', '')
                code = header.get('code', -1)

                logger.debug(f"收到响应: action={action}, code={code}")

                if action == 'ota_upgrade':
                    logger.debug(f"OTA升级响应: code={code}, body={response.get('body', {})}")

                    if code == 0:
                        logger.info("✓ OTA升级指令已接受，设备开始下载固件")
                        self._report_progress("OTA升级指令已接受，设备正在下载固件...")
                        return True
                    else:
                        error_msg = response.get('body', {}).get('error', 'Unknown error')
                        logger.error(f"✗ OTA升级失败 (code={code}): {error_msg}")
                        return False
                else:
                    logger.debug(f"忽略非OTA响应: {action}")

        logger.error("OTA升级响应超时")
        return False

    def burn_mac_addresses(self, device_sn: str, progress_callback: Callable = None) -> tuple[bool, str]:
        try:
            if progress_callback:
                progress_callback("开始烧写MAC地址...")

            logger.info(f"开始为设备 {device_sn} 烧写MAC地址")

            mac_data = self._allocate_mac_from_csv()
            if mac_data:
                logger.info("已从本地CSV文件获取MAC地址")
            else:
                logger.warning("本地CSV分配失败，尝试从云端API获取MAC地址")
                if progress_callback:
                    progress_callback("本地CSV不可用，从云端API分配...")
                mac_data = self._allocate_mac_from_api(device_sn)
            if not mac_data:
                error_msg = "获取MAC地址分配失败（本地CSV和API均失败）"
                logger.error(error_msg)
                if progress_callback:
                    progress_callback(f"❌ {error_msg}")
                return False, error_msg

            wifi_mac = mac_data.get('wifiMac', '')
            sle_mac = mac_data.get('sparkMac', '')

            logger.info(f"获取到MAC地址 - WiFi: {wifi_mac}, SLE: {sle_mac}")
            if progress_callback:
                progress_callback(f"已获取MAC地址 - WiFi: {wifi_mac}, SLE: {sle_mac}")

            if progress_callback:
                progress_callback("检查设备当前MAC地址...")

            current_wifi_mac, current_sle_mac = self._read_current_mac()
            if not current_wifi_mac or not current_sle_mac:
                error_msg = "读取设备当前MAC地址失败"
                logger.error(error_msg)
                if progress_callback:
                    progress_callback(f"❌ {error_msg}")
                return False, error_msg

            logger.info(f"当前MAC地址 - WiFi: {current_wifi_mac}, SLE: {current_sle_mac}")
            if progress_callback:
                progress_callback(f"当前MAC - WiFi: {current_wifi_mac}, SLE: {current_sle_mac}")

            need_burn_wifi = current_wifi_mac.startswith('00')
            need_burn_sle = current_sle_mac.startswith('00')

            if not need_burn_wifi and not need_burn_sle:
                msg = "设备MAC地址已烧写，无需重复烧写"
                logger.info(msg)
                if progress_callback:
                    progress_callback(f"✅ {msg}")
                return True, msg

            failed_items = []

            if need_burn_wifi:
                if progress_callback:
                    progress_callback(f"正在烧写WiFi/BLE MAC: {wifi_mac}...")

                wifi_mac_clean = wifi_mac.replace(":", "").replace("-", "").upper()
                if not self._write_wifi_ble_mac(wifi_mac_clean):
                    failed_items.append("WiFi/BLE MAC烧写失败")
                    logger.error("WiFi/BLE MAC烧写失败")
                else:
                    logger.info("WiFi/BLE MAC烧写成功")
                    if progress_callback:
                        progress_callback("✅ WiFi/BLE MAC烧写成功")
            else:
                logger.info("WiFi/BLE MAC已烧写，跳过")
                if progress_callback:
                    progress_callback("WiFi/BLE MAC已烧写，跳过")

            if need_burn_sle:
                if progress_callback:
                    progress_callback(f"正在烧写SLE MAC: {sle_mac}...")

                sle_mac_clean = sle_mac.replace(":", "").replace("-", "").upper()
                if not self._write_sle_mac(sle_mac_clean):
                    failed_items.append("SLE MAC烧写失败")
                    logger.error("SLE MAC烧写失败")
                else:
                    logger.info("SLE MAC烧写成功")
                    if progress_callback:
                        progress_callback("✅ SLE MAC烧写成功")
            else:
                logger.info("SLE MAC已烧写，跳过")
                if progress_callback:
                    progress_callback("SLE MAC已烧写，跳过")

            if progress_callback:
                progress_callback("验证烧写结果...")

            time.sleep(1)

            verify_wifi_mac, verify_sle_mac = self._read_current_mac()
            if not verify_wifi_mac or not verify_sle_mac:
                failed_items.append("验证烧写结果失败")
            else:
                logger.info(f"验证MAC地址 - WiFi: {verify_wifi_mac}, SLE: {verify_sle_mac}")
                if progress_callback:
                    progress_callback(f"验证MAC - WiFi: {verify_wifi_mac}, SLE: {verify_sle_mac}")

                if need_burn_wifi and verify_wifi_mac.startswith('00'):
                    failed_items.append("WiFi/BLE MAC验证失败（仍为00开头）")

                if need_burn_sle and verify_sle_mac.startswith('00'):
                    failed_items.append("SLE MAC验证失败（仍为00开头）")

            if failed_items:
                error_msg = "、".join(failed_items)
                logger.error(f"MAC烧写失败: {error_msg}")
                if progress_callback:
                    progress_callback(f"❌ 烧写失败: {error_msg}")
                return False, error_msg

            success_msg = "MAC地址烧写成功"
            logger.info(success_msg)
            if progress_callback:
                progress_callback(f"✅ {success_msg}")
            return True, success_msg

        except Exception as e:
            error_msg = f"烧写MAC异常: {str(e)}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback(f"❌ {error_msg}")
            return False, error_msg

    def _allocate_mac_from_api(self, device_sn: str) -> Optional[Dict]:
        try:
            url = "http://ishop-oqa.weidian.com/api/mac/allocate"
            headers = {
                "X-API-KEY": "WD_MAC_ALLOC_SECRET",
                "Content-Type": "application/json",
                "Accept": "*/*",
                "User-Agent": "doorChecker/1.0"
            }
            data = {
                "sn": device_sn,
                "moduleType": "WS73"
            }

            logger.info(f"调用MAC分配API: {url}")
            response = requests.post(url, json=data, headers=headers, timeout=10)

            if response.status_code != 200:
                logger.error(f"API调用失败: HTTP {response.status_code}")
                return None

            result = response.json()
            if result.get('code') != 200:
                logger.error(f"API返回错误: {result.get('message')}")
                return None

            return result.get('data')

        except Exception as e:
            logger.error(f"调用MAC分配API异常: {e}")
            return None

    def _get_csv_path(self) -> str:
        """获取 mac_pool.csv 路径，兼容开发环境和 PyInstaller 打包环境"""
        import os
        return os.path.join(get_app_dir(), 'mac_pool.csv')

    def _allocate_mac_from_csv(self) -> Optional[Dict]:
        """从本地 CSV 文件分配一组 MAC 地址，分配后将 status 置为 1"""
        import os
        csv_path = self._get_csv_path()

        if not os.path.exists(csv_path):
            logger.error(f"本地MAC池文件不存在: {csv_path}")
            return None

        try:
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            allocated = None
            allocated_idx = -1
            for idx, row in enumerate(rows):
                if str(row.get('status', '')).strip() != '1':
                    allocated = row
                    allocated_idx = idx
                    break

            if allocated is None:
                logger.error("本地MAC池已耗尽，所有地址均已分配")
                return None

            wifi_mac = allocated.get('wifi', '').strip()
            sle_mac = allocated.get('sle', '').strip()

            if not wifi_mac or not sle_mac:
                logger.error(f"CSV第{allocated_idx + 2}行数据不完整: wifi={wifi_mac}, sle={sle_mac}")
                return None

            # 标记已分配
            rows[allocated_idx]['status'] = '1'
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['wifi', 'sle', 'status'])
                writer.writeheader()
                writer.writerows(rows)

            logger.info(f"从本地CSV分配MAC地址 - WiFi: {wifi_mac}, SLE: {sle_mac}")
            return {'wifiMac': wifi_mac, 'sparkMac': sle_mac}

        except Exception as e:
            logger.error(f"读取本地MAC池异常: {e}")
            return None

    def _read_current_mac(self) -> tuple[str, str]:
        wifi_mac = self._read_wifi_ble_mac()
        sle_mac = self._read_sle_mac()
        return wifi_mac or "", sle_mac or ""

    def _read_wifi_ble_mac(self) -> Optional[str]:
        read_msg = ReadWifiBleMaxMessage(self.config.device_psk)
        if not self.mqtt_client.publish(read_msg.to_json()):
            logger.error("发送读取WiFi/BLE MAC指令失败")
            return None

        response = self._wait_for_response(self.config.test_timeout)
        if not response:
            logger.error("读取WiFi/BLE MAC响应超时")
            return None

        body = response.get('body', {})
        wifi_mac = body.get('wifi_mac', '')
        logger.debug(f"读取到WiFi MAC: {wifi_mac}")
        return wifi_mac

    def _read_sle_mac(self) -> Optional[str]:
        read_msg = ReadSleMaxMessage(self.config.device_psk)
        if not self.mqtt_client.publish(read_msg.to_json()):
            logger.error("发送读取SLE MAC指令失败")
            return None

        response = self._wait_for_response(self.config.test_timeout)
        if not response:
            logger.error("读取SLE MAC响应超时")
            return None

        body = response.get('body', {})
        sle_mac = body.get('mac', '')
        logger.debug(f"读取到SLE MAC: {sle_mac}")
        return sle_mac

    def _write_wifi_ble_mac(self, mac: str) -> bool:
        write_msg = WriteWifiBleMacMessage(self.config.device_psk, mac)
        if not self.mqtt_client.publish(write_msg.to_json()):
            logger.error("发送烧写WiFi/BLE MAC指令失败")
            return False

        response = self._wait_for_response(self.config.test_timeout)
        if not response:
            logger.error("烧写WiFi/BLE MAC响应超时")
            return False

        code = response.get('header', {}).get('code', -1)
        if code == 0:
            logger.info("WiFi/BLE MAC烧写指令执行成功")
            return True
        else:
            error_msg = response.get('body', {}).get('error', 'Unknown error')
            logger.error(f"WiFi/BLE MAC烧写失败: {error_msg}")
            return False

    def _write_sle_mac(self, mac: str) -> bool:
        write_msg = WriteSleMaxMessage(self.config.device_psk, mac)
        if not self.mqtt_client.publish(write_msg.to_json()):
            logger.error("发送烧写SLE MAC指令失败")
            return False

        response = self._wait_for_response(self.config.test_timeout)
        if not response:
            logger.error("烧写SLE MAC响应超时")
            return False

        code = response.get('header', {}).get('code', -1)
        if code == 0:
            logger.info("SLE MAC烧写指令执行成功")
            return True
        else:
            error_msg = response.get('body', {}).get('error', 'Unknown error')
            logger.error(f"SLE MAC烧写失败: {error_msg}")
            return False

    def reset_config(self, progress_callback: Callable = None) -> tuple[bool, str]:
        try:
            if progress_callback:
                progress_callback("发送重置NV配置指令...")

            reset_msg = ResetConfigMessage(self.config.device_psk)
            if not self.mqtt_client.publish(reset_msg.to_json()):
                error_msg = "发送重置配置指令失败"
                logger.error(error_msg)
                return False, error_msg

            response = self._wait_for_response(self.config.test_timeout)
            if not response:
                error_msg = "重置配置响应超时"
                logger.error(error_msg)
                return False, error_msg

            code = response.get('header', {}).get('code', -1)
            body = response.get('body', {})
            result = body.get('result', '')
            message = body.get('message', '')

            if code == 0 and result == 'success':
                success_msg = f"NV配置重置成功: {message}"
                logger.info(success_msg)
                return True, success_msg
            else:
                error_msg = f"NV配置重置失败: {message or 'Unknown error'}"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"重置配置异常: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
