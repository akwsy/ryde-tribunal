"""Generate a private judge passcode and deployment secrets outside Git."""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.api.demo_access import hash_passcode  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/demo_credentials.py /absolute/private/output/directory")
    output = Path(sys.argv[1]).expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        raise SystemExit("Choose a private directory outside the Git repository")
    output.mkdir(parents=True, exist_ok=True)
    passcode = secrets.token_urlsafe(18)
    files = {
        "judge-passcode.txt": passcode + "\n",
        "demo-secrets.env": "".join(f"{key}={value}\n" for key, value in {
            "DEMO_PASSCODE_HASH": hash_passcode(passcode),
            "DEMO_SESSION_SECRET": secrets.token_urlsafe(48),
            "DEMO_READER_PASSWORD": secrets.token_urlsafe(36),
            "DEMO_WRITER_PASSWORD": secrets.token_urlsafe(36),
            "DEMO_ADMIN_PASSWORD": secrets.token_urlsafe(36),
        }.items()),
    }
    for name, content in files.items():
        path = output / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
    print(f"Private judge credentials created in {output}")


if __name__ == "__main__":
    main()
