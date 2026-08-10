import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class CredentialCipher:
    def __init__(self) -> None:
        seed = settings.credential_encryption_key or settings.jwt_secret
        key = base64.urlsafe_b64encode(hashlib.sha256(f"school-connection:v1:{seed}".encode()).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Kredensial sekolah tidak dapat didekripsi") from exc
