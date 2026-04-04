from pymini.pymini import minify
from pathlib import Path
import pytest


@pytest.mark.parametrize('path,size', [
    ('tests/examples/pyminifier.py', 415),
    ('tests/examples/pyminify.py', 924),
])
def test_reduction(path, size):
    source = Path(path).read_text(encoding="utf-8")
    cleaned, modules = minify(source, Path(path).stem)

    assert len(cleaned) == 1
    assert len(modules) == 1
    assert len(cleaned[0]) <= size
