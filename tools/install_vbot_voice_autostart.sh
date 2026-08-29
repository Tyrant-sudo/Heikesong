#!/bin/bash
set -euo pipefail

SERVICE_NAME=heikesong-voice-person-tracker.service
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_UNIT="${SCRIPT_DIR}/../config/systemd/system/${SERVICE_NAME}"
TARGET_UNIT="/etc/systemd/system/${SERVICE_NAME}"
RUNNER=/userdata/vbot/.local/share/heikesong/voice_kws/bin/run_voice_person_tracker.sh

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer as root: sudo $0" >&2
  exit 1
fi

if [[ ! -f ${SOURCE_UNIT} ]]; then
  echo "Service unit not found: ${SOURCE_UNIT}" >&2
  exit 1
fi

if ! id vbot >/dev/null 2>&1; then
  echo "Required user does not exist: vbot" >&2
  exit 1
fi

if [[ ! -f ${RUNNER} ]]; then
  echo "Voice runner not found: ${RUNNER}" >&2
  exit 1
fi

install -o root -g root -m 0644 "${SOURCE_UNIT}" "${TARGET_UNIT}"
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
systemctl --no-pager --full status "${SERVICE_NAME}"
