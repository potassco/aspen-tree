---
icon: material/file-tree
---

# Fact representation

aspen represents the syntax trees of its sources as facts, which are
the input of meta-encodings. They can be printed with `aspen reify`.

For example, `a :- b.` is represented as follows (the order of the
facts is changed for readability):

```
language(s(0),"clingo").    source_root(s(0),0).
node(0).  type(0,"source_file").  child(0,1).
node(1).  type(1,"rule").  child(1,2). child(1,3). child(1,4). child(1,5).
node(2).  type(2,"literal").  field(2,"head").  child(2,9).
node(9).  type(9,"symbolic_atom").  field(9,"atom").  child(9,10).
node(10). type(10,"identifier").  field(10,"name").  leaf_text(10,"a").
node(3).  leaf_text(3,":-").
node(4).  type(4,"body").  field(4,"body").  child(4,6).
...
node(5).  leaf_text(5,".").
next_sibling(2,3).  next_sibling(3,4).  next_sibling(4,5).
```

## Predicates

| Fact | Meaning |
|---|---|
| `language(S, L)` | Source `S` is parsed with the grammar named `L`. |
| `source_root(S, N)` | `N` is the root node of source `S`. |
| `node(N)` | `N` is a node. |
| `type(N, T)` | Named node `N` has type `T`, e.g. `"rule"`. Anonymous nodes, such as punctuation, have no type. |
| `child(P, C)` | `C` is a child of `P`. |
| `next_sibling(A, B)` | `B` is the next sibling of `A`. |
| `field(C, F)` | Child `C` is in field `F` of its parent, e.g. `"head"`. |
| `leaf_text(N, T)` | Leaf node `N` has text `T`. |
| `error(N)` | `N` is an `ERROR` node of a syntax error (it has no `type/2` fact). |
| `missing(N)` | `N` was inserted by the parser for a syntax error, as the token is missing. |
| `extra(N)` | `N` is an extra node, which may appear anywhere, such as a comment in some grammars. |

The node types and field names are those of the grammar, see e.g. the
`node-types.json` file of the grammar, or reify a sample program.

## Sources and nodes

- Sources are identified by terms, `s(0)`, `s(1)`, ... in the order
  they are parsed, unless an identifier is given via the Python
  interface.
- Nodes are identified by integers, which are unique across all
  sources. They do not follow the order of the nodes in the text: to
  order siblings, use `next_sibling/2`, or the `child_index/2`
  predicate of the [bundled encodings](encodings/index.md).
- When a transformation edits a source, the changed parts of its tree
  are reified anew with fresh identifiers. Identifiers of unchanged
  nodes may change as well, so they should not be relied upon across
  transformation steps.

## Syntax errors

By default, aspen reports syntax errors of the sources as errors, both
when parsing them and when edits introduce them. With
`--allow-syntax-errors` (`raise_syntax_errors=False` in Python), sources
with syntax errors are reified, with their erroneous nodes marked by
`error/1` and `missing/1`.
