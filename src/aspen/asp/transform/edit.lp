#include "@aspen/generic/queries/path_of_node.lp".

#script (python)

from clingo.symbol import Symbol, String

def symbol_to_string(symbol: Symbol) -> String:
    return String(str(symbol))

#end.

% This encoding orders the edits derived by a meta-encoding, and
% queries the paths of the nodes they refer to, so that aspen can find
% them in the sources. Its helper predicates start with _aspen, and
% are not terms of aspen/1, so that the grounder can estimate the
% sizes of their joins separately.

aspen(replace(T, "")) :- aspen(delete(T)).

% _aspen_edit(Edit, Target, Template): the edits.
_aspen_edit(replace(T, S), T, S) :- aspen(replace(T, S)).
_aspen_edit(append(T, S), T, S) :- aspen(append(T, S)).
_aspen_edit(prepend(T, S), T, S) :- aspen(prepend(T, S)).

% _aspen_item(Template, Item): the templates of edits and messages,
% and the templates they contain.
_aspen_item(S, S) :- _aspen_edit(_, _, S).
_aspen_item(S, S) :-
  aspen(log(_, _, S);log(_, S);print(S);print(S, _);exception(_, S);exception(S)).

_aspen_list(S, L) :- _aspen_item(S, (format(_, L);join(_, L))).
_aspen_list(S, L) :- _aspen_list(S, (_, L)).
_aspen_item(S, I) :- _aspen_list(S, (I, _)).

% In mutate(Base, Edits), the base is inserted like any other item. The
% edits (an edit or a list of edits) are not applied to the source, so
% they are not ordered with other edits; only their templates are items.
_aspen_item(S, B) :- _aspen_item(S, mutate(B, _)).
_aspen_mutate_edits(S, E) :- _aspen_item(S, mutate(_, E)).
_aspen_mutate_edits(S, L) :- _aspen_mutate_edits(S, (_, L)).
_aspen_mutate_edit(S, E) :- _aspen_mutate_edits(S, (E, _)).
_aspen_mutate_edit(S, E) :-
  _aspen_mutate_edits(S, E), E=(replace(_, _);append(_, _);prepend(_, _)).
_aspen_item(S, I) :- _aspen_mutate_edit(S, (replace(_, I);append(_, I);prepend(_, I))).

% _aspen_ref(R): the references to nodes, of the form node(N) or
% span(node(N), node(M)), as targets, items, and locations of messages.
_aspen_ref(R) :- _aspen_edit(_, R, _).
_aspen_ref(R) :- _aspen_item(_, R).
_aspen_ref(R) :- _aspen_item(_, original(R)).
_aspen_ref(R) :- _aspen_mutate_edit(_, (replace(R, _);append(R, _);prepend(R, _))).
_aspen_ref(R) :- aspen(log(R, _, _);exception(R, _)).

% _aspen_ends(R, N, M): reference R covers N and its next siblings up
% to M, which _aspen_covers(R, X) enumerates.
_aspen_ends(node(N), N, N) :- _aspen_ref(node(N)).
_aspen_ends(span(node(N), node(M)), N, M) :- _aspen_ref(span(node(N), node(M))).
_aspen_covers(R, N) :- _aspen_ends(R, N, _).
_aspen_covers(R, X') :- _aspen_covers(R, X), _aspen_ends(R, _, M), X != M, next_sibling(X, X').

% aspen locates references by the paths of their first and last nodes
aspen(query(path_of_node((N;M)))) :- _aspen_ends(_, N, M).

% Ordering: aspen(comes_before(E1, E2)) means that edit E1 must be
% applied before edit E2 for the text of E2 to be correct.

% A template inserting node(N) or a span inserts the text of its nodes
% after the edits of them and of their descendants, so these edits
% come first, except for those of the targets of the edit using the
% template, which are ordered below. The targets of an edit are the
% children of P with indices from Lo to Hi (where the root of a source
% has the parent "none").
_aspen_inserts(E, X) :- _aspen_edit(E, _, S), _aspen_item(S, R), _aspen_covers(R, X).
_aspen_inserts(E, Y) :- _aspen_inserts(E, X), child(X, Y).

_aspen_position(X, P, I) :- child(P, X), child_index(X, I).
_aspen_position(X, none, 0) :- source_root(_, X).
_aspen_range(E, P, Lo, Hi) :-
  _aspen_edit(E, T, _), _aspen_ends(T, N, M), _aspen_position(N, P, Lo), _aspen_position(M, P, Hi).

aspen(comes_before(Inner, E)) :-
  _aspen_inserts(E, X), _aspen_edit(Inner, T, _), _aspen_covers(T, X),
  _aspen_position(X, P', I), _aspen_range(E, P, Lo, Hi), #false : P' = P, Lo <= I, I <= Hi.

% Text appended or prepended to a node becomes part of it, so replacing
% the node (or a span containing it) comes first, as it would overwrite
% the text otherwise.
aspen(comes_before(R, E)) :-
  _aspen_edit(R, T, _), R=replace(_, _), _aspen_covers(T, X),
  _aspen_edit(E, node(X), _), E=(append(_, _);prepend(_, _)).
