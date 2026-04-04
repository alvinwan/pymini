from pymini.pymini import minify
from pathlib import Path
import pytest


@pytest.mark.parametrize('path', [
    'tests/examples/pyminifier.py',
    'tests/examples/pyminify.py',
])
def test_reduction(path):
    source = Path(path).read_text(encoding="utf-8")
    cleaned, modules = minify(source, Path(path).stem)

    assert len(cleaned) == 1
    assert len(modules) == 1
    assert len(cleaned[0]) < len(source)
