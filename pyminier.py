import ast
from typing import List


def number_to_digits(n: int, base: int = 10) -> List[int]:
    """Convert a number to a list of digits.
    
    >>> number_to_digits(0)
    [0]
    >>> number_to_digits(1)
    [1]
    >>> number_to_digits(10)
    [1, 0]
    >>> number_to_digits(100)
    [1, 0, 0]
    >>> number_to_digits(257, 16)
    [1, 0, 1]
    """
    digits = [0] if n == 0 else []
    while n > 0:
        digits.append(n % base)
        n //= base
    return digits[::-1]


def variable_name_generator(used: set[str] = []):
    """Generate variable name not currently used in scope.
    
    >>> generator = variable_name_generator()
    >>> next(generator)
    'a'
    >>> for i in range(25):
    ...     _ = next(generator)
    ... 
    >>> next(generator)
    'A'
    >>> for i in range(25):
    ...     _ = next(generator)
    ... 
    >>> next(generator)
    'aa'
    """
    cur = 0
    while True:
        name = ''
        for i, digit in enumerate(number_to_digits(cur, base=52)[::-1]):
            base = 'a' if digit < 26 else 'A'
            name = chr(ord(base) + ((digit % 26) - (i > 0))) + name  # for 1st digit, a = 0. for subsequent, a = 1
        if name not in used:
            yield name
        cur += 1


class ParentSetter(ast.NodeTransformer):
    """Adds parent attribute to each node."""
    def visit(self, node):
        for child in ast.iter_child_nodes(node):
            child.parent = node
        return super().visit(node)


class CommentRemover(ast.NodeTransformer):
    """Drop all comments, both single-line and docstrings.
    
    >>> def apply(code):
    ...     tree = ast.parse(code)
    ...     tree = ParentSetter().visit(tree)
    ...     tree = CommentRemover().visit(tree)
    ...     return ast.unparse(tree)
    ...
    >>> apply('1 + 1  # comment')
    '1 + 1'
    >>> print(apply('''
    ... def square(x):
    ...     \\'\\'\\'Return the square of x.\\'\\'\\'
    ...     return x ** 2
    ... '''))
    def square(x):
        return x ** 2
    >>> print(apply('''
    ... def square(x):
    ...     \\'\\'\\'Return the square of x.\\'\\'\\'
    ... '''))
    def square(x):
        0
    """
    def visit_Expr(self, node):
        if isinstance(node.value, ast.Constant):
            if len(node.parent.body) == 1:  # if body is just the comment
                return ast.parse('0').body[0]  # replace comment with 0
            return None  # otherwise, remove comment
        return node


class VariableRenamer(ast.NodeTransformer):
    """Renames variables according to provided mapping."""
    def __init__(self, mapping=None):
        self.mapping = mapping or {}

    def visit_Name(self, node):
        if node.id in self.mapping:
            node.id = self.mapping[node.id]
        return node


class ImportShortener(VariableRenamer):
    """Shorten imported library names.
    
    >>> apply = lambda code: ast.unparse(ImportShortener().visit(ast.parse(code)))
    >>> apply('import demiurgic')
    'import demiurgic as a'
    >>> apply('from demiurgic import palpitation')
    'from demiurgic import palpitation as b'
    >>> print(apply('import demiurgic;demiurgic.palpitation()'))
    import demiurgic as c
    c.palpitation()
    >>> print(apply('import demiurgic as dei;dei.palpitation()'))
    import demiurgic as d
    d.palpitation()
    """
    def __init__(self, generator=variable_name_generator()):
        super().__init__()
        self.generator = generator

    def _visit_ImportOrImportFrom(self, node):
        for alias in node.names:
            old = alias.asname or alias.name
            self.mapping[old] = alias.asname = next(self.generator)
        return node

    visit_Import = _visit_ImportOrImportFrom
    visit_ImportFrom = _visit_ImportOrImportFrom


def main():
    with open('tests/test.py') as f:
        tree = ast.parse(f.read())

    # minify
    ParentSetter().visit(tree)
    CommentRemover().visit(tree)

    # obfuscate
    ImportShortener().visit(tree)

    with open('tests/ours.py', 'w') as f:
        f.write(ast.unparse(tree))


if __name__ == '__main__':
    main()