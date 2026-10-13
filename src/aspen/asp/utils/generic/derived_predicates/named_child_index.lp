#include "./named.lp".
#include "./child_index.lp".

% a child is indexed if it is named and its type is not skipped
indexed_child(Child) :-
  child(_,Child), named(Child), type(Child,T), not skip_named_child_index(T).

% number of indexed siblings preceding a child, computed by walking
% along the sibling chain (linear in the number of siblings)
indexed_siblings_before(Child,0) :- child(_,Child), not next_sibling(_,Child).
indexed_siblings_before(Child',I+1) :-
  indexed_siblings_before(Child,I), next_sibling(Child,Child'), indexed_child(Child).
indexed_siblings_before(Child',I) :-
  indexed_siblings_before(Child,I), next_sibling(Child,Child'), not indexed_child(Child).

named_child_index(Child, NamedIdx) :-
  indexed_child(Child), indexed_siblings_before(Child, NamedIdx).

#defined skip_named_child_index/1.
