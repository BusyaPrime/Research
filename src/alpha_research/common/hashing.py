from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def stable_json_dumps(payload: Any) -> str:
    """Serialize an object into a deterministic JSON string."""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(payload: str) -> str:
    return sha256_bytes(payload.encode("utf-8"))


def hash_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def hash_mapping(payload: Any) -> str:
    return sha256_text(stable_json_dumps(payload))


def hash_paths(paths: list[Path], base_dir: Path) -> str:
    manifest = []
    for path in sorted(paths, key=lambda item: item.relative_to(base_dir).as_posix()):
        manifest.append(
            {
                "relative_path": path.relative_to(base_dir).as_posix(),
                "sha256": hash_file(path),
            }
        )
    return hash_mapping(manifest)
