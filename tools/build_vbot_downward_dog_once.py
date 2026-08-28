#!/usr/bin/env python3
"""Build a single-cycle Vbot downward-dog trajectory from PILATES_D."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np


SOURCE_BODY_SHA256 = (
    "312a83361427577c02adcc7d9c7383f8cb507c2a23a057c3e1b3c6e9493e4f94"
)
SOURCE_HEAD_SHA256 = (
    "a24e86fbeba40d4b9f538985cd9328db326efe5e911898144e38a68f12aab42b"
)
BODY_PREFIX_STOP = 199
BODY_SUFFIX_START = 1307
HEAD_PREFIX_STOP = 199
HEAD_SUFFIX_START = 709
OUTPUT_FRAMES = 399


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(body_source: Path, head_source: Path, output_dir: Path) -> None:
    source_digest = sha256(body_source)
    if source_digest != SOURCE_BODY_SHA256:
        raise ValueError(f"unexpected body source sha256: {source_digest}")
    head_digest = sha256(head_source)
    if head_digest != SOURCE_HEAD_SHA256:
        raise ValueError(f"unexpected head source sha256: {head_digest}")

    with np.load(body_source, allow_pickle=True) as source:
        if source["qpos"].shape[0] != 1507:
            raise ValueError("unexpected source frame count")
        qpos_jump = np.max(
            np.abs(source["qpos"][BODY_PREFIX_STOP - 1] - source["qpos"][BODY_SUFFIX_START])
        )
        qvel_jump = np.max(
            np.abs(source["qvel"][BODY_PREFIX_STOP - 1] - source["qvel"][BODY_SUFFIX_START])
        )
        if qpos_jump > 1e-3 or qvel_jump > 0.15:
            raise ValueError(
                f"unsafe body splice: qpos_jump={qpos_jump} qvel_jump={qvel_jump}"
            )

        output: dict[str, np.ndarray] = {}
        for key in source.files:
            value = source[key]
            if value.ndim > 0 and value.shape[0] == 1507:
                value = np.concatenate(
                    (value[:BODY_PREFIX_STOP], value[BODY_SUFFIX_START:]), axis=0
                )
            elif key == "split_points":
                value = np.array([0, OUTPUT_FRAMES], dtype=value.dtype)
            output[key] = value

    head = np.loadtxt(head_source, delimiter=",")
    if head.shape != (900, 2):
        raise ValueError(f"unexpected head source shape: {head.shape}")
    head_jump = np.max(
        np.abs(head[HEAD_PREFIX_STOP - 1] - head[HEAD_SUFFIX_START])
    )
    if head_jump > 1e-6:
        raise ValueError(f"unsafe head splice: jump={head_jump}")
    head_output = np.concatenate(
        (head[:HEAD_PREFIX_STOP], head[HEAD_SUFFIX_START:]), axis=0
    )
    head_output = np.pad(
        head_output,
        ((0, OUTPUT_FRAMES - head_output.shape[0]), (0, 0)),
        mode="constant",
    )

    if output["qpos"].shape[0] != OUTPUT_FRAMES:
        raise ValueError("incorrect body output frame count")
    if head_output.shape != (OUTPUT_FRAMES, 2):
        raise ValueError("incorrect head output frame count")

    output_dir.mkdir(parents=True, exist_ok=True)
    body_output = output_dir / "PILATES_D_ONCE_50hz.npz"
    head_output_path = output_dir / "PILATES_D_ONCE.csv"
    np.savez_compressed(body_output, **output)
    np.savetxt(head_output_path, head_output, delimiter=",", fmt="%.9g")

    print(f"body={body_output} frames={OUTPUT_FRAMES} sha256={sha256(body_output)}")
    print(
        f"head={head_output_path} frames={OUTPUT_FRAMES} "
        f"sha256={sha256(head_output_path)}"
    )
    print(f"duration_seconds={OUTPUT_FRAMES / float(output['frequency']):.2f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("body_source", type=Path)
    parser.add_argument("head_source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    build(args.body_source, args.head_source, args.output_dir)


if __name__ == "__main__":
    main()
