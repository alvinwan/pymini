# Benchmarks

Latency is machine-dependent. Recompute these with
`PYTHONPATH=. .venv/bin/python benchmarks/benchmark_speed.py`.

The single-file comparison uses `pymini`, `pyminifier`, and
`python-minifier`. The package benchmark is `pymini`-only.

| Input | `pymini` | `pyminifier` | `python-minifier` |
| --- | ---: | ---: | ---: |
| `tests/examples/pyminifier.py` | `14.1 ms` | `0.4 ms` | `1.5 ms` |
| `tests/examples/pyminify.py` | `1227.6 ms` | `1.1 ms` | `4.0 ms` |
| `TexSoup/` package API | `4928.8 ms` | `—` | `—` |
| `TexSoup/` package CLI | `5062.0 ms` | `—` | `—` |

To reproduce those numbers:

```bash
python3 -m pip install -e ".[dev]" python-minifier
git clone https://github.com/liftoff/pyminifier /tmp/pyminifier
PYTHONPATH=. .venv/bin/python benchmarks/benchmark_speed.py --pyminifier-root /tmp/pyminifier
```
