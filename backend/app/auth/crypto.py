"""Criptografia dos dados sensíveis em repouso (sessão do LinkedIn).

Usa Fernet (AES-128-CBC + HMAC) com a chave derivada de `ENCRYPTION_KEY` — ou de
`SECRET_KEY` quando aquela não é definida. Trocar a chave torna os dados já
gravados ilegíveis; nesse caso o usuário só precisa reconectar o LinkedIn.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings


class DecryptionError(RuntimeError):
    """A chave mudou ou o texto cifrado está corrompido."""


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    secret = settings.encryption_key or settings.secret_key
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"linkedin-auto-apply/at-rest/v1",
        info=b"fernet-key",
    ).derive(secret.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_text(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_text(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise DecryptionError(
            "Não foi possível descriptografar os dados salvos. "
            "Se ENCRYPTION_KEY/SECRET_KEY mudou, reconecte sua conta do LinkedIn."
        ) from exc


def encrypt_json(payload: Any) -> str:
    return encrypt_text(json.dumps(payload, separators=(",", ":")))


def decrypt_json(token: str) -> Any:
    return json.loads(decrypt_text(token))
