#!/usr/bin/env python3
"""Load a Sherpa-ONNX keyword model and optionally decode a WAV file."""

from __future__ import annotations

import argparse
import json
import wave
from array import array
from pathlib import Path

import sherpa_onnx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("--keywords", type=Path)
    parser.add_argument("--wav", type=Path)
    return parser.parse_args()


def read_wave(path: Path) -> tuple[int, list[float]]:
    with wave.open(str(path), "rb") as stream:
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2:
            raise ValueError("WAV must be mono 16-bit PCM")
        sample_rate = stream.getframerate()
        samples = array("h", stream.readframes(stream.getnframes()))
    return sample_rate, [sample / 32768.0 for sample in samples]


def main() -> int:
    args = parse_args()
    model_dir = args.model_dir.resolve()
    keywords = (args.keywords or model_dir / "person_tracking_keywords.txt").resolve()
    spotter = sherpa_onnx.KeywordSpotter(
        tokens=str(model_dir / "tokens.txt"),
        encoder=str(model_dir / "encoder-epoch-13-avg-2-chunk-16-left-64.int8.onnx"),
        decoder=str(model_dir / "decoder-epoch-13-avg-2-chunk-16-left-64.onnx"),
        joiner=str(model_dir / "joiner-epoch-13-avg-2-chunk-16-left-64.int8.onnx"),
        keywords_file=str(keywords),
        num_threads=2,
    )
    result = {"loaded": True, "keyword": ""}
    if args.wav:
        sample_rate, samples = read_wave(args.wav)
        stream = spotter.create_stream()
        keyword = ""
        chunk_size = max(1, sample_rate // 10)
        for offset in range(0, len(samples), chunk_size):
            stream.accept_waveform(sample_rate, samples[offset : offset + chunk_size])
            while spotter.is_ready(stream):
                spotter.decode_stream(stream)
                current = spotter.get_result(stream)
                if current:
                    keyword = current
        stream.input_finished()
        while spotter.is_ready(stream):
            spotter.decode_stream(stream)
            current = spotter.get_result(stream)
            if current:
                keyword = current
        result["keyword"] = keyword
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
