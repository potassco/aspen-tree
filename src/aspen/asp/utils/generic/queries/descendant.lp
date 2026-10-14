aspen(exception(format("Expected node identifier, found {}.", (Node, ())))) :-
  aspen(query(descendant(Node))), not node(Node).

aspen(return(query(descendant(Node)), Node)) :-
  aspen(query(descendant(Node))).

aspen(return(query(descendant(Node)), Node'')) :-
  aspen(return(query(descendant(Node)), Node')), child(Node', Node'').
