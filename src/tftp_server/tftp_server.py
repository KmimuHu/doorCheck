import socket
import os
import threading
import struct
import time
from typing import Optional, Callable
from ..utils.logger import logger


class TFTPServer:
    OPCODE_RRQ = 1
    OPCODE_WRQ = 2
    OPCODE_DATA = 3
    OPCODE_ACK = 4
    OPCODE_ERROR = 5
    OPCODE_OACK = 6
    
    ERROR_NOT_FOUND = 1
    ERROR_ACCESS_VIOLATION = 2
    ERROR_DISK_FULL = 3
    ERROR_ILLEGAL_OPERATION = 4
    
    BLOCK_SIZE = 512
    
    def __init__(self, host: str = '0.0.0.0', port: int = 69):
        self.host = host
        self.port = port
        self.sock = None
        self.running = False
        self.server_thread = None
        self.firmware_file = None
        self.firmware_data = None
        self.transfer_progress_callback = None
        self.active_transfers = {}
    
    def set_firmware_file(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"固件文件不存在: {file_path}")
        
        self.firmware_file = file_path
        with open(file_path, 'rb') as f:
            self.firmware_data = f.read()
        
        logger.info(f"已加载固件文件: {file_path}, 大小: {len(self.firmware_data)} 字节")
    
    def set_progress_callback(self, callback: Callable):
        self.transfer_progress_callback = callback
    
    def start(self):
        if self.running:
            logger.warning("TFTP服务器已在运行")
            return
        
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.host, self.port))
            self.running = True
            
            self.server_thread = threading.Thread(target=self._run_server, daemon=True)
            self.server_thread.start()
            
            logger.info(f"TFTP服务器已启动: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"TFTP服务器启动失败: {e}")
            raise
    
    def stop(self):
        if not self.running:
            return
        
        self.running = False
        if self.sock:
            self.sock.close()
        
        logger.info("TFTP服务器已停止")
    
    def _run_server(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                threading.Thread(target=self._handle_request, args=(data, addr), daemon=True).start()
            except Exception as e:
                if self.running:
                    logger.error(f"TFTP服务器接收数据错误: {e}")
    
    def _handle_request(self, data: bytes, addr: tuple):
        try:
            opcode = struct.unpack('!H', data[:2])[0]
            
            if opcode == self.OPCODE_RRQ:
                self._handle_read_request(data, addr)
            elif opcode == self.OPCODE_ACK:
                self._handle_ack(data, addr)
            else:
                logger.warning(f"不支持的TFTP操作码: {opcode}")
                self._send_error(addr, self.ERROR_ILLEGAL_OPERATION, "不支持的操作")
        except Exception as e:
            logger.error(f"处理TFTP请求失败: {e}")
    
    def _handle_read_request(self, data: bytes, addr: tuple):
        parts = data[2:].split(b'\x00')
        filename = parts[0].decode('ascii')
        mode = parts[1].decode('ascii') if len(parts) > 1 else 'octet'
        
        options = {}
        if len(parts) > 2:
            for i in range(2, len(parts) - 1, 2):
                if i + 1 < len(parts) and parts[i]:
                    option_name = parts[i].decode('ascii').lower()
                    option_value = parts[i + 1].decode('ascii') if parts[i + 1] else ''
                    options[option_name] = option_value
        
        logger.info(f"收到读取请求: {filename} (mode: {mode}, options: {options}) from {addr}")
        
        if not self.firmware_data:
            logger.error("固件文件未加载")
            self._send_error(addr, self.ERROR_NOT_FOUND, "Firmware not loaded")
            return
        
        if filename.endswith('.size'):
            logger.info(f"处理 .size 文件请求，返回固件大小: {len(self.firmware_data)} 字节")
            self._send_size_file(addr, len(self.firmware_data))
            return
        
        expected_filename = os.path.basename(self.firmware_file) if self.firmware_file else None
        if expected_filename and filename != expected_filename:
            logger.info(f"请求文件名 '{filename}' 与上传文件名 '{expected_filename}' 不同，提供已加载的固件")
        
        transfer_id = f"{addr[0]}:{addr[1]}"
        
        transfer_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        transfer_sock.bind((self.host, 0))
        
        self.active_transfers[transfer_id] = {
            'addr': addr,
            'block': 0,
            'total_blocks': (len(self.firmware_data) + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE,
            'sent_bytes': 0,
            'total_bytes': len(self.firmware_data),
            'sock': transfer_sock
        }
        
        threading.Thread(target=self._handle_transfer, args=(transfer_id,), daemon=True).start()
        
        if options:
            self._send_oack(transfer_id, addr, options)
            logger.info(f"发送OACK，等待ACK后开始传输固件: {len(self.firmware_data)} 字节")
        else:
            logger.info(f"开始传输固件: {len(self.firmware_data)} 字节")
            self._send_next_block(transfer_id)
    
    def _handle_transfer(self, transfer_id: str):
        if transfer_id not in self.active_transfers:
            return
        
        transfer = self.active_transfers[transfer_id]
        sock = transfer['sock']
        sock.settimeout(120.0)
        
        local_port = sock.getsockname()[1]
        logger.info(f"传输线程启动: {transfer_id}, 监听端口: {local_port}")
        
        try:
            while transfer_id in self.active_transfers:
                try:
                    data, addr = sock.recvfrom(1024)
                    opcode = struct.unpack('!H', data[:2])[0]
                    
                    
                    if opcode == self.OPCODE_ACK:
                        block_num = struct.unpack('!H', data[2:4])[0]
                        
                        if block_num % 10 == 0 or block_num <= 30:
                            logger.info(f"收到 ACK {block_num} from {addr}")
                        
                        if block_num >= transfer['block']:
                            if transfer['sent_bytes'] >= transfer['total_bytes']:
                                logger.info(f"传输完成: {transfer_id}")
                                if self.transfer_progress_callback:
                                    self.transfer_progress_callback(transfer_id, 100, transfer['total_bytes'], transfer['total_bytes'])
                                break
                            else:
                                transfer['block'] = block_num
                                self._send_next_block(transfer_id)
                except socket.timeout:
                    logger.warning(f"传输超时: {transfer_id}")
                    break
        except Exception as e:
            logger.error(f"传输处理异常: {e}")
        finally:
            if transfer_id in self.active_transfers:
                sock.close()
                del self.active_transfers[transfer_id]
    
    def _handle_ack(self, data: bytes, addr: tuple):
        block_num = struct.unpack('!H', data[2:4])[0]
        transfer_id = f"{addr[0]}:{addr[1]}"
        
        if transfer_id not in self.active_transfers:
            logger.debug(f"收到ACK {block_num} from {addr}，但无对应传输会话（可能是.size文件的ACK）")
            return
        
        transfer = self.active_transfers[transfer_id]
        
        if block_num == transfer['block']:
            if transfer['sent_bytes'] >= transfer['total_bytes']:
                logger.info(f"传输完成: {transfer_id}")
                if self.transfer_progress_callback:
                    self.transfer_progress_callback(transfer_id, 100, transfer['total_bytes'], transfer['total_bytes'])
                del self.active_transfers[transfer_id]
            else:
                self._send_next_block(transfer_id)
    
    def _send_next_block(self, transfer_id: str):
        if transfer_id not in self.active_transfers:
            return
        
        transfer = self.active_transfers[transfer_id]
        transfer['block'] += 1
        
        start = (transfer['block'] - 1) * self.BLOCK_SIZE
        end = min(start + self.BLOCK_SIZE, len(self.firmware_data))
        block_data = self.firmware_data[start:end]
        
        packet = struct.pack('!HH', self.OPCODE_DATA, transfer['block']) + block_data

        transfer['sock'].sendto(packet, transfer['addr'])
        
        transfer['sent_bytes'] = end
        progress = int((transfer['sent_bytes'] / transfer['total_bytes']) * 100)
        
        if self.transfer_progress_callback:
            self.transfer_progress_callback(transfer_id, progress, transfer['sent_bytes'], transfer['total_bytes'])
        
        if transfer['block'] % 100 == 0:
            logger.info(f"发送块 {transfer['block']}/{transfer['total_blocks']}, 进度: {progress}%")
        else:
            logger.debug(f"发送块 {transfer['block']}/{transfer['total_blocks']}, 进度: {progress}%")
    
    def _send_size_file(self, addr: tuple, file_size: int):
        size_str = str(file_size)
        size_data = size_str.encode('ascii')
        
        transfer_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        transfer_sock.bind((self.host, 0))
        transfer_sock.settimeout(2.0)
        
        local_port = transfer_sock.getsockname()[1]
        logger.info(f"发送 .size 文件到 {addr}: {size_str} 字节 (从端口 {local_port})")
        
        packet = struct.pack('!HH', self.OPCODE_DATA, 1) + size_data
        transfer_sock.sendto(packet, addr)
        
        try:
            ack_data, ack_addr = transfer_sock.recvfrom(1024)
            ack_opcode = struct.unpack('!H', ack_data[:2])[0]
            if ack_opcode == self.OPCODE_ACK:
                logger.info(f"收到 .size 文件的 ACK from {ack_addr}")
        except socket.timeout:
            logger.warning(f".size 文件传输未收到 ACK")
        finally:
            transfer_sock.close()
    
    def _send_oack(self, transfer_id: str, addr: tuple, options: dict):
        if transfer_id not in self.active_transfers:
            return
        
        transfer = self.active_transfers[transfer_id]
        packet = struct.pack('!H', self.OPCODE_OACK)
        
        if 'tsize' in options:
            packet += b'tsize\x00'
            packet += str(len(self.firmware_data)).encode('ascii') + b'\x00'
            logger.info(f"OACK: tsize={len(self.firmware_data)}")
        
        if 'blksize' in options:
            packet += b'blksize\x00'
            packet += str(self.BLOCK_SIZE).encode('ascii') + b'\x00'
            logger.info(f"OACK: blksize={self.BLOCK_SIZE}")
        
        transfer['sock'].sendto(packet, addr)
        logger.info(f"发送OACK到 {addr}")
    
    def _send_error(self, addr: tuple, error_code: int, error_msg: str):
        packet = struct.pack('!HH', self.OPCODE_ERROR, error_code) + error_msg.encode('ascii') + b'\x00'
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(packet, addr)
        sock.close()
        logger.error(f"发送错误到 {addr}: {error_msg}")
