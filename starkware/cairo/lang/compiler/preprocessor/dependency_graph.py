from typing import Dict, List, Optional, Set

from starkware.cairo.lang.compiler.ast.code_elements import CodeElementFunction, CodeElementImport
from starkware.cairo.lang.compiler.ast.expr import (
    ExprAssignment,
    ExprDot,
    ExprIdentifier,
    ExprNewOperator,
)
from starkware.cairo.lang.compiler.ast.module import CairoModule
from starkware.cairo.lang.compiler.ast.visitor import Visitor
from starkware.cairo.lang.compiler.error_handling import Location
from starkware.cairo.lang.compiler.identifier_definition import AliasDefinition
from starkware.cairo.lang.compiler.identifier_manager import (
    IdentifierManager,
    MissingIdentifierError,
    NotAnIdentifierError,
)
from starkware.cairo.lang.compiler.preprocessor.pass_manager import PassManagerContext, Stage
from starkware.cairo.lang.compiler.preprocessor.preprocessor_error import PreprocessorError
from starkware.cairo.lang.compiler.scoped_name import ScopedName


class DependencyGraphVisitor(Visitor):
    """
    Tracks the dependencies between scope and identifier (that is, what identifiers are used in each
    scope).
    """

    def __init__(self, identifiers: IdentifierManager):
        super().__init__()
        self.identifiers = identifiers
        # A dictionary from a scope name to the list of identifiers it uses.
        self.visited_identifiers: Dict[ScopedName, List[ScopedName]] = {}
        # Tracks the current function being visited.
        self.current_function: Optional[ScopedName] = None

    def _visit_default(self, obj):
        for child in obj.get_children():
            if child is not None:
                self.visit(child)

    def add_identifier(
        self, name: ScopedName, location: Optional[Location], is_resolved: bool = False
    ):
        if name.path[-1] == "_":
            return
        if is_resolved:
            canonical_name = name
        else:
            try:
                canonical_name = self.identifiers.search(
                    accessible_scopes=self.accessible_scopes, name=name
                ).canonical_name
            except (MissingIdentifierError, NotAnIdentifierError) as e:
                # Don't generate errors on identifiers starting with "__", since they may refer to
                # autogenerated identifiers which were not collected in the identifier collection
                # phase.
                if name.path[-1].startswith("__"):
                    return
                raise PreprocessorError(str(e), location=location)

        if self.current_function is not None:
            self.visited_identifiers.setdefault(self.current_function, []).append(canonical_name)

    def visit_CodeElementMember(self, elm):
        pass

    def visit_ExprDot(self, expr: ExprDot):
        # We override the default visitor, since we must not visit expr.member.
        self.visit(expr.expr)

    def visit_ExprNewOperator(self, expr: ExprNewOperator):
        if self.current_function is None:
            # The new operator is not supported outside of a function since the 'get_ap' needs to be
            # added as a dependency of some function.
            raise PreprocessorError(
                "The new operator is not supported outside of a function.", location=expr.location
            )

        super().visit(expr.expr)

        self.add_identifier(
            name=ScopedName.from_string("starkware.cairo.lang.compiler.lib.registers.get_ap"),
            location=expr.location,
            is_resolved=True,
        )

    def visit_CodeElementFunction(self, elm: CodeElementFunction):
        if elm.element_type == "func":
            # Update self.current_function.
            old_current_function = self.current_function
            try:
                self.current_function = self.current_scope + elm.name
                # Enforce that every function appears in visited_identifiers.
                self.visited_identifiers.setdefault(self.current_scope + elm.name, [])
                super().visit_CodeElementFunction(elm)
            finally:
                self.current_function = old_current_function
        else:
            super().visit_CodeElementFunction(elm)

    def visit_ExprAssignment(self, elm: ExprAssignment):
        # We override the default visitor, since we must not visit expr.identifier.
        self.visit(elm.expr)

    def visit_ExprIdentifier(self, expr: ExprIdentifier):
        self.add_identifier(ScopedName.from_string(expr.name), location=expr.location)

    def visit_CodeElementImport(self, code_elm: CodeElementImport):
        for import_item in code_elm.import_items:
            self.add_identifier(
                ScopedName.from_string(code_elm.path.name)
                + ScopedName.from_string(import_item.orig_identifier.name),
                is_resolved=True,
                location=code_elm.location,
            )

    def find_function_dependencies(self, functions: Set[ScopedName]) -> Set[ScopedName]:
        """
        Finds all the transitive dependencies of a given set of functions.
        """
        finder = FunctionDependencyFinder(self.visited_identifiers)
        for x in functions:
            if x not in self.visited_identifiers:
                continue
            finder.visit(x)
        return finder.visited


class FunctionDependencyFinder:
    """
    A class helper for find_function_dependencies.
    """

    def __init__(self, identifer_dependencies: Dict[ScopedName, List[ScopedName]]):
        self.identifer_dependencies = identifer_dependencies
        self.visited: Set[ScopedName] = set()

    def visit(self, name: ScopedName):
        # Find the largest prefix that is a function.
        while len(name.path) > 0 and name not in self.identifer_dependencies:
            name = name[:-1]
        if name not in self.identifer_dependencies:
            # No such function.
            return
        if name in self.visited:
            return
        self.visited.add(name)
        for identifier in self.identifer_dependencies[name]:
            self.visit(identifier)


def get_main_functions_to_compile(
    identifiers: IdentifierManager, scopes_to_compile: Set[ScopedName]
) -> Set[ScopedName]:
    """
    Retrieves the root functions to compile from a main scope.
    The definition of which functions we need to compile is somewhat arbitrary:
    All functions explicitly defined, or aliased in the main scope.
    """
    main_functions: Set[ScopedName] = set()
    for parent_scope in scopes_to_compile:
        try:
            scope = identifiers.get_scope(parent_scope)
        except MissingIdentifierError:
            continue

        main_functions |= {parent_scope + name for name in scope.subscopes}
        main_functions |= {
            identifier_definition.destination
            for identifier_definition in scope.identifiers.values()
            if isinstance(identifier_definition, AliasDefinition)
        }
    return main_functions


def get_functions_to_compile(
    modules: List[CairoModule], identifiers: IdentifierManager, scopes_to_compile: Set[ScopedName]
) -> Set[ScopedName]:
    """
    Returns a set of reachable function (starting from the functions in the main scope).
    """

    dependency_graph = DependencyGraphVisitor(identifiers)
    for module in modules:
        dependency_graph.visit(module)
    return dependency_graph.find_function_dependencies(
        get_main_functions_to_compile(identifiers=identifiers, scopes_to_compile=scopes_to_compile)
    )


class DependencyGraphStage(Stage):
    def __init__(self, additional_scopes_to_compile: Set[ScopedName]):
        self.additional_scopes_to_compile = additional_scopes_to_compile

    def run(self, context: PassManagerContext):
        assert context.functions_to_compile is None
        context.functions_to_compile = get_functions_to_compile(
            modules=context.modules,
            identifiers=context.identifiers,
            scopes_to_compile={context.main_scope} | self.additional_scopes_to_compile,
        )