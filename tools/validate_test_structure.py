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
    "config/test/v1.yaml",
    "docs/DIRECTORY_STRUCTURE.md",
    "docs/architecture/V1_ARCHITECTURE.md",
    "docs/testing/V1_TEST_LIST.md",
    "docs/testing/V1_TEST_PLAN.md",
    "docs/testing/TRACEABILITY.md",
    "docs/testing/INCREMENTAL_TESTING.md",
    "docs/testing/TEST_CASE_TEMPLATE.md",
    "docs/testing/forms/V1_TEST_RECORD.md",
    "docs/testing/forms/V1_TEST_RECORD.csv",
    "docs/testing/forms/V1_TEST_SUMMARY.md",
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
    "tests/manual/README.md",
    "tests/fixtures/README.md",
    "tests/scenarios/README.md",
    "tests/scenarios/v1/TC-MAT-001-yoga-mat-detection.md",
    "tests/scenarios/v1/TC-MAT-002-mat-loss-and-rejection.md",
    "tests/scenarios/v1/TC-BEH-001-orbit-yoga-mat.md",
    "tests/scenarios/v1/TC-PER-001-user-position.md",
    "tests/scenarios/v1/TC-POSE-001-downward-dog.md",
    "tests/scenarios/v1/TC-ACT-001-imitate-and-photo.md",
    "tests/scenarios/v1/TC-BEH-002-follow-user-direction.md",
    "tests/scenarios/v1/TC-TIM-001-session-timer.md",
    "tests/scenarios/v1/TC-E2E-001-main-flow.md",
    "tests/scenarios/v1/TC-SAFE-001-safety-override.md",
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
    "CAM-001",
    "CAM-002",
    "TIM-001",
    "TIM-002",
    "SYS-001",
    "SAFE-001",
    "SAFE-002",
)

SCENARIO_ID_PATTERN = re.compile(r"^#\s+(TC-[A-Z0-9]+-\d{3})\b", re.MULTILINE)


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

    seen_ids: dict[str, Path] = {}
    scenarios_root = ROOT / "tests/scenarios"
    if scenarios_root.is_dir():
        for path in sorted(scenarios_root.rglob("TC-*.md")):
            content = path.read_text(encoding="utf-8")
            match = SCENARIO_ID_PATTERN.search(content)
            if not match:
                errors.append(f"scenario has no valid title ID: {path.relative_to(ROOT)}")
                continue
            scenario_id = match.group(1)
            if scenario_id in seen_ids:
                first = seen_ids[scenario_id].relative_to(ROOT)
                errors.append(
                    f"duplicate scenario ID {scenario_id}: {first} and {path.relative_to(ROOT)}"
                )
            seen_ids[scenario_id] = path

    test_list_path = ROOT / "docs/testing/V1_TEST_LIST.md"
    if test_list_path.is_file():
        test_list = test_list_path.read_text(encoding="utf-8")
        for scenario_id in seen_ids:
            if scenario_id not in test_list:
                errors.append(f"test list is missing scenario: {scenario_id}")

    expected_scenario_ids = {
        "TC-MAT-001",
        "TC-MAT-002",
        "TC-BEH-001",
        "TC-PER-001",
        "TC-POSE-001",
        "TC-ACT-001",
        "TC-BEH-002",
        "TC-TIM-001",
        "TC-SAFE-001",
        "TC-E2E-001",
    }
    for scenario_id in sorted(expected_scenario_ids - set(seen_ids)):
        errors.append(f"missing V1 scenario ID: {scenario_id}")

    if errors:
        print("V1 test baseline validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        f"V1 test baseline validation passed: "
        f"{len(REQUIRED_PATHS)} required files, {len(seen_ids)} scenario IDs."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
