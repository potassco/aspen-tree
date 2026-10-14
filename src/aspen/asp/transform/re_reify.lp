% Queries used internally by aspen to re-reify changed siblings after
% an edit. The encoding is grounded in its own program part in the
% Control of the transformation, after solving. It is therefore
% self-contained (no includes, which clingo skips if a transformation
% encoding already included them) and only uses predicates prefixed
% by _aspen_re_reify, so that it does not interact with the rules of
% the transformation encodings.
%
% Input: _aspen_re_reify_query(Q) for each query Q, where Q is either
% re_reify_siblings(Source, Path, Length) or
% re_reify_siblings(Source, append_to_source).
%
% Output: _aspen_re_reify_return(Q, V), where V is one of delete(Fact),
% parent(Id), prev_sibling(Id), next_sibling(Id), and
% _aspen_re_reify_error(Msg, Query) for queries that could not be
% answered.
% The program is stratified, so all output atoms are facts after
% grounding.

#program aspen_re_reify.

% Follow the path of each query down the tree. Children of nodes on
% a path are indexed by walking their siblings once, instead of
% computing child indices for the whole tree.

_aspen_re_reify(on_path(Query, Root, Path)) :-
  _aspen_re_reify_query(Query), Query = re_reify_siblings(Source, Path, _),
  source_root(Source, Root).

_aspen_re_reify_error("Source not found", Query) :-
  _aspen_re_reify_query(Query), Query = re_reify_siblings(Source, _, _),
  not source_root(Source, _).

_aspen_re_reify(on_path(Node)) :- _aspen_re_reify(on_path(_, Node, _)).

_aspen_re_reify(child_at(Node, 0, Child)) :-
  _aspen_re_reify(on_path(Node)), child(Node, Child), not next_sibling(_, Child).
_aspen_re_reify(child_at(Node, Idx + 1, Next)) :-
  _aspen_re_reify(child_at(Node, Idx, Child)), next_sibling(Child, Next).

_aspen_re_reify(on_path(Query, Child, Path)) :-
  _aspen_re_reify(on_path(Query, Node, (Idx, Path))),
  _aspen_re_reify(child_at(Node, Idx, Child)).

_aspen_re_reify_error("No node found at path", Query) :-
  _aspen_re_reify(on_path(Query, Node, (Idx, _))),
  not _aspen_re_reify(child_at(Node, Idx, _)).

% Siblings to re-reify, with their index and the number of siblings
% remaining after them.

_aspen_re_reify(sibling(Query, Node, 0, Length - 1)) :-
  _aspen_re_reify(on_path(Query, Node, ())),
  Query = re_reify_siblings(_, _, Length), Length > 0.

_aspen_re_reify_error("Expected positive length", Query) :-
  _aspen_re_reify_query(Query), Query = re_reify_siblings(_, _, Length),
  Length < 1.

_aspen_re_reify(sibling(Query, Next, Idx + 1, Remainder - 1)) :-
  _aspen_re_reify(sibling(Query, Node, Idx, Remainder)),
  next_sibling(Node, Next), Remainder > 0.

_aspen_re_reify_error("Not enough siblings", Query) :-
  _aspen_re_reify(sibling(Query, Node, _, Remainder)),
  not next_sibling(Node, _), Remainder > 0.

% Facts to delete: those describing the subtrees of the siblings.

_aspen_re_reify(delete(Query, node(Node))) :-
  _aspen_re_reify(sibling(Query, Node, _, _)).
_aspen_re_reify(delete(Query, child(Parent, Node))) :-
  _aspen_re_reify(sibling(Query, Node, _, _)), child(Parent, Node).

_aspen_re_reify(delete(Query, (node(Child); child(Node, Child)))) :-
  _aspen_re_reify(delete(Query, node(Node))), child(Node, Child).
_aspen_re_reify(delete(Query, next_sibling(Node, Next))) :-
  _aspen_re_reify(delete(Query, node(Node))), next_sibling(Node, Next).
_aspen_re_reify(delete(Query, next_sibling(Prev, Node))) :-
  _aspen_re_reify(delete(Query, node(Node))), next_sibling(Prev, Node).
_aspen_re_reify(delete(Query, type(Node, Type))) :-
  _aspen_re_reify(delete(Query, node(Node))), type(Node, Type).
_aspen_re_reify(delete(Query, error(Node))) :-
  _aspen_re_reify(delete(Query, node(Node))), error(Node).
_aspen_re_reify(delete(Query, missing(Node))) :-
  _aspen_re_reify(delete(Query, node(Node))), missing(Node).
_aspen_re_reify(delete(Query, extra(Node))) :-
  _aspen_re_reify(delete(Query, node(Node))), extra(Node).
_aspen_re_reify(delete(Query, leaf_text(Node, Text))) :-
  _aspen_re_reify(delete(Query, node(Node))), leaf_text(Node, Text).
_aspen_re_reify(delete(Query, field(Node, Name))) :-
  _aspen_re_reify(delete(Query, node(Node))), field(Node, Name).

_aspen_re_reify_return(Query, delete(Fact)) :-
  _aspen_re_reify(delete(Query, Fact)).

% Related nodes of interest: the parent of the siblings, the previous
% sibling of the first and the next sibling of the last one.

_aspen_re_reify_return(Query, parent(Parent)) :-
  _aspen_re_reify(sibling(Query, Node, 0, _)), child(Parent, Node).
_aspen_re_reify_return(Query, prev_sibling(Prev)) :-
  _aspen_re_reify(sibling(Query, Node, 0, _)), next_sibling(Prev, Node).
_aspen_re_reify_return(Query, next_sibling(Next)) :-
  _aspen_re_reify(sibling(Query, Node, _, 0)), next_sibling(Node, Next).

% When appending to a source, the root is the parent and its last
% child is the previous sibling.

_aspen_re_reify_return(Query, parent(Root)) :-
  _aspen_re_reify_query(Query), Query = re_reify_siblings(Source, append_to_source),
  source_root(Source, Root).
_aspen_re_reify_return(Query, prev_sibling(Last)) :-
  _aspen_re_reify_query(Query), Query = re_reify_siblings(Source, append_to_source),
  source_root(Source, Root), child(Root, Last), not next_sibling(Last, _).

#defined _aspen_re_reify/1.
#defined _aspen_re_reify_query/1.
#defined source_root/2.
#defined child/2.
#defined next_sibling/2.
#defined type/2.
#defined error/1.
#defined missing/1.
#defined extra/1.
#defined leaf_text/2.
#defined field/2.
