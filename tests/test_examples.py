import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="checked-in example output is canonicalized on Python 3.11+",
)
def test_checked_in_examples_match_regenerated_output():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "regenerate_examples.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
