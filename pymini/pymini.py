import ast
import copy
import keyword
from typing import Dict, List, Optional, Set
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

    NOTE: unused_assignments must be modified in-place, since the set is passed
    to RemoveUnusedVariables at initialization. Can't return a new set.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unused_assignments = set()

    def _can_simplify_return(self, previous: ast.stmt, current: ast.stmt) -> bool:
        return (
            isinstance(previous, ast.Assign)
            and len(previous.targets) == 1
            and isinstance(previous.targets[0], ast.Name)
            and isinstance(current, ast.Return)
            and isinstance(current.value, ast.Name)
            and current.value.id == previous.targets[0].id
        )

    def _simplify_body(self, body: List[ast.stmt]) -> List[ast.stmt]:
        for previous, current in zip(body, body[1:]):
            if self._can_simplify_return(previous, current):
                self.unused_assignments.add(id(previous))
                current.value = copy.deepcopy(previous.value)
        return body

    def generic_visit(self, node):
        node = super().generic_visit(node)
        for field, value in ast.iter_fields(node):
            if isinstance(value, list) and value and all(isinstance(item, ast.stmt) for item in value):
                setattr(node, field, self._simplify_body(value))
        return node


class RemoveUnusedVariables(NodeTransformer):
    """Remove all unused variables.
    
    NOTE: cannot store a copy of unused_assignments, as this set is modified
    in-place
    after initialization.
    """
    def __init__(self, unused_assignments: Set[int]):
        super().__init__()
        self.unused_assignments = unused_assignments

    def visit_Assign(self, node: ast.Assign) -> Optional[ast.Assign]:
        if id(node) in self.unused_assignments:
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
    # Deferred optimizations intentionally left off after validating against
    # TexSoup and similar package-shaped inputs:
    # - aliasing repeated name reads into generated locals
    # - hoisting repeated string literals into generated locals at module or
    #   class scope
    # - renaming attribute call sites such as obj.method(...)
    # - renaming methods, class-body attributes, and top-level class names in
    #   preserve-public-API mode
    #
    # All of these reduce size further, but each one caused real runtime
    # regressions once decorators, descriptors, comprehensions, import-time side
    # effects, or class introspection entered the picture. Re-enable them only
    # with regression coverage in tests/test_api.py and the checked-in example
    # outputs kept in sync via scripts/regenerate_examples.py.
    def __init__(self, generator, mapping=None, modules=(), keep_global_variables=False):
        self.mapping = mapping or {}
        self.generator = generator
        self.nodes_to_append = []
        self.public_global_names = set()
        self.scope_stack = []
        self.modules = set(modules)  # don't alias variables imported from these modules
        self.keep_global_variables = keep_global_variables

    def _is_node_global(self, node):
        """Check if a node is global."""
        return (
            not hasattr(node, 'parent') or isinstance(node.parent, ast.Module)
        )

    def _rename_identifier(self, old_name):
        if old_name not in self.mapping.values():
            self.mapping[old_name] = next(self.generator)
        return self.mapping[old_name]

    def _append_public_alias(self, old_name, new_name):
        if old_name != new_name:
            self.nodes_to_append.append(ast.parse(f"{old_name} = {new_name}").body[0])

    def _preserve_function_name(self, name):
        return name.startswith("__") and name.endswith("__")

    def _is_method_definition(self, node):
        return isinstance(getattr(node, "parent", None), ast.ClassDef)

    def _is_class_body_assignment(self, node):
        return isinstance(getattr(node, "parent", None), ast.ClassDef)

    def _should_preserve_binding_targets(self, node):
        return self.keep_global_variables and (
            self._is_node_global(node) or self._is_class_body_assignment(node)
        )

    def _binding_names_from_target(self, target):
        names = set()
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                names.update(self._binding_names_from_target(element))
        return names

    def _rename_assignment_target(self, target):
        if isinstance(target, ast.Name):
            if self._is_active_parameter_name(target.id):
                return
            if target.id in self.mapping:
                target.id = self.mapping[target.id]
            elif target.id not in self.mapping.values():
                self.mapping[target.id] = target.id = next(self.generator)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._rename_assignment_target(element)

    def _is_in_expression_scope(self, node):
        current = getattr(node, "parent", None)
        expression_scopes = (
            ast.Lambda,
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
            ast.GeneratorExp,
        )
        while current is not None:
            if isinstance(current, expression_scopes):
                return True
            current = getattr(current, "parent", None)
        return False

    def _is_in_function_signature(self, node):
        current = getattr(node, "parent", None)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return False
            if isinstance(current, (ast.arguments, ast.arg)):
                return True
            current = getattr(current, "parent", None)
        return False

    def _scope_bindings(self, node):
        bindings = set()
        globals_ = set()
        args = set()

        class ScopeBindingCollector(ast.NodeVisitor):
            def visit_Global(self, inner):
                globals_.update(inner.names)

            def visit_arg(self, inner):
                args.add(inner.arg)
                bindings.add(inner.arg)

            def visit_Name(self, inner):
                if isinstance(inner.ctx, ast.Store):
                    bindings.add(inner.id)

            def visit_FunctionDef(self, inner):
                bindings.add(inner.name)

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, inner):
                bindings.add(inner.name)

            def visit_Lambda(self, inner):
                return None

            def visit_ListComp(self, inner):
                return None

            def visit_SetComp(self, inner):
                return None

            def visit_DictComp(self, inner):
                return None

            def visit_GeneratorExp(self, inner):
                return None

        collector = ScopeBindingCollector()
        args_node = getattr(node, "args", None)
        if args_node is not None:
            collector.visit(args_node)
        for statement in getattr(node, "body", []):
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                collector.visit(statement)
                continue
            collector.visit(statement)
        bindings.difference_update(globals_)
        return {"bindings": bindings, "globals": globals_, "args": args}

    def _is_preserved_public_global_reference(self, name):
        if name not in self.public_global_names:
            return False
        for scope in reversed(self.scope_stack):
            if name in scope["globals"]:
                continue
            if name in scope["bindings"]:
                return False
        return True

    def _is_preserved_function_parameter_reference(self, node):
        if self._is_in_function_signature(node):
            return False
        for scope in reversed(self.scope_stack):
            if node.id in scope["globals"]:
                continue
            if node.id in scope["bindings"]:
                return node.id in scope["args"]
        return False

    def _is_active_parameter_name(self, name):
        for scope in reversed(self.scope_stack):
            if name in scope["globals"]:
                continue
            if name in scope["bindings"]:
                return name in scope["args"]
        return False

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
        c.palpitation()
        >>> print(apply('import demiurgic as dei;dei.palpitation()'))
        import demiurgic as d
        d.palpitation()
        >>> print(apply('import demiurgic;import donotaliasme;from donotaliasme import dolor;'))
        import demiurgic as e
        import donotaliasme
        from donotaliasme import dolor
        """
        if self.keep_global_variables and self._is_node_global(node):
            return self.generic_visit(node)
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
        >>> def apply(src):
        ...     tree = ast.parse(src)
        ...     shortener.visit(tree)
        ...     append_public_aliases(tree, shortener.nodes_to_append)
        ...     return ast.unparse(tree)
        ...
        >>> apply('class Demiurgic: pass\\nholy = Demiurgic()')
        'class Demiurgic:\\n    pass\\nholy = Demiurgic()'
        """
        if self.keep_global_variables and self._is_node_global(node):
            self.scope_stack.append(self._scope_bindings(node))
            try:
                return self.generic_visit(node)
            finally:
                self.scope_stack.pop()
        if node.name not in self.mapping.values():  # TODO: make .values() more efficient
            self.mapping[node.name] = node.name = next(self.generator)
        self.scope_stack.append(self._scope_bindings(node))
        try:
            return self.generic_visit(node)
        finally:
            self.scope_stack.pop()

    def visit_FunctionDef(self, node):
        """Shorten function names.
    
        >>> shortener = VariableShortener(variable_name_generator())
        >>> apply = lambda src: ast.unparse(shortener.visit(ast.parse(src)))
        >>> apply('def demiurgic(palpitation): return palpitation\\nholy = demiurgic()')
        'def a(palpitation):\\n    return palpitation\\nb = a()'
        >>> shortener = VariableShortener(variable_name_generator(), keep_global_variables=True)
        >>> def apply(src):
        ...     tree = ast.parse(src)
        ...     shortener.visit(tree)
        ...     append_public_aliases(tree, shortener.nodes_to_append)
        ...     return ast.unparse(tree)
        ...
        >>> apply('def demiurgic(palpitation): return palpitation\\nholy = demiurgic()')
        'def a(palpitation):\\n    return palpitation\\nholy = a()\\ndemiurgic = a'
        """
        if self._preserve_function_name(node.name) or self._is_method_definition(node):
            self.scope_stack.append(self._scope_bindings(node))
            try:
                return self.generic_visit(node)
            finally:
                self.scope_stack.pop()
        if self.keep_global_variables and self._is_node_global(node):
            if len(node.name) > 1 and node.name not in self.mapping.values():
                old_name = node.name
                node.name = self._rename_identifier(old_name)
                self._append_public_alias(old_name, node.name)
            self.scope_stack.append(self._scope_bindings(node))
            try:
                return self.generic_visit(node)
            finally:
                self.scope_stack.pop()
        if node.name not in self.mapping.values():  # TODO: need to dedup this logic
            self.mapping[node.name] = node.name = next(self.generator)
        self.scope_stack.append(self._scope_bindings(node))
        try:
            return self.generic_visit(node)
        finally:
            self.scope_stack.pop()

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
        if getattr(node, "_pymini_generated", False):
            return node
        if self.keep_global_variables and self._is_class_body_assignment(node):
            for target in node.targets:
                if not self._binding_names_from_target(target):
                    self.visit(target)
            node.value = self.visit(node.value)
            return node
        if self.keep_global_variables and self._is_node_global(node):  # TODO: rename but insert var def if worth it
            for target in node.targets:
                binding_names = self._binding_names_from_target(target)
                if binding_names:
                    self.public_global_names.update(binding_names)
                else:
                    self.visit(target)
            node.value = self.visit(node.value)
            return node
        for target in node.targets:
            self._rename_assignment_target(target)
        return self.generic_visit(node)

    def visit_For(self, node):
        if not self._should_preserve_binding_targets(node):
            self._rename_assignment_target(node.target)
        node.iter = self.visit(node.iter)
        node.body = [self.visit(statement) for statement in node.body]
        node.orelse = [self.visit(statement) for statement in node.orelse]
        return node

    visit_AsyncFor = visit_For

    def visit_With(self, node):
        for item in node.items:
            item.context_expr = self.visit(item.context_expr)
            if item.optional_vars is not None and not self._should_preserve_binding_targets(node):
                self._rename_assignment_target(item.optional_vars)
        node.body = [self.visit(statement) for statement in node.body]
        return node

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node):
        if node.name and not self._should_preserve_binding_targets(node):
            if node.name in self.mapping:
                node.name = self.mapping[node.name]
            elif node.name not in self.mapping.values():
                self.mapping[node.name] = node.name = next(self.generator)
        node.type = self.visit(node.type) if node.type is not None else None
        node.body = [self.visit(statement) for statement in node.body]
        return node

    def visit_Call(self, node):
        """Apply renamed function names."""
        # Leave obj.method(...) alone for now. Attribute renaming broke dynamic
        # dispatch in real libraries and needs stronger type/owner analysis than
        # this AST-local pass currently has.
        if isinstance(node.func, ast.Name):
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
        'print(a, a)'
        >>> shortener = VariableShortener(variable_name_generator(), keep_global_variables=True)
        >>> apply('print(demiurgic)')
        'print(demiurgic)'
        >>> apply('print(demiurgic)')  # saw 'print' 2x but didn't replace
        'print(demiurgic)'
        """
        if node.id in self.mapping.values():  # TODO: make .values() more efficient
            return node
        if self._is_preserved_function_parameter_reference(node):
            return self.generic_visit(node)
        if self._is_in_expression_scope(node):
            if node.id in self.mapping:
                node.id = self.mapping[node.id]
            return self.generic_visit(node)
        if self.keep_global_variables and self._is_preserved_public_global_reference(node.id):
            return self.generic_visit(node)
        if self.keep_global_variables and self._is_node_global(node):
            if node.id in self.mapping:
                node.id = self.mapping[node.id]
            return self.generic_visit(node)
        # Repeated-name alias insertion used to happen here, but it was removed
        # after it leaked across scopes and decorators in real packages.
        if node.id in self.mapping:
            node.id = self.mapping[node.id]
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
        "a = 'demiurgic'\\nb = 'demiurgic'"
        >>> apply("dolor = 'demiurgic'")
        "c = 'demiurgic'"
        >>> apply("cached['demiurgic'] = 'palpitation'")
        "cached['demiurgic'] = 'palpitation'"
        >>> apply("demiurgic = 'demiurgic'")
        "d = 'demiurgic'"
        >>> print(apply("if 'demiurgic' in lorem: print(lorem)"))
        if 'demiurgic' in a:
            print(a)
        """
        if self._is_in_expression_scope(node):
            return node
        if not isinstance(node.value, str):  # TODO: generic for all constants?
            return node
        # Repeated-string hoisting is intentionally disabled for now. It saved
        # bytes, but the helper-insertion strategy was too fragile around scope
        # boundaries and statement ordering.
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
            append_public_aliases(tree, self.module_to_shortener[module].nodes_to_append)
            ParentSetter().visit(tree)
        return trees


class FusedVariableShortener(Transformer):
    """
    Fuse variable shortening across multiple files. Additionally and optionally 
    shortens filenames.
    
    >>> fused = FusedVariableShortener(variable_name_generator(), ('donotrenameme',), {}, keep_module_names=True)
    >>> _ = fused.transform(None)
    >>> fused.modules
    ['donotrenameme']
    """
    def __init__(self, generator, modules, module_to_shortener, keep_module_names=False):
        super().__init__()
        self.generator = generator
        self.modules = list(modules)
        self.module_to_shortener = module_to_shortener
        self.keep_module_names = keep_module_names

    def transform(self, *trees):
        original_modules = list(self.module_to_shortener)
        packages = package_modules(original_modules)
        module_to_module = {}
        if not self.keep_module_names:
            module_to_module = {module: next(self.generator) for module in original_modules}

            # NOTE: Must modify in-place, as this list is passed to Fuser
            for i, module in enumerate(original_modules):
                self.modules[i] = module_to_module[module]

        new_trees = []  # TODO: cleanup
        for tree, module in zip(trees, original_modules):
            # Preserve names already shortened in this module, and only rewrite
            # imported references using the exporter module's mapping.
            fused_mapping = {
                value: value
                for value in self.module_to_shortener[module].mapping.values()
            }

            imported = ImportedVariableShortener(
                self.generator,
                mapping=fused_mapping,
                current_module=module,
                keep_global_variables=True,
                module_to_module={_module: value for _module, value in module_to_module.items() if module != _module},
                module_to_shortener={_module: value for _module, value in self.module_to_shortener.items() if module != _module},
                packages=packages,
            )
            imported.transform(tree)
            append_public_aliases(tree, imported.nodes_to_append)
            ParentSetter().visit(tree)
            new_trees.append(tree)
        return new_trees


def _is_unsupported_hoisted_string_context(node):
    current = node
    pattern_nodes = tuple(
        node_type for node_type in (
            getattr(ast, "MatchValue", None),
            getattr(ast, "MatchSingleton", None),
            getattr(ast, "MatchSequence", None),
            getattr(ast, "MatchMapping", None),
            getattr(ast, "MatchClass", None),
            getattr(ast, "MatchAs", None),
            getattr(ast, "MatchOr", None),
        )
        if node_type is not None
    )
    while hasattr(current, "parent"):
        parent = current.parent
        if isinstance(parent, ast.JoinedStr):
            return True
        if pattern_nodes and isinstance(parent, pattern_nodes):
            return True
        if isinstance(parent, ast.arg) and parent.annotation is current:
            return True
        if isinstance(parent, ast.AnnAssign) and parent.annotation is current:
            return True
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)) and parent.returns is current:
            return True
        current = parent
    return False


class RepeatedStringHoister(Transformer):
    # Reintroduced in the narrowest safe form first: only hoist repeated string
    # literals inside function bodies. Module and class scopes are still left
    # alone because new bindings there change the public surface or class
    # namespace more directly.
    def __init__(self, generator):
        super().__init__()
        self.generator = generator

    def transform(self, *trees):
        for tree in trees:
            ParentSetter().visit(tree)
            collector = RepeatedStringCollector()
            collector.visit(tree)
            RepeatedStringRewriter(self.generator, collector.repeated_strings_by_scope).visit(tree)
            ParentSetter().visit(tree)
            ast.fix_missing_locations(tree)
        return trees


class RepeatedStringCollector(ast.NodeVisitor):
    def __init__(self):
        self.scope_stack = []
        self.repeated_strings_by_scope = {}

    def visit_FunctionDef(self, node):
        counts = {}
        self.scope_stack.append(counts)
        for statement in node.body:
            self.visit(statement)
        self.scope_stack.pop()
        repeated = [
            value
            for value, count in counts.items()
            if count > 1 and len(repr(value)) > 4
        ]
        if repeated:
            self.repeated_strings_by_scope[id(node)] = repeated

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        for statement in node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(statement)

    def visit_Constant(self, node):
        if not self.scope_stack or not isinstance(node.value, str):
            return
        if _is_unsupported_hoisted_string_context(node):
            return
        counts = self.scope_stack[-1]
        counts[node.value] = counts.get(node.value, 0) + 1


class RepeatedStringRewriter(ast.NodeTransformer):
    def __init__(self, generator, repeated_strings_by_scope):
        super().__init__()
        self.generator = generator
        self.repeated_strings_by_scope = repeated_strings_by_scope
        self.scope_stack = []

    def _prepend_assignments(self, body, mapping):
        assignments = []
        for value, name in mapping.items():
            assignment = ast.Assign(
                targets=[ast.Name(id=name, ctx=ast.Store())],
                value=ast.Constant(value=value),
            )
            assignment._pymini_generated = True
            assignments.append(assignment)
        return assignments + body

    def visit_FunctionDef(self, node):
        mapping = {}
        repeated = self.repeated_strings_by_scope.get(id(node), ())
        if repeated:
            mapping = {value: next(self.generator) for value in repeated}
        self.scope_stack.append(mapping)
        node.body = [self.visit(statement) for statement in node.body]
        self.scope_stack.pop()
        if mapping:
            node.body = self._prepend_assignments(node.body, mapping)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        updated_body = []
        for statement in node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                updated_body.append(self.visit(statement))
            else:
                updated_body.append(statement)
        node.body = updated_body
        return node

    def visit_Assign(self, node):
        if getattr(node, "_pymini_generated", False):
            return node
        return self.generic_visit(node)

    def visit_Constant(self, node):
        if not self.scope_stack or not isinstance(node.value, str):
            return node
        if _is_unsupported_hoisted_string_context(node):
            return node
        mapping = self.scope_stack[-1]
        if node.value not in mapping:
            return node
        return ast.copy_location(ast.Name(id=mapping[node.value], ctx=ast.Load()), node)


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
    def __init__(self, *args, current_module=None, module_to_shortener=None, module_to_module=None, packages=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.current_module = current_module
        self.module_to_shortener = module_to_shortener or {}
        self.module_to_module = module_to_module or {}
        self.packages = set(packages)

    def visit_ImportFrom(self, node):
        """Apply shortener for imported module."""
        module_name = resolve_import_from(self.current_module, node, self.packages)
        shortener = self.module_to_shortener.get(module_name, None)
        if shortener is not None:
            for alias in node.names:
                if alias.name == "*":
                    continue
                if alias.name in shortener.mapping:
                    self.mapping[alias.name] = alias.name = shortener.mapping[alias.name]
            if node.level == 0 and module_name in self.module_to_module:
                node.module = self.module_to_module[module_name]
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
    def _dependencies_for_tree(self, module, tree, modules):
        dependencies = ancestor_package_modules(module, modules)
        packages = package_modules(modules)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target_module = resolve_import_from(module, node, packages)
                dependencies.update(internal_module_dependencies(target_module, modules))
                for alias in node.names:
                    if alias.name != "*":
                        dependencies.update(
                            internal_module_dependencies(f"{target_module}.{alias.name}", modules)
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    dependencies.update(internal_module_dependencies(alias.name, modules))
        return dependencies

    def transform(self, *trees):
        module_to_tree = dict(zip(self.modules, trees))
        modules = set(module_to_tree)
        dependency_map = {
            module: self._dependencies_for_tree(module, tree, modules - {module})
            for module, tree in module_to_tree.items()
        }
        self.entry_modules = [
            module for module in self.modules
            if all(module not in dependencies for dependencies in dependency_map.values())
        ] or list(self.modules)
        return [module_to_tree[module] for module in self.modules]

def append_public_aliases(tree, aliases):
    root = next(ast.walk(tree))
    for node in aliases:
        inserted = ast.copy_location(node, root)
        inserted._pymini_generated = True
        root.body.append(inserted)
    ast.fix_missing_locations(tree)


class Unparser:

    def transform(self, *trees):
        for tree in trees:
            yield ast.unparse(tree)


def module_prefixes(module: Optional[str]) -> List[str]:
    if not module:
        return []
    parts = module.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts) + 1)]


def package_modules(modules) -> Set[str]:
    module_names = set(modules)
    packages = set()
    for module in module_names:
        prefixes = module_prefixes(module)
        packages.update(prefixes[:-1])
        if any(other.startswith(f"{module}.") for other in module_names):
            packages.add(module)
    return packages


def ancestor_package_modules(module: str, modules) -> Set[str]:
    module_names = set(modules)
    return {
        prefix
        for prefix in module_prefixes(module)[:-1]
        if prefix in module_names
    }


def module_package_name(module: Optional[str], packages: Set[str]) -> str:
    if not module:
        return ""
    if module in packages:
        return module
    return module.rsplit(".", 1)[0] if "." in module else ""


def resolve_import_from(current_module: Optional[str], node: ast.ImportFrom, packages: Set[str]) -> Optional[str]:
    if node.level == 0:
        return node.module

    package_name = module_package_name(current_module, packages)
    package_parts = package_name.split(".") if package_name else []
    if node.level > len(package_parts) + 1:
        return node.module

    base_parts = package_parts[:len(package_parts) - node.level + 1]
    if node.module:
        base_parts.extend(node.module.split("."))
    return ".".join(part for part in base_parts if part)


def internal_module_dependencies(module: Optional[str], modules) -> Set[str]:
    module_names = set(modules)
    return {
        prefix
        for prefix in module_prefixes(module)
        if prefix in module_names
    }


def bundle_sources(sources: List[str], modules: List[str], entry_modules: Optional[List[str]] = None) -> str:
    source_map = {module: source for module, source in zip(modules, sources)}
    package_names = package_modules(source_map)
    for package_name in sorted(package_names):
        source_map.setdefault(package_name, "")
    if not entry_modules:
        entry_modules = list(modules)

    bundle_runtime = f"""
import importlib.abc as _a
import importlib.util as _u
import sys as _s
_M={source_map!r}
_P={sorted(package_names)!r}
class _L(_a.Loader):
 def __init__(self,n):self.n=n
 def create_module(self,spec):return None
 def exec_module(self,module):
  if self.n in _P:module.__path__=[]
  exec(_M[self.n],module.__dict__)
class _F(_a.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname not in _M:return None
  return _u.spec_from_loader(fullname,_L(fullname),is_package=fullname in _P)
def _R(name,run_name):
 spec=_u.spec_from_loader(run_name,_L(name),is_package=name in _P)
 module=_u.module_from_spec(spec)
 module.__name__=run_name
 module.__package__=name if name in _P else name.rpartition('.')[0]
 if name in _P:module.__path__=[]
 _s.modules[run_name]=module
 _s.modules.setdefault(name,module)
 _L(name).exec_module(module)
 return module
_s.meta_path.insert(0,_F())
if {entry_modules!r}:_R({entry_modules!r}[0],'__main__')
for _m in {entry_modules!r}[1:]:__import__(_m)
"""
    return bundle_runtime.strip() + "\n"


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
                stripped = line.strip()
                if stripped.endswith(':') or stripped.startswith('@'):
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


def minify(sources, modules='main', keep_module_names=False,
           keep_global_variables=False, output_single_file=False,
           single_file_module='bundle'):
    """Uglify source code. Simplify, minify, and obfuscate.

    >>> sources, modules = minify(['''a = 3
    ... def square(x):
    ...     return x ** 2
    ... ''', '''from main import square
    ... square(3)
    ... '''], ['main', 'side'])
    >>> modules
    ['d', 'e']
    >>> sources[0]
    'b=3\\ndef c(x):return x**2'
    >>> sources[1]
    'from d import c;c(3)'
    """
    if isinstance(sources, str):
        sources = [sources]
    else:
        sources = list(sources)
    if isinstance(modules, str):
        modules = [modules]
    else:
        modules = list(modules)

    assert len(sources) == len(modules)

    trees = [ast.parse(source) for source in sources]

    pipeline = Pipeline(

        # simplify
        simplifier := ReturnSimplifier(),
        RemoveUnusedVariables(simplifier.unused_assignments),

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
        RepeatedStringHoister(ind.generator),

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
    if output_single_file:
        cleaned = [bundle_sources(cleaned, fuser.modules, getattr(fuser, "entry_modules", None))]

    output_modules = [single_file_module] if output_single_file else fuser.modules
    return cleaned, output_modules
