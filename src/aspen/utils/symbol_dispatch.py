"""A small declarative dispatcher for clingo Symbols, replacing
hand-written chains of name/arity checks with a flat table of
expected shapes and what to do once one is matched - including
shapes nested arbitrarily deep inside one another."""

from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence, Union

from clingo.symbol import Symbol, SymbolType

__all__ = ["Descend", "SymbolSpec", "dispatch_symbols"]


@dataclass(frozen=True)
class Descend:
    """A SymbolSpec action that, instead of calling a leaf callback,
    continues matching: it takes the symbol's argument at arg_index
    and dispatches it against a nested list of specs.

    Those nested specs may themselves use Descend, which is what
    lets a spec table express symbols nested to any depth - e.g.
    aspen(exception(syntax_error(node(N)))) - as one declarative
    tree instead of a one-off unwrapping helper per level.
    """

    arg_index: int
    specs: Sequence["SymbolSpec"]


@dataclass(frozen=True)
class SymbolSpec:
    """One expected shape of a clingo Symbol: a positive function
    symbol with the given name and arity.

    On a match, action runs: either a plain callback, invoked with
    the whole matched symbol (so it can pull out whichever arguments
    it needs via symb.arguments), or a Descend (see above), which
    continues matching one of the symbol's own arguments against a
    nested spec list instead. Together this keeps a spec table a
    flat-ish, declarative description of the expected shapes - even
    nested ones - instead of a chain of hand-written type/name/arity
    checks with manual unwrapping in between.

    guard, if given, runs only after the name/arity check passes and
    can still reject the match (e.g. when one particular argument
    must itself have a certain shape, without descending into it) -
    rejection falls through to the next spec instead of running
    action.
    """

    name: str
    arity: int
    action: Union[Callable[[Symbol], None], Descend]
    guard: Optional[Callable[[Symbol], bool]] = None

    def try_dispatch(self, symb: Symbol) -> bool:
        """Try to match symb against this spec: on a match, run
        action and return True; otherwise return False without any
        side effects."""
        if (
            symb.type != SymbolType.Function
            or not symb.positive
            or symb.name != self.name
            or len(symb.arguments) != self.arity
        ):
            return False
        if self.guard is not None and not self.guard(symb):
            return False
        if isinstance(self.action, Descend):
            dispatch_symbols([symb.arguments[self.action.arg_index]], self.action.specs)
        else:
            self.action(symb)
        return True


def dispatch_symbols(symbols: Iterable[Symbol], specs: Sequence[SymbolSpec]) -> None:
    """Try each symbol against each spec in order, invoking the first
    matching spec's action. A symbol matching no spec is silently
    skipped."""
    for symb in symbols:
        for spec in specs:
            if spec.try_dispatch(symb):
                break
