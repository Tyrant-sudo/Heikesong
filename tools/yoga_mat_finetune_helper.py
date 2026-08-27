#!/usr/bin/env python3
"""Prepare a tiny yoga-mat fine-tuning dataset when detection fails.

Usage:
  python tools/yoga_mat_finetune_helper.py \
    --source tests/reports/v1_photo_artifacts \
    --out tests/reports/mat_finetune_dataset \
    --label yoga_mat

The tool copies images into a YOLO-style folder layout, writes a dataset.yaml,
and prints a ready-to-run training command. It does not auto-train unless
`--run-train` is explicitly set.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Sample:
    src: Path
    dest_name: str
    split: str


def list_images(folder: Path) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp"}
    return sorted([p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in exts])


def split_items(items: list[Path], train_ratio: float) -> tuple[list[Path], list[Path]]:
    if not items:
        return [], []
    items = list(items)
    random.shuffle(items)
    cut = int(len(items) * train_ratio)
    return items[:cut], items[cut:]


def copy_images(items: list[Path], dst_root: Path, split: str, prefix: str) -> list[Sample]:
    image_dir = dst_root / "images" / split
    image_dir.mkdir(parents=True, exist_ok=True)
    samples: list[Sample] = []
    for idx, src in enumerate(items):
        dst_name = f"{prefix}_{split}_{idx:04d}{src.suffix.lower()}"
        dst_path = image_dir / dst_name
        shutil.copy2(src, dst_path)
        samples.append(Sample(src=src, dest_name=dst_name, split=split))
    return samples


def write_placeholder_labels(dst_root: Path, samples: list[Sample]) -> None:
    if not samples:
        return
    split = samples[0].split
    label_root = dst_root / "labels" / split
    label_root.mkdir(parents=True, exist_ok=True)
    for sample in samples:
        label_file = Path(sample.dest_name).with_suffix(".txt")
        (label_root / label_file).write_text("", encoding="utf-8")


def write_dataset_yaml(dst_root: Path, class_name: str) -> None:
    content = f"""path: .
train: images/train
val: images/val

nc: 1
names: ['{class_name}']
"""
    (dst_root / "dataset.yaml").write_text(content, encoding="utf-8")


def write_manifest(dst_root: Path, samples: list[Sample], class_name: str) -> None:
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "class_name": class_name,
        "items": [
            {"split": s.split, "source": str(s.src), "target": f"images/{s.split}/{s.dest_name}"}
            for s in samples
        ],
    }
    (dst_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect fail-detection frames and build fine-tune dataset.")
    parser.add_argument("--source", required=True, type=Path, help="Directory with collected frames for fallback.")
    parser.add_argument("--out", required=True, type=Path, help="Output dataset directory.")
    parser.add_argument("--label", default="yoga_mat", help="Single-class name in dataset.yaml.")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Train split ratio.")
    parser.add_argument("--model", default="yolo11n.pt", help="Ultralytics model name/path.")
    parser.add_argument("--epochs", type=int, default=20, help="Epoch count for finetune.")
    parser.add_argument("--batch", type=int, default=8, help="Batch size for finetune.")
    parser.add_argument("--imgsz", type=int, default=640, help="Input size for finetune.")
    parser.add_argument("--run-train", action="store_true", help="Run Ultralytics training command directly.")
    return parser.parse_args()


def run_training(args: argparse.Namespace, dataset_path: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "ultralytics",
        "train",
        f"data={dataset_path.as_posix()}",
        f"model={args.model}",
        f"epochs={args.epochs}",
        f"batch={args.batch}",
        f"imgsz={args.imgsz}",
    ]
    try:
        subprocess.run(cmd, check=True, cwd=str(args.out))
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ultralytics CLI not installed in this environment. "
            f"Command: {' '.join(cmd)}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ultralytics train failed with code {exc.returncode}: {' '.join(cmd)}") from exc


def main() -> int:
    args = parse_args()
    if not args.source.exists():
        raise SystemExit(f"source not found: {args.source}")
    if not args.source.is_dir():
        raise SystemExit(f"source is not a directory: {args.source}")

    random.seed(42)
    images = list_images(args.source)
    if not images:
        raise SystemExit(f"no images found in {args.source}")

    args.out.mkdir(parents=True, exist_ok=True)
    train_items, val_items = split_items(images, max(0.01, min(0.99, args.train_ratio)))
    train_samples = copy_images(train_items, args.out, "train", "sample")
    val_samples = copy_images(val_items, args.out, "val", "sample")
    samples = [*train_samples, *val_samples]
    write_placeholder_labels(args.out, train_samples)
    write_placeholder_labels(args.out, val_samples)
    write_dataset_yaml(args.out, args.label)
    write_manifest(args.out, samples, args.label)

    print(f"built_finetune_dataset: {args.out}")
    print(f"train_count: {len(train_items)}")
    print(f"val_count: {len(val_items)}")
    print("next: label files under labels/{train,val} with YOLO format before training.")
    train_cmd = [
        f"{sys.executable} -m ultralytics train",
        f"data={str(args.out / 'dataset.yaml')}",
        f"model={args.model}",
        f"epochs={args.epochs}",
        f"batch={args.batch}",
        f"imgsz={args.imgsz}",
    ]
    print("train_cmd:", " ".join(train_cmd))

    if args.run_train:
        try:
            run_training(args, args.out / "dataset.yaml")
            print("ultralytics training finished.")
        except RuntimeError as exc:
            print(f"{exc}")
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
