"""Loader for the golden set."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

GOLDEN_PATH = Path(__file__).parent / "goldens" / "golden_set.yaml"


def load_golden_set(path: Path | None = None) -> dict[str, Any]:
    return yaml.safe_load((path or GOLDEN_PATH).read_text(encoding="utf-8"))
