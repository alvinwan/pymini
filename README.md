# pymini

`pymini` minifies Python source code by simplifying syntax, shortening identifiers, and stripping unnecessary whitespace. Its primary multi-file workflow preserves package structure; one-file bundling is available as an explicit opt-in.

## Status

This project is maintained as an AST-based minifier for Python 3.9+ code. It is best suited to scripts and small-to-medium package graphs. Package mode preserves package layout and now covers relative imports, dotted imports, star imports, package re-exports, and `importlib`-based internal imports; bundle mode emits a self-contained loader-backed single file for the same kinds of graphs.

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

## TexSoup Validation

`pymini` has been validated against the upstream `TexSoup` test suite in package mode.
Current validation: raw source code `68.2%` smaller, compressed source code
(`.tar.gz`) `36.1%` smaller.
<!-- Raw bytes: 98,181 -> 31,212. Compressed bytes: 70,532 -> 45,054. -->

| Measurement | Original | Minified | Reduction | Reduction Rate |
| --- | ---: | ---: | ---: | ---: |
| Raw Python source (`*.py`) | `98,181` bytes | `31,212` bytes | `66,969` bytes | `68.2%` |
| `.tar.gz` of `TexSoup/` | `70,532` bytes | `45,054` bytes | `25,478` bytes | `36.1%` |

To reproduce that flow locally:

```bash
git clone https://github.com/alvinwan/TexSoup /tmp/texsoup
mkdir -p /tmp/texsoup-out/TexSoup
pymini package /tmp/texsoup/TexSoup -o /tmp/texsoup-out/TexSoup
cp -R /tmp/texsoup/tests /tmp/texsoup-tests
PYTHONPATH=/tmp/texsoup-out:/tmp/texsoup-tests python3 -m pytest /tmp/texsoup-tests/tests -o addopts=''
```

To compare raw package bytes before and after minification:

```bash
rg --files /tmp/texsoup/TexSoup -g '*.py' | xargs cat | wc -c
rg --files /tmp/texsoup-out/TexSoup -g '*.py' | xargs cat | wc -c
```

To compare compressed package snapshots:

```bash
tar -czf /tmp/texsoup-original-package.tar.gz -C /tmp/texsoup TexSoup
tar -czf /tmp/texsoup-minified-package.tar.gz -C /tmp/texsoup-out TexSoup
stat -f%z /tmp/texsoup-original-package.tar.gz
stat -f%z /tmp/texsoup-minified-package.tar.gz
```
