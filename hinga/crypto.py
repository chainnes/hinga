"""Fernet seals for journal text. The demo key is a local file, not a KMS."""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet

from hinga.config import Settings


def cipher_for(settings: Settings, path: str | Path = "data/fernet.key") -> Fernet:
    raw = settings.fernet_key.strip()
    if not raw:
        file = Path(path)
        if file.is_file():
            raw = file.read_text(encoding="utf-8").strip()
        else:
            file.parent.mkdir(parents=True, exist_ok=True)
            raw = Fernet.generate_key().decode("ascii")
            file.write_text(raw, encoding="utf-8")
    return Fernet(raw.encode("ascii"))


def seal(text: str, cipher: Fernet) -> str:
    return cipher.encrypt(text.encode("utf-8")).decode("ascii")


def unseal(token: str, cipher: Fernet) -> str:
    return cipher.decrypt(token.encode("ascii")).decode("utf-8")
