import ast
import importlib.util
import keyword
import subprocess
import sys
from textwrap import dedent

from pymini import minify
from pymini.utils import variable_name_generator


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
    assert [name.asname for name in importer.names] == [None, "square"]

    call = printer.value
    assert call.args[0].id == "PI"
    assert call.args[1].func.id == "square"


def assert_cross_file_imports_are_rewritten(module_source: str, consumer_source: str, modules: list[str]) -> None:
    module_tree = ast.parse(module_source)
    consumer_tree = ast.parse(consumer_source)

    assignment, function = module_tree.body
    assert isinstance(assignment, ast.Assign)

    assert isinstance(function, ast.FunctionDef)
    assert function.name != "square"
    assert len(function.name) == 1

    importer, call = consumer_tree.body
    assert isinstance(importer, ast.ImportFrom)
    assert importer.module == modules[0]
    assert [name.name for name in importer.names] == [function.name]
    assert [name.asname for name in importer.names] == ["square"]

    assert isinstance(call, ast.Expr)
    assert call.value.func.id == "square"


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


def test_minify_handles_subscript_callables(tmp_path):
    cleaned, modules = minify(
        py(
            """
            callbacks = {"main": lambda: 1}
            print(callbacks["main"]())
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n"
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
    condition = next(node for node in function.body if isinstance(node, ast.If))
    simplified_return = next(
        node
        for node in function.body
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
    )

    assert isinstance(condition, ast.If)
    assert isinstance(condition.test, ast.Name)
    assert isinstance(condition.body[0], ast.Return)
    assert isinstance(condition.body[0].value, ast.Name)
    assert condition.body[0].value.id == condition.test.id

    assert isinstance(simplified_return, ast.Return)
    assert isinstance(simplified_return.value, ast.Constant)
    assert simplified_return.value.value == 1
    assert modules == ["main"]


def test_variable_name_generator_skips_python_keywords():
    generator = variable_name_generator()
    names = [next(generator) for _ in range(500)]

    assert all(name.isidentifier() for name in names)
    assert all(not keyword.iskeyword(name) for name in names)


def test_minify_hoists_repeated_strings_inside_functions(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def f():
                return {
                    "left": "PhysicalResourceId",
                    "right": "PhysicalResourceId",
                }

            print(f()["left"], f()["right"])
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    tree = ast.parse(cleaned[0])
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    helper = function.body[0]

    assert isinstance(helper, ast.Assign)
    assert isinstance(helper.value, ast.Constant)
    assert helper.value.value == "PhysicalResourceId"
    assert cleaned[0].count("PhysicalResourceId") == 1

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "PhysicalResourceId PhysicalResourceId\n"
    assert modules == ["main"]


def test_minify_hoists_repeated_strings_at_module_scope_without_leaking_helpers(tmp_path):
    cleaned, modules = minify(
        py(
            """
            left = "PhysicalResourceId"
            right = "PhysicalResourceId"

            print(left, right)
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    tree = ast.parse(cleaned[0])

    assert cleaned[0].count("PhysicalResourceId") == 1
    assert any(isinstance(node, ast.Delete) for node in tree.body)

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    spec = importlib.util.spec_from_file_location("module_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert set(
        name
        for name in module.__dict__
        if len(name) == 1 and not name.startswith("_")
    ) <= {
        node.value.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Name)
        and len(node.value.id) == 1
    }
    assert modules == ["main"]


def test_minify_skips_unprofitable_short_string_hoists_at_module_scope(tmp_path):
    cleaned, modules = minify(
        py(
            """
            left = "Foo"
            right = "Foo"

            print(left, right)
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    assert cleaned[0].count("'Foo'") == 2
    assert "del(" not in cleaned[0]

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Foo Foo\n"
    assert modules == ["main"]


def test_minify_hoists_repeated_strings_into_class_bodies_without_leaking_helpers(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class Token:
                x = "PhysicalResourceId"
                y = "PhysicalResourceId"

            print(Token.x, Token.y, [name for name in Token.__dict__ if len(name) == 1 and name not in {"x", "y"}])
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    tree = ast.parse(cleaned[0])
    class_def = next(node for node in tree.body if isinstance(node, ast.ClassDef))

    assert cleaned[0].count("PhysicalResourceId") == 1
    assert any(isinstance(node, ast.Delete) for node in class_def.body)

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "PhysicalResourceId PhysicalResourceId []\n"
    assert modules == ["main"]


def test_minify_hoisted_strings_do_not_collide_with_lambda_parameters(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def outer():
                return (lambda b: ("hello", "hello"))("x")

            print(outer())
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "('hello', 'hello')\n"
    assert modules == ["main"]


def test_minify_hoisted_strings_do_not_conflict_with_global_declarations(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def outer():
                global b
                return ("hello", "hello")

            print(outer())
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "('hello', 'hello')\n"
    assert modules == ["main"]


def test_minify_aliases_repeated_names_within_single_statements(tmp_path):
    cleaned, modules = minify(
        py(
            """
            IMPORTANT_PUBLIC_NAME = 3

            def show():
                print(IMPORTANT_PUBLIC_NAME, IMPORTANT_PUBLIC_NAME)
                print("helpers", sorted(name for name in locals() if len(name) == 1))

            show()
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    tree = ast.parse(cleaned[0])
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    assert isinstance(function, ast.FunctionDef)

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "3 3\nhelpers []\n"
    assert modules == ["main"]


def test_minify_aliases_repeated_module_names_without_leaking_helpers(tmp_path):
    cleaned, modules = minify(
        py(
            """
            IMPORTANT_PUBLIC_NAME = 3
            print(IMPORTANT_PUBLIC_NAME, IMPORTANT_PUBLIC_NAME)
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    tree = ast.parse(cleaned[0])

    assert any(isinstance(node, ast.Assign) for node in tree.body)

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    spec = importlib.util.spec_from_file_location("aliased_module_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert set(
        name
        for name in module.__dict__
        if len(name) == 1 and not name.startswith("_")
    ) <= {
        node.value.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Name)
        and len(node.value.id) == 1
    }
    assert modules == ["main"]


def test_minify_preserves_global_names_without_breaking_shadowed_locals(tmp_path):
    cleaned, modules = minify(
        py(
            """
            x = 1

            def f():
                x = 2
                return x

            print(f(), x)
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "2 1\n"
    assert modules == ["main"]


def test_minify_keeps_local_aliases_in_function_scope(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def f():
                parsed, src = (1, 2)
                return parsed + src

            print(f())
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "3\n"
    assert modules == ["main"]


def test_minify_keeps_generated_aliases_valid_around_decorators(tmp_path):
    cleaned, modules = minify(
        py(
            """
            import functools

            def deco(fn):
                @functools.wraps(fn)
                def wrapped():
                    return functools.partial(fn)()

                return wrapped

            @deco
            def f():
                return 1

            print(f())
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n"
    assert modules == ["main"]


def test_minify_keeps_comprehension_bindings_in_scope(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def pairs(values):
                return [(key, index) for index, key in enumerate(values)]

            print(pairs(["a", "b"]))
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "[('a', 0), ('b', 1)]\n"
    assert modules == ["main"]


def test_minify_preserves_dunder_method_names(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class Token(str):
                def __new__(cls, text="", position=None):
                    self = str.__new__(cls, text)
                    self.position = position
                    return self

            print(Token("x", position=1).position)
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n"
    assert modules == ["main"]


def test_minify_rewrites_public_class_references_in_attribute_targets(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class Token(str):
                pass

            Token.Empty = Token("")
            print(isinstance(Token.Empty, Token))
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "True\n"
    assert modules == ["main"]


def test_minify_preserves_decorated_method_names(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class C:
                @property
                def value(self):
                    return self._value

                @value.setter
                def value(self, new_value):
                    self._value = new_value

            c = C()
            c.value = 2
            print(c.value)
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "2\n"
    assert modules == ["main"]


def test_minify_rewrites_known_class_method_calls(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class Token:
                def very_long_method_name(self):
                    return 1

                def call(self):
                    return self.very_long_method_name()

            print(Token().call(), Token().very_long_method_name())
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    assert "self.very_long_method_name(" not in cleaned[0]

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1 1\n"
    assert modules == ["main"]


def test_minify_skips_unprofitable_public_class_and_method_aliases(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class Foo(object):
                def __init__(self, *args):
                    pass

                def demiurgic_mystificator(self, dactyl):
                    return dactyl

                def test(self, whatever):
                    print(whatever)

            if __name__ == "__main__":
                f = Foo("epicaricacy", "perseverate")
                f.test("Codswallop")
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    assert "Foo=" not in cleaned[0]
    assert "__qualname__" not in cleaned[0]
    assert "demiurgic_mystificator=" not in cleaned[0]
    assert "test=" not in cleaned[0]

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Codswallop\n"
    assert modules == ["main"]


def test_minify_preserves_class_attribute_names(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class Token:
                token_begin = 1
                token_end = token_begin

            print(Token.token_begin, Token.token_end)
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1 1\n"
    assert modules == ["main"]


def test_minify_preserves_top_level_class_names_in_library_mode(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class Token:
                pass

            print(Token.__name__)
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Token\n"
    assert modules == ["main"]


def test_minify_keeps_reassigned_locals_on_one_name(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def wrap():
                iterator = 1
                iterator = iterator + 1
                return iterator

            print(wrap())
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "2\n"
    assert modules == ["main"]


def test_minify_keeps_loop_bindings_consistent(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def collect(values):
                total = []
                for value in values:
                    total.append(value)
                return total

            print(collect([1, 2]))
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "[1, 2]\n"
    assert modules == ["main"]


def test_minify_does_not_rename_attribute_method_calls(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def f():
                items = [1, 2]
                return items.index(2)

            print(f())
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n"
    assert modules == ["main"]


def test_minify_preserves_parameters_inside_comprehensions(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class TexArgs(list):
                def __contains__(self, item):
                    return any([item == arg for arg in self])

            args = TexArgs(["x"])
            print("x" in args)
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "True\n"
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

    assert_cross_file_imports_are_rewritten(*cleaned, modules)
    assert modules != ["main", "side"]


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


def test_minify_renames_profitable_public_globals_with_aliases(tmp_path):
    cleaned, modules = minify(
        [
            py(
                """
                very_long_public_name = 7
                print(very_long_public_name + very_long_public_name + very_long_public_name)
                """
            ),
            py(
                """
                from main import very_long_public_name

                print(very_long_public_name)
                """
            ),
        ],
        ["main", "side"],
        keep_module_names=True,
        keep_global_variables=True,
    )

    main_tree = ast.parse(cleaned[0])
    consumer_tree = ast.parse(cleaned[1])

    assignment = main_tree.body[0]
    alias = main_tree.body[-1]
    assert isinstance(assignment, ast.Assign)
    assert assignment.targets[0].id != "very_long_public_name"
    assert isinstance(alias, ast.Assign)
    assert alias.targets[0].id == "very_long_public_name"
    assert alias.value.id == assignment.targets[0].id

    importer = consumer_tree.body[0]
    assert isinstance(importer, ast.ImportFrom)
    assert importer.module == "main"
    assert importer.names[0].name == assignment.targets[0].id

    main_path = tmp_path / "main.py"
    side_path = tmp_path / "side.py"
    main_path.write_text(cleaned[0], encoding="utf-8")
    side_path.write_text(cleaned[1], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(side_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "21\n7\n"
    assert modules == ["main", "side"]


def test_minify_can_rename_method_receivers_when_requested(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class Token:
                def __init__(self, data):
                    self.data = data

                def value(self):
                    return self.data

            print(Token(1).value())
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
        rename_arguments=True,
    )

    tree = ast.parse(cleaned[0])
    method_args = [
        node.args.args[0].arg
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"__init__", "value"}
    ]
    assert all(name != "self" for name in method_args)
    assert "self." not in cleaned[0]

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n"
    assert modules == ["main"]


def test_minify_rewrites_internal_keyword_calls_when_renaming_arguments(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def add(left, right):
                return left + right

            class Token:
                def scale(self, factor, bias):
                    return factor + bias

                def call(self):
                    return self.scale(factor=3, bias=4)

            print(add(left=1, right=2))
            print(Token().call())
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
        rename_arguments=True,
    )

    assert "left=" not in cleaned[0]
    assert "right=" not in cleaned[0]
    assert "factor=" not in cleaned[0]
    assert "bias=" not in cleaned[0]

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "3\n7\n"
    assert modules == ["main"]


def test_minify_reuses_short_argument_names_per_function_scope(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def left(alpha):
                return alpha + 1

            def right(beta):
                return beta + 2

            print(left(1), right(2))
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
        rename_arguments=True,
    )

    tree = ast.parse(cleaned[0])
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    arg_names = [function.args.args[0].arg for function in functions]

    assert len(set(arg_names)) == 1
    assert len(arg_names[0]) == 1

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "2 4\n"
    assert modules == ["main"]


def test_minify_keeps_recursive_functions_callable_when_reusing_local_names(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def recur(value):
                if value <= 0:
                    return 0
                return recur(value - 1)

            print(recur(3))
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
        rename_arguments=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "0\n"
    assert modules == ["main"]


def test_minify_keeps_unrenamed_parameter_assignments_stable(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def choose(x, flag):
                if flag:
                    x = 2
                return x

            print(choose(1, False))
            print(choose(1, True))
            """
        ),
        "main",
        rename_arguments=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n2\n"
    assert modules == ["main"]


def test_minify_rewrites_renamed_methods_on_local_instances(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class Demo:
                def test(self):
                    return 1

            instance = Demo()
            print(instance.test())
            """
        ),
        "main",
        rename_arguments=True,
        keep_module_names=True,
    )

    assert ".test(" not in cleaned[0]

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n"
    assert modules == ["main"]


def test_minify_rewrites_constructor_method_keywords_when_renaming_arguments(tmp_path):
    cleaned, modules = minify(
        py(
            """
            class Demo:
                def scale(self, long_value):
                    return long_value

            print(Demo().scale(long_value=1))
            """
        ),
        "main",
        rename_arguments=True,
        keep_module_names=True,
    )

    assert "long_value=" not in cleaned[0]

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n"
    assert modules == ["main"]


def test_minify_keeps_import_alias_argument_metadata(tmp_path):
    cleaned, modules = minify(
        [
            py(
                """
                def square(long_value):
                    return long_value * long_value
                """
            ),
            py(
                """
                from main import square as g

                print(g(long_value=3))
                """
            ),
        ],
        ["main", "side"],
        keep_module_names=True,
        rename_arguments=True,
    )

    assert "long_value=" not in cleaned[1]

    main_path = tmp_path / "main.py"
    side_path = tmp_path / "side.py"
    main_path.write_text(cleaned[0], encoding="utf-8")
    side_path.write_text(cleaned[1], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(side_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "9\n"
    assert modules == ["main", "side"]


def test_minify_rewrites_imported_class_alias_keywords_and_members(tmp_path):
    cleaned, modules = minify(
        [
            py(
                """
                class Time:
                    def __init__(self, hour=None):
                        self.hour = hour

                    Meridiem = type("Meridiem", (), {"PM": 1})
                """
            ),
            py(
                """
                from main import Time as tfhTime

                print(tfhTime(hour=1).hour, tfhTime.Meridiem.PM)
                """
            ),
        ],
        ["main", "side"],
        keep_module_names=True,
        rename_arguments=True,
    )

    assert "hour=" not in cleaned[1]
    assert "Meridiem" not in cleaned[1]

    main_path = tmp_path / "main.py"
    side_path = tmp_path / "side.py"
    main_path.write_text(cleaned[0], encoding="utf-8")
    side_path.write_text(cleaned[1], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(side_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1 1\n"
    assert modules == ["main", "side"]


def test_minify_fuses_files_into_single_module(tmp_path):
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

    bundle_path = tmp_path / "bundle.py"
    bundle_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(bundle_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "9\n"
    assert modules == ["bundle"]


def test_minify_bundle_runs_entry_module_as_main(tmp_path):
    cleaned, modules = minify(
        py(
            """
            if __name__ == "__main__":
                print("ran")
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
        output_single_file=True,
    )

    bundle_path = tmp_path / "bundle.py"
    bundle_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(bundle_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "ran\n"
    assert modules == ["bundle"]


def test_minify_keeps_nonlocal_bindings_in_sync_with_local_renames(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def outer():
                hash_value = 1

                def inner():
                    nonlocal hash_value
                    return hash_value

                return inner()

            print(outer())
            """
        ),
        "main",
        keep_global_variables=False,
        keep_module_names=True,
        rename_arguments=True,
    )

    tree = ast.parse(cleaned[0])
    outer = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    binding = next(
        node.targets[0].id
        for node in outer.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    )
    inner = next(node for node in outer.body if isinstance(node, ast.FunctionDef))
    nonlocal_stmt = next(node for node in inner.body if isinstance(node, ast.Nonlocal))

    assert nonlocal_stmt.names == [binding]

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n"
    assert modules == ["main"]


def test_minify_keeps_future_imports_before_hoisted_helpers(tmp_path):
    cleaned, modules = minify(
        py(
            '''
            """module docs"""
            from __future__ import annotations

            left = "PhysicalResourceId"
            right = "PhysicalResourceId"

            print(left, right)
            '''
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    tree = ast.parse(cleaned[0])
    assert isinstance(tree.body[0], ast.ImportFrom)
    assert tree.body[0].module == "__future__"

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "PhysicalResourceId PhysicalResourceId\n"
    assert modules == ["main"]


def test_minify_preserves_fstring_braces_during_whitespace_removal(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def build(widths):
                return "  ".join((f"{{{x}:<{w}}}" for x, w in enumerate(widths)))

            print(build([1, 2]))
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
        rename_arguments=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "{0:<1}  {1:<2}\n"
    assert modules == ["main"]


def test_minify_keeps_global_declarations_distinct_from_renamed_parameters(tmp_path):
    cleaned, modules = minify(
        py(
            """
            state = True

            def set_state(run):
                global state
                state = run

            set_state(False)
            print(state)
            """
        ),
        "main",
        keep_global_variables=False,
        keep_module_names=True,
        rename_arguments=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "False\n"
    assert modules == ["main"]


def test_minify_keeps_nonlocal_declarations_distinct_from_renamed_parameters(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def outer():
                prog_name = "demo"
                version = "1.0"

                def callback(ctx, param, value):
                    nonlocal prog_name, version
                    return prog_name, version, ctx, param, value

                return callback(1, 2, 3)

            print(outer())
            """
        ),
        "main",
        keep_global_variables=False,
        keep_module_names=True,
        rename_arguments=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "('demo', '1.0', 1, 2, 3)\n"
    assert modules == ["main"]


def test_minify_preserves_placeholder_bodies_after_docstring_removal(tmp_path):
    cleaned, modules = minify(
        py(
            '''
            class Placeholder:
                def close(self):
                    """placeholder"""
                    ...

            print(Placeholder().close())
            '''
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "None\n"
    assert modules == ["main"]


def test_minify_preserves_match_case_spacing(tmp_path):
    cleaned, modules = minify(
        py(
            """
            def classify(state):
                match state:
                    case "remove":
                        return 0
                    case "normal":
                        return 1
                    case _:
                        return 2

            print(classify("normal"))
            """
        ),
        "main",
        keep_global_variables=True,
        keep_module_names=True,
    )

    module_path = tmp_path / "module.py"
    module_path.write_text(cleaned[0], encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1\n"
    assert modules == ["main"]
