#include "../../../../src/aspen/asp/utils/clingo/derived_predicates/named_child_index.lp".
#include "../../../../src/aspen/asp/utils/generic/queries/make_list.lp".

#script (python)

from clingo.symbol import String, Number, Symbol

def string_to_num(string: Symbol) -> Symbol:
    return Number(int(string.string))

#end.
% INFIMUM
symb(N,inf) :- type(N,"infimum").
% SUPREMUM
symb(N,sup) :- type(N,"supremum").
% NUMBER
symb(N,num(@string_to_num(T))) :- type(N,"number"), leaf_text(N,T).
% STRING
symb(N,str(T)) :- type(N,"string"), leaf_text(N,T).
% FSTRING
% we do not support fstrings for now to make our lives slightly easier.
% symb(N,fstr(T)) :- type(N,"fstring"), leaf_text(N,T).
% anonymous variable
symb(N,var(anon)) :- type(N,"anonymous").
% VARIABLE
symb(N,var(T)) :- type(N,"variable"), leaf_text(N,T).
% BINARY OPERATION
symb(N,binop(LS, OT, RS)) :-
  type(N,"binary_operation"),
  child(N,L), field(L,"left"), symb(L,LS),
  child(N,O), field(O,"operator"), leaf_text(O,OT),
  child(N,R), field(R,"right"), symb(R,RS).
% UNARY OPERATION
symb(N,unop(OT,RS)) :-
  type(N,"unary_operation"),
  child(N,O), field(O,"operator"), leaf_text(O,OT)
  child(N,R), field(R,"right"), symb(R,RS).
% ABSOLUTE VALUE
% note: in case of a pool, we map multiple symbols to the same node id
symb(N,abs(TS)) :-
  type(N,"abs"), child(N,T), symb(T,TS).
% (EXTERNAL) FUNCTION
_func_node(N) :- type(N,"function";"external_function").

% case: function with no args; i.e. constant
_func_symb(N,func(I,())) :-
  _func_node(N),n
  child(N,I), type(I,"identifier"), leaf_text(I,IT),
  #false: child(N,A), field(A,"arguments").

% note: in case of a pool, we map multiple symbols to the same node id
% case: function with args
func_arg(N,IT,A) :-
  _func_node(N),
  child(N,I), type(I,"identifier"), leaf_text(I,IT),
  child(N,A), field(A,"arguments").

% case: function has empty pool item argument
_func_symb(N,func(I,())) :- func_arg(N,I,A), type(A,"empty_pool_item").

% case: function has terms argument
aspen(query(make_list(A, CS, I))) :-
  func_arg(N,I,A), type(A,"terms"), child(A,C), named_child_index(C,I), symb(C,CS).

_func_symb(N,func(I,C)) :- func_arg(N,I,A), aspen(return(make_list(A),C)).

% finally, determine if function is external or not
symb(N,func(I,A)) :- _func_symb(N,func(I,A)), type(N,"function").

symb(N,ext_func(I,A)) :- _func_symb(N,func(I,A)), type(N,"external_function").

% TUPLE
% tuple with no child
symb(N,tuple(())) :- type(N,"tuple"), #false: child(N,C), named(C).
% tuple with empty pool item and lone comma evaluate to empty tuple
symb(N,tuple(()))
  :- type(N,"tuple"), child(N,C), type(C,"lone_comma";"empty_pool_item").
% If the tuple has a child that has a symb, it is some term, not terms,
% empty pool item or a lone comma. In this case, the tuple is dropped
% during evaluation by gringo, and we do this already when defining the symbol
symb(N,CS) :- type(N,"tuple"), child(N,C), symb(C,CS).
% finally, a tuple may have terms
aspen(query(make_list(T,CS,I))) :-
  type(N,"tuple"), child(N,T), type(T,"terms"),
  child(T,C), named_child_index(C,I), symb(C,CS).

symb(N,tuple(C)) :-
  type(N,"tuple"), child(N,T), type(T,"terms"), aspen(return(make_list(T),C)).
