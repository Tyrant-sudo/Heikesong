#!/usr/bin/env python3
"""Validate the documentation-first V1 test baseline without third-party packages."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    "function.md",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    ".github/workflows/test-structure.yml",
    ".github/pull_request_template.md",
    "config/device/vbot_edu.yaml",
    "config/test/v1.yaml",
    "config/test/v2.yaml",
    "docs/DIRECTORY_STRUCTURE.md",
    "docs/architecture/V1_ARCHITECTURE.md",
    "docs/architecture/V2_DEMO_ARCHITECTURE.md",
    "docs/devices/VBOT_EDU_BASELINE.md",
    "docs/devices/VBOT_EDU_V1_ACTION_MAPPING.md",
    "docs/testing/V1_TEST_LIST.md",
    "docs/testing/V1_TEST_PLAN.md",
    "docs/testing/VBOT_EDU_TEST_PLAN.md",
    "docs/testing/TRACEABILITY.md",
    "docs/testing/INCREMENTAL_TESTING.md",
    "docs/testing/TEST_CASE_TEMPLATE.md",
    "docs/testing/forms/V1_TEST_RECORD.md",
    "docs/testing/forms/V1_TEST_RECORD.csv",
    "docs/testing/forms/V1_TEST_SUMMARY.md",
    "docs/testing/forms/VBOT_EDU_DEVICE_RECORD.md",
    "src/heikesong/core/models.py",
    "src/heikesong/perception/interfaces.py",
    "src/heikesong/behavior/interfaces.py",
    "src/heikesong/actions/interfaces.py",
    "src/heikesong/services/timer.py",
    "src/heikesong/safety/interfaces.py",
    "tests/README.md",
    "tests/unit/README.md",
    "tests/integration/README.md",
    "tests/hardware/README.md",
    "tests/hardware/vbot_edu/README.md",
    "tests/hardware/vbot_edu/TC-HW-EDU-001-identity-and-versions.md",
    "tests/hardware/vbot_edu/TC-HW-EDU-002-interface-inventory.md",
    "tests/hardware/vbot_edu/TC-HW-EDU-003-sensor-streams.md",
    "tests/hardware/vbot_edu/TC-HW-EDU-004-motion-and-stop.md",
    "tests/hardware/vbot_edu/TC-HW-EDU-005-photo-pipeline.md",
    "tests/hardware/vbot_edu/TC-HW-EDU-006-network-and-recovery.md",
    "tests/hardware/vbot_edu/TC-HW-EDU-007-external-interfaces.md",
    "tests/hardware/vbot_edu/TC-HW-EDU-008-v1-hil-smoke.md",
    "tests/manual/README.md",
    "tests/fixtures/README.md",
    "tests/scenarios/README.md",
    "tests/scenarios/v1/TC-MAT-001-yoga-mat-detection.md",
    "tests/scenarios/v1/TC-MAT-002-mat-loss-and-rejection.md",
    "tests/scenarios/v1/TC-BEH-001-orbit-yoga-mat.md",
    "tests/scenarios/v1/TC-PER-001-user-position.md",
    "tests/scenarios/v1/TC-POSE-001-downward-dog.md",
    "tests/scenarios/v1/TC-ACT-001-imitate-and-photo.md",
    "tests/scenarios/v1/TC-ACT-002-yoga-action-set.md",
    "tests/scenarios/v1/TC-INT-001-yoga-start-feedback.md",
    "tests/scenarios/v1/TC-BEH-002-follow-user-direction.md",
    "tests/scenarios/v1/TC-TIM-001-session-timer.md",
    "tests/scenarios/v1/TC-E2E-001-main-flow.md",
    "tests/scenarios/v1/TC-SAFE-001-safety-override.md",
    "tests/scenarios/v2/TC-E2E-V2-001-visual-yoga-demo.md",
    "tests/unit/test_timer.py",
    "tools/run_unit_tests.py",
)

REQUIRED_REQUIREMENTS = (
    "MAT-001",
    "MAT-002",
    "MAT-003",
    "PER-001",
    "PER-002",
    "POSE-001",
    "POSE-002",
    "BEH-001",
    "BEH-002",
    "ACT-001",
    "ACT-002",
    "BEH-003",
    "DSP-001",
    "VOI-001",
    "INT-001",
    "CAM-001",
    "CAM-002",
    "TIM-001",
    "TIM-002",
    "SYS-001",
    "SAFE-001",
    "SAFE-002",
    "DEV-EDU-001",
    "DEV-EDU-002",
    "DEV-EDU-003",
    "DEV-EDU-004",
    "DEV-EDU-005",
    "DEV-EDU-006",
    "DEV-EDU-007",
    "DEV-EDU-008",
    "DEV-EDU-009",
)

TEST_ID_PATTERN = re.compile(
    r"^#\s+(TC-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3})\b",
    re.MULTILINE,
)

EXPECTED_TEST_IDS = {
    "TC-MAT-001",
    "TC-MAT-002",
    "TC-BEH-001",
    "TC-PER-001",
    "TC-POSE-001",
    "TC-ACT-001",
    "TC-ACT-002",
    "TC-INT-001",
    "TC-BEH-002",
    "TC-TIM-001",
    "TC-SAFE-001",
    "TC-E2E-001",
    "TC-E2E-V2-001",
    "TC-HW-EDU-001",
    "TC-HW-EDU-002",
    "TC-HW-EDU-003",
    "TC-HW-EDU-004",
    "TC-HW-EDU-005",
    "TC-HW-EDU-006",
    "TC-HW-EDU-007",
    "TC-HW-EDU-008",
}

VERSION_PATTERNS = {
    "pyproject.toml": re.compile(r'^version = "([^"]+)"$', re.MULTILINE),
    "src/heikesong/__init__.py": re.compile(
        r'^__version__ = "([^"]+)"$', re.MULTILINE
    ),
    "config/test/v1.yaml": re.compile(r'^version: "([^"]+)"$', re.MULTILINE),
    "CHANGELOG.md": re.compile(r"^## \[([^]]+)]", re.MULTILINE),
}


def main() -> int:
    errors: list[str] = []

    for relative_path in REQUIRED_PATHS:
        if not (ROOT / relative_path).is_file():
            errors.append(f"missing required file: {relative_path}")

    traceability_path = ROOT / "docs/testing/TRACEABILITY.md"
    if traceability_path.is_file():
        traceability = traceability_path.read_text(encoding="utf-8")
        for requirement_id in REQUIRED_REQUIREMENTS:
            if requirement_id not in traceability:
                errors.append(f"traceability is missing requirement: {requirement_id}")

    device_profile_path = ROOT / "config/device/vbot_edu.yaml"
    if device_profile_path.is_file():
        device_profile = device_profile_path.read_text(encoding="utf-8")
        for marker in (
            'edition: "EDU"',
            'profile_status: CONFIRMED-MODEL_PENDING-DEVICE-INTROSPECTION',
            'allow_unverified_motion: false',
        ):
            if marker not in device_profile:
                errors.append(f"Vbot EDU device profile is missing marker: {marker}")

    versions: dict[str, str] = {}
    for relative_path, pattern in VERSION_PATTERNS.items():
        path = ROOT / relative_path
        if path.is_file():
            match = pattern.search(path.read_text(encoding="utf-8"))
            if match:
                versions[relative_path] = match.group(1)
            else:
                errors.append(f"cannot read project version from: {relative_path}")
    if len(set(versions.values())) > 1:
        detail = ", ".join(f"{path}={version}" for path, version in versions.items())
        errors.append(f"project versions are inconsistent: {detail}")

    seen_ids: dict[str, Path] = {}
    for tests_root in (ROOT / "tests/scenarios", ROOT / "tests/hardware"):
        if not tests_root.is_dir():
            continue
        for path in sorted(tests_root.rglob("TC-*.md")):
            content = path.read_text(encoding="utf-8")
            match = TEST_ID_PATTERN.search(content)
            if not match:
                errors.append(f"test has no valid title ID: {path.relative_to(ROOT)}")
                continue
            test_id = match.group(1)
            if test_id in seen_ids:
                first = seen_ids[test_id].relative_to(ROOT)
                errors.append(
                    f"duplicate test ID {test_id}: {first} and {path.relative_to(ROOT)}"
                )
            seen_ids[test_id] = path

    test_list_path = ROOT / "docs/testing/V1_TEST_LIST.md"
    if test_list_path.is_file():
        test_list = test_list_path.read_text(encoding="utf-8")
        for test_id in seen_ids:
            if test_id not in test_list:
                errors.append(f"test list is missing test: {test_id}")

    for test_id in sorted(EXPECTED_TEST_IDS - set(seen_ids)):
        errors.append(f"missing V1 test ID: {test_id}")

    if errors:
        print("V1 test baseline validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        f"V1 test baseline validation passed: "
        f"{len(REQUIRED_PATHS)} required files, {len(seen_ids)} test IDs, "
        f"project version {next(iter(versions.values()), 'unknown')}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
