from pymini.pymini import minify
from pathlib import Path
import pytest


@pytest.mark.parametrize('path,size', [
    ('tests/examples/pyminifier.py', 415),
    ('tests/examples/pyminify.py', 924),
])
def test_reduction(path, size):
    with open(path) as f:
        assert len(minify(f.read(), Path(path).stem)) <= size