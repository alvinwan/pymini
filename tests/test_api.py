import ast
from textwrap import dedent

from pymini import minify


def py(source: str) -> str:
    return dedent(source).strip() + "\n"


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


def assert_bundle_is_shortened(bundle_source: str) -> None:
    bundle_tree = ast.parse(bundle_source)
    function, printer = bundle_tree.body

    assert isinstance(function, ast.FunctionDef)
    assert function.name != "square"
    assert len(function.name) == 1

    call = printer.value
    assert call.args[0].func.id == function.name


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


def test_minify_does_not_crash_when_returning_parameter_names():
    cleaned, modules = minify(
        py(
            """
            def abs_path(path):
                if path:
                    return path

                value = 1
                return value
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    tree = ast.parse(cleaned[0])
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    condition = function.body[0]
    simplified_return = function.body[1]

    assert isinstance(condition, ast.If)
    assert isinstance(condition.body[0], ast.Return)
    assert isinstance(condition.body[0].value, ast.Name)
    assert condition.body[0].value.id == function.args.args[0].arg

    assert isinstance(simplified_return, ast.Return)
    assert isinstance(simplified_return.value, ast.Constant)
    assert simplified_return.value.value == 1
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

    assert_public_api_is_preserved(*cleaned)
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

    assert_bundle_is_shortened(cleaned[0])
    assert modules == ["bundle"]
