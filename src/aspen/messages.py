"""Module rendering the templates derived by transformation
meta-encodings, and messages about nodes of the sources."""

from typing import Callable, Optional

import tree_sitter as ts
from clingo.symbol import Symbol, SymbolType

from aspen.source import Source, source_str
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


def _node_text(source: Source, node: ts.Node) -> str:
    """The text of a node of a source."""
    return source.source_bytes[node.start_byte : node.end_byte].decode(source.encoding)


def _depth_below(node: ts.Node, ancestor: ts.Node) -> Optional[int]:
    """The number of steps from node up to ancestor, or None if
    ancestor is not node or one of its ancestors."""
    depth = 0
    current: Optional[ts.Node] = node
    while current is not None:
        if current == ancestor:
            return depth
        current = current.parent
        depth += 1
    return None


class NodeFormatter:
    """Renders templates and messages about nodes, using locate_node
    to find the source and tree-sitter node of a node(Id) symbol
    (which returns None if the symbol is not the identifier of a
    node), and locate_original_node to find them in the sources as
    they were at the start of the current transformation step."""

    def __init__(self, locate_node: NodeLocator, locate_original_node: NodeLocator):
        self._locate_node = locate_node
        self._locate_original_node = locate_original_node

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
        """Convert template symbol to python str.

        A template is a string, or one of:
        - node(N): the current text of node N, i.e. including the
          edits of it and its descendants applied so far (which the
          transformation encoding orders before the edit using the
          template);
        - original(node(N)): the text of node N at the start of the
          current transformation step, before any edits;
        - format(S, L) and join(S, L): the format string S with the
          templates of the list L inserted, or the templates of the
          list L joined by S;
        - edited(B, E): the text of B, which is node(N) or
          original(node(N)), with the edits E applied, without
          changing the source. E is an edit or a list of edits of
          the form replace(node(M), T), append(node(M), T) or
          prepend(node(M), T), where M is N or a descendant of N, see
          _edited_text;
        - syntax_error(node(N)): a description of the syntax error
          at node N.
        """
        if symb.type == SymbolType.String:
            return symb.string
        if symb.type == SymbolType.Function and symb.positive:
            # accessing the attributes of a symbol is costly
            # (relatively speaking), so each is accessed once
            name = symb.name
            args = symb.arguments
            arity = len(args)
            if arity == 1 and name == "node":
                return _node_text(*self._locate_template_node(symb, self._locate_node))
            if arity == 1 and name == "original" and args[0].match("node", 1):
                return _node_text(
                    *self._locate_template_node(args[0], self._locate_original_node)
                )
            if (
                arity == 2
                and name in ("format", "join")
                and args[0].type == SymbolType.String
                and (args[1].match("", 2) or args[1].match("", 0))
            ):
                inserts = cons_list_symb2py(args[1])
                insert_strs = [self.template_symb2str(s) for s in inserts]
                if name == "format":
                    return args[0].string.format(*insert_strs)
                return args[0].string.join(insert_strs)
            if arity == 2 and name == "edited":
                return self._edited_text(symb, args[0], args[1])
            if arity == 1 and name == "syntax_error" and args[0].match("node", 1):
                source, node = self._locate_template_node(args[0], self._locate_node)
                language = source.parser.language
                assert language is not None
                return format_syntax_error(
                    node,
                    source.source_bytes,
                    source.encoding,
                    language,
                    source_str(source),
                )
        raise ValueError(f"Symbol {symb} could not be converted to string.")

    def _edited_text(self, symb: Symbol, base: Symbol, edits_symb: Symbol) -> str:
        """Convert the template symbol edited(base, edits_symb) to
        python str, by splicing the texts of the edits into the text
        of the base node.

        Like edits of the source, each node may have at most one edit
        of each kind, and the replacement of a node comes before the
        text prepended and appended to it. A replaced node must not
        contain the target of another edit, as the replacement would
        overwrite its text.
        """
        if base.match("node", 1):
            node_symb, locate_node = base, self._locate_node
        elif base.match("original", 1) and base.arguments[0].match("node", 1):
            node_symb, locate_node = base.arguments[0], self._locate_original_node
        else:
            raise ValueError(f"Symbol {symb} could not be converted to string.")
        source, base_node = self._locate_template_node(node_symb, locate_node)
        if edits_symb.match("", 2) or edits_symb.match("", 0):
            edits = cons_list_symb2py(edits_symb)
        else:
            edits = [edits_symb]
        # the edited targets with their depth below the base node
        targets: dict[tuple[Symbol, str], tuple[ts.Node, int]] = {}
        for edit in edits:
            if (
                edit.type != SymbolType.Function
                or edit.name not in ("replace", "append", "prepend")
                or len(edit.arguments) != 2
                or not edit.arguments[0].match("node", 1)
            ):
                raise ValueError(
                    f"Symbol {edit} in template {symb} is not an edit of a node."
                )
            target_symb = edit.arguments[0]
            _, target = self._locate_template_node(target_symb, locate_node)
            depth = _depth_below(target, base_node)
            if depth is None:
                raise ValueError(
                    self.node_message(
                        target_symb,
                        f"Target of edit {edit} in template {symb} is not "
                        f"inside the edited node {node_symb}.",
                    )
                )
            if (target_symb, edit.name) in targets:
                raise ValueError(
                    self.node_message(
                        target_symb,
                        f"Multiple {edit.name} edits defined for node in "
                        f"template {symb}, expected at most one.",
                    )
                )
            targets[(target_symb, edit.name)] = (target, depth)
        for (replaced_symb, name), (replaced, _) in targets.items():
            if name != "replace":
                continue
            for (target_symb, _), (target, _) in targets.items():
                # a depth of 0 is the replaced node itself
                if _depth_below(target, replaced):
                    raise ValueError(
                        self.node_message(
                            target_symb,
                            f"Edit of node in template {symb} is inside the "
                            f"node {replaced_symb}, which is replaced.",
                        )
                    )
        # The texts to splice in, as (start, end, key, text), sorted so
        # that at the same position, appends of nodes ending there come
        # first (inner ones first), then prepends of nodes starting
        # there (outer ones first), then the replacement of a node.
        pieces: list[tuple[int, int, tuple[int, int], bytes]] = []
        for edit in edits:
            target, depth = targets[(edit.arguments[0], edit.name)]
            text = bytes(self.template_symb2str(edit.arguments[1]), source.encoding)
            if edit.name == "append":
                pieces.append((target.end_byte, target.end_byte, (0, -depth), text))
            elif edit.name == "prepend":
                pieces.append((target.start_byte, target.start_byte, (1, depth), text))
            else:
                pieces.append((target.start_byte, target.end_byte, (2, 0), text))
        pieces.sort(key=lambda piece: (piece[0], piece[2]))
        source_bytes = source.source_bytes
        cursor = base_node.start_byte
        edited = b""
        for start, end, _, text in pieces:
            edited += source_bytes[cursor:start] + text
            cursor = end
        edited += source_bytes[cursor : base_node.end_byte]
        return edited.decode(source.encoding)

    def _locate_template_node(
        self, symb: Symbol, locate_node: NodeLocator
    ) -> tuple[Source, ts.Node]:
        located = locate_node(symb)
        if located is None:
            raise ValueError(
                f"Symbol {symb} could not be converted to string, "
                "as it is not the identifier of a node."
            )
        return located
