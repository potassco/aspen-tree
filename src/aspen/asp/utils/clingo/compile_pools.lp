% Compile away all pools of a clingo program in one step, in the same
% way as clingo itself unpools programs. Apply it e.g. via
%   aspen transform prg.lp -l clingo \
%     --meta-string '#include "@aspen/clingo/compile_pools.lp".'
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
% An alternative of a pool replaces the span of its items (from the
% first to the last item, including the separators) by one of them,
% where an alternative is chosen for each pool directly nested in it.
% More generally, the alternatives of pool items, conditions and
% literals (holders) choose an alternative for each pool directly
% nested in them.
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

pool(P) :- type(P, T), pool_type(T), child(P, S), leaf_text(S, ";").

% the items of argument pools are their arguments, the items of tuples
% and absolute values are their children other than delimiters
pool_item(P, I) :-
  pool(P), type(P, T), arg_pool_type(T),
  child(P, I), field(I, "arguments"), type(I, ("terms";"empty_pool_item")).
pool_item(P, I) :-
  pool(P), type(P, ("tuple";"abs")), child(P, I),
  #false : leaf_text(I, ("(";")";"|";";")).

% the span of the items of a pool, between its opening and closing
% delimiters
items_span(P, span(node(F), node(L))) :-
  pool_item(P, F), next_sibling(O, F), leaf_text(O, ("(";"|")),
  pool_item(P, L), next_sibling(L, C), leaf_text(C, (")";"|")).

% conditional literals, their conditions and literals
condition(L, C) :- type(L, "conditional_literal"), child(L, C), field(C, "condition").
literal(L, A) :- type(L, "conditional_literal"), child(L, A), field(A, "literal").

% holders and the pools directly nested in them (an item may be a pool
% itself)

holder(I) :- pool_item(_, I).
holder(C) :- condition(_, C).
holder(A) :- literal(L, A), pooled(L).

below(H, H) :- holder(H), not pool(H).
below(H, N') :- below(H, N), child(N, N'), not pool(N').
nested(H, H) :- holder(H), pool(H).
nested(H, Q) :- below(H, N), child(N, Q), pool(Q).

% the alternatives of holders as lists of edits, with ranks to order them

nested_rank(H, Q, J) :- nested(H, Q), J = #count{ Q' : nested(H, Q'), Q' < Q }.
num_nested(H, M) :- holder(H), M = #count{ Q : nested(H, Q) }.

partial_alternative(H, 0, (), ()) :- holder(H).
partial_alternative(H, J+1, (Edit, Edits), (Rank, R)) :-
  partial_alternative(H, J, Edits, Rank), nested_rank(H, Q, J), pool_alternative(Q, Edit, R).
alternative(H, Edits, Rank) :- partial_alternative(H, M, Edits, Rank), num_nested(H, M).

% Choosing an empty item of an argument pool removes the parentheses as
% well (as e.g. @f() is not allowed).
pool_alternative(P, replace(Span, mutate(node(I), Edits)), (I, Rank)) :-
  pool_item(P, I), items_span(P, Span), alternative(I, Edits, Rank),
  #false : type(I, "empty_pool_item"), type(P, T), arg_pool_type(T).
pool_alternative(P, replace(span(node(O), node(C)), ""), (I, ())) :-
  pool_item(P, I), type(I, "empty_pool_item"), type(P, T), arg_pool_type(T),
  child(P, O), leaf_text(O, "("), child(P, C), leaf_text(C, ")").

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
  Copy = mutate(node(L), (replace(node(C), mutate(node(C), Cond)),
                          (replace(node(A), mutate(node(A), Lit)), ()))).
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
variant(R, mutate(node(R), Edits), Rank) :- combination(R, M, Edits, Rank), num_units(R, M).

% the list of variants is built from the last variant to the first
variant_rank(R, V, J) :- variant(R, V, Rank), J = #count{ Rank' : variant(R, _, Rank'), Rank' > Rank }.
num_variants(R, M) :- unit(R, _), M = #count{ Rank : variant(R, _, Rank) }.
variant_list(R, 0, ()) :- unit(R, _).
variant_list(R, J+1, (V, Variants)) :- variant_list(R, J, Variants), variant_rank(R, V, J).

aspen(replace(node(R), join(Sep, Variants))) :-
  variant_list(R, M, Variants), num_variants(R, M), scope(R, Sep).
