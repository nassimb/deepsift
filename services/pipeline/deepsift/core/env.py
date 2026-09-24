"""Load KEY=VALUE pairs from the repository .env into os.environ (never overrides, never logs values)."""

from __future__ import annotations

import os

from deepsift.core.config import ROOT


def load_dotenv() -> list[str]:
    path = ROOT / ".env"
    loaded = []
    if not path.exists():
        return loaded
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v and k not in os.environ:
            os.environ[k] = v
            loaded.append(k)
    return loaded
