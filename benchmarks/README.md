# Benchmarks

This directory holds the current size and speed measurements for `pymini`, plus
the benchmark harness used to reproduce them.

- [Compression](#compression)
- [Speed](#speed)
- [TexSoup Validation](#texsoup-validation)

# Compression

Checked-in fixture comparison:

| Input | Original | `pymini` | `pyminifier` | `python-minifier` |
| --- | ---: | ---: | ---: | ---: |
| `tests/examples/pyminifier.py` | `1,355` bytes | `511` bytes, `62.3%` | `676` bytes, `50.1%` | `1,020` bytes, `24.7%` |
| `tests/examples/pyminify.py` | `1,990` bytes | `981` bytes, `50.7%` | `1,605` bytes, `19.3%` | `983` bytes, `50.6%` |

TexSoup package mode (`pymini` only):

| Input | Original | `pymini` | Reduction |
| --- | ---: | ---: | ---: |
| `TexSoup/` raw Python source (`*.py`) | `98,181` bytes | `33,107` bytes | `66.3%` |
| `TexSoup/` compressed source (`.tar.gz`) | `70,532` bytes | `11,850` bytes | `83.2%` |

TexSoup file-by-file package comparison. All three outputs pass the upstream
TexSoup test suite (`78` tests):

| Input | Original | `pymini` | `pyminifier` | `python-minifier` |
| --- | ---: | ---: | ---: | ---: |
| `TexSoup/` raw Python source (`*.py`) | `98,181` bytes | `32,131` bytes, `67.3%` | `34,643` bytes, `64.7%` | `83,303` bytes, `15.2%` |
| `TexSoup/` compressed source (`.tar.gz`) | `23,116` bytes | `10,926` bytes, `52.7%` | `9,741` bytes, `57.9%` | `21,532` bytes, `6.9%` |

# Speed

Latency is machine-dependent. Recompute these with
`PYTHONPATH=. .venv/bin/python benchmarks/benchmark_speed.py`.

| Input | `pymini` | `pyminifier` | `python-minifier` |
| --- | ---: | ---: | ---: |
| `tests/examples/pyminifier.py` | `2.5 ms` | `0.4 ms` | `1.6 ms` |
| `tests/examples/pyminify.py` | `5.7 ms` | `1.2 ms` | `4.2 ms` |
| `TexSoup/` package API | `410.4 ms` | `—` | `—` |
| `TexSoup/` package CLI | `414.0 ms` | `—` | `—` |

To reproduce those numbers:

```bash
python3 -m pip install -e ".[dev]" python-minifier
git clone https://github.com/liftoff/pyminifier /tmp/pyminifier
PYTHONPATH=. .venv/bin/python benchmarks/benchmark_speed.py --pyminifier-root /tmp/pyminifier
```

# TexSoup Validation

`pymini` has been validated against the upstream `TexSoup` test suite in
package mode. Current validation: upstream pytest passes (`78` tests), raw
source code is `66.3%` smaller, and compressed source code (`.tar.gz`) is
`83.2%` smaller.

<!-- Raw bytes: 98,181 -> 33,107. Compressed bytes: 70,532 -> 11,850. -->

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
