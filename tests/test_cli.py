import ast
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pymini", *args],
        cwd=PROJECT_ROOT,
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


def assert_bundle_preserves_public_alias(bundle_source: str) -> None:
    bundle_tree = ast.parse(bundle_source)
    function, alias, printer = bundle_tree.body

    assert isinstance(function, ast.FunctionDef)
    assert function.name != "square"
    assert len(function.name) == 1

    assert isinstance(alias, ast.Assign)
    assert alias.targets[0].id == "square"
    assert alias.value.id == function.name

    call = printer.value
    assert call.args[0].func.id == function.name


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
    assert_bundle_preserves_public_alias(bundle_path.read_text(encoding="utf-8"))


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
