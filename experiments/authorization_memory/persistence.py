from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import platform
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return jsonable(value.to_dict())
    if dataclasses.is_dataclass(value):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_hash(value: Any) -> str:
    serialized = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_run_dir(
    domain_id: str,
    label: str,
    *,
    tag: str | None = None,
    root: Path = Path("results"),
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    safe_domain = _path_component(domain_id, "domain_id")
    safe_label = _path_component(label, "label")
    suffix = f"__{_path_component(tag, 'tag')}" if tag else ""
    run_dir = root / safe_domain / f"{stamp}__{safe_label}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jsonable(value), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(jsonable(row), ensure_ascii=False, sort_keys=True) + "\n"
            )
            count += 1
    return count


def git_info() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", *args],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except Exception:  # noqa: BLE001
            return None

    status = git("status", "--porcelain")
    return {
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "commit": git("rev-parse", "HEAD"),
        "dirty": None if status is None else bool(status),
    }


def runtime_info() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def _path_component(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    if not normalized:
        raise ValueError(f"{name} has no filesystem-safe characters")
    return normalized[:160]
