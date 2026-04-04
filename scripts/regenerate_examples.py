#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from pymini import minify


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "tests" / "examples"
OUTPUT_DIR = ROOT / "examples"
MINIFY_OPTIONS = {"keep_global_variables": True}


def generated_examples() -> dict[str, str]:
    outputs: dict[str, str] = {}
    for source_path in sorted(SOURCE_DIR.glob("*.py")):
        cleaned, _ = minify(
            source_path.read_text(encoding="utf-8"),
            source_path.stem,
            **MINIFY_OPTIONS,
        )
        outputs[source_path.name] = cleaned[0]
    return outputs


def write_examples() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, source in generated_examples().items():
        (OUTPUT_DIR / name).write_text(source, encoding="utf-8")


def check_examples() -> list[str]:
    mismatches = []
    expected = generated_examples()
    for name, source in expected.items():
        output_path = OUTPUT_DIR / name
        if not output_path.exists() or output_path.read_text(encoding="utf-8") != source:
            mismatches.append(name)
    extra_outputs = sorted(
        path.name for path in OUTPUT_DIR.glob("*.py") if path.name not in expected
    )
    return mismatches + extra_outputs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the checked-in minified example outputs."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the checked-in outputs differ from regenerated output",
    )
    args = parser.parse_args()

    if args.check:
        mismatches = check_examples()
        if mismatches:
            print("example outputs are stale:")
            for name in mismatches:
                print(name)
            return 1
        return 0

    write_examples()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
