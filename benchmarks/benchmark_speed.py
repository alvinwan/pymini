#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import shutil
import sys
import tempfile
from pathlib import Path
from statistics import mean
from time import perf_counter
from types import SimpleNamespace

from pymini import minify
from pymini.cli import load_sources, main as cli_main, resolve_python_files


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = ROOT / "tests" / "examples"
DEFAULT_TEXSOUP_ROOT = Path("/tmp/pymini-texsoup-repo/TexSoup")
DEFAULT_PYMINIFIER_ROOT = Path("/tmp/pymini-pyminifier-src/pyminifier-2.1")
PYMINI_BENCHMARK_KWARGS = {
    "keep_module_names": False,
    "keep_global_variables": False,
    "rename_arguments": True,
}
PYMINI_CLI_FLAGS = [
    "--rename-modules",
    "--rename-global-variables",
    "--rename-arguments",
]


def benchmark_transform(
    transform,
    source: str,
    *,
    iterations: int,
    warmup: int,
) -> dict[str, float]:
    result = None
    for _ in range(warmup):
        result = transform(source)
    samples = []
    for _ in range(iterations):
        start = perf_counter()
        result = transform(source)
        samples.append(perf_counter() - start)
    avg = mean(samples)
    output_bytes = len((result or "").encode())
    return {
        "output_bytes": float(output_bytes),
        "avg_ms": avg * 1000,
        "throughput_kb_s": (len(source.encode()) / 1024) / avg,
    }


def pymini_single_file_transform(path: Path):
    def transform(source: str) -> str:
        outputs, _ = minify(source, path.stem, **PYMINI_BENCHMARK_KWARGS)
        return outputs[0]

    return transform


def load_python_minifier():
    try:
        python_minifier = importlib.import_module("python_minifier")
    except ImportError:
        return None

    def factory(path: Path):
        return lambda source: python_minifier.minify(source, filename=path.name)

    return factory


def load_pyminifier(pyminifier_root: Path):
    if not pyminifier_root.exists():
        return None
    sys.path.insert(0, str(pyminifier_root))
    try:
        minification = importlib.import_module("pyminifier.minification")
        token_utils = importlib.import_module("pyminifier.token_utils")
    except ImportError:
        return None
    options = SimpleNamespace(tabs=False)

    def factory(path: Path):
        def transform(source: str) -> str:
            tokens = token_utils.listified_tokenizer(source)
            return minification.minify(tokens, options)

        return transform

    return factory


def benchmark_package_api(
    package_root: Path,
    *,
    iterations: int,
    warmup: int,
) -> dict[str, float]:
    paths, module_root = resolve_python_files(str(package_root))
    sources, modules, _ = load_sources(paths, module_root=module_root)
    for _ in range(warmup):
        minify(
            sources,
            modules,
            **PYMINI_BENCHMARK_KWARGS,
        )
    samples = []
    outputs = None
    for _ in range(iterations):
        start = perf_counter()
        outputs, _ = minify(
            sources,
            modules,
            **PYMINI_BENCHMARK_KWARGS,
        )
        samples.append(perf_counter() - start)
    raw_bytes = sum(len(source.encode()) for source in sources)
    output_bytes = sum(len(output.encode()) for output in (outputs or []))
    avg = mean(samples)
    return {
        "files": float(len(paths)),
        "bytes": float(raw_bytes),
        "output_bytes": float(output_bytes),
        "avg_ms": avg * 1000,
        "throughput_kb_s": (raw_bytes / 1024) / avg,
    }


def benchmark_package_cli(package_root: Path, *, iterations: int) -> dict[str, float]:
    samples = []
    output_bytes = 0
    for _ in range(iterations):
        output_dir = Path(tempfile.mkdtemp(prefix="pymini-bench-"))
        try:
            start = perf_counter()
            rc = cli_main(["package", str(package_root), *PYMINI_CLI_FLAGS, "-o", str(output_dir)])
            samples.append(perf_counter() - start)
            if rc != 0:
                raise RuntimeError(f"pymini CLI returned {rc}")
            output_bytes = sum(len(path.read_bytes()) for path in output_dir.rglob("*.py"))
        finally:
            shutil.rmtree(output_dir)
    avg = mean(samples)
    return {"avg_ms": avg * 1000, "output_bytes": float(output_bytes)}


def print_example_results(
    *,
    example_iterations: int,
    warmup: int,
    pyminifier_root: Path,
) -> None:
    tool_factories = [("pymini", pymini_single_file_transform)]
    python_minifier = load_python_minifier()
    if python_minifier is not None:
        tool_factories.append(("python-minifier", python_minifier))
    pyminifier_factory = load_pyminifier(pyminifier_root)
    if pyminifier_factory is not None:
        tool_factories.append(("pyminifier", pyminifier_factory))

    print("Single-file API benchmarks")
    print("input\ttool\tinput_bytes\toutput_bytes\tavg_ms\tthroughput_kb_s")
    for path in sorted(EXAMPLE_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for tool_name, factory in tool_factories:
            result = benchmark_transform(
                factory(path),
                source,
                iterations=example_iterations,
                warmup=warmup,
            )
            print(
                f"{path.name}\t"
                f"{tool_name}\t"
                f"{len(source.encode())}\t"
                f"{int(result['output_bytes'])}\t"
                f"{result['avg_ms']:.3f}\t"
                f"{result['throughput_kb_s']:.1f}"
            )


def print_package_results(
    texsoup_root: Path,
    *,
    package_api_iterations: int,
    package_cli_iterations: int,
    warmup: int,
) -> None:
    if not texsoup_root.exists():
        print(f"TexSoup benchmark skipped: {texsoup_root} does not exist")
        return

    api_result = benchmark_package_api(
        texsoup_root,
        iterations=package_api_iterations,
        warmup=warmup,
    )
    cli_result = benchmark_package_cli(
        texsoup_root,
        iterations=package_cli_iterations,
    )

    print()
    print("Package benchmarks")
    print("name\tfiles\tinput_bytes\toutput_bytes\tavg_ms\tthroughput_kb_s")
    print(
        f"TexSoup-api\t"
        f"{int(api_result['files'])}\t"
        f"{int(api_result['bytes'])}\t"
        f"{int(api_result['output_bytes'])}\t"
        f"{api_result['avg_ms']:.3f}\t"
        f"{api_result['throughput_kb_s']:.1f}"
    )
    print(
        f"TexSoup-cli\t-\t-\t{int(cli_result['output_bytes'])}\t"
        f"{cli_result['avg_ms']:.3f}\t-"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark pymini speed on repo fixtures.")
    parser.add_argument(
        "--texsoup-root",
        type=Path,
        default=DEFAULT_TEXSOUP_ROOT,
        help="Path to a TexSoup package checkout for package-mode benchmarks.",
    )
    parser.add_argument(
        "--pyminifier-root",
        type=Path,
        default=DEFAULT_PYMINIFIER_ROOT,
        help="Path to a pyminifier source checkout for baseline single-file benchmarks.",
    )
    parser.add_argument(
        "--example-iterations",
        type=int,
        default=10,
        help="Number of timed runs per single-file example.",
    )
    parser.add_argument(
        "--package-api-iterations",
        type=int,
        default=3,
        help="Number of timed runs for the in-memory package benchmark.",
    )
    parser.add_argument(
        "--package-cli-iterations",
        type=int,
        default=3,
        help="Number of timed runs for the end-to-end CLI package benchmark.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Warmup runs to perform before each benchmark group.",
    )
    args = parser.parse_args()

    print_example_results(
        example_iterations=args.example_iterations,
        warmup=args.warmup,
        pyminifier_root=args.pyminifier_root,
    )
    print_package_results(
        args.texsoup_root,
        package_api_iterations=args.package_api_iterations,
        package_cli_iterations=args.package_cli_iterations,
        warmup=args.warmup,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
