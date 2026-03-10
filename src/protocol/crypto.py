import hmac
import hashlib
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
