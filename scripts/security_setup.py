"""Initialize ignored, permission-restricted deployment secrets without printing them."""

from pathlib import Path
import secrets
from cryptography.fernet import Fernet

directory = Path(".secrets")
directory.mkdir(mode=0o700, exist_ok=True)
directory.chmod(0o700)
for name, factory in [
    ("admin-token", lambda: secrets.token_urlsafe(48).encode()),
    ("master-key", Fernet.generate_key),
]:
    path = directory / name
    if not path.exists():
        with path.open("xb") as output:
            path.chmod(0o600)
            output.write(factory())
    print(f"Ready: {path} (value not printed)")
