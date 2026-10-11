"""A small declarative mechanism for matching clingo Symbols,
replacing hand-written chains of type/name/arity checks with a flat,
composable description of expected shapes and what to do once one is
matched. SymbolSpec is the base of a small boolean algebra: Func, Num,
Str and Tup are leaves mirroring clingo's own Symbol/Function/Number/
String API, combined with At/AnyOf/AllOf/Not, with Check as an escape
hatch. Func and Tup also carry an optional action, so dispatch and
shape-checking are the same mechanism - a nested dispatch table is
just At(index, AnyOf([...Func/Tup instances with actions...]))."""

import abc
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence

from clingo.symbol import Symbol, SymbolType

__all__ = [
    "AllOf",
    "AnyOf",
    "At",
    "Check",
    "Func",
    "Not",
    "Num",
    "Str",
    "SymbolSpec",
    "Tup",
    "dispatch_symbols",
]


class SymbolSpec(abc.ABC):
    """A composable predicate over a symbol. Built from Func/Num/Str/
    Tup leaves combined with At/AnyOf/AllOf/Not, with Check as an
    escape hatch for validation the others can't express."""

    @abc.abstractmethod
    def matches(self, symb: Symbol) -> bool:
        """Whether symb satisfies this spec."""


@dataclass(frozen=True)
class Func(SymbolSpec):
    """Matches a Function symbol with the given name - mirroring
    clingo.symbol.Function - optionally constrained by arity (any
    arity matches when omitted), by positive/negative sign, and/or by
    an extra shape.

    On a match, action - if given - runs as a side effect, receiving
    the whole matched symbol so it can pull out whichever arguments it
    needs via symb.arguments. A Func with no action is a pure shape
    check, usable anywhere a SymbolSpec is expected.

    That is also how nested dispatch works, since Func is itself a
    SymbolSpec: At(index, AnyOf([Func(...), Func(...), ...])) descends
    into an argument and tries each alternative in turn, running the
    first match's action - a nested dispatch table expressed with the
    same machinery used for plain validation, instead of a second one.

    shape, if given, is checked only after the name/arity/sign check
    passes, and can still reject the match (e.g. when one particular
    argument must itself have a certain shape, without descending into
    it for the action) - rejection means matches() returns False
    without running action.
    """

    name: str
    arity: Optional[int] = None
    positive: bool = True
    action: Optional[Callable[[Symbol], None]] = None
    shape: Optional[SymbolSpec] = None

    def matches(self, symb: Symbol) -> bool:
        if symb.type != SymbolType.Function or symb.positive != self.positive:
            return False
        if symb.name != self.name:
            return False
        if self.arity is not None and len(symb.arguments) != self.arity:
            return False
        if self.shape is not None and not self.shape.matches(symb):
            return False
        if self.action is not None:
            self.action(symb)
        return True


class Tup(Func):
    """Matches a plain tuple - mirroring clingo.symbol.Tuple_ - shorthand
    for Func(name="", ...), optionally constrained by arity (any arity
    matches when omitted) and/or by an extra shape. action behaves the
    same as on Func."""

    def __init__(
        self,
        arity: Optional[int] = None,
        action: Optional[Callable[[Symbol], None]] = None,
        shape: Optional[SymbolSpec] = None,
    ) -> None:
        super().__init__(name="", arity=arity, action=action, shape=shape)


@dataclass(frozen=True)
class Num(SymbolSpec):
    """Matches a Number symbol - mirroring clingo.symbol.Number -
    optionally constrained to the given value (any value matches when
    omitted). On a match, action - if given - runs as a side effect,
    the same as on Func."""

    number: Optional[int] = None
    action: Optional[Callable[[Symbol], None]] = None

    def matches(self, symb: Symbol) -> bool:
        if symb.type != SymbolType.Number:
            return False
        if self.number is not None and symb.number != self.number:
            return False
        if self.action is not None:
            self.action(symb)
        return True


@dataclass(frozen=True)
class Str(SymbolSpec):
    """Matches a String symbol - mirroring clingo.symbol.String -
    optionally constrained to the given value (any value matches when
    omitted). On a match, action - if given - runs as a side effect,
    the same as on Func."""

    string: Optional[str] = None
    action: Optional[Callable[[Symbol], None]] = None

    def matches(self, symb: Symbol) -> bool:
        if symb.type != SymbolType.String:
            return False
        if self.string is not None and symb.string != self.string:
            return False
        if self.action is not None:
            self.action(symb)
        return True


@dataclass(frozen=True)
class Check(SymbolSpec):
    """Escape hatch: matches when predicate(symb) is true, for
    validation that doesn't reduce to a type/name/arity check - e.g.
    comparing two arguments to each other, or checking a Number's
    value. Composes with At/AnyOf/AllOf/Not like any other SymbolSpec,
    so it only has to cover the one condition that needs a callback,
    not the whole shape."""

    predicate: Callable[[Symbol], bool]

    def matches(self, symb: Symbol) -> bool:
        return self.predicate(symb)


@dataclass(frozen=True)
class At(SymbolSpec):
    """Descends into symb.arguments[index], then checks shape against
    that argument instead of against symb itself. shape may itself be
    an At, which is what lets a shape reach arguments of arguments, to
    any depth - e.g. At(1, At(0, Func(name="foo", arity=1))) checks
    symb.arguments[1].arguments[0]. shape can also be a Func/Tup with
    an action (or an AnyOf of several), which is what turns At into a
    way to dispatch into a nested argument instead of merely checking
    it - see Func's docstring."""

    index: int
    shape: SymbolSpec

    def matches(self, symb: Symbol) -> bool:
        return self.shape.matches(symb.arguments[self.index])


@dataclass(frozen=True)
class AnyOf(SymbolSpec):
    """Matches when at least one of options matches, trying them in
    order and stopping at the first match via short-circuit evaluation
    - so if an option is a Func/Tup with a side-effecting action, only
    the first match's action runs, exactly like a dispatch table's
    first-match-wins semantics."""

    options: Sequence[SymbolSpec]

    def matches(self, symb: Symbol) -> bool:
        return any(option.matches(symb) for option in self.options)


@dataclass(frozen=True)
class AllOf(SymbolSpec):
    """Matches when every one of options matches."""

    options: Sequence[SymbolSpec]

    def matches(self, symb: Symbol) -> bool:
        return all(option.matches(symb) for option in self.options)


@dataclass(frozen=True)
class Not(SymbolSpec):
    """Matches when shape does not - included for symmetry, though
    none of the shapes currently needed use negation."""

    shape: SymbolSpec

    def matches(self, symb: Symbol) -> bool:
        return not self.shape.matches(symb)


def dispatch_symbols(symbols: Iterable[Symbol], spec: SymbolSpec) -> None:
    """Try spec against each symbol, running its action (if any) on a
    match. A symbol not matching spec is silently skipped. To try
    several alternatives, pass spec=AnyOf([...]) - dispatch_symbols
    itself only ever applies the one spec it's given."""
    for symb in symbols:
        spec.matches(symb)
