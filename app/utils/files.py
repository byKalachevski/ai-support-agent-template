from pathlib import Path
from typing import Iterable


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_dirs(paths: Iterable[str | Path]) -> None:
    for path in paths:
        ensure_dir(path)

