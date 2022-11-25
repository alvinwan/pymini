import ast
import keyword
from typing import Dict, List


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


class VariableNameCollector(ast.NodeVisitor):
    """Collects all variable names in scope."""
    def __init__(self):
        self.names = set()

    def visit_Name(self, node):
        self.names.add(node.id)


class VariableShortener(ast.NodeTransformer):
    """Renames variables according to provided mapping."""
    def __init__(self, generator=variable_name_generator(), mapping=None):
        self.mapping = mapping or {}
        self.generator = generator

    def _visit_ImportOrImportFrom(self, node):
        """Shorten imported library names.
    
        >>> g = variable_name_generator()
        >>> apply = lambda src: ast.unparse(ImportShortener(g).visit(ast.parse(src)))
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
        for alias in node.names:
            old = alias.asname or alias.name
            self.mapping[old] = alias.asname = next(self.generator)
        return self.generic_visit(node)

    visit_Import = _visit_ImportOrImportFrom
    visit_ImportFrom = _visit_ImportOrImportFrom

    def visit_ClassDef(self, node):
        """Shorten class names.
    
        >>> shortener = ClassOrFunctionShortener(variable_name_generator())
        >>> apply = lambda src: ast.unparse(shortener.visit(ast.parse(src)))
        >>> apply('class Demiurgic: pass\\nx = Demiurgic()')
        'class a:\\n    pass\\nx = a()'
        """
        self.mapping[node.name] = node.name = next(self.generator)
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """Shorten function and argument names.
    
        >>> shortener = ClassOrFunctionShortener(variable_name_generator())
        >>> apply = lambda src: ast.unparse(shortener.visit(ast.parse(src)))
        >>> apply('def demiurgic(): pass\\nx = demiurgic()')
        'def b():\\n    pass\\nx = b()'
        """
        for arg in node.args.args + [node.args.vararg, node.args.kwarg]:
            if arg is not None:
                self.mapping[arg.arg] = arg.arg = next(self.generator)
        self.mapping[node.name] = node.name = next(self.generator)
        return self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef
    
    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in self.mapping:
                node.func.attr = self.mapping[node.func.attr]
        else:
            if node.func.id in self.mapping:
                node.func.id = self.mapping[node.func.id]
        return self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in self.mapping:
            node.id = self.mapping[node.id]
        return self.generic_visit(node)


class WhitespaceRemover(ast.NodeTransformer):
    """Remove all whitespace.

    Performs the following whitespace removals:
    - removes blank lines
    - removes trailing whitespace
    - create 1-liners
    - use 1-space indentation
    - merge 1-liners with previous line where possible
    - remove extra whitespace around characters
    
    >>> apply = lambda src: WhitespaceRemover().handle(src)
    >>> apply('''
    ... 
    ... x = 7   
    ... ''')  # drop all blank lines + remove trailing whitespace
    'x=7'
    >>> apply('''
    ... 
    ... def square(x):
    ...     x += 1
    ...     return x ** 2
    ... ''')  # combines lines + merges with def line
    'def square(x):x+=1;return x**2'
    """
    def handle(self, source: str):
        # remove blank lines
        source = '\n'.join(filter(bool, source.splitlines()))

        # remove trailing whitespace
        source = '\n'.join(line.rstrip() for line in source.splitlines())

        # segment file by indentation
        segments = self.segments_from_source(source)

        # reduce indentation to one space
        segments = self.reduce_indentation(segments)

        # make into one-liners where possible
        segments = self.make_one_liners(segments)

        # merge one-liners with predicates
        segments = self.merge_one_liners(segments)

        # regenerate source, where indents use only 1 space
        source = '\n'.join(
            '\n'.join([' ' * segment['indents'] + line for line in segment['lines']])
            for segment in segments
        )

        # remove extraneous whitespace
        source = self.remove_extraneous_whitespace(source)
        
        return source

    def segments_from_source(self, source: str) -> List[Dict]:
        """Segment provided source code by indentation level.

        >>> WhitespaceRemover().segments_from_source('''
        ... def square(x):
        ...     return x ** 2
        ... ''')
        [{'indents': 0, 'lines': ['', 'def square(x):']}, {'indents': 4, 'lines': ['return x ** 2']}]
        """
        segments = []
        segment = None
        for line in source.splitlines():
            indents = len(line) - len(line.lstrip())
            line = line.lstrip()
            if segment is None:
                segment = {'indents': indents, 'lines': [line]}
            elif indents != segment['indents']:
                segments.append(segment)
                segment = {'indents': indents, 'lines': [line]}
            else:
                segment['lines'].append(line)
        if segment:
            segments.append(segment)
        return segments

    def reduce_indentation(self, segments: List) -> List:
        """Reduce indentation to 1 space.
        
        >>> def apply(src):
        ...     remover = WhitespaceRemover()
        ...     segments = remover.segments_from_source(src)
        ...     segments = remover.reduce_indentation(segments)
        ...     return remover.source_from_segments(segments)
        ...
        >>> print(apply('''def square(x):
        ...     return x ** 2'''))
        def square(x):
         return x ** 2
        >>> print(apply('''for i in range(10):
        ...     if x == 5:
        ...         print(x)
        ...     if x == 6:
        ...       print(x)'''))
        for i in range(10):
         if x == 5:
          print(x)
         if x == 6:
          print(x)
        """
        def update_valley(valley, indents):
            new_to_old = list(sorted(indents))
            for segment in valley:
                segment['indents'] = new_to_old.index(segment['indents'])

        indents = set()
        valley = []
        for segment in segments:
            if segment['indents'] in indents: # we've gone back up a level
                update_valley(valley, indents)
                valley = [segment]
                if segment['indents'] != max(indents):
                    indents.remove(max(indents))
                continue
            valley.append(segment)
            indents.add(segment['indents'])
        update_valley(valley, indents)
        return segments

    def make_one_liners(self, segments: List) -> List:
        """Make one-liners from no-colon segments."""
        for segment in segments:
            if not any(line.strip().endswith(':') for line in segment['lines']):
                segment['lines'] = [';'.join(segment['lines'])]
        return segments

    def merge_one_liners(self, segments: List) -> List:
        """Merge one-liners with previous segment, if the previous ends in a colon.
        
        >>> def apply(src):
        ...     remover = WhitespaceRemover()
        ...     segments = remover.segments_from_source(src)
        ...     segments = remover.merge_one_liners(segments)
        ...     return remover.source_from_segments(segments)
        ...
        >>> print(apply('''def square(x):
        ...     return x ** 2'''))
        def square(x):return x ** 2
        >>> print(apply('''for i in range(10):
        ...     if x == 5:
        ...         print(x)
        ...     if x == 6:
        ...       print(x)'''))
        for i in range(10):
            if x == 5:print(x)
            if x == 6:print(x)
        """
        new_segments = []
        i = 0
        while i < len(segments):
            if segments[i]['lines'][-1].strip().endswith(':') and len(segments[i+1]['lines']) == 1 and not segments[i+1]['lines'][0].endswith(':'):
                segments[i]['lines'][-1] = segments[i]['lines'][-1] + segments[i+1]['lines'][0]
                new_segments.append(segments[i])
                i += 1
            else:
                new_segments.append(segments[i])
            i += 1
        return new_segments

    def source_from_segments(self, segments: List) -> str:
        return '\n'.join(
            '\n'.join([' ' * segment['indents'] + line for line in segment['lines']])
            for segment in segments
        )

    def remove_extraneous_whitespace(self, source: str) -> str:
        """Remove all unneeded whitespace.
        
        >>> remover = WhitespaceRemover()
        >>> remover.remove_extraneous_whitespace('''def square( x ) : return x ** 2''')
        'def square(x):return x**2'
        >>> remover.remove_extraneous_whitespace('''try : import os''')
        'try:import os'
        """
        import tokenize
        from io import StringIO
        lines = []
        for line in source.splitlines():
            tokens = []
            last_token = None
            for token in tokenize.generate_tokens(StringIO(line).readline):
                token = token.string
                if token in keyword.kwlist and tokens and last_token not in ':;':
                    tokens.append(token)
                elif tokens and (last_token not in keyword.kwlist or token in ':;'):
                    tokens[-1] += token
                else:
                    tokens.append(token)
                last_token = token
            lines.append(' '.join(tokens))
        return '\n'.join(lines)


def main():
    with open('tests/test.py') as f:
        tree = ast.parse(f.read())

    # minify
    ParentSetter().visit(tree)
    CommentRemover().visit(tree)

    # obfuscate
    collector = VariableNameCollector()
    collector.visit(tree)
    generator = variable_name_generator(collector.names)
    VariableShortener(generator).visit(tree)

    string = ast.unparse(tree)
    string = WhitespaceRemover().handle(string)

    with open('tests/ours.py', 'w') as f:
        f.write(string)


if __name__ == '__main__':
    main()