"""Unit tests for aspen.utils.symbol_dispatch."""

from unittest import TestCase

from clingo.symbol import Function, Number, String, Symbol

from aspen.utils.symbol_dispatch import Descend, SymbolSpec, dispatch_symbols


class TestSymbolSpec(TestCase):
    """Test SymbolSpec.try_dispatch directly."""

    def test_try_dispatch_matches_name_and_arity(self) -> None:
        """Test that a symbol matching the spec's name and arity is
        dispatched to the callback, which receives the whole symbol."""
        seen: list[Symbol] = []
        spec = SymbolSpec("foo", 2, seen.append)
        symb = Function("foo", [Number(1), Number(2)])
        self.assertTrue(spec.try_dispatch(symb))
        self.assertEqual(seen, [symb])

    def test_try_dispatch_rejects_wrong_name(self) -> None:
        """Test that a symbol with a different name doesn't match,
        and the callback is never called."""
        seen: list[Symbol] = []
        spec = SymbolSpec("foo", 1, seen.append)
        symb = Function("bar", [Number(1)])
        self.assertFalse(spec.try_dispatch(symb))
        self.assertEqual(seen, [])

    def test_try_dispatch_rejects_wrong_arity(self) -> None:
        """Test that a symbol with the right name but a different
        arity doesn't match."""
        seen: list[Symbol] = []
        spec = SymbolSpec("foo", 2, seen.append)
        symb = Function("foo", [Number(1)])
        self.assertFalse(spec.try_dispatch(symb))
        self.assertEqual(seen, [])

    def test_try_dispatch_rejects_non_function_symbol(self) -> None:
        """Test that a non-function symbol (e.g. a string) never
        matches, regardless of name/arity."""
        spec = SymbolSpec("foo", 0, lambda symb: None)
        self.assertFalse(spec.try_dispatch(String("foo")))

    def test_try_dispatch_rejects_negative_symbol(self) -> None:
        """Test that a negative function symbol (-foo(1)) doesn't
        match a spec for the (positive) name 'foo'."""
        seen: list[Symbol] = []
        spec = SymbolSpec("foo", 1, seen.append)
        symb = Function("foo", [Number(1)], False)
        self.assertFalse(spec.try_dispatch(symb))
        self.assertEqual(seen, [])

    def test_try_dispatch_guard_can_reject_a_name_arity_match(self) -> None:
        """Test that a guard runs after the name/arity check and can
        still reject the match, in which case the callback is never
        called."""
        seen: list[Symbol] = []
        spec = SymbolSpec(
            "foo",
            1,
            seen.append,
            guard=lambda symb: symb.arguments[0].match("bar", 0),
        )
        matching = Function("foo", [Function("bar", [])])
        rejected = Function("foo", [Function("baz", [])])
        self.assertTrue(spec.try_dispatch(matching))
        self.assertFalse(spec.try_dispatch(rejected))
        self.assertEqual(seen, [matching])

    def test_try_dispatch_descend_dispatches_into_argument(self) -> None:
        """Test that a Descend action matches the outer symbol, then
        dispatches the argument at arg_index against the nested
        specs, instead of calling a leaf callback on the outer
        symbol itself."""
        seen: list[Symbol] = []
        inner = Function("bar", [Number(1)])
        spec = SymbolSpec("aspen", 1, Descend(0, [SymbolSpec("bar", 1, seen.append)]))
        outer = Function("aspen", [inner])
        self.assertTrue(spec.try_dispatch(outer))
        self.assertEqual(seen, [inner])

    def test_try_dispatch_descend_uses_given_arg_index(self) -> None:
        """Test that Descend descends into the argument at the given
        index, not just the first one."""
        seen: list[Symbol] = []
        second = Function("bar", [])
        spec = SymbolSpec("wrap", 2, Descend(1, [SymbolSpec("bar", 0, seen.append)]))
        outer = Function("wrap", [Number(1), second])
        self.assertTrue(spec.try_dispatch(outer))
        self.assertEqual(seen, [second])

    def test_try_dispatch_descend_no_match_is_silent(self) -> None:
        """Test that the outer symbol still matches (and action still
        runs) even when nothing inside the nested specs matches the
        descended-into argument - Descend itself never fails once the
        outer name/arity/guard have matched."""
        inner = Function("baz", [])
        spec = SymbolSpec(
            "aspen", 1, Descend(0, [SymbolSpec("bar", 0, lambda symb: None)])
        )
        outer = Function("aspen", [inner])
        self.assertTrue(spec.try_dispatch(outer))

    def test_try_dispatch_descend_arbitrarily_nested(self) -> None:
        """Test that Descend actions can nest to any depth, each one
        wrapping the next: matching a 3-levels-deep w1(w2(w3(leaf)))
        shape by descending through w1, w2 and w3 in turn, recovering
        leaf at the bottom."""
        seen: list[Symbol] = []
        leaf = Function("leaf", [])
        symb = Function("w1", [Function("w2", [Function("w3", [leaf])])])

        leaf_specs = [SymbolSpec("leaf", 0, seen.append)]
        w3_specs = [SymbolSpec("w3", 1, Descend(0, leaf_specs))]
        w2_specs = [SymbolSpec("w2", 1, Descend(0, w3_specs))]
        top_specs = [SymbolSpec("w1", 1, Descend(0, w2_specs))]

        dispatch_symbols([symb], top_specs)
        self.assertEqual(seen, [leaf])


class TestDispatchSymbols(TestCase):
    """Test dispatch_symbols."""

    def test_dispatch_symbols_picks_first_matching_spec(self) -> None:
        """Test that each symbol is dispatched to the first spec that
        matches it, trying specs in the given order."""
        first_seen: list[Symbol] = []
        second_seen: list[Symbol] = []
        specs = [
            SymbolSpec("foo", 1, first_seen.append),
            SymbolSpec("foo", 1, second_seen.append),
        ]
        symb = Function("foo", [Number(1)])
        dispatch_symbols([symb], specs)
        self.assertEqual(first_seen, [symb])
        self.assertEqual(second_seen, [])

    def test_dispatch_symbols_tries_later_specs_on_no_match(self) -> None:
        """Test that a symbol not matching one spec is still tried
        against the rest."""
        seen: list[Symbol] = []
        specs = [
            SymbolSpec("foo", 2, lambda symb: None),
            SymbolSpec("foo", 1, seen.append),
        ]
        symb = Function("foo", [Number(1)])
        dispatch_symbols([symb], specs)
        self.assertEqual(seen, [symb])

    def test_dispatch_symbols_skips_symbols_matching_nothing(self) -> None:
        """Test that a symbol matching no spec at all is silently
        skipped, rather than raising."""
        seen: list[Symbol] = []
        specs = [SymbolSpec("foo", 1, seen.append)]
        dispatch_symbols([Function("bar", [])], specs)
        self.assertEqual(seen, [])
