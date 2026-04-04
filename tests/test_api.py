from textwrap import dedent

from pymini import minify


def py(source: str) -> str:
    return dedent(source).strip() + "\n"


def test_minify_simplifies_returns():
    cleaned, modules = minify(
        py(
            """
            def f():
                value = 1
                return value
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    assert cleaned == ["def f():return 1"]
    assert modules == ["main"]


def test_minify_updates_cross_file_imports():
    cleaned, modules = minify(
        [
            py(
                """
                a = 3

                def square(x):
                    return x ** 2
                """
            ),
            py(
                """
                from main import square

                square(3)
                """
            ),
        ],
        ["main", "side"],
    )

    assert cleaned == ["b=3\ndef d(c):return c**2", "from e import d;d(3)"]
    assert modules == ["e", "f"]


def test_minify_preserves_public_names_when_requested():
    cleaned, modules = minify(
        [
            py(
                """
                PI = 3

                def square(x):
                    return x ** 2
                """
            ),
            py(
                """
                from main import PI, square

                print(PI, square(3))
                """
            ),
        ],
        ["main", "side"],
        keep_module_names=True,
        keep_global_variables=True,
    )

    assert cleaned == [
        "PI=3\ndef square(a):return a**2",
        "from main import PI,square;print(PI,square(3))",
    ]
    assert modules == ["main", "side"]


def test_minify_fuses_files_into_single_module():
    cleaned, modules = minify(
        [
            py(
                """
                def square(x):
                    return x ** 2
                """
            ),
            py(
                """
                from main import square

                print(square(3))
                """
            ),
        ],
        ["main", "side"],
        output_single_file=True,
    )

    assert cleaned == ["def b(a):return a**2\nprint(b(3))"]
    assert modules == ["bundle"]
