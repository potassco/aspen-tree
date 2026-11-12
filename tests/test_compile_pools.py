"""Test the bundled encoding compiling away pools of clingo programs in
one step, which exercises edited templates in many positions."""

from unittest import TestCase

from clingo import ast
from clingo.symbol import Function, Number

from aspen.tree import AspenTree

from .common import clingo_lang, input_dir, spy_re_reify

# The lists whose order does not matter, which are sorted to compare
# programs, as the encoding does not keep the order of clingo.
SORTED_LISTS = {
    ast.ASTType.Rule: "body",
    ast.ASTType.Minimize: "body",
    ast.ASTType.Disjunction: "elements",
    ast.ASTType.Aggregate: "elements",
    ast.ASTType.BodyAggregate: "elements",
    ast.ASTType.HeadAggregate: "elements",
    ast.ASTType.TheoryAtom: "elements",
    ast.ASTType.ConditionalLiteral: "condition",
    ast.ASTType.BodyAggregateElement: "condition",
    ast.ASTType.TheoryAtomElement: "condition",
}


def normalize(node: ast.AST) -> ast.AST:
    """Sort the lists of node whose order does not matter."""
    updates: dict[str, ast.AST | list[ast.AST]] = {}
    for key in node.child_keys:
        value = getattr(node, key)
        if isinstance(value, ast.ASTSequence):
            items = [normalize(item) for item in value]
            if SORTED_LISTS.get(node.ast_type) == key:
                items.sort(key=str)
            updates[key] = items
        elif isinstance(value, ast.AST):
            updates[key] = normalize(value)
    return node.update(**updates)


def parse_statements(program: str) -> list[ast.AST]:
    """Parse the statements of a program, except program parts."""
    statements: list[ast.AST] = []
    ast.parse_string(
        program,
        lambda stmt: (
            statements.append(stmt) if stmt.ast_type != ast.ASTType.Program else None
        ),
    )
    return statements


class TestCompilePools(TestCase):
    """Test the encoding compiling away pools."""

    def test_compile_pools(self) -> None:
        """Test that compiling away the pools of a program gives the
        same statements as unpooling it by clingo, up to the order of
        lists whose order does not matter, in a single transformation
        step (i.e. re-reifying once)."""
        program = (input_dir / "pools.lp").read_text()
        tree = AspenTree(default_language=clingo_lang)
        tree.parse(program)
        with spy_re_reify() as re_reify:
            tree.transform(meta_string='#include "@aspen/clingo/compile_pools.lp".')
            re_reify.assert_called_once()
        result = tree.sources[Function("s", [Number(0)])].source_bytes.decode()
        statements = parse_statements(result)
        for stmt in statements:
            self.assertEqual([str(s) for s in stmt.unpool()], [str(stmt)])
        expected = sorted(
            str(normalize(unpooled))
            for stmt in parse_statements(program)
            for unpooled in stmt.unpool()
        )
        self.assertListEqual(sorted(str(normalize(s)) for s in statements), expected)
