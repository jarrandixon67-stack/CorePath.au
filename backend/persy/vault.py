import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken


def owner_key(subject: str):
    return hashlib.sha256(subject.encode()).hexdigest()


class Vault:
    def __init__(self, cipher: Fernet):
        self.cipher = cipher

    def seal(self, payload, owner, record_id, purpose):
        return self.cipher.encrypt(
            json.dumps(
                {"owner": owner, "record": str(record_id), "purpose": purpose, "payload": payload},
                ensure_ascii=False,
            ).encode()
        )

    def open(self, value, owner, record_id, purpose):
        data = json.loads(self.cipher.decrypt(bytes(value)))
        if (
            data.get("owner") != owner
            or data.get("record") != str(record_id)
            or data.get("purpose") != purpose
        ):
            raise InvalidToken("Encrypted record binding did not match")
        return data["payload"]
