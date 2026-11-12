% Compile away all pools of a clingo program in one step, in the same
% way as clingo itself unpools programs.
%
% Each pool belongs to a scope, which is replaced by its variants,
% one for each combination of alternatives of its units:
% - in an aggregate, optimize or theory element, the element is
%   replaced by its variants;
% - otherwise, the statement is replaced by its variants.
% The units of a scope are the pools not nested in other pools, and in
% statements, the conditional literals whose conditions contain pools.
%
% As in clingo, such a conditional literal is replaced by one copy for
% each alternative of its condition, where the pools of its literal
% are unpooled separately in each copy: an alternative of the
% conditional literal chooses an alternative of its literal for each
% copy.
%
% The alternatives of pool items, conditions and literals (holders)
% choose an alternative for each of their slots: the pools directly
% nested in them, and for pool items, the other items and separators
% of the pool, whose only alternative is to remove them.
%
% Lists are built by recursion over the ranks of their elements, by
% prepending single elements. To keep the encoding stratified (which
% would make grounding blow up), lists are not built via the make_list
% query of aspen (queries would depend on returns), and the three
% levels that count the alternatives of the previous one (holders,
% copies of conditional literals, and scopes) use separate predicates.

% pools and their items

pool_type("symbolic_atom";"function";"external_function";"theory_atom";"tuple";"abs").
arg_pool_type("symbolic_atom";"function";"external_function";"theory_atom").

pool_separator(P, S) :- type(P, T), pool_type(T), child(P, S), leaf_text(S, ";").
pool(P) :- pool_separator(P, _).

% the items of argument pools are their arguments, the items of tuples
% and absolute values are their children other than delimiters
pool_item(P, I) :-
  pool(P), type(P, T), arg_pool_type(T),
  child(P, I), field(I, "arguments"), type(I, ("terms";"empty_pool_item")).
pool_item(P, I) :-
  pool(P), type(P, ("tuple";"abs")), child(P, I),
  #false : leaf_text(I, ("(";")";"|";";")).

% conditional literals, their conditions and literals
condition(L, C) :- type(L, "conditional_literal"), child(L, C), field(C, "condition").
literal(L, A) :- type(L, "conditional_literal"), child(L, A), field(A, "literal").

% holders and their slots

holder(I) :- pool_item(_, I).
holder(C) :- condition(_, C).
holder(A) :- literal(L, A), pooled(L).

% the pools directly nested in a holder (an item may be a pool itself)
below(H, H) :- holder(H), not pool(H).
below(H, N') :- below(H, N), child(N, N'), not pool(N').
nested(H, H) :- holder(H), pool(H).
nested(H, Q) :- below(H, N), child(N, Q), pool(Q).

% Choosing an item of a pool removes the separators and the other
% items, and if the chosen item of an argument pool is empty, the
% parentheses (as e.g. @f() is not allowed).
removed(I, S) :- pool_item(P, I), pool_separator(P, S).
removed(I, I') :- pool_item(P, I), pool_item(P, I'), I != I'.
removed(I, N) :-
  pool_item(P, I), type(I, "empty_pool_item"),
  type(P, T), arg_pool_type(T), child(P, N), leaf_text(N, ("(";")")).

slot(H, N) :- removed(H, N).
slot(H, Q) :- nested(H, Q).
slot_rank(H, S, J) :- slot(H, S), J = #count{ S' : slot(H, S'), S' < S }.
num_slots(H, M) :- holder(H), M = #count{ S : slot(H, S) }.

% the alternatives of holders as lists of edits, with ranks to order them

option(H, N, replace(node(N), ""), ()) :- removed(H, N).
option(H, Q, Edit, Rank) :- nested(H, Q), pool_alternative(Q, Edit, Rank).

partial_alternative(H, 0, (), ()) :- holder(H).
partial_alternative(H, J+1, (Edit, Edits), (Rank, R)) :-
  partial_alternative(H, J, Edits, Rank), slot_rank(H, S, J), option(H, S, Edit, R).
alternative(H, Edits, Rank) :- partial_alternative(H, M, Edits, Rank), num_slots(H, M).

pool_alternative(P, replace(node(P), edited(node(P), Edits)), (I, Rank)) :-
  pool_item(P, I), alternative(I, Edits, Rank).

% the alternatives of conditional literals with pooled conditions

pooled(L) :- condition(L, C), nested(C, _).

copy_rank(L, Rank, K) :-
  pooled(L), condition(L, C), alternative(C, _, Rank),
  K = #count{ Rank' : alternative(C, _, Rank'), Rank' < Rank }.
num_copies(L, M) :- pooled(L), condition(L, C), M = #count{ Rank : alternative(C, _, Rank) }.

partial_copies(L, 0, (), ()) :- pooled(L).
partial_copies(L, K+1, (Copy, Copies), (Rank, LitRank)) :-
  partial_copies(L, K, Copies, Rank), copy_rank(L, CondRank, K),
  condition(L, C), alternative(C, Cond, CondRank),
  literal(L, A), alternative(A, Lit, LitRank),
  Copy = edited(node(L), (replace(node(C), edited(node(C), Cond)),
                          (replace(node(A), edited(node(A), Lit)), ()))).
literal_alternative(L, replace(node(L), join("; ", Copies)), Rank) :-
  partial_copies(L, M, Copies, Rank), num_copies(L, M).

% scopes, identified by their node, with the separator of their variants

scope(S, "\n") :- source_root(_, R), child(R, S).
scope(E, "; ") :-
  type(E, ("set_aggregate_element";"body_aggregate_element";"head_aggregate_element";
           "optimize_element";"theory_element")).

% The region of a scope contains its nodes outside of nested scopes,
% the conditions of conditional literals, and the literals of pooled
% ones. As it ends at pools, the pools in it are not nested in others.
region(R, R) :- scope(R, _).
region(R, N') :-
  region(R, N), not pool(N), child(N, N'), not scope(N', _),
  not condition(_, N'), #false : literal(L, N'), pooled(L).

unit(R, P) :- region(R, P), pool(P).
unit(R, L) :- region(R, L), pooled(L).

unit_alternative(P, Edit, Rank) :- pool_alternative(P, Edit, Rank).
unit_alternative(L, Edit, Rank) :- literal_alternative(L, Edit, Rank).

% the variants of the scopes, as combinations of the alternatives of
% their units

unit_rank(R, U, J) :- unit(R, U), J = #count{ U' : unit(R, U'), U' < U }.
num_units(R, M) :- unit(R, _), M = #count{ U : unit(R, U) }.

combination(R, 0, (), ()) :- unit(R, _).
combination(R, J+1, (Edit, Edits), (Rank, A)) :-
  combination(R, J, Edits, Rank), unit_rank(R, U, J), unit_alternative(U, Edit, A).
variant(R, edited(node(R), Edits), Rank) :- combination(R, M, Edits, Rank), num_units(R, M).

% the list of variants is built from the last variant to the first
variant_rank(R, V, J) :- variant(R, V, Rank), J = #count{ Rank' : variant(R, _, Rank'), Rank' > Rank }.
num_variants(R, M) :- unit(R, _), M = #count{ Rank : variant(R, _, Rank) }.
variant_list(R, 0, ()) :- unit(R, _).
variant_list(R, J+1, (V, Variants)) :- variant_list(R, J, Variants), variant_rank(R, V, J).

aspen(replace(node(R), join(Sep, Variants))) :-
  variant_list(R, M, Variants), num_variants(R, M), scope(R, Sep).
