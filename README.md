# pymini

`pymini` minifies Python source code by simplifying syntax, shortening identifiers, and stripping unnecessary whitespace. Its primary multi-file workflow preserves package structure; one-file bundling is available as an explicit opt-in.

## Status

This project is maintained as an AST-based minifier for Python 3.9+ code. It is best suited to scripts and small module graphs that use straightforward imports such as `from module import name`.

## Installation

```bash
python3 -m pip install pymini
```

## CLI

Package mode is the default and preserves the package tree:

```bash
pymini package src -o out
```

Legacy invocation without an explicit mode still defaults to `package`:

```bash
pymini src -o out
```

By default, `pymini` preserves module paths and public globals. When possible, it keeps the public surface stable by emitting aliases while still shortening internal names. To trade API stability for more aggressive compression:

```bash
pymini package src --rename-global-variables -o out
```

Bundle mode emits a single file and is better suited to app-style graphs than libraries:

```bash
pymini bundle src -o out/bundle.py
```

The legacy `--single-file` flag is still accepted as a compatibility alias for bundle mode.

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
