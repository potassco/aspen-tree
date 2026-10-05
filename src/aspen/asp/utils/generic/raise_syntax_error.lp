#include "./queries/path_of_node.lp".

% _template_symb2str's syntax_error(node(N)) branch needs the
% tree-sitter node for N, which it looks up via path_of_node - trigger
% that query here instead of relying on some other already-loaded
% encoding happening to ask for it.
aspen(query(path_of_node(Node))) :- aspen(exception(syntax_error(node(Node)))).

aspen(exception(syntax_error(node(Node)))) :- missing(Node).
aspen(exception(syntax_error(node(Node)))) :- error(Node).
