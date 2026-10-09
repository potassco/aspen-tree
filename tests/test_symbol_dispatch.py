"""Unit tests for aspen.utils.symbol_dispatch."""

from unittest import TestCase

from clingo.symbol import Function, Number, String, Symbol, SymbolType

from aspen.utils.symbol_dispatch import (
    AllOf,
    AnyOf,
    At,
    Check,
    Is,
    Not,
    SymbolSpec,
    dispatch_symbols,
)


class TestIs(TestCase):
    """Test Is directly: the single concrete SymbolSpec leaf, merging
    a type/name/arity check with an optional dispatch action."""

    def test_is_type(self) -> None:
        """Test that Is(type=...) checks the given symbol's SymbolType
        directly."""
        shape = Is(type=SymbolType.String)
        self.assertTrue(shape.matches(String("x")))
        self.assertFalse(shape.matches(Number(1)))

    def test_is_name_and_arity(self) -> None:
        """Test that Is(name=..., arity=...) checks the symbol's
        Function name and arity together."""
        shape = Is(name="bar", arity=1)
        self.assertTrue(shape.matches(Function("bar", [Number(1)])))
        self.assertFalse(shape.matches(Function("bar", [])))
        self.assertFalse(shape.matches(Function("baz", [Number(1)])))

    def test_is_name_only_any_arity(self) -> None:
        """Test that Is(name=...) with no arity accepts any arity,
        matching only on the name."""
        shape = Is(name="bar")
        self.assertTrue(shape.matches(Function("bar", [])))
        self.assertTrue(shape.matches(Function("bar", [Number(1), Number(2)])))
        self.assertFalse(shape.matches(Function("baz", [])))

    def test_is_name_or_arity_rejects_non_function_symbol(self) -> None:
        """Test that checking name/arity on a non-Function symbol
        (e.g. a Number) fails cleanly instead of raising."""
        shape = Is(name="bar")
        self.assertFalse(shape.matches(Number(1)))

    def test_is_name_and_arity_matches_dispatches_to_action(self) -> None:
        """Test that a symbol matching name and arity is dispatched to
        the action, which receives the whole symbol."""
        seen: list[Symbol] = []
        spec = Is("foo", 2, seen.append)
        symb = Function("foo", [Number(1), Number(2)])
        self.assertTrue(spec.matches(symb))
        self.assertEqual(seen, [symb])

    def test_is_rejects_wrong_name_without_running_action(self) -> None:
        """Test that a symbol with a different name doesn't match,
        and the action is never called."""
        seen: list[Symbol] = []
        spec = Is("foo", 1, seen.append)
        symb = Function("bar", [Number(1)])
        self.assertFalse(spec.matches(symb))
        self.assertEqual(seen, [])

    def test_is_rejects_wrong_arity_without_running_action(self) -> None:
        """Test that a symbol with the right name but a different
        arity doesn't match."""
        seen: list[Symbol] = []
        spec = Is("foo", 2, seen.append)
        symb = Function("foo", [Number(1)])
        self.assertFalse(spec.matches(symb))
        self.assertEqual(seen, [])

    def test_is_rejects_non_function_symbol_even_with_an_action(self) -> None:
        """Test that a non-function symbol (e.g. a string) never
        matches a name/arity check, regardless of an action."""
        spec = Is("foo", 0, lambda symb: None)
        self.assertFalse(spec.matches(String("foo")))

    def test_is_rejects_negative_symbol(self) -> None:
        """Test that a negative function symbol (-foo(1)) doesn't
        match a spec for the (positive) name 'foo'."""
        seen: list[Symbol] = []
        spec = Is("foo", 1, seen.append)
        symb = Function("foo", [Number(1)], False)
        self.assertFalse(spec.matches(symb))
        self.assertEqual(seen, [])

    def test_is_with_no_action_is_a_pure_shape_check(self) -> None:
        """Test that an Is with no action just checks the shape and
        runs nothing - usable anywhere a SymbolSpec is expected, the
        same role At(0, Is(name=...)) already relies on."""
        spec = Is("foo", 1)
        self.assertTrue(spec.matches(Function("foo", [Number(1)])))
        self.assertFalse(spec.matches(Function("bar", [Number(1)])))

    def test_is_shape_can_reject_a_name_arity_match(self) -> None:
        """Test that shape is checked after the name/arity check and
        can still reject the match, in which case the action is never
        called."""
        seen: list[Symbol] = []
        spec = Is(
            "foo",
            1,
            seen.append,
            shape=At(0, Is(name="bar", arity=0)),
        )
        matching = Function("foo", [Function("bar", [])])
        rejected = Function("foo", [Function("baz", [])])
        self.assertTrue(spec.matches(matching))
        self.assertFalse(spec.matches(rejected))
        self.assertEqual(seen, [matching])

    def test_at_any_of_dispatches_into_argument(self) -> None:
        """Test that At(index, AnyOf([...])) dispatches into a nested
        argument: it descends into the argument at index and tries
        each nested Is in turn, running the first match's action,
        instead of calling an action on the outer symbol itself."""
        seen: list[Symbol] = []
        inner = Function("bar", [Number(1)])
        spec = Is("aspen", 1, shape=At(0, AnyOf([Is("bar", 1, seen.append)])))
        outer = Function("aspen", [inner])
        self.assertTrue(spec.matches(outer))
        self.assertEqual(seen, [inner])

    def test_at_uses_given_arg_index_for_dispatch(self) -> None:
        """Test that the At wrapping a nested dispatch table descends
        into the argument at the given index, not just the first
        one."""
        seen: list[Symbol] = []
        second = Function("bar", [])
        spec = Is("wrap", 2, shape=At(1, AnyOf([Is("bar", 0, seen.append)])))
        outer = Function("wrap", [Number(1), second])
        self.assertTrue(spec.matches(outer))
        self.assertEqual(seen, [second])

    def test_at_any_of_tries_alternatives_in_order(self) -> None:
        """Test that a nested AnyOf of several Is instances tries them
        in order and runs only the first match's action - first-match-
        wins dispatch semantics, expressed with the same machinery
        used for plain shape-checking."""
        first_seen: list[Symbol] = []
        second_seen: list[Symbol] = []
        inner = Function("bar", [Number(1)])
        first_spec = Is("bar", 1, first_seen.append)
        second_spec = Is("bar", 1, second_seen.append)
        alternatives = AnyOf([first_spec, second_spec])
        spec = Is("aspen", 1, shape=At(0, alternatives))
        outer = Function("aspen", [inner])
        self.assertTrue(spec.matches(outer))
        self.assertEqual(first_seen, [inner])
        self.assertEqual(second_seen, [])

    def test_at_any_of_no_match_leaves_outer_unmatched_without_raising(self) -> None:
        """Test that when nothing in the nested AnyOf matches the
        descended-into argument, the outer spec doesn't match either -
        but nothing raises, and no action runs."""
        inner = Function("baz", [])
        spec = Is("aspen", 1, shape=At(0, AnyOf([Is("bar", 0, lambda symb: None)])))
        outer = Function("aspen", [inner])
        self.assertFalse(spec.matches(outer))

    def test_is_nests_arbitrarily_as_a_shape(self) -> None:
        """Test that Is can be nested via At to any depth: matching a
        3-levels-deep w1(w2(w3(leaf))) shape by descending through w1,
        w2 and w3 in turn and running leaf's action at the bottom -
        the same mechanism used for plain shape-checking, with no
        separate dispatch-only construct needed."""
        seen: list[Symbol] = []
        leaf = Function("leaf", [])
        symb = Function("w1", [Function("w2", [Function("w3", [leaf])])])

        spec = Is(
            "w1",
            1,
            shape=At(
                0,
                Is(
                    "w2",
                    1,
                    shape=At(0, Is("w3", 1, shape=At(0, Is("leaf", 0, seen.append)))),
                ),
            ),
        )
        self.assertTrue(spec.matches(symb))
        self.assertEqual(seen, [leaf])


class TestShapeCombinators(TestCase):
    """Test At, AnyOf, AllOf, Not and Check directly - the pure,
    action-free SymbolSpec combinators Is composes with."""

    def test_at_descends_into_argument(self) -> None:
        """Test that At(index, shape) checks shape against
        symb.arguments[index], not against symb itself."""
        shape = At(0, Is(name="bar", arity=1))
        self.assertTrue(shape.matches(Function("f", [Function("bar", [Number(1)])])))
        self.assertFalse(shape.matches(Function("f", [Function("baz", [Number(1)])])))

    def test_at_uses_given_index(self) -> None:
        """Test that At descends into the argument at the given
        index, not just the first one."""
        shape = At(1, Is(name="bar", arity=0))
        self.assertTrue(shape.matches(Function("f", [Number(1), Function("bar", [])])))
        self.assertFalse(shape.matches(Function("f", [Function("bar", []), Number(1)])))

    def test_at_nests_to_match_argument_of_argument(self) -> None:
        """Test that At can nest, reaching an argument of an argument
        (and deeper)."""
        shape = At(1, At(0, Is(name="foo", arity=1)))
        matching = Function(
            "f", [Number(1), Function("g", [Function("foo", [Number(2)])])]
        )
        wrong_inner = Function(
            "f", [Number(1), Function("g", [Function("bar", [Number(2)])])]
        )
        self.assertTrue(shape.matches(matching))
        self.assertFalse(shape.matches(wrong_inner))

    def test_any_of_matches_when_one_option_matches(self) -> None:
        """Test that AnyOf matches as soon as any option matches."""
        shape = AnyOf([At(0, Is(name="", arity=2)), At(0, Is(name="", arity=0))])
        self.assertTrue(shape.matches(Function("f", [Function("", [Number(1)] * 2)])))
        self.assertTrue(shape.matches(Function("f", [Function("", [])])))
        self.assertFalse(shape.matches(Function("f", [Function("", [Number(1)])])))

    def test_all_of_requires_every_option(self) -> None:
        """Test that AllOf only matches when every option matches,
        and that options may constrain different argument indices."""
        shape = AllOf([At(0, Is(type=SymbolType.String)), At(1, Is(name="", arity=2))])
        matching = Function("f", [String("x"), Function("", [Number(1), Number(2)])])
        wrong_first = Function("f", [Number(1), Function("", [Number(1), Number(2)])])
        wrong_second = Function("f", [String("x"), Function("", [Number(1)])])
        self.assertTrue(shape.matches(matching))
        self.assertFalse(shape.matches(wrong_first))
        self.assertFalse(shape.matches(wrong_second))

    def test_any_of_can_combine_different_argument_indices(self) -> None:
        """Test that AnyOf can express an OR across different
        argument positions, not just alternatives at one position."""
        shape = AnyOf([At(0, Is(name="foo", arity=1)), At(1, Is(name="bar", arity=2))])
        matches_first = Function("f", [Function("foo", [Number(1)]), Number(2)])
        matches_second = Function(
            "f", [Number(1), Function("bar", [Number(1), Number(2)])]
        )
        matches_neither = Function("f", [Number(1), Number(2)])
        self.assertTrue(shape.matches(matches_first))
        self.assertTrue(shape.matches(matches_second))
        self.assertFalse(shape.matches(matches_neither))

    def test_not_negates_a_shape(self) -> None:
        """Test that Not inverts whatever shape it wraps."""
        shape = Not(At(0, Is(type=SymbolType.String)))
        self.assertFalse(shape.matches(Function("f", [String("x")])))
        self.assertTrue(shape.matches(Function("f", [Number(1)])))

    def test_check_runs_the_given_predicate(self) -> None:
        """Test that Check matches exactly when its predicate returns
        true for the given symbol - the escape hatch for validation
        that isn't a SymbolType/name/arity check, e.g. a Number's
        value, or comparing two arguments to each other."""
        shape = Check(lambda symb: symb.arguments[0].number > symb.arguments[1].number)
        self.assertTrue(shape.matches(Function("f", [Number(2), Number(1)])))
        self.assertFalse(shape.matches(Function("f", [Number(1), Number(2)])))

    def test_check_composes_with_at_and_any_of(self) -> None:
        """Test that Check is just another SymbolSpec: it can be
        descended into via At, and combined with AnyOf/AllOf/Not like
        any other shape - it only has to cover the one condition that
        needs a callback, not the whole shape."""
        shape = AllOf(
            [
                At(0, Is(type=SymbolType.Number)),
                At(0, Check(lambda symb: symb.number > 0)),
            ]
        )
        self.assertTrue(shape.matches(Function("f", [Number(1)])))
        self.assertFalse(shape.matches(Function("f", [Number(-1)])))
        self.assertFalse(shape.matches(Function("f", [String("x")])))

    def test_all_combinators_are_symbol_specs(self) -> None:
        """Test that every shape - Is included - is a SymbolSpec, the
        single base both pure shape-checks and dispatch-capable specs
        share."""
        shapes: list[SymbolSpec] = [
            Is(name="foo"),
            At(0, Is(name="foo")),
            AnyOf([Is(name="foo")]),
            AllOf([Is(name="foo")]),
            Not(Is(name="foo")),
            Check(lambda symb: True),
        ]
        for shape in shapes:
            self.assertIsInstance(shape, SymbolSpec)


class TestDispatchSymbols(TestCase):
    """Test dispatch_symbols. It takes a single spec; trying several
    alternatives in order, first-match-wins, is AnyOf's job - the
    caller wraps specs in AnyOf([...]) itself when that's needed."""

    def test_dispatch_symbols_runs_action_on_each_matching_symbol(self) -> None:
        """Test that every symbol matching spec has its action run,
        receiving that symbol."""
        seen: list[Symbol] = []
        spec = Is("foo", 1, seen.append)
        matching = Function("foo", [Number(1)])
        dispatch_symbols([matching], spec)
        self.assertEqual(seen, [matching])

    def test_dispatch_symbols_skips_symbols_matching_nothing(self) -> None:
        """Test that a symbol not matching spec is silently skipped,
        rather than raising."""
        seen: list[Symbol] = []
        spec = Is("foo", 1, seen.append)
        dispatch_symbols([Function("bar", [])], spec)
        self.assertEqual(seen, [])

    def test_dispatch_symbols_with_any_of_picks_first_matching_alternative(self) -> None:
        """Test that passing spec=AnyOf([...]) lets a caller try
        several alternatives in order, running only the first match's
        action - dispatch_symbols itself stays single-spec."""
        first_seen: list[Symbol] = []
        second_seen: list[Symbol] = []
        spec = AnyOf([Is("foo", 1, first_seen.append), Is("foo", 1, second_seen.append)])
        symb = Function("foo", [Number(1)])
        dispatch_symbols([symb], spec)
        self.assertEqual(first_seen, [symb])
        self.assertEqual(second_seen, [])
