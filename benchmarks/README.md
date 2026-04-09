# Benchmarks

This directory holds the current size and speed measurements for `pymini`, plus
the benchmark harness used to reproduce them.

- [Results](#results)
- [Reproduce](#reproduce)
- [Validation](#validation)

# Results

![Benchmark summary chart comparing minify-only minification and minify-plus-wheel compression across packages](./summary.svg)

## Compression

Compression multipliers below are all relative to the original raw Python
source bytes for that repo.

### Minify Only

| Package | Original bytes | pymini | pyminifier | python-minifier |
| --- | ---: | ---: | ---: | ---: |
| TexSoup | 98,181 | 4.0x | 2.8x | 1.2x |
| timefhuman | 119,155 | 1.9x | 1.2x | 1.6x |
| pyminifier | 90,901 | 2.9x | 1.8x | 1.8x |
| rich | 1,217,001 | 2.6x | failed | 1.6x |

| Package | Original bytes | pymini bytes | pyminifier bytes | python-minifier bytes |
| --- | ---: | ---: | ---: | ---: |
| TexSoup | 98,181 | 24,724 | 34,643 | 83,303 |
| timefhuman | 119,155 | 63,821 | 98,576 | 76,466 |
| pyminifier | 90,901 | 31,372 | 50,022 | 51,574 |
| rich | 1,217,001 | 471,254 | failed | 752,839 |

Minify-only failures:

- rich + pyminifier: minification fails on `rich/__init__.py` with
  `TypeError: 'NoneType' object is not subscriptable` in
  `pyminifier.minification.reduce_operators`.

### tar.gz Results

| Package | Original bytes | tar.gz only | pymini + tar.gz | pyminifier + tar.gz | python-minifier + tar.gz |
| --- | ---: | ---: | ---: | ---: | ---: |
| TexSoup | 98,181 | 4.3x | 11.5x | 10.1x | 4.6x |
| timefhuman | 119,155 | 4.7x | 5.9x | 5.1x | 5.5x |
| pyminifier | 90,901 | 4.2x | 8.0x | 7.4x | 5.5x |
| rich | 1,217,001 | 5.5x | 10.5x | failed | 6.5x |

| Package | Original tar.gz bytes | pymini + tar.gz bytes | pyminifier + tar.gz bytes | python-minifier + tar.gz bytes |
| --- | ---: | ---: | ---: | ---: |
| TexSoup | 22,990 | 8,522 | 9,740 | 21,530 |
| timefhuman | 25,222 | 20,338 | 23,154 | 21,809 |
| pyminifier | 21,820 | 11,357 | 12,354 | 16,524 |
| rich | 220,870 | 115,910 | failed | 185,878 |

tar.gz failures:

- rich + pyminifier: the same minification failure prevents the compressed
  package snapshot from being produced.

### Wheel Results

Wheel builds are stricter than raw package snapshots because they exercise the
repo's actual packaging metadata.

| Package | Original bytes | wheel only | pymini + wheel | pyminifier + wheel | python-minifier + wheel |
| --- | ---: | ---: | ---: | ---: | ---: |
| TexSoup | 98,181 | 3.4x | 7.3x | 6.6x | 3.6x |
| timefhuman | 119,155 | 2.9x | 3.4x | 3.1x | 3.2x |
| pyminifier | 90,901 | 1.1x | 1.5x | 1.4x | 1.2x |
| rich | 1,217,001 | 3.9x | 6.6x | failed | 4.6x |

| Package | Original wheel bytes | pymini wheel bytes | pyminifier wheel bytes | python-minifier wheel bytes |
| --- | ---: | ---: | ---: | ---: |
| TexSoup | 28,773 | 13,475 | 14,793 | 27,050 |
| timefhuman | 40,591 | 35,094 | 38,229 | 37,092 |
| pyminifier | 79,693 | 61,088 | 64,019 | 76,101 |
| rich | 310,458 | 183,326 | failed | 266,399 |

`pymini` is benchmarked with `--rename-modules --rename-global-variables --rename-arguments`.
The `pymini` rows use package mode. The baselines minify each file
independently in the preserved package tree. For wheel rows, each tool first
rewrites the package tree, then `python -m build --wheel` runs on that
rewritten checkout.

Wheel-specific failures:

- pyminifier wheel rows use a small benchmark-only compatibility patch for the
  repo's legacy `setup.py` and `collections.Iterable` imports so the original
  project still builds on Python 3.13.
- rich + pyminifier: minification fails on `rich/__init__.py` with
  `TypeError: 'NoneType' object is not subscriptable` in
  `pyminifier.minification.reduce_operators`, so the wheel build never starts.

## Speed

| Input | pymini | pyminifier | python-minifier |
| --- | ---: | ---: | ---: |
| pyminifier.py | 29.3 ms | 4.1 ms | 16.1 ms |
| pyminify.py | 36.2 ms | 7.6 ms | 28.4 ms |
| click | 1.937 s | failed | 2.167 s |
| pytest | 3.258 s | failed | 3.156 s |
| TexSoup | 218.6 ms | failed | 251.1 ms |
| timefhuman | 441.5 ms | failed | 450.6 ms |
| pyminifier | 180.7 ms | 73.0 ms | 197.2 ms |
| rich | 3.226 s | failed | 3.080 s |

pyminifier minification fails on `__init__.py` with
  `TypeError: 'NoneType' object is not subscriptable`.

The single-file rows use the same transforms as
[benchmark_speed.py](./benchmark_speed.py). The broader package snapshot was
originally averaged over three fresh-process runs from the same environment
used for the compression comparison. `pymini` used package mode with
`--rename-modules --rename-global-variables --rename-arguments`, while the
baseline tools minified each file independently in the preserved package tree.
The `click`, `pytest`, and `pyminifier` rows use the checked-in fixtures under
`.bench-repos`; the other package rows use local package checkouts. The
single-file rows plus the checked-in `click` and `pyminifier` fixture rows
were refreshed in-process on April 9, 2026 for the repeated-string-hoisting
optimization. `summary.svg` is unchanged because it only charts compression
ratios, not speed.

# Reproduce

Recompute the speed measurements with:

```bash
python3 -m pip install -e ".[dev]" python-minifier
git clone https://github.com/liftoff/pyminifier /tmp/pyminifier
PYTHONPATH=. .venv/bin/python benchmarks/benchmark_speed.py --pyminifier-root /tmp/pyminifier
```

The larger package comparisons in this file were run against these checkouts:

- `TexSoup`
- `timefhuman`
- `pyminifier`
- `rich`
- `click`
- `pytest`

# Validation

Each package result above was checked against the repo's own test suite using a
temporary minified package tree on `PYTHONPATH`.

| Package | pymini | pyminifier | python-minifier |
| --- | --- | --- | --- |
| TexSoup | 78 passed | 78 passed | 78 passed |
| timefhuman | 187 passed | 187 passed | 187 passed |
| rich | 952 passed, 25 skipped | build failed | 952 passed, 25 skipped |

`pyminifier` failed on `rich` before tests ran, with an `IndentationError`
during minification. The `pyminifier` repo itself is omitted here because one
upstream test shells out to a `pyminifier` executable on `PATH`, which is not a
like-for-like package-tree validation.

## TexSoup

<!-- Raw bytes: 98,181 -> 24,724. Compressed bytes: 22,990 -> 8,522. -->

To reproduce that flow locally:

```bash
git clone https://github.com/alvinwan/TexSoup /tmp/texsoup
mkdir -p /tmp/texsoup-out/TexSoup
pymini package /tmp/texsoup/TexSoup -o /tmp/texsoup-out/TexSoup --rename-modules --rename-global-variables --rename-arguments
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
mkdir -p /tmp/texsoup-compare/original/TexSoup /tmp/texsoup-compare/minified/TexSoup
rsync -a --prune-empty-dirs --include '*/' --include '*.py' --exclude '*' /tmp/texsoup/TexSoup/ /tmp/texsoup-compare/original/TexSoup/
rsync -a --prune-empty-dirs --include '*/' --include '*.py' --exclude '*' /tmp/texsoup-out/TexSoup/ /tmp/texsoup-compare/minified/TexSoup/
tar -czf /tmp/texsoup-original-package.tar.gz -C /tmp/texsoup-compare/original TexSoup
tar -czf /tmp/texsoup-minified-package.tar.gz -C /tmp/texsoup-compare/minified TexSoup
stat -f%z /tmp/texsoup-original-package.tar.gz
stat -f%z /tmp/texsoup-minified-package.tar.gz
```
