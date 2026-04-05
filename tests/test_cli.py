import ast
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pymini", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def run_python(code: str, *, pythonpath: Optional[Path] = None, cwd: Optional[Path] = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if pythonpath is not None:
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(pythonpath) if not existing else f"{pythonpath}{os.pathsep}{existing}"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd or PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def run_python_file(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(path)],
        cwd=path.parent,
        capture_output=True,
        text=True,
        check=False,
    )


def py(source: str) -> str:
    return dedent(source).strip() + "\n"


def write_py(path: Path, source: str) -> None:
    path.write_text(py(source), encoding="utf-8")


def assert_public_api_is_preserved(module_source: str, consumer_source: str) -> None:
    module_tree = ast.parse(module_source)
    consumer_tree = ast.parse(consumer_source)

    assignment, function, alias = module_tree.body
    assert isinstance(assignment, ast.Assign)
    assert assignment.targets[0].id == "PI"

    assert isinstance(function, ast.FunctionDef)
    assert function.name != "square"
    assert len(function.name) == 1

    assert isinstance(alias, ast.Assign)
    assert alias.targets[0].id == "square"
    assert alias.value.id == function.name

    importer, printer = consumer_tree.body
    assert isinstance(importer, ast.ImportFrom)
    assert importer.module == "main"
    assert [name.name for name in importer.names] == ["PI", function.name]

    call = printer.value
    assert call.args[0].id == "PI"
    assert call.args[1].func.id == function.name


def test_cli_accepts_directories(tmp_path):
    source_dir = tmp_path / "src"
    output_dir = tmp_path / "out"
    source_dir.mkdir()
    write_py(
        source_dir / "main.py",
        """
        PI = 3

        def square(x):
            return x ** 2
        """,
    )
    write_py(
        source_dir / "side.py",
        """
        from main import PI, square

        print(PI, square(3))
        """,
    )

    result = run_cli(
        "package",
        str(source_dir),
        "-o",
        str(output_dir),
    )

    assert result.returncode == 0, result.stderr
    assert_public_api_is_preserved(
        (output_dir / "main.py").read_text(encoding="utf-8"),
        (output_dir / "side.py").read_text(encoding="utf-8"),
    )


def test_cli_can_write_single_file_output(tmp_path):
    source_dir = tmp_path / "src"
    bundle_path = tmp_path / "bundle.py"
    source_dir.mkdir()
    write_py(
        source_dir / "main.py",
        """
        def square(x):
            return x ** 2
        """,
    )
    write_py(
        source_dir / "side.py",
        """
        from main import square

        print(square(3))
        """,
    )

    result = run_cli("bundle", str(source_dir), "-o", str(bundle_path))

    assert result.returncode == 0, result.stderr
    execution = run_python_file(bundle_path)
    assert execution.returncode == 0, execution.stderr
    assert execution.stdout == "9\n"


def test_cli_preserves_nested_package_paths(tmp_path):
    source_dir = tmp_path / "src"
    output_dir = tmp_path / "out"
    source_dir.mkdir()
    (source_dir / "pkg").mkdir()
    (source_dir / "pkg" / "sub").mkdir(parents=True)

    write_py(
        source_dir / "pkg" / "__init__.py",
        """
        ROOT = 1
        """,
    )
    write_py(
        source_dir / "pkg" / "sub" / "__init__.py",
        """
        CHILD = 2
        """,
    )

    result = run_cli(
        "package",
        str(source_dir),
        "-o",
        str(output_dir),
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "pkg" / "__init__.py").read_text(encoding="utf-8") == "ROOT=1"
    assert (output_dir / "pkg" / "sub" / "__init__.py").read_text(encoding="utf-8") == "CHILD=2"


def test_cli_errors_when_no_python_files_match(tmp_path):
    source_dir = tmp_path / "empty"
    source_dir.mkdir()

    result = run_cli("package", str(source_dir))

    assert result.returncode != 0
    assert "no Python files matched" in result.stderr


def test_cli_defaults_to_package_mode_for_legacy_invocation(tmp_path):
    source_dir = tmp_path / "src"
    output_dir = tmp_path / "out"
    source_dir.mkdir()
    write_py(
        source_dir / "main.py",
        """
        PI = 3
        """,
    )

    result = run_cli(str(source_dir), "-o", str(output_dir))

    assert result.returncode == 0, result.stderr
    assert (output_dir / "main.py").read_text(encoding="utf-8") == "PI=3"


def test_cli_can_aggressively_rename_globals_in_package_mode(tmp_path):
    source_dir = tmp_path / "src"
    output_dir = tmp_path / "out"
    source_dir.mkdir()
    write_py(
        source_dir / "main.py",
        """
        public_name = 3
        """,
    )

    result = run_cli(
        "package",
        str(source_dir),
        "--rename-global-variables",
        "-o",
        str(output_dir),
    )

    assert result.returncode == 0, result.stderr
    tree = ast.parse((output_dir / "main.py").read_text(encoding="utf-8"))
    assignment = tree.body[0]
    assert isinstance(assignment, ast.Assign)
    assert assignment.targets[0].id != "public_name"
    assert len(assignment.targets[0].id) == 1


def test_cli_can_rename_arguments_when_requested(tmp_path):
    source_dir = tmp_path / "src"
    output_dir = tmp_path / "out"
    source_dir.mkdir()
    write_py(
        source_dir / "main.py",
        """
        class Token:
            def __init__(self, value):
                self.value = value

            def show(self):
                return self.value

        print(Token(3).show())
        """,
    )

    result = run_cli(
        "package",
        str(source_dir),
        "--rename-arguments",
        "-o",
        str(output_dir),
    )

    assert result.returncode == 0, result.stderr
    output = (output_dir / "main.py").read_text(encoding="utf-8")
    assert "self." not in output

    execution = run_python_file(output_dir / "main.py")
    assert execution.returncode == 0, execution.stderr
    assert execution.stdout == "3\n"


def test_cli_package_mode_supports_relative_star_reexports(tmp_path):
    source_dir = tmp_path / "src"
    output_dir = tmp_path / "out"
    pkg_dir = source_dir / "pkg"
    pkg_dir.mkdir(parents=True)

    write_py(
        pkg_dir / "__init__.py",
        """
        from .helpers import *

        __all__ = ["greet"]
        """,
    )
    write_py(
        pkg_dir / "helpers.py",
        """
        def greet():
            return "hello"
        """,
    )
    write_py(
        source_dir / "app.py",
        """
        from pkg import greet

        print(greet())
        """,
    )

    result = run_cli("package", str(source_dir), "-o", str(output_dir))

    assert result.returncode == 0, result.stderr
    execution = run_python("import app", pythonpath=output_dir, cwd=tmp_path)
    assert execution.returncode == 0, execution.stderr
    assert execution.stdout == "hello\n"


def test_cli_package_mode_supports_dotted_and_dynamic_imports(tmp_path):
    source_dir = tmp_path / "src"
    output_dir = tmp_path / "out"
    pkg_dir = source_dir / "pkg"
    pkg_dir.mkdir(parents=True)

    write_py(pkg_dir / "__init__.py", "VALUE = 1")
    write_py(
        pkg_dir / "helpers.py",
        """
        def greet():
            return "hello"
        """,
    )
    write_py(
        source_dir / "app.py",
        """
        import importlib
        import pkg.helpers

        print(pkg.helpers.greet(), importlib.import_module("pkg.helpers").greet())
        """,
    )

    result = run_cli("package", str(source_dir), "-o", str(output_dir))

    assert result.returncode == 0, result.stderr
    execution = run_python("import app", pythonpath=output_dir, cwd=tmp_path)
    assert execution.returncode == 0, execution.stderr
    assert execution.stdout == "hello hello\n"


def test_cli_bundle_mode_supports_complex_package_graphs(tmp_path):
    source_dir = tmp_path / "src"
    bundle_path = tmp_path / "bundle.py"
    pkg_dir = source_dir / "pkg"
    pkg_dir.mkdir(parents=True)

    write_py(
        pkg_dir / "__init__.py",
        """
        EVENTS = ["pkg"]

        from .shared import register
        from .helpers import *

        register(EVENTS)
        __all__ = ["EVENTS", "greet"]
        """,
    )
    write_py(
        pkg_dir / "shared.py",
        """
        def register(events):
            events.append("shared")

        def label():
            return "hello"
        """,
    )
    write_py(
        pkg_dir / "helpers.py",
        """
        from .shared import label

        def greet():
            return label()
        """,
    )
    write_py(
        source_dir / "app.py",
        """
        from pkg import *
        import importlib
        import pkg.helpers

        print(",".join(EVENTS), greet(), pkg.helpers.greet(), importlib.import_module("pkg.shared").label())
        """,
    )

    result = run_cli("bundle", str(source_dir), "-o", str(bundle_path))

    assert result.returncode == 0, result.stderr
    execution = run_python_file(bundle_path)
    assert execution.returncode == 0, execution.stderr
    assert execution.stdout == "pkg,shared hello hello hello\n"
