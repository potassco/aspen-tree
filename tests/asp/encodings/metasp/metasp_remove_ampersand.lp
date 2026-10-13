#include "@aspen/generic/queries/descendant.lp".

#program metasp_remove_ampersand.

metasp_type(MetaType) :- type(MetaType, "metasp_type").
aspen(query(descendant(MetaType)))  :- metasp_type(MetaType).
exempt(Node) :- aspen(return(query(descendant(MetaType)), Node)), metasp_type(MetaType).

ampersand(Amp) :-
  type(Node, ("metasp_function"; "metasp_symbolic_atom"; "metasp_signature")),
  child(Node, Amp),
  leaf_text(Amp, "&"),
  not exempt(Node).

% Replacing the ampersand by the prefix directly (instead of deleting
% it and rewriting the identifier via a node template) avoids
% templates that reference nodes, which are costly to order.
aspen(replace(node(Amp), "__")) :- ampersand(Amp).
