#include "../derived_predicates/child_index.lp".

% Initialize the query.
aspen(node_on_path((Source, Path), RootId, Path)) :-
  aspen(query(node_at_path(Source, Path))), source_root(Source, RootId).

% Raise error if there is no such source
aspen(exception(format("Source {} not found.", (@symbol_to_string(Source), ())))) :-
  aspen(query(node_at_path(Source, Path))), not source_root(Source, _).

% Children by index of the nodes on paths, so that each step along a
% path is a lookup instead of an enumeration of all children of a node
% (for each query passing through it).
aspen(_on_path(NodeId)) :- aspen(node_on_path(_, NodeId, _)).
aspen(_child_at(NodeId, Idx, ChildId)) :-
  aspen(_on_path(NodeId)), child(NodeId, ChildId), child_index(ChildId, Idx).

% Recursive step, following the path down the tree.
aspen(node_on_path(Query, ChildId, Path)) :-
  aspen(node_on_path(Query, NodeId, (Idx, Path))),
  aspen(_child_at(NodeId, Idx, ChildId)).

% Raise error if we cannot follow path all the way to a node
aspen(exception(node(NodeId),
  format("No node found at path {} of source {}: this node has no child with index {}.",
	 (@symbol_to_string(QueryPath), (@symbol_to_string(Source), (@symbol_to_string(Idx), ())))))) :-
  aspen(node_on_path((Source, QueryPath), NodeId, (Idx, _))),
  #false : aspen(_child_at(NodeId, Idx, _)).

% If we have exhausted the path, we return the current node as answer to the query.
aspen(return(node_at_path(Source, QueryPath), NodeId)) :-
  aspen(node_on_path((Source, QueryPath), NodeId, ())).
