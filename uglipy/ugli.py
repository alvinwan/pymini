import ast
import keyword
from typing import Dict, List, Set
from .utils import variable_name_generator


class Transformer:
    def transform(self, *trees):
        for tree in trees:
            self.visit(tree)
        return trees


class NodeTransformer(Transformer, ast.NodeTransformer):
    pass


class NodeVisitor(Transformer, ast.NodeVisitor):
    pass


class Pipeline:

    def __init__(self, *transformers):
        self.transformers = transformers

    def transform(self, *trees):
        for transformer in self.transformers:
            trees = transformer.transform(*trees)
        return trees


class ReturnSimplifier(NodeTransformer):
    """Simplify return statements in the following form:
    
        x = (some code)
        return x
        
    to
    
        return (some code)

    NOTE: unused_names must be modified in-place, since the set is passed to
    RemoveUnusedVariables at initialization. Can't return a new set.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name_to_node = {}
        self.unused_names = set()

    def visit_Assign(self, node: ast.Assign) -> ast.Assign:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            self.name_to_node[node.targets[0].id] = node
        return self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> ast.Return:
        if isinstance(node.value, ast.Name):
            self.unused_names.add(node.value.id)
            node = self.name_to_node[node.value.id]
            return ast.Return(value=node.value)
        return self.generic_visit(node)


class RemoveUnusedVariables(NodeTransformer):
    """Remove all unused variables.
    
    NOTE: cannot store a copy of unused_names, as this set is modified in-place
    after initialization.
    """
    def __init__(self, unused_names: Set[str]):
        super().__init__()
        self.unused_names = unused_names

    def visit_Assign(self, node: ast.Name) -> ast.Name:
        if isinstance(node.targets[0], ast.Name) and node.targets[0].id in self.unused_names:
            return None
        return self.generic_visit(node)


class VariableNameCollector(NodeVisitor):
    """Collects all variable names in scope."""
    def __init__(self):
        self.names = set()

    def visit_Name(self, node):
        self.names.add(node.id)


class ParentSetter(NodeTransformer):
    """Adds parent attribute to each node.
    
    >>> def apply(src):
    ...     tree = ast.parse(src)
    ...     ParentSetter().visit(tree)
    ...     return tree
    ...
    >>> tree = apply("lorem = 'demiurgic'\\nipsum = 'demiurgic'")
    >>> isinstance(tree.body[0].parent, ast.Module)
    True
    >>> isinstance(tree.body[0].value.parent, ast.Assign)
    True
    """
    def visit(self, node):
        for child in ast.iter_child_nodes(node):
            child.parent = node
            self.visit(child)
        return super().visit(node)


class CommentRemover(NodeTransformer):
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


class VariableShortener(NodeTransformer):
    """Renames variables according to provided mapping.
    
    >>> shortener = VariableShortener(variable_name_generator(), mapping={'donotrename': 'donotrename'})
    >>> apply = lambda src: ast.unparse(shortener.visit(ast.parse(src)))
    >>> print(apply('mamamia = 1; donotrename = 2;'))
    a = 1
    donotrename = 2
    """
    def __init__(self, generator, mapping=None, modules=(), keep_global_variables=False):
        self.mapping = mapping or {}
        self.generator = generator
        self.name_to_node = {}
        self.nodes_to_insert = []
        # TODO: cleanup
        self.str_name_to_node = {}
        self.str_mapping = {}
        self.modules = modules # dont alias variables imported from these modules
        self.keep_global_variables = keep_global_variables

    def _is_node_global(self, node):
        """Check if a node is global."""
        return (
            not hasattr(node, 'parent') or isinstance(node.parent, ast.Module)
        )

    def _visit_ImportOrImportFrom(self, node):
        """Shorten imported library names.
    
        >>> shortener = VariableShortener(variable_name_generator(), modules=('donotaliasme',))
        >>> apply = lambda src: ast.unparse(shortener.visit(ast.parse(src)))
        >>> apply('import demiurgic')
        'import demiurgic as a'
        >>> apply('from demiurgic import palpitation')
        'from demiurgic import palpitation as b'
        >>> apply('from demiurgic import a')  # single-letter import should be left alone
        'from demiurgic import a'
        >>> print(apply('import demiurgic;demiurgic.palpitation()'))  # TODO: bug - variable should remember object its bound to
        import demiurgic as c
        c.b()
        >>> print(apply('import demiurgic as dei;dei.palpitation()'))
        import demiurgic as d
        d.b()
        >>> print(apply('import demiurgic;import donotaliasme;from donotaliasme import dolor;'))
        import demiurgic as e
        import donotaliasme
        from donotaliasme import dolor
        """
        if isinstance(node, ast.Import) or node.module not in self.modules:
            for alias in node.names:
                if isinstance(node, ast.ImportFrom) or alias.name not in self.modules:
                    old = alias.asname or alias.name
                    if len(old) > 1:
                        self.mapping[old] = alias.asname = next(self.generator)
        return self.generic_visit(node)

    visit_Import = _visit_ImportOrImportFrom
    visit_ImportFrom = _visit_ImportOrImportFrom

    def visit_ClassDef(self, node):
        """Shorten class names.
    
        >>> shortener = VariableShortener(variable_name_generator())
        >>> apply = lambda src: ast.unparse(shortener.visit(ast.parse(src)))
        >>> apply('class Demiurgic: pass\\nholy = Demiurgic()')
        'class a:\\n    pass\\nb = a()'
        >>> shortener = VariableShortener(variable_name_generator(), keep_global_variables=True)
        >>> apply('class Demiurgic: pass\\nholy = Demiurgic()')
        'class Demiurgic:\\n    pass\\nholy = Demiurgic()'
        """
        if node.name not in self.mapping.values() and not (  # TODO: make .values() more efficient 
            self.keep_global_variables and self._is_node_global(node)
        ):  # TODO: rename but insert var def if worth it
            self.mapping[node.name] = node.name = next(self.generator)
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """Shorten function and argument names.
    
        >>> shortener = VariableShortener(variable_name_generator())
        >>> apply = lambda src: ast.unparse(shortener.visit(ast.parse(src)))
        >>> apply('def demiurgic(palpitation): return palpitation\\nholy = demiurgic()')
        'def b(a):\\n    return a\\nc = b()'
        >>> shortener = VariableShortener(variable_name_generator(), keep_global_variables=True)
        >>> apply('def demiurgic(palpitation): return palpitation\\nholy = demiurgic()')
        'def demiurgic(a):\\n    return a\\nholy = demiurgic()'
        """
        for arg in node.args.args + [node.args.vararg, node.args.kwarg]:
            if arg is not None and arg.arg not in self.mapping.values():  # TODO: make .values() more efficient
                self.mapping[arg.arg] = arg.arg = next(self.generator)
        if self.keep_global_variables and self._is_node_global(node):  # TODO: rename but insert var def if worth it
            return self.generic_visit(node)
        if node.name not in self.mapping.values():  # TODO: need to dedup this logic
            self.mapping[node.name] = node.name = next(self.generator)
        return self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node):
        """Shorten newly-defined variable names.
        
        >>> shortener = VariableShortener(variable_name_generator())
        >>> apply = lambda src: ast.unparse(shortener.visit(ast.parse(src)))
        >>> apply('demiurgic = 1\\nholy = demiurgic')
        'a = 1\\nb = a'
        >>> shortener = VariableShortener(variable_name_generator(), keep_global_variables=True)
        >>> apply('demiurgic = 1\\nholy = demiurgic')
        'demiurgic = 1\\nholy = demiurgic'
        """
        if self.keep_global_variables and self._is_node_global(node):  # TODO: rename but insert var def if worth it
            return self.generic_visit(node)
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id not in self.mapping.values():  # TODO: make .values() more efficient
                self.mapping[target.id] = target.id = next(self.generator)
        return self.generic_visit(node)

    def visit_Call(self, node):
        """Apply renamed function names."""
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in self.mapping:
                node.func.attr = self.mapping[node.func.attr]
        else:
            if node.func.id in self.mapping:
                node.func.id = self.mapping[node.func.id]
        return self.generic_visit(node)

    def visit_Name(self, node):
        """Apply renamed variables.
        
        Additionally, if any variable is used more than once *and the variable
        length is greater than 1, shorten it.

        >>> shortener = VariableShortener(variable_name_generator())
        >>> apply = lambda src: ast.unparse(shortener.visit(ast.parse(src)))
        >>> apply('print(demiurgic)')
        'print(demiurgic)'
        >>> apply('demiurgic = 1\\nholy = demiurgic\\necho(demiurgic)')
        'a = 1\\nb = a\\necho(a)'
        >>> apply('print(demiurgic, demiurgic)')  # now print has been seen 2x
        'c(a, a)'
        >>> shortener = VariableShortener(variable_name_generator(), keep_global_variables=True)
        >>> apply('print(demiurgic)')
        'print(demiurgic)'
        >>> apply('print(demiurgic)')  # saw 'print' 2x but didn't replace
        'print(demiurgic)'
        """
        if node.id in self.mapping.values():  # TODO: make .values() more efficient
            return node
        if node.id in self.mapping:
            node.id = self.mapping[node.id]
        elif self.keep_global_variables and self._is_node_global(node):  # TODO: rename but insert var def if worth it  # TODO: this optimization should only apply to var def
            return self.generic_visit(node)
        elif node.id in self.name_to_node:
            self.mapping[node.id] = new_variable_name = next(self.generator)
            self.nodes_to_insert.append(ast.parse(f'{new_variable_name} = {node.id}').body[0])
            self.name_to_node.pop(node.id).id = node.id = new_variable_name
        elif len(node.id) > 1:  # if original variable name more than 1 char
            self.name_to_node[node.id] = node
        return self.generic_visit(node)

    def visit_Constant(self, node):
        """Shorten string literals that are repeated.
        
        >>> shortener = VariableShortener(variable_name_generator())
        >>> def apply(src):
        ...     tree = ast.parse(src)
        ...     ParentSetter().visit(tree)
        ...     shortener.visit(tree)
        ...     return ast.unparse(tree)
        ...
        >>> apply("lorem = 'demiurgic'\\nipsum = 'demiurgic'")
        'a = c\\nb = c'
        >>> apply("dolor = 'demiurgic'")
        'd = c'
        >>> apply("cached['demiurgic'] = 'palpitation'")
        "cached[c] = 'palpitation'"
        >>> apply("demiurgic = 'demiurgic'")
        'e = c'
        >>> print(apply("if 'demiurgic' in lorem: print(lorem)"))
        if c in a:
            print(a)
        """
        if not isinstance(node.s, str):  # TODO: generic for all constants?
            return node
        # TODO: this is a copy of visit_Name, basically
        if node.s in self.str_mapping.values():  # TODO: make more efficient
            return node
        if node.s in self.str_mapping:
            node = ast.parse(self.str_mapping[node.s]).body[0].value
        elif node.s in self.str_name_to_node:
            old_s = node.s
            self.str_mapping[node.s] = new_variable_name = next(self.generator)
            self.nodes_to_insert.append(ast.parse(f"{new_variable_name} = '{node.s}'").body[0])
            old_node = self.str_name_to_node[node.s]
            # TODO: instead of writing all these cases, replace in a second pass?
            if hasattr(old_node, 'parent'):
                if isinstance(old_node.parent, ast.Assign):
                    old_node.parent.value = ast.parse(self.str_mapping[node.s]).body[0].value
                if isinstance(old_node.parent, ast.Subscript):
                    old_node.parent.slice = ast.parse(self.str_mapping[node.s]).body[0].value
            node = ast.parse(self.str_mapping[node.s]).body[0].value
            del self.str_name_to_node[old_s]
        else:
            self.str_name_to_node[node.s] = node
        return node


class IndependentVariableShorteners(Transformer):
    def __init__(self, names, modules, keep_global_variables=False):
        super().__init__()
        self.generator = variable_name_generator(names)
        self.module_to_shortener = {
            module: VariableShortener(
                self.generator,
                modules=modules,
                keep_global_variables=keep_global_variables
            ) for module in modules
        }
        self.modules = modules

    def transform(self, *trees):
        for module, tree in zip(self.modules, trees):
            self.module_to_shortener[module].transform(tree)
            define_custom_variables(tree, self.module_to_shortener[module].nodes_to_insert)
        return trees


class FusedVariableShortener(Transformer):
    """
    Fuse variable shortening across multiple files. Additionally and optionally 
    shortens filenames.
    
    >>> fused = FusedVariableShortener(variable_name_generator(), ('donotrenameme',), {}, keep_module_names=True)
    >>> _ = fused.transform(None)
    >>> fused.modules
    ('donotrenameme',)
    """
    def __init__(self, generator, modules, module_to_shortener, keep_module_names=False):
        super().__init__()
        self.generator = generator
        self.modules = modules
        self.module_to_shortener = module_to_shortener
        self.keep_module_names = keep_module_names

    def transform(self, *trees):
        if self.keep_module_names:
            return trees

        # shorten module names
        module_to_module = {module: next(self.generator) for module in self.modules}

        # NOTE: Must modify in-place, as this list is passed to Fuser
        for i, module in enumerate(self.modules):
            self.modules[i] = module_to_module[module]

        new_trees = []  # TODO: cleanup
        for tree, module in zip(trees, module_to_module):

            # rerun shortening on ea file based on imports from *other files
            fused_mapping = {}
            for _module, shortener in self.module_to_shortener.items():
                if _module != module:
                    fused_mapping.update(shortener.mapping)
                else:
                    # HACK: identity needed, so that we don't rename variables
                    # *again. TODO: figure out why single-char variables are
                    # being renamed
                    fused_mapping.update({v: v for v in shortener.mapping.values()})

            imported = ImportedVariableShortener(
                self.generator,
                mapping=fused_mapping,
                module_to_module={_module: value for _module, value in module_to_module.items() if module != _module},
                module_to_shortener={_module: value for _module, value in self.module_to_shortener.items() if module != _module},
            )
            new_trees.extend(imported.transform(tree))
        return new_trees


class ImportedVariableShortener(VariableShortener):
    """Use different module shorteners to adjust variables in this module
    
    >>> generator = variable_name_generator()
    >>> shortener = VariableShortener(generator)
    >>> ast.unparse(shortener.visit(ast.parse('demiurgic = 1\\nholy = demiurgic')))
    'a = 1\\nb = a'
    >>> fused = ImportedVariableShortener(generator, module_to_shortener={'silly': shortener})
    >>> apply = lambda src: ast.unparse(fused.visit(ast.parse(src)))
    >>> apply('from silly import demiurgic, dontreplaceme; print(demiurgic)')
    'from silly import a, dontreplaceme\\nprint(a)'
    """
    def __init__(self, *args, module_to_shortener={}, module_to_module={}, **kwargs):
        super().__init__(*args, **kwargs)
        self.module_to_shortener = module_to_shortener
        self.module_to_module = module_to_module

    def visit_ImportFrom(self, node):
        """Apply shortener for imported module."""
        shortener = self.module_to_shortener.get(node.module, None)
        if shortener is not None:
            for alias in node.names:
                if alias.name in shortener.mapping:
                    self.mapping[alias.name] = alias.name = shortener.mapping[alias.name]
            if node.module in self.module_to_module:  # TODO: handle nested modules
                node.module = self.module_to_module[node.module]
        return self.generic_visit(node)


class Fuser(Transformer):
    def __init__(self, modules):
        super().__init__()
        self.modules = modules

    def transform(self, *trees):
        return trees


class FileFuser(Fuser):
    """Fuse all files together.
    
    Determine dependency between files by checking import statements. After
    linearizing dependencies, combine files in that order.
    """
    def transform(self, *trees):
        # TODO: find imports and use them to determine file ordering
        for tree in trees[1:]:
            trees[0].body += tree.body
        return [trees[0]]


def define_custom_variables(tree, mapping):
    root = next(ast.walk(tree))
    for node in mapping:
        root.body.insert(0, ast.copy_location(node, root))
    ast.fix_missing_locations(tree)


class Unparser:

    def transform(self, *trees):
        for tree in trees:
            yield ast.unparse(tree)


class WhitespaceRemover(NodeTransformer):
    """Remove all whitespace.

    Performs the following whitespace removals:
    - removes blank lines
    - removes trailing whitespace
    - create 1-liners
    - use 1-space indentation
    - merge 1-liners with previous line where possible
    - remove extra whitespace around characters
    
    >>> apply = lambda src: WhitespaceRemover().visit(src)
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

    def transform(self, *sources: List[str]):
        for source in sources:
            yield self.visit(source)

    def visit(self, source: str):
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
            # combine any colon-less lines
            lines = []
            for line in segment['lines']:
                if line.strip().endswith(':'):
                    lines.append(line)
                elif lines:
                    lines[-1] += ';' + line
                else:
                    lines.append(line)
            segment['lines'] = lines
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
                if token in keyword.kwlist and tokens and not any(last_token.endswith(c) for c in ':;= '):
                    tokens.append(token)
                elif tokens and (last_token not in keyword.kwlist or token in ':;='):
                    tokens[-1] += token
                else:
                    tokens.append(token)
                last_token = token
            lines.append(' '.join(tokens))
        return '\n'.join(lines)


def uglipy(sources, modules='main', keep_module_names=False,
           keep_global_variables=False, output_single_file=False,):
    """Uglify source code. Simplify, minify, and obfuscate.

    >>> sources, modules = uglipy(['''a = 3
    ... def square(x):
    ...     return x ** 2
    ... ''', '''from main import square
    ... square(3)
    ... '''], ['main', 'side'])
    >>> modules
    ['e', 'f']
    >>> sources[0]
    'b=3\\ndef d(c):return c**2'
    >>> sources[1]
    'from e import d;d(3)'
    """
    if isinstance(sources, str):
        sources = [sources]
    if isinstance(modules, str):
        modules = [modules]

    assert len(sources) == len(modules)

    trees = [ast.parse(source) for source in sources]

    pipeline = Pipeline(

        # simplify
        simplifier := ReturnSimplifier(),
        RemoveUnusedVariables(simplifier.unused_names),

        # minify
        ParentSetter(),
        CommentRemover(),

        # obfuscate
        collector := VariableNameCollector(),  # gather all variables across files TODO: this is naive. could compress further by actually tracking only variables in the right scope, so we can use more 1-letter vars
        ind := IndependentVariableShorteners(
            names=collector.names,
            modules=modules,
            keep_global_variables=keep_global_variables,
        ),  # obscure within files (but not across files)
        fused := FusedVariableShortener(
            generator=ind.generator,
            module_to_shortener=ind.module_to_shortener,
            modules=ind.modules,
            keep_module_names=keep_module_names,
        ),  # obfuscate across files

        # optionally fuse files
        fuser := (
            FileFuser(modules=fused.modules) if output_single_file
            else Fuser(modules=fused.modules)
        ),

        # final post-processing to remove whitespace (minify)
        Unparser(),
        WhitespaceRemover(),
    )
    cleaned = list(pipeline.transform(*trees))

    return cleaned, fuser.modules
