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
    "config/test/v1.yaml",
    "docs/DIRECTORY_STRUCTURE.md",
    "docs/testing/V1_TEST_PLAN.md",
    "docs/testing/TRACEABILITY.md",
    "docs/testing/TEST_CASE_TEMPLATE.md",
    "tests/README.md",
    "tests/unit/README.md",
    "tests/integration/README.md",
    "tests/hardware/README.md",
    "tests/manual/README.md",
    "tests/fixtures/README.md",
    "tests/scenarios/README.md",
    "tests/scenarios/v1/TC-E2E-001-main-flow.md",
    "tests/scenarios/v1/TC-SAFE-001-safety-override.md",
)

REQUIRED_REQUIREMENTS = (
    "BEH-001",
    "BEH-010",
    "PER-001",
    "PER-005",
    "ANO-001",
    "SAFE-001",
    "SAFE-007",
    "CAM-001",
    "CAM-003",
    "SYS-001",
    "SYS-002",
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
