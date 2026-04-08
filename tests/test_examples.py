import sys
from pathlib import Path

import pytest
from pymini import minify


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "tests" / "examples"
GENERATED_SUFFIX = ".pymini.py"
MINIFY_OPTIONS = {"keep_global_variables": True}


def generated_examples() -> dict[str, str]:
    outputs: dict[str, str] = {}
    for source_path in sorted(EXAMPLES_DIR.glob("*.py")):
        if source_path.name.endswith(GENERATED_SUFFIX):
            continue
        cleaned, _ = minify(
            source_path.read_text(encoding="utf-8"),
            source_path.stem,
            **MINIFY_OPTIONS,
        )
        outputs[source_path.name.removesuffix(".py") + GENERATED_SUFFIX] = cleaned[0]
    return outputs


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="checked-in example output is canonicalized on Python 3.11+",
)
def test_checked_in_examples_match_regenerated_output():
    mismatches = []
    expected = generated_examples()
    for name, source in expected.items():
        output_path = EXAMPLES_DIR / name
        if (
            not output_path.exists()
            or output_path.read_text(encoding="utf-8").rstrip("\n") != source.rstrip("\n")
        ):
            mismatches.append(name)
    extra_outputs = sorted(
        path.name
        for path in EXAMPLES_DIR.glob(f"*{GENERATED_SUFFIX}")
        if path.name not in expected
    )

    assert not (mismatches + extra_outputs), "\n".join(mismatches + extra_outputs)
