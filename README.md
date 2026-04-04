# pymini

`pymini` minifies Python source code by simplifying syntax, shortening identifiers, and stripping unnecessary whitespace. It supports single-file input and small groups of related modules.

## Status

This project is maintained as an AST-based minifier for Python 3.9+ code. It is best suited to scripts and small module graphs that use straightforward imports such as `from module import name`.

## Installation

```bash
python3 -m pip install pymini
```

## CLI

Minify a single file, a directory, or a glob:

```bash
pymini "src/**/*.py" -o out
```

If you need module names and top-level public symbols to remain stable, keep them explicitly:

```bash
pymini src --keep-module-names --keep-global-variables -o out
```

Create a single bundled output file:

```bash
pymini src --single-file -o out/bundle.py
```

Without `--keep-module-names`, output filenames may also be shortened as part of the minification pass.

## Python API

```python
from pymini import minify

sources, modules = minify(
    [
        "def square(x):\n    return x ** 2\n",
        "from main import square\nprint(square(3))\n",
    ],
    ["main", "side"],
)
```

## Development

Install development dependencies and run the test suite:

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
```
