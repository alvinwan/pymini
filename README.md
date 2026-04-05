# pymini

`pymini` is an AST-based Python minifier for scripts and packages. It preserves
package layout by default, can emit a single-file bundle when asked, and can
shrink Python code by roughly `30%` to `90%` depending on the codebase and
whether you compare raw source or compressed archives.

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

Current checked-in fixtures:

| Input | Original | Minified | Reduction |
| --- | ---: | ---: | ---: |
| `tests/examples/pyminifier.py` | `1,355` bytes | `511` bytes | `62.3%` |
| `tests/examples/pyminify.py` | `1,990` bytes | `981` bytes | `50.7%` |
| `TexSoup/` raw Python source (`*.py`) | `98,181` bytes | `33,107` bytes | `66.3%` |
| `TexSoup/` compressed source (`.tar.gz`) | `70,532` bytes | `11,850` bytes | `83.2%` |

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
