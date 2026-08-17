import hmac
import hashlib
import json
import uuid
import secrets
import base64


def generate_nonce(length: int = 16) -> str:
    return secrets.token_hex(length // 2)


def generate_message_id() -> str:
    return uuid.uuid4().hex


def calculate_hmac_signature(data: str, key: str) -> str:
    signature = hmac.new(
        key.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode('utf-8')


def _cjson_serialize(obj) -> str:
    """序列化为cJSON_PrintUnformatted兼容格式。

    对象: key紧凑排列，无空格
    数组: 元素之间逗号后有空格 ", "
    """
    if isinstance(obj, dict):
        items = []
        for k in sorted(obj.keys()):
            items.append(f'"{k}":{_cjson_serialize(obj[k])}')
        return "{" + ",".join(items) + "}"
    elif isinstance(obj, list):
        elements = [_cjson_serialize(item) for item in obj]
        return "[" + ", ".join(elements) + "]"
    elif isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    elif isinstance(obj, bool):
        return "true" if obj else "false"
    elif isinstance(obj, int):
        return str(obj)
    elif isinstance(obj, float):
        return str(obj)
    elif obj is None:
        return "null"
    else:
        return json.dumps(obj, ensure_ascii=False)


def body_to_sign_json(body: dict) -> str:
    """将body序列化为签名用的JSON字符串，匹配设备端cJSON格式。"""
    return _cjson_serialize(body)


def build_sign_data(ver: str, mid: str, ts: int, action: str, body: str, nonce: str, psk: str) -> str:
    return f"{ver}{mid}{ts}{action}{body}{nonce}{psk}"


def verify_signature(message: dict, psk: str) -> bool:
    try:
        header = message.get('header', {})
        body = message.get('body', {})

        body_json = body_to_sign_json(body)

        sign_data = build_sign_data(
            header.get('ver', ''),
            header.get('mid', ''),
            header.get('ts', 0),
            header.get('action', ''),
            body_json,
            header.get('nonce', ''),
            psk
        )

        expected_sig = calculate_hmac_signature(sign_data, psk)
        actual_sig = header.get('sig', '')

        return expected_sig == actual_sig
    except Exception:
        return False
