# pymini

`pymini` is an AST-based Python minifier for scripts and packages. It preserves
package layout by default, can emit a single-file bundle when asked, and can
shrink Python code by roughly `50%` to `75%` on the checked-in fixtures and
validated package benchmarks when aggressive renaming is enabled.

- [Getting Started](#getting-started)
- [Installation](#installation)
- [Benchmarks](./benchmarks/README.md)

# Getting Started

Package mode preserves the package tree:

```bash
pymini package src -o out
```

Bundle mode emits one file:

```bash
pymini bundle src -o out/bundle.py
```

You can also use the Python API directly:

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

# Compression

Current checked-in fixtures, using
`--rename-modules --rename-global-variables --rename-arguments`:

| Input | Original | Minified | Reduction |
| --- | ---: | ---: | ---: |
| `tests/examples/pyminifier.py` | `1,355` bytes | `438` bytes | `67.7%` |
| `tests/examples/pyminify.py` | `1,990` bytes | `935` bytes | `53.0%` |
| `TexSoup/` raw Python source (`*.py`) | `98,181` bytes | `24,722` bytes | `74.8%` |
| `TexSoup/` compressed source (`.tar.gz`) | `23,656` bytes | `9,208` bytes | `61.1%` |

For baseline comparisons, speed results, and TexSoup validation details, see
[benchmarks/README.md](./benchmarks/README.md).

# Installation

## Pip

```bash
python3 -m pip install pymini
```

## From source

```bash
git clone https://github.com/alvinwan/pymini.git
cd pymini
python3 -m pip install -e ".[dev]"
```
