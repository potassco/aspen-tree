"""Unit tests for spans of sibling nodes, span(node(N), node(M)), as
edit targets and templates."""

from contextlib import redirect_stdout
from io import StringIO

from aspen.tree import AspenTree
from aspen.utils.testing import AspenTestCase

from .common import clingo_lang

# The meta-encoding prefix of the tests, with lit(X, L) for the body
# literal L of identifier X, and comma(X, C) for the comma C after it.
LITS = (
    'lit(X, L) :- type(L, "body_literal"), child(L, A), child(A, I), '
    "leaf_text(I, X). "
    'comma(X, C) :- lit(X, L), next_sibling(L, C), leaf_text(C, ","). '
)
B_C = 'lit("b", B), lit("c", C)'
B_C_D = 'lit("b", B), lit("c", C), lit("d", D)'
IDENT_E = 'leaf_text(E, "e"), type(E, "identifier")'


class TestSpan(AspenTestCase):
    """Test spans of sibling nodes."""

    def test_transform_span(self) -> None:
        """Test replacing, deleting and inserting spans of sibling
        nodes."""
        for meta_str, expected in [
            (
                f'aspen(replace(span(node(B), node(C)), "x")) :- {B_C}.',
                "a :- x, d. e.",
            ),
            (
                'aspen(delete(span(node(K), node(C)))) :- comma("b", K), lit("c", C).',
                "a :- b, d. e.",
            ),
            # the inserted span includes the edits of its nodes
            (
                'aspen(replace(node(C), "z")) :- lit("c", C). '
                "aspen(replace(node(E), "
                'format("f :- {}", (span(node(B), node(C)), ())))) '
                f":- {IDENT_E}, {B_C}.",
                "a :- b, z, d. f :- b, z.",
            ),
            (
                'aspen(replace(node(C), "z")) :- lit("c", C). '
                "aspen(replace(node(E), "
                'format("f :- {}", (original(span(node(B), node(C))), ())))) '
                f":- {IDENT_E}, {B_C}.",
                "a :- b, z, d. f :- b, c.",
            ),
            # the first node of a replaced span can be prepended to,
            # and its last node appended to
            (
                f'aspen(replace(span(node(B), node(C)), "x")) :- {B_C}. '
                'aspen(prepend(node(B), "p, ")) :- lit("b", B). '
                'aspen(append(node(C), ", q")) :- lit("c", C).',
                "a :- p, x, q, d. e.",
            ),
        ]:
            with self.subTest(meta_str=meta_str):
                self.assert_transform_isomorphic(
                    language=clingo_lang,
                    sources=["a :- b, c, d. e."],
                    meta_string=LITS + meta_str,
                    expected_sources=[expected],
                )

    def test_transform_span_mutate(self) -> None:
        """Test spans as templates, and as base and as target of
        replacements in mutate templates."""
        for template, expected in [
            ("span(node(B), node(D))", "b, c, d"),
            (
                "mutate(span(node(B), node(D)), "
                + 'replace(span(node(B), node(C)), "x"))',
                "x, d",
            ),
            (
                "mutate(original(span(node(B), node(C))), "
                '(replace(node(C), "z"), ()))',
                "b, z",
            ),
            (
                'mutate(node(R), (replace(span(node(B), node(C)), "x"), '
                '(prepend(node(B), "("), (append(node(C), ")"), ()))))',
                "a :- (x), d.",
            ),
        ]:
            with self.subTest(template=template):
                tree = AspenTree(default_language=clingo_lang)
                tree.parse("a :- b, c, d.")
                meta_str = (
                    LITS + f"aspen(print({template})) :- " f'type(R, "rule"), {B_C_D}.'
                )
                with redirect_stdout(StringIO()) as buf:
                    tree.transform(meta_string=meta_str)
                self.assertEqual(buf.getvalue(), expected + "\n")

    def test_transform_span_errors(self) -> None:
        """Test the errors raised by invalid spans and conflicting edits
        of spans."""
        span = r"span\(node\(\d+\),node\(\d+\)\)"
        for meta_str, regex in [
            (
                'aspen(replace(span(node(C), node(B)), "x")) :- ' f"{B_C}.",
                rf"^s\(0\):1:8-9: Invalid span {span}: "
                r"node\(\d+\) is not node\(\d+\) or a later sibling of it\.\n"
                r"a :- b, c, d\.\n        \^$",
            ),
            (
                f'aspen(replace(span(node(B), node(C)), "x")) :- {B_C}. '
                'aspen(replace(node(C), "y")) :- lit("c", C).',
                r"^Replace edits of overlapping nodes, expected at most one:\n"
                r"s\(0\):1:5-9: replace with 'x'\na :- b, c, d\.\n     \^\^\^\^\n"
                r"s\(0\):1:8-9: replace with 'y'\na :- b, c, d\.\n        \^$",
            ),
            (
                f'aspen(replace(span(node(B), node(C)), "x")) :- {B_C}. '
                'aspen(append(node(B), "y")) :- lit("b", B).',
                r"^s\(0\):1:5-6: Cannot append to a node inside the replaced span "
                rf"{span}, only to its first node \(prepend\) or last node "
                r"\(append\): append 'y'\.",
            ),
            (
                f'aspen(append(span(node(B), node(C)), "x")) :- {B_C}.',
                r"only replace edits \(and delete\) may have a span as target",
            ),
            (
                "aspen(print(mutate(span(node(B), node(C)), "
                f'replace(node(D), "x")))) :- {B_C_D}.',
                r"^s\(0\):1:11-12: Target of edit .* is not inside the mutated "
                rf"{span}\.",
            ),
            (
                "aspen(print(mutate(span(node(B), node(D)), "
                '(replace(span(node(B), node(C)), "x"), '
                f'(append(node(B), "y"), ()))))) :- {B_C_D}.',
                r"^s\(0\):1:5-6: Edit of node in template .* is inside "
                rf"{span}, which is replaced\.",
            ),
        ]:
            with self.subTest(meta_str=meta_str):
                tree = AspenTree(default_language=clingo_lang)
                tree.parse("a :- b, c, d.")
                with self.assertRaisesRegex(ValueError, regex):
                    tree.transform(meta_string=LITS + meta_str)

    def test_transform_span_zero_width_node(self) -> None:
        """Test spans starting or ending with a node of zero width, such
        as an empty pool item, which tree-sitter's next_sibling skips."""
        nodes = (
            'type(E, "empty_pool_item"), type(T, "tuple"), child(T, E), '
            'type(N, "number"), child(T, N)'
        )
        for source, span in [
            ("p((1;)).", "span(node(N), node(E))"),
            ("p((;1)).", "span(node(E), node(N))"),
        ]:
            with self.subTest(source=source):
                self.assert_transform_isomorphic(
                    language=clingo_lang,
                    sources=[source],
                    meta_string=f'aspen(replace({span}, "x")) :- {nodes}.',
                    expected_sources=["p((x))."],
                )
