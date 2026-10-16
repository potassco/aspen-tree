"""Unit tests for module aspen.tree"""

import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

# pylint: disable=import-error,no-name-in-module
from clingo.symbol import Function, Number, String, parse_term

from aspen.messages import cons_list_symb2py
from aspen.tree import AspenTree, TransformError, generic_util_path
from aspen.utils.testing import AspenTestCase
from aspen.utils.tree_sitter_utils import get_node_at_path

from .common import clingo_lang, encoding_dir, input_dir, output_dir, spy_re_reify


class TestAspenTree(AspenTestCase):  # pylint: disable=too-many-public-methods
    """Test suite for AspenTree class."""

    def test_path2py(self) -> None:
        """Test conversion of symbolic path to python list"""
        tree = AspenTree(default_language=clingo_lang)
        good_path = parse_term("(1, (2, ()))")
        self.assertListEqual(
            tree._path_symb2py(good_path), [1, 2]  # pylint: disable=protected-access
        )
        inverted_path = parse_term("(((), 2), 1)")
        re_str = r"Malformed path symbol"
        with self.assertRaisesRegex(ValueError, re_str):
            tree._path_symb2py(inverted_path)  # pylint: disable=protected-access
        bad_element_path = parse_term("(a, (b, ()))")
        with self.assertRaisesRegex(ValueError, re_str):
            tree._path_symb2py(bad_element_path)  # pylint: disable=protected-access

    def test_conslist2pylist(self) -> None:
        """Test conversion of symbolic cons list to python list"""
        good_path = parse_term("(1, (2, ()))")
        self.assertListEqual(
            cons_list_symb2py(good_path),
            [Number(1), Number(2)],
        )
        inverted_path = parse_term("(((), 2), 1)")
        re_str = r"Expected tuple of arity 2"
        with self.assertRaisesRegex(ValueError, re_str):
            cons_list_symb2py(inverted_path)
        const_cons_list = parse_term("(a, (b, ()))")
        const_py_list = [Function("a", []), Function("b", [])]
        self.assertListEqual(
            cons_list_symb2py(const_cons_list),
            const_py_list,
        )

    def test_node2path_symb(self) -> None:
        """Test calculation of path symbol of a tree sitter node."""
        tree = AspenTree(default_language=clingo_lang)
        source = tree.parse("a(1).")
        node = get_node_at_path(tree.sources[source].tree, [0, 0, 0, 2], reverse=True)
        expected_path_symb = parse_term("(0, (0, (0, (2, ()))))")
        path_symb = tree._node2path_symb(node)  # pylint: disable=protected-access
        self.assertEqual(path_symb, expected_path_symb)

    def test_source_path_symb2ts(self) -> None:
        """Test conversion of node id to tree sitter tree node."""
        tree = AspenTree(default_language=clingo_lang)
        source_id = parse_term("test(42)")
        tree.parse("a.", identifier=source_id)
        source_path_syb = parse_term("(test(42), (0, ( 0, ())))")
        source, node = tree._source_path_symb2ts(  # pylint: disable=protected-access
            source_path_syb
        )
        expected_source = tree.sources[source_id]
        self.assertEqual(source, expected_source)
        expected_node = get_node_at_path(
            tree.sources[source_id].tree, [0, 0], reverse=True
        )
        self.assertEqual(node, expected_node)
        unknown_source_node_id = parse_term("(foo(41),())")
        with self.assertRaisesRegex(ValueError, r"Unknown source symbol."):
            tree._source_path_symb2ts(  # pylint: disable=protected-access
                unknown_source_node_id
            )
        non_existent_path_node_id = parse_term("(test(42),(2, (0, ())))")
        regex_str = r"No node found in tree at path"
        with self.assertRaisesRegex(ValueError, regex_str):
            tree._source_path_symb2ts(  # pylint: disable=protected-access
                non_existent_path_node_id
            )

    def test_parse_strings(self) -> None:
        """Test parsing of input strings."""
        self.assert_parse_equals_file(
            clingo_lang, "a :- b.", output_dir / "ab_reified.txt"
        )

    def test_parse_files(self) -> None:
        """Test parsing of input files."""
        s0 = Function("s", [Number(0)])
        path_fact = Function(
            "source_path",
            [s0, String(str(input_dir / "ab.lp"))],
        )
        self.assert_parse_equals_file(
            clingo_lang,
            input_dir / "ab.lp",
            output_dir / "ab_reified.txt",
            additional_expected_facts=[path_fact],
        )

    def test_reify_error_missing_node(self) -> None:
        """Test reification of error and missing node. Disables the
        default syntax-error-raising behavior, since this test is
        specifically about the reified representation of such nodes."""
        self.assert_parse_equals_file(
            clingo_lang,
            "+a.",
            output_dir / "error_missing_reified.txt",
            raise_syntax_errors=False,
        )

    def test_parse_no_lang(self) -> None:
        """Test that parse method raises ValueError when no language
        is given and no default language is given."""
        tree = AspenTree()
        regex = r"No language specified, and no default language is set."
        with self.assertRaisesRegex(ValueError, regex):
            tree.parse("a.")

    def test_transform_add_vars(self) -> None:
        """Test transformation, adding variables to atoms."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=["a :- b."],
            meta_files=[encoding_dir / "add_var.lp"],
            initial_program=("add_var_to_atoms", [String("X")]),
            expected_sources=["a(X) :- b(X)."],
        )

    def test_transform_add_vars_include_generic(self) -> None:
        """Test that re-reification after a transformation is not
        affected by the transformation encoding including the generic
        utility encodings."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=["a :- b."],
            meta_files=[encoding_dir / "add_var.lp"],
            meta_string='#include "@aspen/generic/all.lp".',
            initial_program=("add_var_to_atoms", [String("X")]),
            expected_sources=["a(X) :- b(X)."],
        )

    def test_transform_add_vars_append(self) -> None:
        """Test transformation, adding variables to atoms, using append."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=["a :- b."],
            meta_files=[encoding_dir / "add_var_append.lp"],
            initial_program=("add_var_to_atoms", [String("X")]),
            expected_sources=["a(X) :- b(X)."],
        )

    def test_transform_join(self) -> None:
        """Test transformation that uses a string join."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=["a."],
            meta_files=[encoding_dir / "add_body_to_facts.lp"],
            expected_sources=["a :- b; c."],
        )

    def test_transform_join_dependency(self) -> None:
        """Test transformation that uses a string join and dependencies."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=["a. :- b."],
            meta_files=[encoding_dir / "add_body_to_facts_depend.lp"],
            expected_sources=["a :- d; c. :- d."],
        )

    def test_transform_multiple_replacess_same_node(self) -> None:
        """Test that transformation raises error when defining
        multiple replacements for the same node."""
        tree = AspenTree(default_language=clingo_lang)
        tree.parse("p(1).")
        meta_str = (
            'aspen(replace(node(N),format(S,()))) :- source_root(_,N); S=("a.";"b.").'
        )
        regex_str = (
            r"^s\(0\):1:0-5: Multiple edits defined for node, expected one: "
            r"replace with 'a\.'; replace with 'b\.'\.\np\(1\)\.\n\^\^\^\^\^$"
        )
        with self.assertRaisesRegex(ValueError, regex_str):
            tree.transform(meta_string=meta_str)
        # edits of other kinds, and those with templates that cannot
        # be converted to text, are described as well
        meta_str = (
            'aspen(replace(node(N),"a.");append(node(N),foo(1))) :- source_root(_,N).'
        )
        regex_str = r"expected one: append foo\(1\); replace with 'a\.'\."
        with self.assertRaisesRegex(ValueError, regex_str):
            tree.transform(meta_string=meta_str)

    def test_transform_spanning_ancestor(self) -> None:
        """Test that transformation succeeds when editing a node which
        has ancestors that span the same byte range."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=[b"a."],
            meta_string='aspen(replace(node(N),"b")) :- leaf_text(N, "a").',
            expected_sources=["b."],
        )

    def test_transform_prepend(self) -> None:
        """Test that transformation succeeds when prepending text before
        a node."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=["a."],
            meta_string='aspen(prepend(node(N), "x :- y. ")) :- leaf_text(N, "a").',
            expected_sources=["x :- y. a."],
        )

    def test_transform_format_without_inserts(self) -> None:
        """Test that a format template may have an empty list of
        inserts."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=["a."],
            meta_string='aspen(replace(node(N),format("b",()))) :- leaf_text(N, "a").',
            expected_sources=["b."],
        )

    def test_transform_exception_not_a_node(self) -> None:
        """Test that an exception located at a symbol that is not a
        node identifier is reported along with the symbol."""
        self.assert_transform_raises(
            message_regex=(
                r"^node\(999\): bad\n"
                r"Expected a node identifier as input for path_of_node query, "
                r"found 999\.$"
            ),
            language=clingo_lang,
            sources=["a."],
            meta_string='aspen(exception(node(999), "bad")).',
        )

    def test_transform_template_not_a_node(self) -> None:
        """Test that a template inserting a symbol that is not a node
        identifier raises an error."""
        tree = AspenTree(default_language=clingo_lang)
        tree.parse("a.")
        regex = r"Symbol node\(999\) could not be converted to string, as it is not"
        with self.assertRaisesRegex(ValueError, regex):
            tree.transform(meta_string='aspen(print(format("{}", (node(999), ())))).')

    def test_query_node_at_path_broken_path(self) -> None:
        """Test that the node_at_path query raises an error located at
        the node where the path cannot be followed further."""
        self.assert_transform_raises(
            message_regex=(
                r"^s\(0\):1:0-7: No node found at path \(0,\(5,\(\)\)\) of "
                r"source s\(0\): this node has no child with index 5\.\n"
                r"a :- b\.\n\^\^\^\^\^\^\^$"
            ),
            language=clingo_lang,
            sources=["a :- b."],
            meta_string=(
                '#include "@aspen/generic/queries/node_at_path.lp".'
                "aspen(query(node_at_path(s(0),(0,(5,())))))."
            ),
        )

    def test_query_node_at_path_unknown_source(self) -> None:
        """Test that the node_at_path query raises an error for an
        unknown source."""
        self.assert_transform_raises(
            message_regex=r"^Source s\(7\) not found\.$",
            language=clingo_lang,
            sources=["a."],
            meta_string=(
                '#include "@aspen/generic/queries/node_at_path.lp".'
                "aspen(query(node_at_path(s(7),(0,()))))."
            ),
        )

    def test_queries_not_a_node(self) -> None:
        """Test that queries expecting a node identifier raise an
        error showing the given symbol otherwise."""
        for query, message in (
            ("descendant", r"^Expected node identifier, found f\(x\)\.$"),
            (
                "delete_subtree",
                r"^Expected input N to query delete_subtree\(N\) to be node id, "
                r"found: f\(x\)$",
            ),
        ):
            with self.subTest(query=query):
                self.assert_transform_raises(
                    message_regex=message,
                    language=clingo_lang,
                    sources=["a."],
                    meta_string=(
                        f'#include "@aspen/generic/queries/{query}.lp".'
                        f"aspen(query({query}(f(x))))."
                    ),
                )

    def test_transform_bad_replace(self) -> None:
        """Test that tranformation raises error when invalid
        replacement is used in aspen(replace(S,R))."""
        tree = AspenTree(default_language=clingo_lang)
        tree.parse("p(1).")
        meta_str = "aspen(replace(node(N),foo(1))) :- source_root(_,N)."
        regex_str = r"Symbol foo\(1\) could not be converted to string\."
        with self.assertRaisesRegex(ValueError, regex_str):
            tree.transform(meta_string=meta_str)

    def test_transform_dependencies(self) -> None:
        """Test that edits in transformation are applied in the
        correct order to satisfy implicit dependencies between edits"""
        tree = AspenTree(default_language=clingo_lang)
        tree.parse("a :- b.")
        meta_str = (
            'aspen(replace(node(N), format("{0}", (node(M), ()))))'
            ' :- leaf_text(N, "a"), leaf_text(M, "b").'
            'aspen(replace(node(M), format("{0}", (node(N), ()))))'
            ' :- leaf_text(N, "a"), leaf_text(M, "b").'
        )
        error_regex = (
            r"Transformation edits define cyclic dependencies via format strings\. "
            r"One such cycle:\n"
            r"s\(0\):1:(0-1|5-6): replace with '[ab]'\na :- b\.\n *\^\n"
            r"which must be applied before\n"
            r"s\(0\):1:(0-1|5-6): replace with '[ab]'\na :- b\.\n *\^\n"
            r"which must be applied before\n"
        )
        with self.assertRaisesRegex(ValueError, error_regex):
            tree.transform(meta_string=meta_str)
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=["a(b)."],
            meta_files=[encoding_dir / "add_var.lp"],
            meta_string=(
                '#program add_var_to_atoms(var). aspen(replace(node(N),"c")) '
                ':- leaf_text(N,"b").'
            ),
            initial_program=("add_var_to_atoms", [String("X")]),
            expected_sources=["a(c,X)."],
        )

    def test_transform_multiple_steps(self) -> None:
        """Test that transformation works as expected when multiple
        steps are defined."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=["a :- b."],
            meta_files=[
                encoding_dir / "rename_a_to_b.lp",
                encoding_dir / "add_var.lp",
            ],
            initial_program=("rename_x_to_y", [String("a"), String("b")]),
            expected_sources=["b(X) :- b(X)."],
        )

    def test_transform_skip_final_re_reify(self) -> None:
        """Test that when skipping re-reification after the final
        transformation step, the facts are reified anew on access."""
        tree = AspenTree(default_language=clingo_lang)
        tree.parse("a :- b.")
        with spy_re_reify() as re_reify:
            tree.transform(
                meta_files=[encoding_dir / "add_var.lp"],
                initial_program=("add_var_to_atoms", [String("X")]),
                skip_final_re_reify=True,
            )
            re_reify.assert_not_called()
        source = tree.sources[Function("s", [Number(0)])]
        self.assertEqual(source.source_bytes, b"a(X) :- b(X).")
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=["a :- b."],
            meta_files=[encoding_dir / "add_var.lp"],
            initial_program=("add_var_to_atoms", [String("X")]),
            expected_sources=["a(X) :- b(X)."],
            skip_final_re_reify=True,
        )

    def test_transform_skip_final_re_reify_multiple_steps(self) -> None:
        """Test that when skipping re-reification after the final
        transformation step, it is still done after the steps before,
        as the following steps need the facts."""
        with spy_re_reify() as re_reify:
            self.assert_transform_isomorphic(
                language=clingo_lang,
                sources=["a :- b."],
                meta_files=[
                    encoding_dir / "rename_a_to_b.lp",
                    encoding_dir / "add_var.lp",
                ],
                initial_program=("rename_x_to_y", [String("a"), String("b")]),
                expected_sources=["b(X) :- b(X)."],
                skip_final_re_reify=True,
            )
            self.assertEqual(re_reify.call_count, 1)

    def test_transform_skip_final_re_reify_syntax_error(self) -> None:
        """Test that syntax errors introduced by the final
        transformation step are raised even when skipping
        re-reification."""
        self.assert_transform_raises(
            message_regex=r"s\(0\):2:1: unexpected '\('\nb\(\.\n \^",
            language=clingo_lang,
            sources=["a.\nb."],
            meta_string='aspen(replace(node(N), "b(")) :- leaf_text(N, "b").',
            skip_final_re_reify=True,
        )

    def test_transform_bad_next_step(self) -> None:
        """Test that transformation raises error when multiple next
        programs are derived."""
        tree = AspenTree(default_language=clingo_lang)
        tree.parse("")
        meta_str = 'aspen(next_program("foo", (,))). aspen(next_program("bar", (,))).'
        error_regex = r"Multiple next_program-s defined, expected one"
        with self.assertRaisesRegex(ValueError, error_regex):
            tree.transform(meta_string=meta_str)
        meta_str = "aspen(next_program(a,b))."
        error_regex = (
            r"First argument of next_program must be a string, "
            r"second must be a tuple, found"
        )
        with self.assertRaisesRegex(ValueError, error_regex):
            tree.transform(meta_string=meta_str)

    def test_transform_multiline(self) -> None:
        """Test transform where multiline replacement occurs."""
        meta_str = """aspen(replace(node(N),format("{0}", (node(M),())))) :-
 leaf_text(N,"a"), type(M,"symbolic_atom"), child(M,L), type(L,"terms")."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=[
                """
a.
p(1
,
2)."""
            ],
            meta_string=meta_str,
            expected_sources=[
                """
p(1
,
2).
p(1
,
2)."""
            ],
        )

    def test_transform_logs_info(self) -> None:
        """Test that tranformation logs messages as expected."""
        source_path = encoding_dir / "multiline.lp"
        loc_log_str = str(source_path).replace("\\", "\\\\")
        loc_log_str += r":1:0-3:0: This is a log for a node"
        self.assert_transform_logs(
            log_level="INFO",
            message2num_matches={
                loc_log_str: 1,
                r" This is a log without location.": 1,
            },
            language=clingo_lang,
            source=source_path,
            meta_files=[encoding_dir / "log_info.lp"],
        )

    def test_transform_logs_warn(self) -> None:
        """Test that tranformation logs messages as expected."""
        source_path = input_dir / "a.lp"
        loc_log_str = str(source_path).replace("\\", "\\\\")
        loc_log_str += r":1:0-2: This is a log for node 'a.'."
        self.assert_transform_logs(
            log_level="WARNING",
            message2num_matches={
                loc_log_str: 1,
                r" This is a log without location.": 1,
            },
            language=clingo_lang,
            source=source_path,
            meta_files=[encoding_dir / "log_warning.lp"],
        )

    def test_transform_logs_show_node_span(self) -> None:
        """Test that a log message attached to a node shows that
        node's text span underlined right after it, in the same
        caret style as syntax errors - rather than just the bare
        location prefix."""
        source_path = input_dir / "a.lp"
        loc_log_str = str(source_path).replace("\\", "\\\\")
        loc_log_str += r":1:0-2: This is a log for node 'a\.'\.\na\.\n\^\^"
        self.assert_transform_logs(
            log_level="WARNING",
            message2num_matches={loc_log_str: 1},
            language=clingo_lang,
            source=source_path,
            meta_files=[encoding_dir / "log_warning.lp"],
        )

    def test_transform_raises(self) -> None:
        """Test that transformation raises error as expected."""
        self.assert_transform_raises(
            message_regex=r"s\(0\):1:0-1: This is an error for node 'a'.",
            language=clingo_lang,
            sources=["a."],
            meta_files=[encoding_dir / "raise_error.lp"],
        )

    def test_transform_raises_shows_node_span(self) -> None:
        """Test that an exception attached to a node shows that
        node's text span underlined right after it, in the same caret
        style as syntax errors - rather than just the bare location
        prefix."""
        self.assert_transform_raises(
            message_regex=r"s\(0\):1:0-1: This is an error for node 'a'\.\na\.\n\^",
            language=clingo_lang,
            sources=["a."],
            meta_files=[encoding_dir / "raise_error.lp"],
        )

    def test_transform_raises_no_loc(self) -> None:
        """Test that transformation raises error as expected."""
        self.assert_transform_raises(
            message_regex=r"This is an error with no location.",
            language=clingo_lang,
            sources=["a."],
            meta_files=[encoding_dir / "raise_error_no_loc.lp"],
        )

    def test_parse_raises_syntax_error_missing(self) -> None:
        """Test that a missing-token syntax error is raised
        immediately after parsing (the default), reporting its
        location, the offending source line with a caret, and the
        missing token - but no "expected" hint, since node.type
        already is the answer."""
        tree = AspenTree(default_language=clingo_lang)
        with self.assertRaisesRegex(
            TransformError,
            r"s\(0\):1:6: missing '\.'\na :- b\n      \^",
        ):
            tree.parse("a :- b")

    def test_parse_raises_syntax_error_with_hint(self) -> None:
        """Test that an ERROR node whose lookahead set is short and
        specific gets an "expected one of: ..." hint appended - the
        parser consumed the valid keyword '#sum' and stranded the
        typo'd trailing 'a' right before the '{' it wanted. Raised
        immediately after parsing, like any other syntax error."""
        tree = AspenTree(default_language=clingo_lang)
        with self.assertRaisesRegex(
            TransformError,
            (
                r"s\(0\):1:9: unexpected 'a', expected one of: \{\n"
                r"a :- #suma\{X : b\(X\)\} = 2\.\n"
                r"         \^"
            ),
        ):
            tree.parse("a :- #suma{X : b(X)} = 2.")

    def test_parse_raises_syntax_error_without_hint(self) -> None:
        """Test that an ERROR node whose lookahead set is long (a
        generic, heavily-reused continuation point, not a specific
        expectation) gets no "expected" hint - a long list would just
        be noise, not a pointer to the mistake."""
        tree = AspenTree(default_language=clingo_lang)
        with self.assertRaisesRegex(
            TransformError,
            r"s\(0\):1:3: unexpected ','\na\(1,,2\)\.\n   \^",
        ) as ctx:
            tree.parse("a(1,,2).")
        self.assertNotIn("expected one of", str(ctx.exception))

    def test_parse_raises_multiple_syntax_errors_sorted_by_position(self) -> None:
        """Test that several syntax errors found while reifying one
        source are all collected and raised together, in document
        order - not whatever order the subtree walk happened to visit
        them in."""
        tree = AspenTree(default_language=clingo_lang)
        with self.assertRaisesRegex(
            TransformError,
            (
                r"s\(0\):1:9: unexpected 'a', expected one of: \{\n"
                r"a :- #suma\{X : b\(X\)\} = 2\.\n"
                r"         \^\n"
                r"s\(0\):2:6: missing '\.'\nc :- d\n      \^"
            ),
        ):
            tree.parse("a :- #suma{X : b(X)} = 2.\nc :- d")

    def test_parse_syntax_errors_can_be_disabled(self) -> None:
        """Test that raise_syntax_errors=False lets parse() succeed
        even with syntax errors in the source, leaving the usual
        error(Node)/missing(Node) facts for the caller to inspect or
        act on instead."""
        tree = AspenTree(default_language=clingo_lang, raise_syntax_errors=False)
        tree.parse("a :- b")
        self.assertTrue(any(f.match("missing", 1) for f in tree.facts))

    def test_transform_raise_syntax_error_lp_still_works_when_disabled(self) -> None:
        """Test that the older, explicit raise_syntax_error.lp
        transform-time mechanism remains usable by anyone who disables
        the automatic parse-time check - it derives the same
        exception from the same error(Node)/missing(Node) facts."""
        tree = AspenTree(default_language=clingo_lang, raise_syntax_errors=False)
        tree.parse("a :- b")
        with self.assertRaisesRegex(
            TransformError,
            r"s\(0\):1:6: missing '\.'\na :- b\n      \^",
        ):
            tree.transform(meta_files=[generic_util_path / "raise_syntax_error.lp"])

    def test_transform_meta_encoding_aspen_include(self) -> None:
        """Test that a user-authored meta-encoding can #include
        "@aspen/..." to reach aspen's own bundled ASP utility library,
        without needing to know where aspen itself is installed."""
        tree = AspenTree(default_language=clingo_lang)
        tree.parse("a(1,2).")
        meta_str = (
            '#include "@aspen/clingo/derived_predicates/named_child_index.lp".\n'
            '#include "@aspen/clingo/derived_predicates/symbol_signature.lp".\n'
            'aspen(print(format("{0}", (Name, ())))) :- '
            "symbol_signature(N, (Name, Arity))."
        )
        with redirect_stdout(StringIO()) as buf:
            tree.transform(meta_string=meta_str)
            self.assertEqual(buf.getvalue(), "a\n")

    def test_transform_meta_encoding_file_with_aspen_include(self) -> None:
        """Test that the '@aspen/' convention also works from a
        meta-encoding file on disk (meta_files), including when it is
        itself #include-d (via a normal local, relative path) from a
        second user-authored file."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            helpers_path = tmp_path / "helpers.lp"
            helpers_path.write_text(
                '#include "@aspen/clingo/derived_predicates/named_child_index.lp".\n'
                '#include "@aspen/clingo/derived_predicates/symbol_signature.lp".\n'
            )
            main_path = tmp_path / "main.lp"
            main_path.write_text(
                '#include "./helpers.lp".\n'
                'aspen(print(format("{0}", (Name, ())))) :- '
                "symbol_signature(N, (Name, Arity))."
            )
            tree = AspenTree(default_language=clingo_lang)
            tree.parse("a(1,2).")
            with redirect_stdout(StringIO()) as buf:
                tree.transform(meta_files=[main_path])
                self.assertEqual(buf.getvalue(), "a\n")

    def test_transform_print(self) -> None:
        """Test that aspen(print(String)) symbols derived during
        transformation prints String to stdout."""
        tree = AspenTree(default_language=clingo_lang)
        with redirect_stdout(StringIO()) as buf:
            tree.transform(meta_string='aspen(print(format("Hello {}", ("World", ())))).')
            printed_text = buf.getvalue()
            self.assertEqual(printed_text, "Hello World\n")

    def test_transform_print_to_io(self) -> None:
        """Test that aspen(print(String)) symbols derived during
        transformation prints String to stdout."""
        tree = AspenTree(default_language=clingo_lang)
        with StringIO() as buf:
            tree.textio_symbols[Function("io", [])] = buf
            tree.transform(
                meta_string='aspen(print(format("Hello {}", ("World", ())), io)).'
            )
            printed_text = buf.getvalue()
            self.assertEqual(printed_text, "Hello World\n")

    def test_transform_print_to_source(self) -> None:
        """Test that if Source is a valid source symbol, then
        aspen(print(String, Source)) symbols derived during
        transformation append String to the given Source."""
        self.assert_transform_isomorphic(
            language=clingo_lang,
            sources=[""],
            meta_string='aspen(print("a.", s(0))).',
            expected_sources=["a.\n"],
        )

    def test_write_default_destination_prints_to_stdout(self) -> None:
        """Test that a source parsed with no destination (the
        default) is printed to stdout by write()."""
        tree = AspenTree(default_language=clingo_lang)
        tree.parse("a :- b.")
        with redirect_stdout(StringIO()) as buf:
            tree.write()
            self.assertEqual(buf.getvalue(), "a :- b.\n")

    def test_write_to_file_destination(self) -> None:
        """Test that a source parsed with a destination path has its
        text written there instead of printed."""
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.lp"
            tree = AspenTree(default_language=clingo_lang)
            tree.parse("a :- b.", destination=out_path)
            with redirect_stdout(StringIO()) as buf:
                tree.write()
                self.assertEqual(buf.getvalue(), "")
            self.assertEqual(out_path.read_text(), "a :- b.\n")

    def test_write_multiple_sources_in_parse_order(self) -> None:
        """Test that write() handles every source, in the order they
        were parsed, each according to its own destination."""
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.lp"
            tree = AspenTree(default_language=clingo_lang)
            tree.parse("a.", destination=out_path)
            tree.parse("b.")
            tree.parse("c.")
            with redirect_stdout(StringIO()) as buf:
                tree.write()
                self.assertEqual(buf.getvalue(), "b.\nc.\n")
            self.assertEqual(out_path.read_text(), "a.\n")

    def test_write_after_transform_writes_transformed_text(self) -> None:
        """Test that write() reflects a source's current, possibly
        transformed text, not its text at parse time."""
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.lp"
            tree = AspenTree(default_language=clingo_lang)
            tree.parse("a :- b.", destination=out_path)
            tree.transform(
                meta_files=[encoding_dir / "add_var.lp"],
                initial_program=("add_var_to_atoms", [String("X")]),
            )
            tree.write()
            self.assertEqual(out_path.read_text(), "a(X) :- b(X).\n")
