import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from heikesong.actions.photo_store import (
    PhotoArtifactStore,
    normalize_jpeg_payload,
)


class PhotoArtifactStoreTests(unittest.TestCase):
    def test_normalize_jpeg_payload_removes_transport_padding(self) -> None:
        jpeg = b"\xff\xd8photo\xff\xd9"
        self.assertEqual(jpeg, normalize_jpeg_payload(jpeg + b"\x00" * 6))
        self.assertEqual(jpeg, normalize_jpeg_payload(jpeg))

    def test_normalize_jpeg_payload_rejects_missing_markers(self) -> None:
        with self.assertRaisesRegex(ValueError, "start"):
            normalize_jpeg_payload(b"not-jpeg\xff\xd9")
        with self.assertRaisesRegex(ValueError, "end"):
            normalize_jpeg_payload(b"\xff\xd8missing-end")

    def test_store_is_idempotent_by_correlation_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = PhotoArtifactStore(Path(directory))
            data = b"\xff\xd8photo-one\xff\xd9"
            digest = hashlib.sha256(data).hexdigest()
            first = store.store("photo:1", data, 123.5, digest, {"channel": 0})
            second = store.store(
                "photo:1", b"\xff\xd8different\xff\xd9", 124.0, "other", {}
            )

            self.assertEqual(first, second)
            self.assertEqual(data, Path(first.path).read_bytes())
            entries = [
                json.loads(line)
                for line in (Path(directory) / "manifest.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(1, len(entries))
            self.assertEqual("photo:1", entries[0]["correlation_id"])

    def test_rejects_invalid_jpeg_and_empty_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = PhotoArtifactStore(Path(directory))
            with self.assertRaisesRegex(ValueError, "correlation_id"):
                store.store("", b"\xff\xd8x\xff\xd9", 1.0, "hash", {})
            with self.assertRaisesRegex(ValueError, "JPEG"):
                store.store("bad", b"not-jpeg", 1.0, "hash", {})


if __name__ == "__main__":
    unittest.main()
