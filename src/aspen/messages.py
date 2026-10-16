"""Module rendering the templates derived by transformation
meta-encodings, and messages about nodes of the sources."""

from typing import Callable, Optional

import tree_sitter as ts
from clingo.symbol import Symbol, SymbolType

from aspen.source import Source, source_str
from aspen.utils.symbol_dispatch import (
    AllOf,
    AnyOf,
    At,
    Func,
    Str,
    SymbolSpec,
    Tup,
    dispatch_symbols,
)
from aspen.utils.tree_sitter_utils import format_node_span, format_syntax_error

NodeLocator = Callable[[Symbol], Optional[tuple[Source, ts.Node]]]


def cons_list_symb2py(l: Symbol) -> list[Symbol]:
    """Convert symbolic cons list consisting of nested tuples into a
    python list of symbols."""
    l_py: list[Symbol] = []
    while True:
        # accessing the arguments of a symbol is costly (relatively
        # speaking), so it is done once per element
        args = l.arguments if l.type == SymbolType.Function else None
        if args == [] and l.name == "":
            return l_py
        if args is None or len(args) != 2 or l.name != "":
            raise ValueError(f"Expected tuple of arity 2, found: {l}.")
        l_py.append(args[0])
        l = args[1]


def loc_prefix(source: Source, node: ts.Node) -> str:
    """The location prefix of a node of a source for error and log
    messages."""
    start_p, end_p = node.start_point, node.end_point
    if start_p.row == end_p.row:
        span_str = f"{start_p.row + 1}:{start_p.column}-{end_p.column}"
    else:
        span_str = f"{start_p.row + 1}:{start_p.column}-{end_p.row + 1}:{end_p.column}"
    return f"{source_str(source)}:{span_str}: "


class NodeFormatter:
    """Renders templates and messages about nodes, using locate_node
    to find the source and tree-sitter node of a node(Id) symbol
    (which returns None if the symbol is not the identifier of a
    node)."""

    def __init__(self, locate_node: NodeLocator):
        self._locate_node = locate_node
        self._template_strs: list[str] = []
        self._template_spec = self._build_template_spec()

    def node_message(self, node_symb: Symbol, text: str) -> str:
        """Message about the node with the given node(Id) symbol,
        consisting of its location in the source, the text, and the
        part of the source spanned by the node. If the node is not
        known (e.g. as the symbol is not the identifier of a node,
        which is reported separately), the symbol is shown instead."""
        located = self._locate_node(node_symb)
        if located is None:
            return f"{node_symb}: {text}"
        source, node = located
        span = format_node_span(node, source.source_bytes, source.encoding)
        return f"{loc_prefix(source, node)}{text}\n{span}"

    def node_position(self, node_symb: Symbol) -> tuple[str, int]:
        """Key to sort node(Id) symbols by their position in the
        sources."""
        located = self._locate_node(node_symb)
        # symbols that are not node identifiers are reported as
        # errors of the path_of_node query before this is reached
        assert located is not None
        source, node = located
        return str(source.id), node.start_byte

    def describe_edit(self, edit_symb: Symbol) -> str:
        """Describe an edit symbol by its kind and the text it inserts
        (or its template, if it cannot be converted to text)."""
        template = edit_symb.arguments[1]
        try:
            insert = repr(self.template_symb2str(template))
        except ValueError:
            insert = str(template)
        if edit_symb.name == "replace":
            return f"replace with {insert}"
        return f"{edit_symb.name} {insert}"

    def template_symb2str(self, symb: Symbol) -> str:
        """Convert template symbol to python str."""
        if symb.type == SymbolType.String:
            return symb.string
        # The actions of the template spec push the string of the
        # matched symbol to the stack (after converting its inserts
        # recursively, which push and pop their own strings).
        num_results = len(self._template_strs)
        dispatch_symbols([symb], self._template_spec)
        if len(self._template_strs) == num_results:
            raise ValueError(f"Symbol {symb} could not be converted to string.")
        return self._template_strs.pop()

    def _locate_template_node(self, symb: Symbol) -> tuple[Source, ts.Node]:
        located = self._locate_node(symb)
        if located is None:
            raise ValueError(
                f"Symbol {symb} could not be converted to string, "
                "as it is not the identifier of a node."
            )
        return located

    def _build_template_spec(self) -> SymbolSpec:
        """Build the spec dispatching template symbols to the actions
        converting them to strings, see template_symb2str."""

        def _node(symb: Symbol) -> None:
            source, node = self._locate_template_node(symb)
            start, end = node.start_byte, node.end_byte
            self._template_strs.append(
                source.source_bytes[start:end].decode(source.encoding)
            )

        def _format(symb: Symbol) -> None:
            format_string = symb.arguments[0].string
            inserts = cons_list_symb2py(symb.arguments[1])
            insert_strs = [self.template_symb2str(s) for s in inserts]
            self._template_strs.append(format_string.format(*insert_strs))

        def _join(symb: Symbol) -> None:
            join_str = symb.arguments[0].string
            inserts = cons_list_symb2py(symb.arguments[1])
            insert_strs = [self.template_symb2str(s) for s in inserts]
            self._template_strs.append(join_str.join(insert_strs))

        def _syntax_error(symb: Symbol) -> None:
            source, node = self._locate_template_node(symb.arguments[0])
            language = source.parser.language
            assert language is not None
            self._template_strs.append(
                format_syntax_error(
                    node,
                    source.source_bytes,
                    source.encoding,
                    language,
                    source_str(source),
                )
            )

        list_shape = AnyOf([At(1, Tup(2)), At(1, Tup(0))])
        return AnyOf(
            [
                Func("node", 1, action=_node),
                Func(
                    "format",
                    2,
                    action=_format,
                    shape=AllOf([At(0, Str()), list_shape]),
                ),
                Func(
                    "join",
                    2,
                    action=_join,
                    shape=AllOf([At(0, Str()), list_shape]),
                ),
                Func(
                    "syntax_error",
                    1,
                    action=_syntax_error,
                    shape=At(0, Func(name="node", arity=1)),
                ),
            ]
        )
