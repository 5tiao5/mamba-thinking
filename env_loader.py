from __future__ import annotations

import os
from pathlib import Path


def load_product_agent_dotenv(dotenv_path: Path | None = None) -> Path | None:
    """
    Load environment variables from `product_agent/.env` if it exists.

    Existing process environment variables always win; the file only fills in
    missing values so local shell overrides and CI secrets remain authoritative.
    """
    env_path = dotenv_path or Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)

    return env_path
