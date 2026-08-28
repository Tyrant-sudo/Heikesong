"""Persistent, idempotent storage for captured Vbot photos."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class PhotoArtifact:
    correlation_id: str
    path: str
    captured_at: float
    sha256: str


def normalize_jpeg_payload(payload: bytes) -> bytes:
    """Return the JPEG through its final EOI marker, excluding transport padding."""
    if len(payload) < 4 or not payload.startswith(b"\xff\xd8"):
        raise ValueError("camera response does not start with a JPEG marker")
    eoi_offset = payload.rfind(b"\xff\xd9")
    if eoi_offset < 2:
        raise ValueError("camera response has no JPEG end marker")
    return payload[: eoi_offset + 2]


class PhotoArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.jsonl"
        self._artifacts = self._load_manifest()

    def store(
        self,
        correlation_id: str,
        jpeg_data: bytes,
        captured_at: float,
        sha256: str,
        metadata: Mapping[str, object],
    ) -> PhotoArtifact:
        if not correlation_id:
            raise ValueError("correlation_id must not be empty")
        existing = self._artifacts.get(correlation_id)
        if existing is not None and Path(existing.path).is_file():
            return existing
        if len(jpeg_data) < 4 or not (
            jpeg_data.startswith(b"\xff\xd8") and jpeg_data.endswith(b"\xff\xd9")
        ):
            raise ValueError("camera response is not a complete JPEG")

        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", correlation_id).strip("-.")
        if not safe_id:
            safe_id = "capture"
        filename = f"{captured_at:.3f}_{safe_id[:80]}.jpg"
        path = self.root / filename
        temporary = path.with_suffix(".jpg.tmp")
        temporary.write_bytes(jpeg_data)
        temporary.replace(path)

        artifact = PhotoArtifact(correlation_id, str(path), captured_at, sha256)
        entry = {
            "correlation_id": correlation_id,
            "path": str(path),
            "captured_at": captured_at,
            "sha256": sha256,
            **dict(metadata),
        }
        with self.manifest_path.open("a", encoding="utf-8") as manifest:
            manifest.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
            manifest.write("\n")
        self._artifacts[correlation_id] = artifact
        return artifact

    def _load_manifest(self) -> dict[str, PhotoArtifact]:
        artifacts: dict[str, PhotoArtifact] = {}
        if not self.manifest_path.is_file():
            return artifacts
        for line in self.manifest_path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
                artifact = PhotoArtifact(
                    correlation_id=str(entry["correlation_id"]),
                    path=str(entry["path"]),
                    captured_at=float(entry["captured_at"]),
                    sha256=str(entry["sha256"]),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            artifacts[artifact.correlation_id] = artifact
        return artifacts
