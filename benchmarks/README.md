# Benchmarks

This directory holds the current size and speed measurements for `pymini`, plus
the benchmark harness used to reproduce them.

- [Results](#results)
- [Reproduce](#reproduce)
- [TexSoup Validation](#texsoup-validation)

# Results

| Input | Original | `pymini` size | `pymini` speed | `pyminifier` size | `pyminifier` speed | `python-minifier` size | `python-minifier` speed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `pyminifier.py` | `1,355` bytes | `438` bytes, `67.7%` | `2.1 ms` | `611` bytes, `54.9%` | `0.4 ms` | `1,020` bytes, `24.7%` | `1.7 ms` |
| `pyminify.py` | `1,990` bytes | `935` bytes, `53.0%` | `5.9 ms` | `1,540` bytes, `22.6%` | `1.2 ms` | `983` bytes, `50.6%` | `4.3 ms` |
| `TexSoup/*.py` | `98,181` bytes | `24,288` bytes, `75.3%` | `127.5 ms` | `34,643` bytes, `64.7%` | `29.7 ms` | `83,303` bytes, `15.2%` | `123.6 ms` |
| `TexSoup.tar.gz` | `23,101` bytes | `8,363` bytes, `63.8%` | `127.5 ms` | `9,718` bytes, `57.9%` | `29.7 ms` | `21,497` bytes, `6.9%` | `123.6 ms` |

`pymini` is benchmarked with `--rename-modules --rename-global-variables --rename-arguments`.
`TexSoup/*.py` compares validated package outputs. `pymini` uses package mode;
the baselines minify each file independently in the preserved package tree. All
three outputs pass the upstream TexSoup test suite (`78` tests). The
`TexSoup.tar.gz` row reuses those same minification timings and only changes
the size measurement to the compressed archive.

# Reproduce

Recompute the speed measurements with:

```bash
python3 -m pip install -e ".[dev]" python-minifier
git clone https://github.com/liftoff/pyminifier /tmp/pyminifier
PYTHONPATH=. .venv/bin/python benchmarks/benchmark_speed.py --pyminifier-root /tmp/pyminifier
```

# TexSoup Validation

`pymini` has been validated against the upstream `TexSoup` test suite in
package mode with `--rename-modules --rename-global-variables --rename-arguments`.
Current validation: upstream pytest passes (`78` tests), raw source code is
`75.3%` smaller, and compressed source code (`.tar.gz`) is `63.8%` smaller
when measured on clean `.py`-only package snapshots.

<!-- Raw bytes: 98,181 -> 24,288. Compressed bytes: 23,101 -> 8,363. -->

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
