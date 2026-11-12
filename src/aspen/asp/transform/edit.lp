#include "@aspen/generic/queries/path_of_node.lp".

#script (python)

from clingo.symbol import Symbol, String

def symbol_to_string(symbol: Symbol) -> String:
    return String(str(symbol))

#end.

aspen(replace(N,"")) :- aspen(delete(N)).

aspen(node_in_template(Template, Item)) :-
  aspen(item_in_template(Template, Item)), Item=node(N).

aspen(list_in_template(Template, List)) :-
  aspen(item_in_template(Template, Item)), Item=join(Sep, List).

aspen(list_in_template(Template, List)) :-
  aspen(item_in_template(Template, Item)), Item=format(FormatStr, List).

aspen(list_in_template(Template, Rest)) :-
  aspen(list_in_template(Template, (First, Rest))).

aspen(item_in_template(Template, First)) :-
  aspen(list_in_template(Template, (First, Rest))).

% In edited(Base, Edits), the base is inserted like any other item.
% The edits are not applied to the source, so they are not ordered
% with other edits; only their templates are items of the template.
aspen(item_in_template(Template, Base)) :-
  aspen(item_in_template(Template, edited(Base, Edits))).

aspen(_edited_edits(Template, Edits)) :-
  aspen(item_in_template(Template, edited(Base, Edits))).
aspen(_edited_edits(Template, Rest)) :-
  aspen(_edited_edits(Template, (First, Rest))).

aspen(_edited_edit(Template, First)) :-
  aspen(_edited_edits(Template, (First, Rest))).
aspen(_edited_edit(Template, Edit)) :-
  aspen(_edited_edits(Template, Edit)),
  Edit=(replace(N, S);append(N, S);prepend(N, S)).

aspen(item_in_template(Template, S)) :-
  aspen(_edited_edit(Template, (replace(N, S);append(N, S);prepend(N, S)))).

aspen(item_in_template(Template, Template)) :-
  aspen(replace(Node, Template);append(Node, Template);prepend(Node, Template)).

aspen(_edit_target(replace(node(N), S), N)) :- aspen(replace(node(N), S)).
aspen(_edit_target(append(node(N), S), N)) :- aspen(append(node(N), S)).
aspen(_edit_target(prepend(node(N), S), N)) :- aspen(prepend(node(N), S)).

% aspen(comes_before(Edit',Edit)) means Edit' must occur before Edit
% for the text replacement to be correct.
% The join is split into small steps, so that only descendants of
% nodes inserted by edits are checked against replacement targets
% (instead of all pairs of templates and replacements).
aspen(_edit_insert(replace(N, S), InsertNode)) :-
  aspen(replace(N, S)), aspen(node_in_template(S, node(InsertNode))).
aspen(_edit_insert(append(N, S), InsertNode)) :-
  aspen(append(N, S)), aspen(node_in_template(S, node(InsertNode))).
aspen(_edit_insert(prepend(N, S), InsertNode)) :-
  aspen(prepend(N, S)), aspen(node_in_template(S, node(InsertNode))).

aspen(_insert_desc(InsertNode, InsertNode)) :- aspen(_edit_insert(_, InsertNode)).
aspen(_insert_desc(InsertNode, Node')) :-
  aspen(_insert_desc(InsertNode, Node)), child(Node, Node').

aspen(_edit_insert_desc(Edit, Node)) :-
  aspen(_edit_insert(Edit, InsertNode)), aspen(_insert_desc(InsertNode, Node)).

% A node inserted by a template has the text it has after all edits
% of it and of its descendants, so these edits must come first.
% Edits of the same node are excluded, as they are ordered below.
aspen(comes_before(Inner, Edit)) :-
  aspen(_edit_insert_desc(Edit, TargetNode)),
  aspen(_edit_target(Inner, TargetNode)),
  aspen(_edit_target(Edit, EditTarget)), EditTarget != TargetNode.

% Text appended or prepended to a node becomes part of the node, so
% replacing the node must come first, or it would overwrite the text.
aspen(comes_before(replace(N, S), append(N, S'))) :-
  aspen(replace(N, S)), aspen(append(N, S')).
aspen(comes_before(replace(N, S), prepend(N, S'))) :-
  aspen(replace(N, S)), aspen(prepend(N, S')).

% query the paths of node ids that occur as targets or as inserts
% in templates, so that they can be used by aspen to find the
% corresponding tree-sitter nodes for processing.

% targets
aspen(query(path_of_node(N))) :-
  aspen(log(node(N), _, _);exception(node(N), _);
        replace(node(N), _);append(node(N), _);prepend(node(N), _)).

% template inserts
aspen(item_in_template(Template, Template)) :-
  aspen(log(_, _, Template);log(_, Template);print(Template);print(Template, _);
     	exception(_, Template);exception(Template)).

aspen(query(path_of_node(Node))) :- aspen(node_in_template(_, node(Node))).

% inserts of original text create no dependencies between edits, as
% they are converted to text from the sources before any edits
aspen(query(path_of_node(Node))) :-
  aspen(item_in_template(_, original(node(Node)))).

% targets of the edits of edited(Base, Edits)
aspen(query(path_of_node(N))) :-
  aspen(_edited_edit(_, (replace(node(N), S);append(node(N), S);prepend(node(N), S)))).
