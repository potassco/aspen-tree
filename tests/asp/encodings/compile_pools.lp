#include "@aspen/generic/queries/make_list.lp".

% Compile away the pools of rules with at most one pool, by replacing
% each such rule with one variant per element of the pool.

pool_atom(A) :-
  type(A, "symbolic_atom"),
  child(A, T1), field(T1, "arguments"),
  child(A, T2), field(T2, "arguments"), T1 != T2.
pool_element(A, T) :- pool_atom(A), child(A, T), field(T, "arguments").
atom_name(A, I) :- pool_atom(A), child(A, I), field(I, "name").

in_rule(R, R) :- type(R, "rule").
in_rule(R, N') :- in_rule(R, N), child(N, N').

variant(R, T, edited(node(R), replace(node(A), format("{}({})", (node(I), (node(T), ())))))) :-
  in_rule(R, A), atom_name(A, I), pool_element(A, T).

aspen(query(make_list(R, V, T))) :- variant(R, T, V).
aspen(replace(node(R), join("\n", Vs))) :- aspen(return(make_list(R), Vs)).
