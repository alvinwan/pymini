import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_examples_match_regenerated_output():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "regenerate_examples.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
