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


def shorten_imports(tree, variable_name_generator=variable_name_generator()):
    """Shorten imported library names.
    
    >>> apply = lambda code: ast.unparse(shorten_imports(ast.parse(code))[0])
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
    mapping = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                old = alias.asname or alias.name
                mapping[old] = alias.asname = next(variable_name_generator)
    rename_variables(tree, mapping)
    return tree, mapping


def rename_variables(tree, mapping):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in mapping:
                node.id = mapping[node.id]
    return mapping


def main():
    with open('tests/test.py') as f:
        tree = ast.parse(f.read())

    generator = variable_name_generator()
    shorten_imports(tree, generator)

    print(ast.unparse(tree))


if __name__ == '__main__':
    main()