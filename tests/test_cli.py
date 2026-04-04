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
        str(source_dir),
        "--keep-module-names",
        "--keep-global-variables",
        "-o",
        str(output_dir),
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "main.py").read_text(encoding="utf-8") == "PI=3\ndef square(a):return a**2"
    assert (output_dir / "side.py").read_text(encoding="utf-8") == "from main import PI,square;print(PI,square(3))"


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

    result = run_cli(str(source_dir), "--single-file", "-o", str(bundle_path))

    assert result.returncode == 0, result.stderr
    assert bundle_path.read_text(encoding="utf-8") == "def b(a):return a**2\nprint(b(3))"


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
        str(source_dir),
        "--keep-module-names",
        "--keep-global-variables",
        "-o",
        str(output_dir),
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "pkg" / "__init__.py").read_text(encoding="utf-8") == "ROOT=1"
    assert (output_dir / "pkg" / "sub" / "__init__.py").read_text(encoding="utf-8") == "CHILD=2"


def test_cli_errors_when_no_python_files_match(tmp_path):
    source_dir = tmp_path / "empty"
    source_dir.mkdir()

    result = run_cli(str(source_dir))

    assert result.returncode != 0
    assert "no Python files matched" in result.stderr
