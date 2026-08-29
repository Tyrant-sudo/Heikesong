#!/usr/bin/env python3
"""Speak arbitrary text with Vbot's native TTS and save the playback audio."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import subprocess
import tempfile
import uuid
import wave
from pathlib import Path

import paramiko


EXPECTED_HOST_KEY = "BgbUqN+/l3ITadNFP4fTwgEKKMRGUa8yfgWOygPDEOE"
REMOTE_AUDIO_DIR = "/userdata/vbot/.local/share/heikesong/audio"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", help="Text for the native Vbot voice to speak")
    parser.add_argument("output", type=Path, help="Destination 16 kHz WAV file")
    parser.add_argument("--host", default="192.168.126.2")
    parser.add_argument("--user", default="vbot")
    parser.add_argument("--password-env", default="VBOT_SSH_PASSWORD")
    parser.add_argument("--reference-channel", type=int, default=4)
    return parser.parse_args()


def connect(host: str, user: str, password: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        username=user,
        password=password,
        timeout=8,
        auth_timeout=8,
        look_for_keys=False,
        allow_agent=False,
    )
    key = client.get_transport().get_remote_server_key()
    actual = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode()
    if actual.rstrip("=") != EXPECTED_HOST_KEY:
        client.close()
        raise RuntimeError(f"unexpected SSH host key: SHA256:{actual.rstrip('=')}")
    return client


def capture_native_tts(
    client: paramiko.SSHClient,
    text: str,
    remote_path: str,
) -> None:
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("ascii")
    remote_script = r'''
import base64
import time
import uuid
import wave

import rclpy
from foxglove_msgs.msg import RawAudio
from function_msgs.srv import SetSpeak
from speech_msgs.msg import ChatTtsNotification

TEXT = base64.b64decode("__TEXT_B64__").decode("utf-8")
OUTPUT = "__REMOTE_PATH__"

rclpy.init()
node = rclpy.create_node("heikesong_native_tts_capture")
audio = bytearray()
sample_rate = 0
channels = 0
tts_started = False
tts_completed = False
tts_start_offset = None
tts_end_offset = None


def on_audio(message):
    global sample_rate, channels
    if message.format != "pcm-s16" or not message.data:
        return
    if not sample_rate:
        sample_rate = int(message.sample_rate)
        channels = int(message.number_of_channels)
    if (
        int(message.sample_rate) == sample_rate
        and int(message.number_of_channels) == channels
    ):
        audio.extend(bytes(message.data))


def on_tts(message):
    global tts_started, tts_completed, tts_start_offset, tts_end_offset
    if message.notification_type == message.TTS_START_PLAYBACK:
        tts_started = True
        tts_start_offset = len(audio)
    elif message.notification_type == message.TTS_COMPLETED:
        tts_completed = True
        tts_end_offset = len(audio)


node.create_subscription(RawAudio, "/raw_audio_dump", on_audio, 50)
node.create_subscription(
    ChatTtsNotification,
    "/speech/ChatTtsNotification",
    on_tts,
    20,
)
client = node.create_client(SetSpeak, "/set_speak")
if not client.wait_for_service(timeout_sec=5.0):
    raise RuntimeError("/set_speak is unavailable")


def request_speech(pre_check):
    request = SetSpeak.Request()
    request.target_state = 1
    request.mode = request.HUMAN_VOICE
    request.req_id = "HEIKESONG-TTS-" + uuid.uuid4().hex[:8]
    request.pre_check = pre_check
    request.machine_language_name = ""
    request.human_language_text = TEXT
    future = client.call_async(request)
    deadline = time.monotonic() + 8.0
    while not future.done() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if not future.done() or future.exception() is not None:
        raise RuntimeError("/set_speak timed out")
    response = future.result()
    if not response.success:
        raise RuntimeError(
            f"/set_speak rejected request: {response.error_code} {response.message}"
        )


pre_roll_end = time.monotonic() + 0.6
while time.monotonic() < pre_roll_end:
    rclpy.spin_once(node, timeout_sec=0.1)
request_speech(True)
request_speech(False)

deadline = time.monotonic() + 20.0
completed_at = None
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.1)
    if tts_completed and completed_at is None:
        completed_at = time.monotonic()
    if completed_at is not None and time.monotonic() - completed_at >= 0.5:
        break

if not tts_started or not tts_completed:
    raise RuntimeError("native TTS start/completion events were not observed")
if not audio or not sample_rate or not channels:
    raise RuntimeError("no raw playback audio was captured")

bytes_per_second = 2 * channels * sample_rate
margin = int(0.15 * bytes_per_second)
start_offset = max(0, (tts_start_offset or 0) - margin)
end_offset = min(len(audio), (tts_end_offset or len(audio)) + margin)
captured_audio = audio[start_offset:end_offset]

with wave.open(OUTPUT, "wb") as stream:
    stream.setnchannels(channels)
    stream.setsampwidth(2)
    stream.setframerate(sample_rate)
    stream.writeframes(captured_audio)

print(
    f"captured rate={sample_rate} channels={channels} "
    f"duration={len(captured_audio) / bytes_per_second:.3f}",
    flush=True,
)
node.destroy_node()
rclpy.shutdown()
'''
    remote_script = remote_script.replace("__TEXT_B64__", encoded_text).replace(
        "__REMOTE_PATH__", remote_path
    )
    command = """export COLCON_CURRENT_PREFIX=/app/opt/ros/humble
. /app/opt/ros/humble/local_setup.sh
export COLCON_CURRENT_PREFIX=/app/idl_msgs
. /app/idl_msgs/local_setup.sh
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_SESSION_CONFIG_URI=/app_param/zenoh/s100_session.json5
export ZENOH_ROUTER_CHECK_ATTEMPTS=-1
python3 - <<'PY'
""" + remote_script + "\nPY"
    _, stdout, stderr = client.exec_command(command, timeout=35)
    status = stdout.channel.recv_exit_status()
    output = stdout.read().decode("utf-8", "replace")
    error = stderr.read().decode("utf-8", "replace")
    if status != 0:
        raise RuntimeError(f"native TTS capture failed:\n{output}{error}")
    print(output.strip())


def extract_reference_channel(
    raw_path: Path,
    output_path: Path,
    channel: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_filter = (
        f"pan=mono|c0=c{channel},"
        "silenceremove="
        "start_periods=1:start_silence=0.02:start_threshold=-45dB,"
        "areverse,"
        "silenceremove="
        "start_periods=1:start_silence=0.06:start_threshold=-45dB,"
        "areverse,afade=t=in:st=0:d=0.01,apad=pad_dur=0.08"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(raw_path),
            "-af",
            audio_filter,
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        check=True,
    )


def main() -> int:
    args = parse_args()
    password = os.environ.get(args.password_env)
    if not password:
        raise SystemExit(f"missing password environment variable: {args.password_env}")
    if not args.text.strip():
        raise SystemExit("text must not be empty")
    if args.reference_channel < 0:
        raise SystemExit("reference channel must be non-negative")

    capture_id = uuid.uuid4().hex[:10]
    remote_path = f"{REMOTE_AUDIO_DIR}/native_tts_capture_{capture_id}.wav"
    client = connect(args.host, args.user, password)
    try:
        capture_native_tts(client, args.text, remote_path)
        with tempfile.TemporaryDirectory() as temporary_dir:
            raw_path = Path(temporary_dir) / "native_tts_raw.wav"
            sftp = client.open_sftp()
            try:
                sftp.get(remote_path, str(raw_path))
                sftp.remove(remote_path)
            finally:
                sftp.close()
            extract_reference_channel(
                raw_path,
                args.output.resolve(),
                args.reference_channel,
            )
    finally:
        client.close()

    with wave.open(str(args.output.resolve()), "rb") as stream:
        duration = stream.getnframes() / stream.getframerate()
        audio_format = (
            stream.getframerate(),
            stream.getnchannels(),
            stream.getsampwidth() * 8,
        )
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(
        f"saved={args.output.resolve()} duration={duration:.3f}s "
        f"format={audio_format[0]}Hz/{audio_format[1]}ch/{audio_format[2]}bit "
        f"sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
