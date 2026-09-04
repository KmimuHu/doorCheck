import asyncio
import logging
import os
import ssl
import sys
import subprocess
from amqtt.broker import Broker
from ..utils.logger import logger
from ..utils.paths import get_app_dir


def _patch_amqtt_mqtt31_support():
    """Monkey-patch amqtt 使其同时支持 MQTT v3.1 (MQIsdp) 和 v3.1.1 (MQTT)。
    amqtt 默认只接受 proto_name="MQTT" + proto_level=4，
    而嵌入式设备可能使用 MQTT v3.1（proto_name="MQIsdp", proto_level=3）。
    通过 patch ConnectVariableHeader.from_stream，在解析阶段将 v3.1 转换为 v3.1.1。"""
    import amqtt.mqtt.protocol.broker_handler as bh

    if getattr(bh, '_mqtt31_patched', False):
        return

    from amqtt.mqtt.connect import ConnectVariableHeader
    _orig_from_stream = ConnectVariableHeader.from_stream

    @classmethod
    async def _patched_from_stream(cls, reader, fixed_header):
        result = await _orig_from_stream.__func__(cls, reader, fixed_header)
        if result.proto_name == "MQIsdp" and result.proto_level == 3:
            logger.debug("MQTT v3.1 客户端连接，自动转换为 v3.1.1 兼容模式")
            result.proto_name = "MQTT"
            result.proto_level = 4
        return result

    ConnectVariableHeader.from_stream = _patched_from_stream
    bh._mqtt31_patched = True
    logger.info("已启用 MQTT v3.1 (MQIsdp) 兼容支持")


def _enable_legacy_ssl_ciphers():
    """Patch ssl.create_default_context 使其创建的上下文包含传统密码套件。
    OpenSSL 3.0 默认只提供 GCM/CHACHA20，而嵌入式设备 mbedtls 需要 AES-CBC-SHA 等旧套件。
    通过 patch 标准库函数而非 amqtt 内部 API，确保在 PyInstaller 打包后同样生效。"""
    if getattr(ssl, '_legacy_ciphers_enabled', False):
        return
    _original = ssl.create_default_context

    def _patched(*args, **kwargs):
        ctx = _original(*args, **kwargs)
        ctx.set_ciphers('DEFAULT:!aNULL:!eNULL:@SECLEVEL=0')
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    ssl.create_default_context = _patched
    ssl._legacy_ciphers_enabled = True
    logger.info("已启用传统SSL密码套件（兼容嵌入式设备）")


class MQTTBrokerManager:
    def __init__(self, host: str = '0.0.0.0', port: int = 1883, ssl_enabled: bool = True):
        self.host = host
        self.port = port
        self.ssl_enabled = ssl_enabled
        self.broker = None
        self.loop = None
        self.running = False
        self.broker_thread = None

        logging.getLogger('amqtt').setLevel(logging.WARNING)

    def _cleanup_port(self):
        try:
            if sys.platform == 'win32':
                result = subprocess.run(
                    f'netstat -ano | findstr ":{self.port}" | findstr "LISTENING"',
                    shell=True, capture_output=True, text=True
                )
                if result.stdout.strip():
                    for line in result.stdout.strip().split('\n'):
                        parts = line.split()
                        if parts:
                            pid = parts[-1]
                            subprocess.run(f'taskkill /PID {pid} /F', shell=True)
                            logger.info(f"已清理占用端口{self.port}的进程: PID={pid}")
            else:
                result = subprocess.run(
                    f"lsof -i :{self.port} | grep LISTEN | awk '{{print $2}}'",
                    shell=True, capture_output=True, text=True
                )
                if result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        subprocess.run(f"kill -9 {pid}", shell=True)
                        logger.info(f"已清理占用端口{self.port}的进程: PID={pid}")
        except Exception as e:
            logger.warning(f"清理端口失败: {e}")

    async def _start_broker(self):
        try:
            app_dir = get_app_dir()
            ca_file = os.path.join(app_dir, 'certs', 'ca.crt')
            cert_file = os.path.join(app_dir, 'certs', 'mqtt_server.crt')
            key_file = os.path.join(app_dir, 'certs', 'mqtt_server.key')

            config = {
                'listeners': {},
                'sys_interval': 10,
                'auth': {
                    'allow-anonymous': True,
                    'plugins': ['auth_anonymous']
                },
                'topic-check': {
                    'enabled': False
                }
            }

            if self.ssl_enabled and os.path.exists(ca_file) and os.path.exists(cert_file) and os.path.exists(key_file):
                config['listeners']['default'] = {
                    'type': 'tcp',
                    'bind': f'{self.host}:{self.port}',
                    'ssl': True,
                    'cafile': ca_file,
                    'certfile': cert_file,
                    'keyfile': key_file
                }
                logger.info(f"MQTT Broker SSL已启用 [CA: {ca_file}, Cert: {cert_file}]")
            else:
                config['listeners']['default'] = {
                    'type': 'tcp',
                    'bind': f'{self.host}:{self.port}'
                }
                logger.info(f"MQTT Broker 非SSL模式")

            _enable_legacy_ssl_ciphers()
            _patch_amqtt_mqtt31_support()
            self.broker = Broker(config)
            await self.broker.start()

            protocol = "SSL/TCP" if self.ssl_enabled else "TCP"
            logger.info(f"MQTT Broker已启动 ({protocol}): {self.host}:{self.port}")
            self.running = True

            # 保持运行直到 running 标志被设为 False
            while self.running:
                await asyncio.sleep(0.5)

            # 循环退出后，主动关闭 broker
            logger.debug("开始关闭 MQTT Broker...")
            if self.broker:
                await self.broker.shutdown()
                logger.debug("MQTT Broker shutdown 完成")

        except Exception as e:
            logger.error(f"MQTT Broker启动失败: {e}")
            raise

    def start(self):
        """在独立线程中启动 MQTT Broker"""
        import threading
        self.broker_thread = threading.Thread(target=self._run_broker, daemon=True)
        self.broker_thread.start()
        logger.info("MQTT Broker 线程已启动")

    def _run_broker(self):
        """在独立线程中运行 broker 的 event loop"""
        try:
            self._cleanup_port()
            # Windows 上 amqtt 需要 SelectorEventLoop（ProactorEventLoop 不支持部分 SSL 操作）
            if sys.platform == 'win32':
                self.loop = asyncio.SelectorEventLoop()
            else:
                self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._start_broker())
        except Exception as e:
            logger.error(f"MQTT Broker运行异常: {e}")
        finally:
            # 清理 loop
            if self.loop and not self.loop.is_closed():
                # 给一点时间让所有任务完成
                try:
                    pending = asyncio.all_tasks(self.loop)
                    for task in pending:
                        task.cancel()
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except:
                    pass
                self.loop.close()
            logger.debug("MQTT Broker event loop 已关闭")

    def stop(self):
        """停止 MQTT Broker"""
        if not self.running:
            # 已经停止，避免重复调用
            return

        logger.info("正在停止 MQTT Broker...")

        # 设置停止标志，让 _start_broker 中的循环退出
        self.running = False

        # 等待线程结束（broker 会在 _start_broker 循环退出后自动关闭）
        # 因为是 daemon 线程，即使未完成也不会阻塞程序退出
        if self.broker_thread and self.broker_thread.is_alive():
            # 缩短等待时间到 1.5 秒（broker shutdown 通常很快）
            self.broker_thread.join(timeout=1.5)
            if self.broker_thread.is_alive():
                # daemon 线程会在主程序退出时自动终止，所以这只是个提示
                logger.debug("MQTT Broker 线程仍在运行（守护线程将随主程序退出）")
            else:
                logger.debug("MQTT Broker 线程已正常结束")

        logger.info("MQTT Broker已停止")