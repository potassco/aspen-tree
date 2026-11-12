"""Module rendering the templates derived by transformation
meta-encodings, and messages about nodes of the sources."""

from typing import Callable, Optional

import tree_sitter as ts
from clingo.symbol import Symbol, SymbolType

from aspen.source import Source, source_str
from aspen.utils.tree_sitter_utils import format_point_span, format_syntax_error

NodeLocator = Callable[[Symbol], Optional[tuple[Source, ts.Node]]]

# The kinds of edits, and those whose target may be a span.
EDIT_KINDS = ("replace", "append", "prepend")
SPAN_EDIT_KINDS = ("replace",)


def is_span(symb: Symbol) -> bool:
    """Whether symb is of the form span(node(N), node(M))."""
    return (
        symb.match("span", 2)
        and symb.arguments[0].match("node", 1)
        and symb.arguments[1].match("node", 1)
    )


def is_target(symb: Symbol) -> bool:
    """Whether symb is of the form node(N) or span(node(N), node(M))."""
    return symb.match("node", 1) or is_span(symb)


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


def loc_prefix(source: Source, start_p: ts.Point, end_p: ts.Point) -> str:
    """The location prefix of the part of a source between two points
    for error and log messages."""
    if start_p.row == end_p.row:
        span_str = f"{start_p.row + 1}:{start_p.column}-{end_p.column}"
    else:
        span_str = f"{start_p.row + 1}:{start_p.column}-{end_p.row + 1}:{end_p.column}"
    return f"{source_str(source)}:{span_str}: "


def _nodes_text(source: Source, nodes: list[ts.Node]) -> str:
    """The text of a run of sibling nodes of a source."""
    start, end = nodes[0].start_byte, nodes[-1].end_byte
    return source.source_bytes[start:end].decode(source.encoding)


def _depth_in(node: ts.Node, ancestors: list[ts.Node]) -> Optional[int]:
    """The number of steps from node up to one of ancestors, or None
    if there is none."""
    for ancestor in ancestors:
        depth = _depth_below(node, ancestor)
        if depth is not None:
            return depth
    return None


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
        """Message about the node with the given node(Id) symbol (or
        the nodes of a span(node(N), node(M)) symbol), consisting of
        its location in the source, the text, and the part of the
        source spanned by the node. If the node is not known (e.g. as
        the symbol is not the identifier of a node, which is reported
        separately), the symbol is shown instead."""
        located = self._locate_ends(node_symb)
        if located is None:
            return f"{node_symb}: {text}"
        source, first, last = located
        start, end = first.start_point, last.end_point
        span = format_point_span(start, end, source.source_bytes, source.encoding)
        return f"{loc_prefix(source, start, end)}{text}\n{span}"

    def node_position(self, node_symb: Symbol) -> tuple[str, int]:
        """Key to sort node(Id) (and span) symbols by their position in
        the sources."""
        located = self._locate_ends(node_symb)
        # symbols that are not node identifiers are reported as
        # errors of the path_of_node query before this is reached
        assert located is not None
        source, first, _ = located
        return str(source.id), first.start_byte

    def _locate_ends(
        self, node_symb: Symbol
    ) -> Optional[tuple[Source, ts.Node, ts.Node]]:
        """The source, and first and last node of a node(Id) or span
        symbol, or None if they are not known. The span is not
        checked, so that this can be used to report invalid spans."""
        first_symb, last_symb = (
            node_symb.arguments if is_span(node_symb) else (node_symb, node_symb)
        )
        first = self._locate_node(first_symb)
        last = self._locate_node(last_symb)
        if first is None or last is None:
            return None
        return first[0], first[1], last[1]

    def locate_target(
        self, target_symb: Symbol, original: bool = False
    ) -> tuple[Source, list[ts.Node]]:
        """The source and nodes of a node(Id) symbol, or of a
        span(node(N), node(M)) symbol, whose nodes are N and its next
        siblings up to M. If original is set, they are located in the
        sources as they were at the start of the transformation step.
        Raises a ValueError if a node is not known, or M is not N or a
        later sibling of it."""
        locate_node = self._locate_original_node if original else self._locate_node
        if not is_span(target_symb):
            source, node = self._locate_template_node(target_symb, locate_node)
            return source, [node]
        first_symb, last_symb = target_symb.arguments
        source, first = self._locate_template_node(first_symb, locate_node)
        _, last = self._locate_template_node(last_symb, locate_node)
        # The siblings are taken from the children of the parent, as
        # next_sibling skips nodes of zero width, such as empty pool
        # items.
        siblings = [first] if first.parent is None else first.parent.children
        start = siblings.index(first)
        for end in range(start, len(siblings)):
            if siblings[end] == last:
                return source, siblings[start : end + 1]
        raise ValueError(
            self.node_message(
                first_symb,
                f"Invalid span {target_symb}: {last_symb} is not "
                f"{first_symb} or a later sibling of it.",
            )
        )

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
        - span(node(N), node(M)): the current text from the start of
          node N to the end of node M, which must be N or a later
          sibling of N;
        - original(node(N)), original(span(node(N), node(M))): the
          text of node N (or the span) at the start of the current
          transformation step, before any edits;
        - format(S, L) and join(S, L): the format string S with the
          templates of the list L inserted, or the templates of the
          list L joined by S;
        - mutate(B, E): the text of B, which is node(N), a span, or
          either of them wrapped in original(...), with the edits E
          applied, without changing the source. E is an edit or a
          list of edits of the form replace(T, S), append(node(M), S)
          or prepend(node(M), S), where T is node(M) or a span, and
          the nodes are in B or descendants of nodes in B, see
          _mutate_text;
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
            if (arity == 1 and name == "node") or (arity == 2 and is_span(symb)):
                return _nodes_text(*self.locate_target(symb))
            if arity == 1 and name == "original" and is_target(args[0]):
                return _nodes_text(*self.locate_target(args[0], original=True))
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
            if arity == 2 and name == "mutate":
                return self._mutate_text(symb, args[0], args[1])
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

    def _mutate_text(self, symb: Symbol, base: Symbol, edits_symb: Symbol) -> str:
        """Convert the template symbol mutate(base, edits_symb) to
        python str, by splicing the texts of the edits into the text
        of the base node (or span).

        Like edits of the source, each node may have at most one edit
        of each kind, and the replacement of a node comes before the
        text prepended and appended to it. A replaced node (or span)
        must not contain the target of another edit, as the
        replacement would overwrite its text, except that the first
        node of a replaced span may be prepended to, and its last node
        appended to.
        """
        original = base.match("original", 1)
        if original:
            base = base.arguments[0]
        if not is_target(base):
            raise ValueError(f"Symbol {symb} could not be converted to string.")
        source, base_nodes = self.locate_target(base, original)
        if edits_symb.match("", 2) or edits_symb.match("", 0):
            edits = cons_list_symb2py(edits_symb)
        else:
            edits = [edits_symb]
        targets = self._mutate_targets(symb, edits, base, base_nodes, original)
        # The texts to splice in, as (start, end, key, text), sorted so
        # that at the same position, appends of nodes ending there come
        # first (inner ones first), then prepends of nodes starting
        # there (outer ones first), then the replacements of nodes, where
        # those of empty nodes come first.
        pieces: list[tuple[int, int, tuple[int, int], bytes]] = []
        for edit in edits:
            nodes, depth = targets[(edit.arguments[0], edit.name)]
            start, end = nodes[0].start_byte, nodes[-1].end_byte
            text = bytes(self.template_symb2str(edit.arguments[1]), source.encoding)
            if edit.name == "append":
                pieces.append((end, end, (0, -depth), text))
            elif edit.name == "prepend":
                pieces.append((start, start, (1, depth), text))
            else:
                pieces.append((start, end, (2, 0), text))
        pieces.sort(key=lambda piece: (piece[0], piece[2], piece[1]))
        source_bytes = source.source_bytes
        cursor = base_nodes[0].start_byte
        mutated = b""
        for start, end, _, text in pieces:
            mutated += source_bytes[cursor:start] + text
            cursor = end
        mutated += source_bytes[cursor : base_nodes[-1].end_byte]
        return mutated.decode(source.encoding)

    def _mutate_targets(
        self,
        symb: Symbol,
        edits: list[Symbol],
        base: Symbol,
        base_nodes: list[ts.Node],
        original: bool,
    ) -> dict[tuple[Symbol, str], tuple[list[ts.Node], int]]:
        """Check the edits of the template symbol symb, which mutates
        the node (or span) base (see _mutate_text), and return the
        nodes of their targets by target symbol and kind of edit,
        together with their depth below the nodes of the base."""
        targets: dict[tuple[Symbol, str], tuple[list[ts.Node], int]] = {}
        for edit in edits:
            if (
                edit.type != SymbolType.Function
                or edit.name not in EDIT_KINDS
                or len(edit.arguments) != 2
                or not (
                    edit.arguments[0].match("node", 1)
                    or (edit.name in SPAN_EDIT_KINDS and is_span(edit.arguments[0]))
                )
            ):
                raise ValueError(
                    f"Symbol {edit} in template {symb} is not an edit of a node "
                    "(or for replace, of a span)."
                )
            target_symb = edit.arguments[0]
            _, nodes = self.locate_target(target_symb, original)
            depth = _depth_in(nodes[0], base_nodes)
            if depth is None or _depth_in(nodes[-1], base_nodes) is None:
                raise ValueError(
                    self.node_message(
                        target_symb,
                        f"Target of edit {edit} in template {symb} is not "
                        f"inside the mutated {base}.",
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
            targets[(target_symb, edit.name)] = (nodes, depth)
        for (replaced_symb, name), (replaced, _) in targets.items():
            if name == "replace":
                self._check_inside_replaced(symb, replaced_symb, replaced, targets)
        return targets

    def _check_inside_replaced(
        self,
        symb: Symbol,
        replaced_symb: Symbol,
        replaced: list[ts.Node],
        targets: dict[tuple[Symbol, str], tuple[list[ts.Node], int]],
    ) -> None:
        """Check that no target of an edit of the template symbol symb
        is inside the replaced nodes, except for the edits prepending
        to the first one and appending to the last one."""
        for (target_symb, name), (nodes, _) in targets.items():
            if (target_symb, name) == (replaced_symb, "replace"):
                continue
            if name == "prepend" and nodes[0] == replaced[0]:
                continue
            if name == "append" and nodes[-1] == replaced[-1]:
                continue
            if any(_depth_in(node, replaced) is not None for node in nodes):
                raise ValueError(
                    self.node_message(
                        target_symb,
                        f"Edit of node in template {symb} is inside "
                        f"{replaced_symb}, which is replaced.",
                    )
                )

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
