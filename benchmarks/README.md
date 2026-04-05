# Benchmarks

This directory holds the current size and speed measurements for `pymini`, plus
the benchmark harness used to reproduce them.

- [Results](#results)
- [Reproduce](#reproduce)
- [TexSoup Validation](#texsoup-validation)

# Results

| Input | Original | `pymini` size | `pymini` speed | `pyminifier` size | `pyminifier` speed | `python-minifier` size | `python-minifier` speed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `pyminifier.py` | `1,355` bytes | `511` bytes, `62.3%` | `2.4 ms` | `676` bytes, `50.1%` | `0.4 ms` | `1,020` bytes, `24.7%` | `1.6 ms` |
| `pyminify.py` | `1,990` bytes | `981` bytes, `50.7%` | `5.4 ms` | `1,605` bytes, `19.3%` | `1.2 ms` | `983` bytes, `50.6%` | `4.1 ms` |
| `TexSoup/*.py` | `98,181` bytes | `33,107` bytes, `66.3%` | `399.3 ms` | `34,643` bytes, `64.7%` | `31.3 ms` | `83,303` bytes, `15.2%` | `120.8 ms` |
| `TexSoup.tar.gz` | `23,118` bytes | `11,368` bytes, `50.8%` | `—` | `9,741` bytes, `57.9%` | `—` | `21,532` bytes, `6.9%` | `—` |

`TexSoup/*.py` compares validated package outputs. `pymini` uses package mode;
the baselines minify each file independently in the preserved package tree. All
three outputs pass the upstream TexSoup test suite (`78` tests).

# Reproduce

Recompute the speed measurements with:

```bash
python3 -m pip install -e ".[dev]" python-minifier
git clone https://github.com/liftoff/pyminifier /tmp/pyminifier
PYTHONPATH=. .venv/bin/python benchmarks/benchmark_speed.py --pyminifier-root /tmp/pyminifier
```

# TexSoup Validation

`pymini` has been validated against the upstream `TexSoup` test suite in
package mode. Current validation: upstream pytest passes (`78` tests), raw
source code is `66.3%` smaller, and compressed source code (`.tar.gz`) is
`50.8%` smaller when measured on clean `.py`-only package snapshots.

<!-- Raw bytes: 98,181 -> 33,107. Compressed bytes: 23,118 -> 11,368. -->

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
