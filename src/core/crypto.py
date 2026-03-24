import hmac
import hashlib
import random
import string
import time
import base64


def generate_nonce(length: int = 32) -> str:
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


def generate_message_id(action: str) -> str:
    ts = int(time.time())
    rand = random.randint(1000, 9999)
    return f"cmd-{action}-{ts}-{rand}"


def calculate_hmac_signature(data: str, key: str) -> str:
    signature = hmac.new(
        key.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode('utf-8')


def build_sign_data(ver: str, mid: str, ts: int, action: str, body: str, nonce: str, psk: str) -> str:
    return f"{ver}{mid}{ts}{action}{body}{nonce}{psk}"


def verify_signature(message: dict, psk: str) -> bool:
    try:
        import json
        header = message.get('header', {})
        body = message.get('body', {})
        
        body_json = json.dumps(body, separators=(', ', ': '), ensure_ascii=False)
        
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
