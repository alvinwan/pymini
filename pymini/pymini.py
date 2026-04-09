import ast
import copy
import keyword
from collections import Counter
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


class ScopeLocalNameCollector(ast.NodeVisitor):
    def __init__(self):
        self.reserved_names = set()
        self.bindings = set()
        self.loads = set()
        self.external_bindings = set()
        self.args = set()

    def visit_Name(self, node):
        self.reserved_names.add(node.id)
        if isinstance(node.ctx, ast.Store):
            self.bindings.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            self.loads.add(node.id)

    def visit_arg(self, node):
        self.reserved_names.add(node.arg)
        self.bindings.add(node.arg)
        self.args.add(node.arg)
        if node.annotation is not None:
            self.visit(node.annotation)

    def visit_Global(self, node):
        self.reserved_names.update(node.names)
        self.external_bindings.update(node.names)

    visit_Nonlocal = visit_Global

    def visit_ExceptHandler(self, node):
        if node.name:
            self.reserved_names.add(node.name)
            self.bindings.add(node.name)
        if node.type is not None:
            self.visit(node.type)
        for statement in node.body:
            self.visit(statement)

    def visit_Import(self, node):
        for alias in node.names:
            bound_name = alias.asname or alias.name.split(".", 1)[0]
            self.reserved_names.add(bound_name)
            self.bindings.add(bound_name)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name == "*":
                continue
            bound_name = alias.asname or alias.name
            self.reserved_names.add(bound_name)
            self.bindings.add(bound_name)

    def _visit_nested_function(self, node):
        self.reserved_names.add(node.name)
        self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)
        for argument in (
            [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            + ([node.args.vararg] if node.args.vararg is not None else [])
            + ([node.args.kwarg] if node.args.kwarg is not None else [])
        ):
            if argument is not None and argument.annotation is not None:
                self.visit(argument.annotation)
        returns = getattr(node, "returns", None)
        if returns is not None:
            self.visit(returns)

    def visit_FunctionDef(self, node):
        self._visit_nested_function(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.reserved_names.add(node.name)
        self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)

    def visit_Lambda(self, node):
        return None

    def visit_ListComp(self, node):
        return None

    def visit_SetComp(self, node):
        return None

    def visit_DictComp(self, node):
        return None

    def visit_GeneratorExp(self, node):
        return None


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
        return node


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
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
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
    # Compression passes in this transformer use these guardrails:
    # - repeated-name aliasing is statement-local and deleted after the
    #   statement, so helpers do not leak across later code
    # - repeated-string hoisting now runs at function, module, and class scope,
    #   with cleanup deletes for module/class helpers
    # - preserve-public-API mode can rename top-level classes, methods, and
    #   class-body attributes, but it emits explicit aliases and fixes class
    #   __name__/__qualname__ for compatibility
    # - attribute rewriting is limited to owners we can prove from the AST
    #   (`self`, `cls`, or known class names), not arbitrary dynamic receivers
    #
    # Keep regression coverage in tests/test_api.py and the checked-in example
    # outputs under tests/examples in sync whenever these rules change.
    def __init__(
        self,
        generator,
        mapping=None,
        modules=(),
        keep_global_variables=False,
        rename_arguments=False,
        reserved_names=None,
    ):
        self.mapping = mapping or {}
        self.mapping_values = set(self.mapping.values())
        self.generator = generator
        self.reserved_names = set(reserved_names or ())
        self.nodes_to_append = []
        self.public_global_names = set()
        self.scope_stack = []
        self.local_rename_scopes = []
        self.instance_type_scopes = [{}]
        self.class_context_stack = []
        self.class_member_mappings = {}
        self.callable_argument_infos = {}
        self.class_method_argument_infos = {}
        self._class_public_member_reference_cache = {}
        self._module_attribute_reference_cache = {}
        self._scope_analysis_cache = {}
        self.modules = set(modules)  # don't alias variables imported from these modules
        self.keep_global_variables = keep_global_variables
        self.rename_arguments = rename_arguments

    def _is_node_global(self, node):
        """Check if a node is global."""
        return (
            not hasattr(node, 'parent') or isinstance(node.parent, ast.Module)
        )

    def _rename_identifier(self, old_name):
        if old_name not in self.mapping:
            while True:
                candidate = next(self.generator)
                if candidate not in self.mapping_values and candidate not in self.reserved_names:
                    self.mapping[old_name] = candidate
                    self.mapping_values.add(candidate)
                    break
        return self.mapping[old_name]

    def _lookup_local_identifier(self, old_name):
        for scope in reversed(self.local_rename_scopes):
            if old_name in scope["mapping"]:
                return scope["mapping"][old_name]
        return None

    def _lookup_visible_identifier(self, old_name):
        local_name = self._lookup_local_identifier(old_name)
        if local_name is not None:
            return local_name
        return self.mapping.get(old_name)

    def _rename_local_identifier(self, old_name):
        if old_name in self.mapping_values:
            return old_name
        scope = self.local_rename_scopes[-1]
        if old_name not in scope["mapping"]:
            new_name = next(scope["generator"])
            scope["mapping"][old_name] = new_name
            scope["used_names"].add(new_name)
        return scope["mapping"][old_name]

    def _push_instance_scope(self):
        self.instance_type_scopes.append({})

    def _pop_instance_scope(self):
        self.instance_type_scopes.pop()

    def _set_instance_type(self, name, class_name):
        scope = self.instance_type_scopes[-1]
        if class_name is None:
            scope.pop(name, None)
        else:
            scope[name] = class_name

    def _lookup_instance_type(self, name):
        for scope in reversed(self.instance_type_scopes):
            if name in scope:
                return scope[name]
        return None

    def _append_public_alias(self, old_name, new_name):
        if old_name != new_name:
            self.nodes_to_append.append(ast.parse(f"{old_name} = {new_name}").body[0])

    def _generated_assignment(self, source):
        node = ast.parse(source).body[0]
        node._pymini_generated = True
        return node

    def _containing_module(self, node):
        current = node
        while hasattr(current, "parent") and not isinstance(current.parent, ast.Module):
            current = current.parent
        return current.parent if hasattr(current, "parent") else None

    def _current_class_context(self):
        if self.class_context_stack:
            return self.class_context_stack[-1]
        return None

    def _preserve_function_name(self, name):
        return name.startswith("__") and name.endswith("__")

    def _estimated_short_name_length(self):
        return 1

    def _rename_savings(self, old_name, count):
        return max(0, len(old_name) - self._estimated_short_name_length()) * count

    def _public_class_alias_cost(self, old_name):
        short_name = "a"
        return sum(
            len(statement)
            for statement in (
                f"{old_name}={short_name}",
                f"{short_name}.__name__={old_name!r}",
                f"{short_name}.__qualname__={old_name!r}",
            )
        )

    def _public_member_alias_cost(self, old_name):
        return len(f"{old_name}=a")

    def _public_global_alias_cost(self, old_name):
        return len(f"{old_name}=a")

    def _public_class_reference_count(self, node, old_name):
        module = self._containing_module(node)
        count = 1
        if module is None:
            return count
        for current in ast.walk(module):
            if isinstance(current, ast.Name) and current.id == old_name:
                count += 1
        return count

    def _class_public_member_references(self, class_node):
        cache_key = id(class_node)
        cached = self._class_public_member_reference_cache.get(cache_key)
        if cached is not None:
            return cached

        name_loads = Counter()
        attribute_loads_by_base = {}
        for current in ast.walk(class_node):
            if isinstance(current, ast.Name) and isinstance(current.ctx, ast.Load):
                name_loads[current.id] += 1
            elif isinstance(current, ast.Attribute) and isinstance(current.value, ast.Name):
                base_name = current.value.id
                base_counts = attribute_loads_by_base.get(base_name)
                if base_counts is None:
                    base_counts = Counter()
                    attribute_loads_by_base[base_name] = base_counts
                base_counts[current.attr] += 1

        cached = {
            "name_loads": name_loads,
            "attribute_loads_by_base": attribute_loads_by_base,
        }
        self._class_public_member_reference_cache[cache_key] = cached
        return cached

    def _module_attribute_references(self, module):
        cache_key = id(module)
        cached = self._module_attribute_reference_cache.get(cache_key)
        if cached is not None:
            return cached

        attribute_loads_by_base = {}
        for current in ast.walk(module):
            if not isinstance(current, ast.Attribute) or not isinstance(current.value, ast.Name):
                continue
            base_name = current.value.id
            base_counts = attribute_loads_by_base.get(base_name)
            if base_counts is None:
                base_counts = Counter()
                attribute_loads_by_base[base_name] = base_counts
            base_counts[current.attr] += 1

        self._module_attribute_reference_cache[cache_key] = attribute_loads_by_base
        return attribute_loads_by_base

    def _public_member_reference_count(self, class_node, class_name, member_name):
        references = self._class_public_member_references(class_node)
        count = 1 + references["name_loads"].get(member_name, 0)
        attribute_loads_by_base = references["attribute_loads_by_base"]
        for base_name in {"self", "cls", class_name}:
            count += attribute_loads_by_base.get(base_name, {}).get(member_name, 0)
        module = self._containing_module(class_node)
        if module is not None:
            count += self._module_attribute_references(module).get(class_name, {}).get(member_name, 0)
        return count

    def _public_global_reference_count(self, node, old_name):
        module = self._containing_module(node)
        count = 1
        if module is None:
            return count
        for current in ast.walk(module):
            if (
                isinstance(current, ast.Name)
                and isinstance(current.ctx, ast.Load)
                and current.id == old_name
            ):
                count += 1
        return count

    def _should_rename_public_class(self, node, old_name):
        return self._rename_savings(
            old_name,
            self._public_class_reference_count(node, old_name),
        ) > self._public_class_alias_cost(old_name)

    def _should_rename_public_member(self, class_node, class_name, member_name):
        return self._rename_savings(
            member_name,
            self._public_member_reference_count(class_node, class_name, member_name),
        ) > self._public_member_alias_cost(member_name)

    def _should_rename_public_global(self, node, old_name):
        return self._rename_savings(
            old_name,
            self._public_global_reference_count(node, old_name),
        ) > self._public_global_alias_cost(old_name)

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

    def _function_argument_nodes(self, arguments):
        return [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            *([arguments.vararg] if arguments.vararg is not None else []),
            *([arguments.kwarg] if arguments.kwarg is not None else []),
        ]

    def _is_staticmethod(self, node):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "staticmethod":
                return True
            if isinstance(decorator, ast.Attribute) and decorator.attr == "staticmethod":
                return True
        return False

    def _should_rename_argument(self, name):
        return (
            self.rename_arguments
            and not self._preserve_function_name(name)
            and (len(name) > 1 or name in {"self", "cls"})
        )

    def _rename_function_arguments(self, node):
        argument_mapping = {}
        positional_params = [arg.arg for arg in [*node.args.posonlyargs, *node.args.args]]
        for argument in self._function_argument_nodes(node.args):
            old_name = argument.arg
            if not self._should_rename_argument(old_name):
                continue
            new_name = self._rename_local_identifier(old_name)
            argument.arg = new_name
            if old_name != new_name:
                argument_mapping[old_name] = new_name
        receiver_names = set()
        if self._is_method_definition(node) and not self._is_staticmethod(node) and positional_params:
            receiver_name = positional_params.pop(0)
            receiver_names.add(receiver_name)
            receiver_names.add(argument_mapping.get(receiver_name, receiver_name))
        return {
            "rename_map": argument_mapping,
            "positional_params": positional_params,
            "receiver_names": receiver_names,
        }

    def _record_callable_argument_info(self, old_name, new_name, argument_info):
        if not argument_info["rename_map"] and not argument_info["positional_params"]:
            return
        copied = {
            "rename_map": dict(argument_info["rename_map"]),
            "positional_params": list(argument_info["positional_params"]),
        }
        self.callable_argument_infos[old_name] = copied
        self.callable_argument_infos[new_name] = copied

    def _call_argument_info(self, func):
        if isinstance(func, ast.Name):
            return self.callable_argument_infos.get(func.id)
        if not isinstance(func, ast.Attribute):
            return None
        base_name = func.value.id if isinstance(func.value, ast.Name) else None
        class_context = self._current_class_context()
        if base_name is not None:
            if class_context is not None and base_name in (
                class_context["receiver_names"]
                | {class_context["old_name"], class_context["new_name"]}
            ):
                return class_context["argument_infos"].get(func.attr)
            instance_class = self._lookup_instance_type(base_name)
            if instance_class in self.class_method_argument_infos:
                return self.class_method_argument_infos[instance_class].get(func.attr)
            if base_name in self.class_method_argument_infos:
                return self.class_method_argument_infos[base_name].get(func.attr)
        receiver_class = self._receiver_class_name(func.value)
        if receiver_class in self.class_method_argument_infos:
            return self.class_method_argument_infos[receiver_class].get(func.attr)
        return None

    def _rewrite_keywords_as_positional(self, node, argument_info):
        if any(isinstance(arg, ast.Starred) for arg in node.args):
            return
        positional_params = argument_info["positional_params"]
        if not positional_params:
            return
        next_position = len(node.args)
        rewritten_keywords = []
        can_convert = True
        for keyword in node.keywords:
            if (
                can_convert
                and keyword.arg is not None
                and next_position < len(positional_params)
                and keyword.arg == positional_params[next_position]
            ):
                node.args.append(keyword.value)
                next_position += 1
                continue
            can_convert = False
            rewritten_keywords.append(keyword)
        node.keywords = rewritten_keywords

    def _rename_assignment_target(self, target, create_new=True):
        if isinstance(target, ast.Name):
            if self._is_active_parameter_name(target.id) or self._preserve_function_name(target.id):
                return
            if (
                self.local_rename_scopes
                and self.scope_stack
                and target.id in self.scope_stack[-1]["bindings"]
                and target.id not in self.scope_stack[-1]["globals"]
            ):
                target.id = self._rename_local_identifier(target.id)
                return
            if target.id in self.mapping:
                target.id = self.mapping[target.id]
            elif create_new and target.id not in self.mapping_values:
                target.id = self._rename_identifier(target.id)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._rename_assignment_target(element, create_new=create_new)

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

    def _scope_analysis(self, node):
        cache_key = id(node)
        cached = self._scope_analysis_cache.get(cache_key)
        if cached is not None:
            return cached

        collector = ScopeLocalNameCollector()
        args_node = getattr(node, "args", None)
        if args_node is not None:
            collector.visit(args_node)
        for statement in getattr(node, "body", []):
            collector.visit(statement)

        cached = {
            "reserved_names": frozenset(collector.reserved_names),
            "bindings": frozenset(collector.bindings - collector.external_bindings),
            "external_bindings": frozenset(collector.external_bindings),
            "args": frozenset(collector.args),
        }
        self._scope_analysis_cache[cache_key] = cached
        return cached

    def _scope_bindings(self, node):
        analysis = self._scope_analysis(node)
        return {
            "bindings": set(analysis["bindings"]),
            "globals": set(analysis["external_bindings"]),
            "args": set(analysis["args"]),
        }

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
        if self.rename_arguments:
            return False
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
                if name not in scope["args"]:
                    return False
                if not self.rename_arguments:
                    return True
                return name not in scope.get("renamed_args", set())
        return False

    def _local_scope_state(self, node):
        analysis = self._scope_analysis(node)
        reserved_names = set(analysis["reserved_names"])
        local_bindings = analysis["bindings"]
        for name in analysis["reserved_names"] - local_bindings:
            visible_name = self._lookup_visible_identifier(name)
            if visible_name is not None:
                reserved_names.add(visible_name)
        used_names = set(reserved_names)
        return {
            "mapping": {},
            "used_names": used_names,
            "generator": variable_name_generator(used_names),
        }

    def _receiver_class_name(self, node):
        if isinstance(node, ast.Name):
            return self._lookup_instance_type(node.id)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in self.class_member_mappings or func.id in self.class_method_argument_infos:
                    return func.id
                class_context = self._current_class_context()
                if class_context is not None and func.id in {
                    class_context["old_name"],
                    class_context["new_name"],
                }:
                    return func.id
        return None

    def _record_instance_assignment(self, target, value):
        class_name = self._receiver_class_name(value)
        if isinstance(target, ast.Name):
            self._set_instance_type(target.id, class_name)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._record_instance_assignment(element, value)

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
        import demiurgic as a
        a.palpitation()
        >>> print(apply('import demiurgic as dei;dei.palpitation()'))
        import demiurgic as c
        c.palpitation()
        >>> print(apply('import demiurgic;import donotaliasme;from donotaliasme import dolor;'))
        import demiurgic as a
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
                        alias.asname = self._rename_identifier(old)
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
        old_name = node.name
        parent_class_context = self._current_class_context()
        rename_public_class = False
        if self.keep_global_variables and self._is_node_global(node):
            if (
                len(node.name) > 1
                and node.name not in self.mapping_values
                and self._should_rename_public_class(node, old_name)
            ):
                node.name = self._rename_identifier(old_name)
                rename_public_class = old_name != node.name
            class_context = {
                "old_name": old_name,
                "new_name": node.name,
                "aliases": [],
                "member_mapping": {},
                "argument_infos": {},
                "receiver_names": {"self", "cls"},
            }
            self.class_context_stack.append(class_context)
            self.scope_stack.append(self._scope_bindings(node))
            self._push_instance_scope()
            try:
                node = self.generic_visit(node)
            finally:
                self._pop_instance_scope()
                self.scope_stack.pop()
                self.class_context_stack.pop()
            if class_context["member_mapping"]:
                self.class_member_mappings[old_name] = dict(class_context["member_mapping"])
                self.class_member_mappings[node.name] = dict(class_context["member_mapping"])
            if class_context["argument_infos"]:
                self.class_method_argument_infos[old_name] = dict(class_context["argument_infos"])
                self.class_method_argument_infos[node.name] = dict(class_context["argument_infos"])
                constructor_info = class_context["argument_infos"].get("__init__")
                if constructor_info is not None:
                    copied = {
                        "rename_map": dict(constructor_info["rename_map"]),
                        "positional_params": list(constructor_info["positional_params"]),
                    }
                    self.callable_argument_infos[old_name] = copied
                    self.callable_argument_infos[node.name] = {
                        "rename_map": dict(copied["rename_map"]),
                        "positional_params": list(copied["positional_params"]),
                    }
            if class_context["aliases"]:
                node.body.extend(class_context["aliases"])
            if rename_public_class:
                return [
                    node,
                    self._generated_assignment(f"{old_name} = {node.name}"),
                    self._generated_assignment(f"{node.name}.__name__ = {old_name!r}"),
                    self._generated_assignment(f"{node.name}.__qualname__ = {old_name!r}"),
                ]
            return node
        if self.local_rename_scopes and not self._is_node_global(node):
            node.name = self._rename_local_identifier(node.name)
        elif node.name not in self.mapping_values:
            node.name = self._rename_identifier(node.name)
        if parent_class_context is not None and old_name != node.name:
            parent_class_context["member_mapping"][old_name] = node.name
            if self.keep_global_variables:
                parent_class_context["aliases"].append(
                    self._generated_assignment(f"{old_name} = {node.name}")
                )
        class_context = {
            "old_name": old_name,
            "new_name": node.name,
            "aliases": [],
            "member_mapping": {},
            "argument_infos": {},
            "receiver_names": {"self", "cls"},
        }
        self.class_context_stack.append(class_context)
        self.scope_stack.append(self._scope_bindings(node))
        self._push_instance_scope()
        try:
            node = self.generic_visit(node)
        finally:
            self._pop_instance_scope()
            self.scope_stack.pop()
            self.class_context_stack.pop()
        if class_context["member_mapping"]:
            self.class_member_mappings[old_name] = dict(class_context["member_mapping"])
            self.class_member_mappings[node.name] = dict(class_context["member_mapping"])
        if class_context["argument_infos"]:
            self.class_method_argument_infos[old_name] = dict(class_context["argument_infos"])
            self.class_method_argument_infos[node.name] = dict(class_context["argument_infos"])
            constructor_info = class_context["argument_infos"].get("__init__")
            if constructor_info is not None:
                copied = {
                    "rename_map": dict(constructor_info["rename_map"]),
                    "positional_params": list(constructor_info["positional_params"]),
                }
                self.callable_argument_infos[old_name] = copied
                self.callable_argument_infos[node.name] = {
                    "rename_map": dict(copied["rename_map"]),
                    "positional_params": list(copied["positional_params"]),
                }
        return node

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
        old_name = node.name
        if self._preserve_function_name(node.name):
            self.scope_stack.append(self._scope_bindings(node))
            self.local_rename_scopes.append(self._local_scope_state(node))
            self._push_instance_scope()
            try:
                argument_info = self._rename_function_arguments(node)
                self.scope_stack[-1]["renamed_args"] = set(argument_info["rename_map"])
                class_context = self._current_class_context()
                if class_context is not None:
                    class_context["receiver_names"].update(argument_info["receiver_names"])
                    if argument_info["rename_map"] or argument_info["positional_params"]:
                        copied = {
                            "rename_map": dict(argument_info["rename_map"]),
                            "positional_params": list(argument_info["positional_params"]),
                        }
                        class_context["argument_infos"][old_name] = copied
                return self.generic_visit(node)
            finally:
                self._pop_instance_scope()
                self.local_rename_scopes.pop()
                self.scope_stack.pop()
        if self._is_method_definition(node):
            class_context = self._current_class_context()
            class_name = class_context["old_name"] if class_context is not None else ""
            if (
                len(old_name) > 1
                and (
                    not self.keep_global_variables
                    or class_context is None
                    or self._should_rename_public_member(node.parent, class_name, old_name)
                )
            ):
                node.name = self._rename_identifier(old_name)
            if class_context is not None and old_name != node.name:
                class_context["member_mapping"][old_name] = node.name
                if self.keep_global_variables:
                    class_context["aliases"].append(
                        self._generated_assignment(f"{old_name} = {node.name}")
                    )
            self.scope_stack.append(self._scope_bindings(node))
            self.local_rename_scopes.append(self._local_scope_state(node))
            self._push_instance_scope()
            try:
                argument_info = self._rename_function_arguments(node)
                self.scope_stack[-1]["renamed_args"] = set(argument_info["rename_map"])
                if class_context is not None:
                    class_context["receiver_names"].update(argument_info["receiver_names"])
                    if argument_info["rename_map"] or argument_info["positional_params"]:
                        copied = {
                            "rename_map": dict(argument_info["rename_map"]),
                            "positional_params": list(argument_info["positional_params"]),
                        }
                        class_context["argument_infos"][old_name] = copied
                        class_context["argument_infos"][node.name] = copied
                return self.generic_visit(node)
            finally:
                self._pop_instance_scope()
                self.local_rename_scopes.pop()
                self.scope_stack.pop()
        if self.keep_global_variables and self._is_node_global(node):
            if len(node.name) > 1 and node.name not in self.mapping_values:
                node.name = self._rename_identifier(old_name)
                self._append_public_alias(old_name, node.name)
            self.scope_stack.append(self._scope_bindings(node))
            self.local_rename_scopes.append(self._local_scope_state(node))
            self._push_instance_scope()
            try:
                argument_info = self._rename_function_arguments(node)
                self.scope_stack[-1]["renamed_args"] = set(argument_info["rename_map"])
                self._record_callable_argument_info(old_name, node.name, argument_info)
                return self.generic_visit(node)
            finally:
                self._pop_instance_scope()
                self.local_rename_scopes.pop()
                self.scope_stack.pop()
        if self.local_rename_scopes and not self._is_node_global(node):
            node.name = self._rename_local_identifier(node.name)
        elif node.name not in self.mapping_values:
            node.name = self._rename_identifier(node.name)
        self.scope_stack.append(self._scope_bindings(node))
        self.local_rename_scopes.append(self._local_scope_state(node))
        self._push_instance_scope()
        try:
            argument_info = self._rename_function_arguments(node)
            self.scope_stack[-1]["renamed_args"] = set(argument_info["rename_map"])
            self._record_callable_argument_info(old_name, node.name, argument_info)
            return self.generic_visit(node)
        finally:
            self._pop_instance_scope()
            self.local_rename_scopes.pop()
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
        if self._is_class_body_assignment(node):
            class_context = self._current_class_context()
            for target in node.targets:
                binding_names = self._binding_names_from_target(target)
                if binding_names:
                    for name in sorted(binding_names):
                        if self._preserve_function_name(name):
                            continue
                        if (
                            len(name) > 1
                            and (
                                not self.keep_global_variables
                                or class_context is None
                                or self._should_rename_public_member(
                                    node.parent,
                                    class_context["old_name"],
                                    name,
                                )
                            )
                        ):
                            new_name = self._rename_identifier(name)
                            if class_context is not None and name != new_name:
                                class_context["member_mapping"][name] = new_name
                                if self.keep_global_variables:
                                    class_context["aliases"].append(
                                        self._generated_assignment(f"{name} = {new_name}")
                                    )
                    self._rename_assignment_target(target, create_new=False)
                else:
                    self.visit(target)
            node.value = self.visit(node.value)
            return node
        if self.keep_global_variables and self._is_node_global(node):  # TODO: rename but insert var def if worth it
            for target in node.targets:
                binding_names = self._binding_names_from_target(target)
                if binding_names:
                    preserved_names = set()
                    for name in sorted(binding_names):
                        if self._preserve_function_name(name):
                            preserved_names.add(name)
                            continue
                        if (
                            len(name) > 1
                            and name not in self.mapping_values
                            and self._should_rename_public_global(node, name)
                        ):
                            new_name = self._rename_identifier(name)
                            self._append_public_alias(name, new_name)
                        else:
                            preserved_names.add(name)
                    self.public_global_names.update(preserved_names)
                    self._rename_assignment_target(target, create_new=False)
                else:
                    self.visit(target)
            node.value = self.visit(node.value)
            for target in node.targets:
                self._record_instance_assignment(target, node.value)
            return node
        for target in node.targets:
            if self._binding_names_from_target(target):
                self._rename_assignment_target(target)
            else:
                self.visit(target)
        node.value = self.visit(node.value)
        for target in node.targets:
            self._record_instance_assignment(target, node.value)
        return node

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
            elif node.name not in self.mapping_values:
                node.name = self._rename_identifier(node.name)
        node.type = self.visit(node.type) if node.type is not None else None
        node.body = [self.visit(statement) for statement in node.body]
        return node

    def visit_Global(self, node):
        node.names = [self.mapping.get(name, name) for name in node.names]
        return node

    def visit_Nonlocal(self, node):
        node.names = [
            self._lookup_local_identifier(name) or name
            for name in node.names
        ]
        return node

    def visit_Call(self, node):
        """Apply renamed function names."""
        node = self.generic_visit(node)
        argument_info = self._call_argument_info(node.func)
        if argument_info is not None:
            self._rewrite_keywords_as_positional(node, argument_info)
            rename_map = argument_info["rename_map"]
            for keyword in node.keywords:
                if keyword.arg in rename_map:
                    keyword.arg = rename_map[keyword.arg]
        return node

    def visit_Attribute(self, node):
        node.value = self.visit(node.value)
        base_name = node.value.id if isinstance(node.value, ast.Name) else None
        attribute_mapping = None
        class_context = self._current_class_context()
        if base_name is not None:
            if class_context is not None and base_name in {
                class_context["old_name"],
                class_context["new_name"],
            } | class_context["receiver_names"]:
                attribute_mapping = class_context["member_mapping"]
            else:
                instance_class = self._lookup_instance_type(base_name)
                if instance_class in self.class_member_mappings:
                    attribute_mapping = self.class_member_mappings[instance_class]
                elif base_name in self.class_member_mappings:
                    attribute_mapping = self.class_member_mappings[base_name]
        if attribute_mapping is None:
            receiver_class = self._receiver_class_name(node.value)
            if receiver_class in self.class_member_mappings:
                attribute_mapping = self.class_member_mappings[receiver_class]
        if attribute_mapping and node.attr in attribute_mapping:
            node.attr = attribute_mapping[node.attr]
        return node

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
        if node.id in self.mapping_values:
            return node
        local_name = self._lookup_local_identifier(node.id)
        if local_name is not None:
            node.id = local_name
            return self.generic_visit(node)
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
    def __init__(
        self,
        reserved_names_by_module,
        modules,
        keep_global_variables=False,
        rename_arguments=False,
        reuse_names_across_modules=True,
    ):
        super().__init__()
        self.reuse_names_across_modules = reuse_names_across_modules
        self.module_reserved_names = {
            module: set(names)
            for module, names in zip(modules, reserved_names_by_module)
        }
        all_reserved_names = set().union(*self.module_reserved_names.values()) if self.module_reserved_names else set()
        self.generator = variable_name_generator(
            set() if self.reuse_names_across_modules else all_reserved_names
        )
        self.module_to_shortener = {
            module: VariableShortener(
                (
                    variable_name_generator(self.module_reserved_names.get(module))
                    if self.reuse_names_across_modules
                    else self.generator
                ),
                modules=modules,
                keep_global_variables=keep_global_variables,
                rename_arguments=rename_arguments,
                reserved_names=(
                    self.module_reserved_names.get(module)
                    if self.reuse_names_across_modules
                    else all_reserved_names
                ),
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
        _invalidate_reserved_names_cache()
        original_modules = list(self.module_to_shortener)
        packages = package_modules(original_modules)
        module_to_module = {}
        if not self.keep_module_names:
            preserved_package_modules = {
                module
                for module in original_modules
                if module == "__init__" or module in packages
            }
            def renamed_module_name(module):
                if module in preserved_package_modules:
                    return module
                package_name = module_package_name(module, packages)
                short_name = next(self.generator)
                if package_name:
                    return f"{package_name}.{short_name}"
                return short_name
            module_to_module = {
                module: renamed_module_name(module)
                for module in original_modules
            }

            # NOTE: Must modify in-place, as this list is passed to Fuser
            for i, module in enumerate(original_modules):
                self.modules[i] = module_to_module[module]

        new_trees = []  # TODO: cleanup
        for tree, module in zip(trees, original_modules):
            # Preserve names already shortened in this module, and only rewrite
            # imported references using the exporter module's mapping.
            fused_mapping = {
                value: value
                for value in _reserved_names_in_node(tree)
            }

            imported = ImportedVariableShortener(
                self.generator,
                mapping=fused_mapping,
                current_module=module,
                keep_global_variables=True,
                reserved_names=self.module_to_shortener[module].reserved_names,
                module_to_module={_module: value for _module, value in module_to_module.items() if module != _module},
                module_to_shortener={_module: value for _module, value in self.module_to_shortener.items() if module != _module},
                packages=packages,
            )
            imported.transform(tree)
            append_public_aliases(tree, imported.nodes_to_append)
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


def _is_docstring_constant(node):
    expr = getattr(node, "parent", None)
    if not isinstance(expr, ast.Expr) or expr.value is not node:
        return False
    owner = getattr(expr, "parent", None)
    body = getattr(owner, "body", None)
    return bool(body) and body[0] is expr


def _reserved_names_in_node(node):
    cached_version = getattr(node, "_pymini_reserved_names_version", None)
    if cached_version == _RESERVED_NAMES_CACHE_VERSION:
        return node._pymini_reserved_names

    names = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.arg):
        names.add(node.arg)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.add(node.name)
    elif isinstance(node, ast.alias):
        names.add(node.asname or node.name.split(".", 1)[0])
    elif isinstance(node, (ast.Global, ast.Nonlocal)):
        names.update(node.names)
    elif isinstance(node, ast.ExceptHandler) and node.name:
        names.add(node.name)

    for child in ast.iter_child_nodes(node):
        names.update(_reserved_names_in_node(child))

    cached = frozenset(names)
    node._pymini_reserved_names = cached
    node._pymini_reserved_names_version = _RESERVED_NAMES_CACHE_VERSION
    return cached


_RESERVED_NAMES_CACHE_VERSION = 0


def _invalidate_reserved_names_cache():
    global _RESERVED_NAMES_CACHE_VERSION
    _RESERVED_NAMES_CACHE_VERSION += 1


class RepeatedStringHoister(Transformer):
    def __init__(self, generator):
        super().__init__()
        self.generator = generator

    def transform(self, *trees):
        _invalidate_reserved_names_cache()
        for tree in trees:
            ParentSetter().visit(tree)
            collector = RepeatedStringCollector()
            collector.visit(tree)
            RepeatedStringRewriter(self.generator, collector.repeated_strings_by_scope).visit(tree)
        return trees


class RepeatedStringCollector(ast.NodeVisitor):
    def __init__(self):
        self.scope_stack = []
        self.repeated_strings_by_scope = {}

    def _visit_scope(self, node):
        counts = {}
        self.scope_stack.append(counts)
        for statement in node.body:
            self.visit(statement)
        self.scope_stack.pop()
        if counts:
            self.repeated_strings_by_scope[id(node)] = counts

    def visit_Module(self, node):
        self._visit_scope(node)

    def visit_FunctionDef(self, node):
        self._visit_scope(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._visit_scope(node)

    def visit_Constant(self, node):
        if not self.scope_stack or not isinstance(node.value, str):
            return
        if _is_unsupported_hoisted_string_context(node):
            return
        if _is_docstring_constant(node):
            return
        counts = self.scope_stack[-1]
        counts[node.value] = counts.get(node.value, 0) + 1


class RepeatedStringRewriter(ast.NodeTransformer):
    def __init__(self, generator, repeated_strings_by_scope):
        super().__init__()
        self.generator = generator
        self.repeated_strings_by_scope = repeated_strings_by_scope
        self.scope_stack = []

    def _next_safe_name(self, reserved_names):
        while True:
            candidate = next(self.generator)
            if candidate not in reserved_names:
                reserved_names.add(candidate)
                return candidate

    def _is_profitable(self, value, count, scope_type):
        literal_len = len(repr(value))
        short_name_len = 1
        original_cost = count * literal_len
        helper_cost = short_name_len + 1 + literal_len
        rewritten_cost = count * short_name_len
        cleanup_cost = len("del(a,)") if scope_type in {"module", "class"} else 0
        return original_cost > helper_cost + rewritten_cost + cleanup_cost

    def _scope_mapping(self, node):
        counts = self.repeated_strings_by_scope.get(id(node), {})
        if not counts:
            return {}
        if isinstance(node, ast.Module):
            scope_type = "module"
        elif isinstance(node, ast.ClassDef):
            scope_type = "class"
        else:
            scope_type = "function"
        reserved_names = set(_reserved_names_in_node(node))
        return {
            value: self._next_safe_name(reserved_names)
            for value, count in counts.items()
            if count > 1 and len(repr(value)) > 4 and self._is_profitable(value, count, scope_type)
        }

    def _assignment_insertion_index(self, body):
        insert_at = 0
        if body and ast.get_docstring(ast.Module(body=body, type_ignores=[])) is not None:
            insert_at = 1
        while (
            insert_at < len(body)
            and isinstance(body[insert_at], ast.ImportFrom)
            and body[insert_at].module == "__future__"
        ):
            insert_at += 1
        return insert_at

    def _prepend_assignments(self, body, mapping):
        assignments = []
        for value, name in mapping.items():
            assignment = ast.Assign(
                targets=[ast.Name(id=name, ctx=ast.Store())],
                value=ast.Constant(value=value),
            )
            assignment._pymini_generated = True
            assignments.append(assignment)
        insert_at = self._assignment_insertion_index(body)
        return body[:insert_at] + assignments + body[insert_at:]

    def _append_cleanup(self, body, mapping):
        if not mapping:
            return body
        cleanup = ast.Delete(
            targets=[ast.Tuple(elts=[ast.Name(id=name, ctx=ast.Del()) for name in mapping.values()], ctx=ast.Del())],
        )
        cleanup._pymini_generated = True
        return body + [cleanup]

    def visit_Module(self, node):
        mapping = self._scope_mapping(node)
        self.scope_stack.append(mapping)
        node.body = [self.visit(statement) for statement in node.body]
        self.scope_stack.pop()
        if mapping:
            node.body = self._prepend_assignments(node.body, mapping)
            node.body = self._append_cleanup(node.body, mapping)
        return node

    def visit_FunctionDef(self, node):
        mapping = self._scope_mapping(node)
        self.scope_stack.append(mapping)
        node.body = [self.visit(statement) for statement in node.body]
        self.scope_stack.pop()
        if mapping:
            node.body = self._prepend_assignments(node.body, mapping)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        mapping = self._scope_mapping(node)
        self.scope_stack.append(mapping)
        node.body = [self.visit(statement) for statement in node.body]
        self.scope_stack.pop()
        if mapping:
            node.body = self._prepend_assignments(node.body, mapping)
            node.body = self._append_cleanup(node.body, mapping)
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
        if _is_docstring_constant(node):
            return node
        mapping = self.scope_stack[-1]
        if node.value not in mapping:
            return node
        return ast.copy_location(ast.Name(id=mapping[node.value], ctx=ast.Load()), node)


def _is_terminal_statement(node):
    return isinstance(node, (ast.Return, ast.Raise, ast.Continue, ast.Break))


class RepeatedNameAliaser(ast.NodeTransformer):
    def __init__(self, generator):
        super().__init__()
        self.generator = generator

    def transform(self, *trees):
        _invalidate_reserved_names_cache()
        for tree in trees:
            self.visit(tree)
        return trees

    def _next_safe_name(self, reserved_names):
        while True:
            candidate = next(self.generator)
            if candidate not in reserved_names:
                reserved_names.add(candidate)
                return candidate

    def _alias_assignment(self, mapping):
        names = list(mapping)
        aliases = list(mapping.values())
        if len(names) == 1:
            node = ast.Assign(
                targets=[ast.Name(id=aliases[0], ctx=ast.Store())],
                value=ast.Name(id=names[0], ctx=ast.Load()),
            )
        else:
            node = ast.Assign(
                targets=[ast.Tuple(elts=[ast.Name(id=alias, ctx=ast.Store()) for alias in aliases], ctx=ast.Store())],
                value=ast.Tuple(elts=[ast.Name(id=name, ctx=ast.Load()) for name in names], ctx=ast.Load()),
            )
        node._pymini_generated = True
        return node

    def _cleanup(self, mapping):
        node = ast.Delete(
            targets=[ast.Tuple(elts=[ast.Name(id=alias, ctx=ast.Del()) for alias in mapping.values()], ctx=ast.Del())],
        )
        node._pymini_generated = True
        return node

    def _rewrite_body(self, body):
        rewritten = []
        for statement in body:
            statement = self.visit(statement)
            mapping = RepeatedNameCollector.for_statement(statement, self._next_safe_name)
            if not mapping:
                rewritten.append(statement)
                continue
            rewritten_statement = RepeatedNameRewriter(mapping).visit(statement)
            rewritten.append(self._alias_assignment(mapping))
            rewritten.append(rewritten_statement)
            if not _is_terminal_statement(statement):
                rewritten.append(self._cleanup(mapping))
        return rewritten

    def visit_Module(self, node):
        node.body = self._rewrite_body(node.body)
        return node

    def visit_FunctionDef(self, node):
        node.body = self._rewrite_body(node.body)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        node.body = self._rewrite_body(node.body)
        return node


class RepeatedNameCollector(ast.NodeVisitor):
    def __init__(self):
        self.counts = {}
        self.bindings = set()

    @classmethod
    def for_statement(cls, statement, allocator):
        collector = cls()
        collector.visit(statement)
        repeated = [
            name
            for name, count in collector.counts.items()
            if count > 1 and len(name) > 1 and name not in collector.bindings
        ]
        if not repeated:
            return {}
        reserved_names = set(_reserved_names_in_node(statement))
        return {
            name: allocator(reserved_names)
            for name in repeated
        }

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.counts[node.id] = self.counts.get(node.id, 0) + 1
        elif isinstance(node.ctx, ast.Store):
            self.bindings.add(node.id)

    def visit_arg(self, node):
        self.bindings.add(node.arg)

    def visit_Global(self, node):
        self.bindings.update(node.names)

    visit_Nonlocal = visit_Global

    def visit_ExceptHandler(self, node):
        if node.name:
            self.bindings.add(node.name)
        if node.type is not None:
            self.visit(node.type)
        for statement in node.body:
            self.visit(statement)

    def visit_Import(self, node):
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name.split(".", 1)[0])

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name != "*":
                self.bindings.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node):
        self.bindings.add(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.bindings.add(node.name)

    def visit_Lambda(self, node):
        return node

    def visit_ListComp(self, node):
        return node

    def visit_SetComp(self, node):
        return node

    def visit_DictComp(self, node):
        return node

    def visit_GeneratorExp(self, node):
        return node


class RepeatedNameRewriter(ast.NodeTransformer):
    def __init__(self, mapping):
        super().__init__()
        self.mapping = mapping

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and node.id in self.mapping:
            node.id = self.mapping[node.id]
        return node

    def visit_FunctionDef(self, node):
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        return node

    def visit_Lambda(self, node):
        return node

    def visit_ListComp(self, node):
        return node

    def visit_SetComp(self, node):
        return node

    def visit_DictComp(self, node):
        return node

    def visit_GeneratorExp(self, node):
        return node


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
        package_import_module = module_name if module_name in self.packages else None
        for alias in node.names:
            if alias.name == "*":
                continue
            original_name = alias.name
            imported_module_name = (
                f"{package_import_module}.{original_name}"
                if package_import_module
                else None
            )
            if imported_module_name in self.module_to_module:
                alias.name = self.module_to_module[imported_module_name].rsplit(".", 1)[-1]
                if alias.asname is None and alias.name != original_name:
                    alias.asname = original_name
            if shortener is None:
                continue
            imported_name = alias.asname or original_name
            class_member_info = shortener.class_member_mappings.get(original_name)
            class_method_info = shortener.class_method_argument_infos.get(original_name)
            if original_name in shortener.callable_argument_infos:
                argument_info = shortener.callable_argument_infos[original_name]
                self.callable_argument_infos[imported_name] = {
                    "rename_map": dict(argument_info["rename_map"]),
                    "positional_params": list(argument_info["positional_params"]),
                }
            if original_name in shortener.mapping:
                renamed_name = shortener.mapping[original_name]
                preserve_binding_name = (
                    self.keep_global_variables
                    and self._is_node_global(node)
                    and imported_name != renamed_name
                )
                alias.name = renamed_name
                if preserve_binding_name:
                    alias.asname = imported_name
                    self.mapping[imported_name] = imported_name
                else:
                    self.mapping[original_name] = renamed_name
                if imported_name != alias.name and imported_name in self.callable_argument_infos:
                    copied = self.callable_argument_infos[imported_name]
                    self.callable_argument_infos[alias.name] = {
                        "rename_map": dict(copied["rename_map"]),
                        "positional_params": list(copied["positional_params"]),
                    }
            local_binding_name = alias.asname or alias.name
            if class_member_info is not None:
                copied_members = dict(class_member_info)
                self.class_member_mappings[imported_name] = dict(copied_members)
                self.class_member_mappings[local_binding_name] = dict(copied_members)
            if class_method_info is not None:
                copied_methods = {
                    method_name: {
                        "rename_map": dict(info["rename_map"]),
                        "positional_params": list(info["positional_params"]),
                    }
                    for method_name, info in class_method_info.items()
                }
                self.class_method_argument_infos[imported_name] = {
                    method_name: {
                        "rename_map": dict(info["rename_map"]),
                        "positional_params": list(info["positional_params"]),
                    }
                    for method_name, info in copied_methods.items()
                }
                self.class_method_argument_infos[local_binding_name] = copied_methods
        if module_name in self.module_to_module:
            rewritten_module = self.module_to_module[module_name]
            if node.level == 0:
                node.module = rewritten_module
            else:
                package_name = module_package_name(self.current_module, self.packages)
                package_parts = package_name.split(".") if package_name else []
                base_parts = package_parts[:len(package_parts) - node.level + 1]
                if base_parts and rewritten_module.startswith(".".join(base_parts) + "."):
                    node.module = rewritten_module[len(".".join(base_parts)) + 1:]
                else:
                    node.module = rewritten_module
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
        ast.fix_missing_locations(inserted)
        root.body.append(inserted)


class Unparser:

    def transform(self, *trees):
        for tree in trees:
            yield ast.unparse(tree)


class LocationFixer(Transformer):
    def transform(self, *trees):
        for tree in trees:
            ast.fix_missing_locations(tree)
        return trees


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
        keywords = set(keyword.kwlist)
        keywords.update(getattr(keyword, "softkwlist", ()))
        lines = []
        for line in source.splitlines():
            generated = list(tokenize.generate_tokens(StringIO(line).readline))
            if any(
                tokenize.tok_name.get(token.type, "").startswith("FSTRING_")
                for token in generated
            ):
                lines.append(line)
                continue
            tokens = []
            last_token = None
            for token in generated:
                token = token.string
                if token in keywords and tokens and not any(last_token.endswith(c) for c in ':;= '):
                    tokens.append(token)
                elif tokens and (last_token not in keywords or token in ':;='):
                    tokens[-1] += token
                else:
                    tokens.append(token)
                last_token = token
            lines.append(' '.join(tokens))
        return '\n'.join(lines)


def minify(sources, modules='main', keep_module_names=False,
           keep_global_variables=False, rename_arguments=False, output_single_file=False,
           single_file_module='bundle', fast=True):
    """Uglify source code. Simplify, minify, and obfuscate.

    >>> sources, modules = minify(['''a = 3
    ... def square(x):
    ...     return x ** 2
    ... ''', '''from main import square
    ... square(3)
    ... '''], ['main', 'side'])
    >>> modules
    ['a', 'b']
    >>> sources[0]
    'b=3\\ndef c(x):return x**2'
    >>> sources[1]
    'from a import c as square;square(3)'
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
    _invalidate_reserved_names_cache()
    reserved_names_by_module = [_reserved_names_in_node(tree) for tree in trees]

    simplifier = ReturnSimplifier()
    ind = IndependentVariableShorteners(
        reserved_names_by_module=reserved_names_by_module,
        modules=modules,
        keep_global_variables=keep_global_variables,
        rename_arguments=rename_arguments,
        reuse_names_across_modules=not output_single_file,
    )
    fused = FusedVariableShortener(
        generator=ind.generator,
        module_to_shortener=ind.module_to_shortener,
        modules=ind.modules,
        keep_module_names=keep_module_names,
    )
    fuser = (
        FileFuser(modules=fused.modules) if output_single_file
        else Fuser(modules=fused.modules)
    )
    pipeline_steps = [
        # simplify
        simplifier,
        RemoveUnusedVariables(simplifier.unused_assignments),

        # minify
        ParentSetter(),
        CommentRemover(),

        # obfuscate
        ind,
        fused,
    ]
    if not fast:
        pipeline_steps.extend((
            RepeatedStringHoister(ind.generator),
            RepeatedNameAliaser(ind.generator),
        ))
    pipeline_steps.extend((
        # optionally fuse files
        fuser,

        # final post-processing to remove whitespace (minify)
        LocationFixer(),
        Unparser(),
        WhitespaceRemover(),
    ))
    pipeline = Pipeline(*pipeline_steps)
    cleaned = list(pipeline.transform(*trees))
    if output_single_file:
        cleaned = [bundle_sources(cleaned, fuser.modules, getattr(fuser, "entry_modules", None))]

    output_modules = [single_file_module] if output_single_file else fuser.modules
    return cleaned, output_modules
