% Compile away all pools of a clingo program, in the same way as
% clingo itself unpools programs.
%
% Each pool belongs to a scope, whose pools are unpooled together, by
% replacing a node with its variants (one for each combination of
% items of the pools):
% - in an aggregate, optimize or theory element, the element is
%   replaced by its variants;
% - in the condition of a conditional literal, the conditional literal
%   is replaced by its variants;
% - otherwise, the statement is replaced by its variants.
% Each step unpools the pools not nested in other pools, and the
% encoding is applied again while nested pools remain. As in clingo,
% the pools of a statement are only unpooled once the pools of the
% conditions of its conditional literals are, so that each copy of a
% conditional literal is unpooled separately.
%
% Lists are built by recursion over the ranks of their elements, as
% building them via the make_list query of aspen would make the
% encoding non-stratified (queries would depend on returns), which
% makes grounding blow up.

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

pool_parenthesis(P, N) :-
  pool(P), type(P, T), arg_pool_type(T), child(P, N), leaf_text(N, ("(";")")).

in_pool(N) :- pool(P), child(P, N).
in_pool(N') :- in_pool(N), child(N, N').
outer_pool(P) :- pool(P), not in_pool(P).

% Choosing an item of a pool removes the separators and the other
% items, and if the chosen item of an argument pool is empty, the
% parentheses (as e.g. @f() is not allowed).
removed(P, I, S) :- outer_pool(P), pool_item(P, I), pool_separator(P, S).
removed(P, I, I') :- outer_pool(P), pool_item(P, I), pool_item(P, I'), I != I'.
removed(P, I, N) :-
  outer_pool(P), pool_item(P, I), type(I, "empty_pool_item"), pool_parenthesis(P, N).

removed_rank(P, I, N, K) :- removed(P, I, N), K = #count{ N' : removed(P, I, N'), N' < N }.
removed_list(P, I, 0, ()) :- outer_pool(P), pool_item(P, I).
removed_list(P, I, K+1, (replace(node(N), ""), Edits)) :-
  removed_list(P, I, K, Edits), removed_rank(P, I, N, K).

choice(P, I, replace(node(P), edited(node(P), Edits))) :-
  removed_list(P, I, K, Edits), K = #count{ N : removed(P, I, N) }.

% scopes, identified by the root of their region, together with the
% node replaced by the variants, and the separator of the variants

scope(S, S, "\n") :- source_root(_, R), child(R, S).
scope(E, E, "; ") :-
  type(E, ("set_aggregate_element";"body_aggregate_element";"head_aggregate_element";
           "optimize_element";"theory_element")).
scope(C, L, "; ") :- type(L, "conditional_literal"), child(L, C), field(C, "condition").

region(R, R) :- scope(R, _, _).
region(R, N') :- region(R, N), child(N, N'), not scope(N', _, _).

scope_pool(R, P) :- region(R, P), outer_pool(P).

waiting(S) :- scope_pool(S, _), region(S, L), scope(C, L, _), C != L, scope_pool(C, _).
ready(R) :- scope_pool(R, _), not waiting(R).

% the variants of the scopes, as combinations of the choices of
% items of their pools

pool_rank(R, P, J) :- ready(R), scope_pool(R, P), J = #count{ P' : scope_pool(R, P'), P' < P }.
num_pools(R, K) :- ready(R), K = #count{ P : scope_pool(R, P) }.

combination(R, 0, (), ()) :- ready(R).
combination(R, J+1, (Edit, Edits), (I, Rank)) :-
  combination(R, J, Edits, Rank), pool_rank(R, P, J), choice(P, I, Edit).

variant(R, Rank, edited(node(N), Edits)) :-
  combination(R, K, Edits, Rank), num_pools(R, K), scope(R, N, _).
variant_rank(R, V, J) :- variant(R, Rank, V), J = #count{ Rank' : variant(R, Rank', _), Rank' > Rank }.
num_variants(R, M) :- ready(R), M = #count{ Rank : variant(R, Rank, _) }.

% the list is built from the last variant to the first
variant_list(R, 0, ()) :- ready(R).
variant_list(R, J+1, (V, Variants)) :- variant_list(R, J, Variants), variant_rank(R, V, J).

aspen(replace(node(N), join(Sep, Variants))) :-
  variant_list(R, M, Variants), num_variants(R, M), scope(R, N, Sep).

% apply the encoding again while pools remain

aspen(next_program("base", ())) :- pool(P), in_pool(P).
aspen(next_program("base", ())) :- waiting(_).
