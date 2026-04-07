# pymini

`pymini` is an AST-based Python minifier for scripts and packages. It can
shrink raw Python source code by up to **4x** and the associated `.whl` files
by up to **7.3x**.

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

![Benchmark summary chart comparing minify-only minification and minify-plus-wheel compression across packages](./benchmarks/summary.svg)

For these results, we validate that all package tests still run and pass,
with the minified source code. For the full compression tables, speed results,
and package validation, see [benchmarks/README.md](./benchmarks/README.md).

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
