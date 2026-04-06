# pymini

`pymini` is an AST-based Python minifier for scripts and packages. It preserves
package layout by default, can emit a single-file bundle when asked, and can
shrink Python packages by roughly `2x` to `4x` on the validated benchmarks
below when aggressive renaming is enabled.

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

Representative compression results, using
`--rename-modules --rename-global-variables --rename-arguments`:

| Input | Original bytes | pymini | pyminifier | python-minifier |
| --- | ---: | ---: | ---: | ---: |
| TexSoup | 98,181 | 4.0x | 2.8x | 1.2x |
| timefhuman | 119,155 | 1.9x | 1.2x | 1.6x |
| rich | 1,217,001 | 2.6x | failed | 1.6x |

For the full compression tables, speed results, and package validation
results, see [benchmarks/README.md](./benchmarks/README.md).

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
