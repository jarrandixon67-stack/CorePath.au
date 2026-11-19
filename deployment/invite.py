"""Generate one trial invitation for an operator's local secret store."""

import hashlib
import json
import secrets
import sys


def main():
    if not sys.stdout.isatty():
        raise SystemExit("Run in a private interactive terminal.")
    subject = "member-" + secrets.token_hex(8)
    password = secrets.token_urlsafe(24)
    salt = secrets.token_bytes(16)
    # Match persy.trial.password_digest. Keep the password and verifier out of Git.
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    print(json.dumps({subject: salt.hex() + ":" + digest.hex()}))
    print("Invite username", subject)
    print("Invite password", password)


if __name__ == "__main__":
    main()
