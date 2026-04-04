import glob
import sys
from argparse import ArgumentParser, SUPPRESS
from pathlib import Path
from typing import Iterable, Optional, Sequence

from pymini import __version__
from pymini.pymini import minify


PACKAGE_MODE = "package"
BUNDLE_MODE = "bundle"
MODES = {PACKAGE_MODE, BUNDLE_MODE}


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="pymini")
    parser.add_argument(
        "mode",
        choices=sorted(MODES),
        help="Output mode: preserve a package tree or bundle everything into one file.",
    )
    parser.add_argument('path', help='Path to the file or directory to minify')
    parser.add_argument(
        '--rename-modules',
        action='store_true',
        help='Allow module names to be shortened when the selected mode supports it.',
    )
    parser.add_argument(
        '--rename-global-variables',
        action='store_true',
        help='Rename top-level globals instead of preserving them through public aliases.',
    )
    parser.add_argument('--single-file', action='store_true', help=SUPPRESS)
    parser.add_argument('-o', '--output', help='Path to the output directory', default='./')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    return parser


def normalize_argv(argv: Optional[Sequence[str]]) -> list[str]:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return args
    if args[0] in MODES:
        return args
    if args[0].startswith("-"):
        return [PACKAGE_MODE, *args]
    return [PACKAGE_MODE, *args]


def effective_mode(args) -> str:
    return BUNDLE_MODE if args.single_file else args.mode


def resolve_options(args) -> tuple[str, bool, bool, bool]:
    mode = effective_mode(args)
    keep_module_names = not args.rename_modules
    keep_global_variables = not args.rename_global_variables
    return mode, keep_module_names, keep_global_variables, mode == BUNDLE_MODE


def resolve_python_files(path: str) -> tuple[list[Path], Optional[Path]]:
    candidate = Path(path)
    if candidate.is_file():
        return ([candidate], None) if is_python_source(candidate) else ([], None)
    if candidate.is_dir():
        return (sorted(
            file_path for file_path in candidate.rglob("*.py")
            if is_python_source(file_path)
        ), candidate)
    return (sorted(
        Path(file_path) for file_path in glob.glob(path, recursive=True)
        if Path(file_path).is_file() and is_python_source(Path(file_path))
    ), None)


def is_python_source(path: Path) -> bool:
    return path.suffix == ".py" and ".ugli." not in path.name


def module_name_from_relative_path(path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    if len(parts) > 1 and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def load_sources(paths: Iterable[Path], *, module_root: Optional[Path]) -> tuple[list[str], list[str], dict[str, Path]]:
    sources, modules = [], []
    module_to_output_path = {}
    for path in paths:
        sources.append(path.read_text(encoding="utf-8"))
        if module_root is None:
            module = path.stem
            output_path = Path(path.name)
        else:
            output_path = path.relative_to(module_root)
            module = module_name_from_relative_path(output_path)
        modules.append(module)
        module_to_output_path[module] = output_path
    return sources, modules, module_to_output_path


def ensure_unique_modules(modules: Sequence[str]) -> None:
    duplicates = sorted({module for module in modules if modules.count(module) > 1})
    if duplicates:
        duplicate_list = ", ".join(repr(module) for module in duplicates)
        raise ValueError(
            f"input resolves to duplicate module names: {duplicate_list}. "
            "Pass a package root directory instead of a narrower glob or file list."
        )


def write_outputs(
    sources: Sequence[str],
    modules: Sequence[str],
    output: Path,
    *,
    single_file: bool,
    keep_module_names: bool,
    module_to_output_path: dict[str, Path],
) -> None:
    if single_file:
        destination = output if output.suffix == ".py" else output / f"{modules[0]}.py"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(sources[0], encoding="utf-8")
        return

    if output.suffix == ".py":
        raise ValueError("output must be a directory unless --single-file is set")

    output.mkdir(parents=True, exist_ok=True)
    for source, module in zip(sources, modules):
        destination = (
            output / module_to_output_path[module]
            if keep_module_names and module in module_to_output_path
            else output / f"{module}.py"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_argv(argv))
    mode, keep_module_names, keep_global_variables, output_single_file = resolve_options(args)
    paths, module_root = resolve_python_files(args.path)
    if not paths:
        parser.error(f"no Python files matched {args.path!r}")

    try:
        sources, modules, module_to_output_path = load_sources(paths, module_root=module_root)
        ensure_unique_modules(modules)
    except ValueError as exc:
        parser.error(str(exc))
    cleaned, modules = minify(
        sources,
        modules,
        keep_module_names=keep_module_names,
        keep_global_variables=keep_global_variables,
        output_single_file=output_single_file,
    )
    try:
        write_outputs(
            cleaned,
            modules,
            Path(args.output),
            single_file=output_single_file,
            keep_module_names=keep_module_names,
            module_to_output_path=module_to_output_path,
        )
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
