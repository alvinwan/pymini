from ugli import uglipy
from pathlib import Path
import pytest


@pytest.mark.parametrize('path,size', [
    ('tests/examples/pyminifier.py', 415),
    ('tests/examples/pyminify.py', 924),
])
def test_reduction(path, size):
    with open(path) as f:
        assert len(uglipy(f.read(), Path(path).stem)) <= size