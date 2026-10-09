"""A small declarative mechanism for matching clingo Symbols,
replacing hand-written chains of name/arity checks with a flat,
composable description of expected shapes and what to do once one is
matched. SymbolSpec is the base of a small boolean algebra (built
from Is leaves combined with At/AnyOf/AllOf/Not, with Check as an
escape hatch); Is itself carries an optional action, so dispatch and
shape-checking are the same mechanism - a nested dispatch table is
just At(index, AnyOf([...Is instances with actions...]))."""

import abc
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence

from clingo.symbol import Symbol, SymbolType

__all__ = [
    "AllOf",
    "AnyOf",
    "At",
    "Check",
    "Is",
    "Not",
    "SymbolSpec",
    "dispatch_symbols",
]


class SymbolSpec(abc.ABC):
    """A composable predicate over a symbol. Built from Is leaves
    combined with At/AnyOf/AllOf/Not, with Check as an escape hatch
    for validation the others can't express."""

    @abc.abstractmethod
    def matches(self, symb: Symbol) -> bool:
        """Whether symb satisfies this spec."""


@dataclass(frozen=True)
class Is(SymbolSpec):
    """Matches when the given symbol itself has the given SymbolType
    and/or Function name+arity, and/or an extra shape - fields left
    as None are unconstrained. name="" with some arity matches a
    plain tuple, the same shape Symbol.match("", arity) checks for.

    On a match, action - if given - runs as a side effect, receiving
    the whole matched symbol so it can pull out whichever arguments it
    needs via symb.arguments. An Is with no action is a pure shape
    check, usable anywhere a SymbolSpec is expected.

    That is also how nested dispatch works, since Is is itself a
    SymbolSpec: At(index, AnyOf([Is(...), Is(...), ...])) descends
    into an argument and tries each alternative in turn, running the
    first match's action - a nested dispatch table expressed with the
    same machinery used for plain validation, instead of a second one.

    shape, if given, is checked only after the type/name/arity check
    passes, and can still reject the match (e.g. when one particular
    argument must itself have a certain shape, without descending into
    it for the action) - rejection means matches() returns False
    without running action.
    """

    name: Optional[str] = None
    arity: Optional[int] = None
    positive: bool = True
    action: Optional[Callable[[Symbol], None]] = None
    shape: Optional[SymbolSpec] = None
    type: Optional[SymbolType] = None

    def matches(self, symb: Symbol) -> bool:
        if self.type is not None and symb.type != self.type:
            return False
        if self.name is not None or self.arity is not None:
            if symb.type != SymbolType.Function or not symb.positive:
                return False
            if self.name is not None and symb.name != self.name:
                return False
            if self.arity is not None and len(symb.arguments) != self.arity:
                return False
        if self.shape is not None and not self.shape.matches(symb):
            return False
        if self.action is not None:
            self.action(symb)
        return True


@dataclass(frozen=True)
class Check(SymbolSpec):
    """Escape hatch: matches when predicate(symb) is true, for
    validation that doesn't reduce to a SymbolType/name/arity check -
    e.g. comparing two arguments to each other, or checking a
    Number's value. Composes with At/AnyOf/AllOf/Not like any other
    SymbolSpec, so it only has to cover the one condition that needs a
    callback, not the whole shape."""

    predicate: Callable[[Symbol], bool]

    def matches(self, symb: Symbol) -> bool:
        return self.predicate(symb)


@dataclass(frozen=True)
class At(SymbolSpec):
    """Descends into symb.arguments[index], then checks shape against
    that argument instead of against symb itself. shape may itself be
    an At, which is what lets a shape reach arguments of arguments, to
    any depth - e.g. At(1, At(0, Is(name="foo", arity=1))) checks
    symb.arguments[1].arguments[0]. shape can also be an Is with an
    action (or an AnyOf of several), which is what turns At into a way
    to dispatch into a nested argument instead of merely checking it -
    see Is's docstring."""

    index: int
    shape: SymbolSpec

    def matches(self, symb: Symbol) -> bool:
        return self.shape.matches(symb.arguments[self.index])


@dataclass(frozen=True)
class AnyOf(SymbolSpec):
    """Matches when at least one of options matches, trying them in
    order and stopping at the first match via short-circuit evaluation
    - so if an option is an Is with a side-effecting action, only the
    first match's action runs, exactly like a dispatch table's
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
        spec
