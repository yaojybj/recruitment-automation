"""敏感信息加密存储 - Moka API密钥、Boss账号等"""

from __future__ import annotations

import os
import json
import base64
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


CREDENTIAL_FILE = Path("./config/credentials.enc")
KEY_FILE = Path("./config/.keyfile")


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def init_credential_store(master_password: str):
    """初始化加密存储（首次使用时调用）"""
    salt = os.urandom(16)
    key = _derive_key(master_password, salt)

    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_bytes(salt)

    data = {
        "moka_app_key": "",
        "moka_app_secret": "",
        "moka_org_id": "",
        "boss_cookie": "",
    }
    fernet = Fernet(key)
    encrypted = fernet.encrypt(json.dumps(data).encode())
    CREDENTIAL_FILE.write_bytes(encrypted)


def save_credentials(master_password: str, credentials: dict):
    """保存加密凭据"""
    if not KEY_FILE.exists():
        init_credential_store(master_password)

    salt = KEY_FILE.read_bytes()
    key = _derive_key(master_password, salt)
    fernet = Fernet(key)

    existing = load_credentials(master_password)
    existing.update(credentials)

    encrypted = fernet.encrypt(json.dumps(existing).encode())
    CREDENTIAL_FILE.write_bytes(encrypted)


def load_credentials(master_password: str) -> dict:
    """加载并解密凭据"""
    if not CREDENTIAL_FILE.exists() or not KEY_FILE.exists():
        return {}

    salt = KEY_FILE.read_bytes()
    key = _derive_key(master_password, salt)
    fernet = Fernet(key)

    encrypted = CREDENTIAL_FILE.read_bytes()
    decrypted = fernet.decrypt(encrypted)
    return json.loads(decrypted.decode())


def credential_store_exists() -> bool:
    return CREDENTIAL_FILE.exists() and KEY_FILE.exists()
