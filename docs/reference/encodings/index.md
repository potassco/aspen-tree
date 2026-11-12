---
icon: material/file-code
---

# Bundled encodings

aspen ships encodings that meta-encodings can include via the `@aspen/`
prefix, e.g. `#include "@aspen/generic/queries/path_of_node.lp".`
They are organized by language: those under `generic/` work for any
grammar, those under `clingo/` and `aspcore2/` for the respective
grammars.

## Transformations

### Compiling away pools

`@aspen/clingo/compile_pools.lp` compiles away all pools of a clingo
program, such as `p(1;2)`, `(a;b,c)` or `|X;Y|`, including nested pools
and empty pool items, in the same way as clingo itself does when
grounding. It works in a single transformation step, and can be used
on its own or included by other meta-encodings:

```console
$ printf 'a(1;2) :- b(X;Y), { c(3;4) : d }.\n' | aspen transform - -l clingo \
    -s '#include "@aspen/clingo/compile_pools.lp".'
a(1) :- b(X), { c(3) : d; c(4) : d }.
a(2) :- b(X), { c(3) : d; c(4) : d }.
a(1) :- b(Y), { c(3) : d; c(4) : d }.
a(2) :- b(Y), { c(3) : d; c(4) : d }.
```

As in clingo, pools in aggregate, optimize and theory elements are
unpooled within the element, pools in the condition of a conditional
literal create copies of the conditional literal, and all other pools
create copies of the statement. The encoding derives the variants via
[hypothetical edits](../transformations.md#hypothetical-edits).

### Reporting syntax errors

`@aspen/generic/raise_syntax_error.lp` derives an exception for each
`error/1` and `missing/1` node, describing the syntax error. It is
only useful together with `--allow-syntax-errors`, as aspen reports
syntax errors by itself otherwise.

## Queries

Queries are posed by deriving `aspen(query(Q))`, and answered by
`aspen(return(Q, R))` in the same step, see
[queries](../transformations.md#queries). All queries under
`@aspen/generic/queries/` can be included together via
`@aspen/generic/queries/include_all.lp`, except `make_list.lp`.

| Encoding | Query | Answer |
|---|---|---|
| `path_of_node.lp` | `path_of_node(N)` | `(S, P)`: the source `S` of node `N`, and the list `P` of child indices leading from its root to `N`, e.g. `(s(0), (0, (2, ())))`. |
| `node_at_path.lp` | `node_at_path(S, P)` | The node at path `P` (as above) in source `S`. |
| `descendant.lp` | `descendant(N)` | Each descendant of `N`, including `N` itself. The answers are `aspen(return(query(descendant(N)), M))`. |
| `delete_subtree.lp` | `delete_subtree(N)` | Each fact of the subtree of `N`, including the `child/2` fact connecting it to its parent. |
| `isomorphic.lp` | `isomorphic(S1, S2)` | `isomorphic(S1, S2)` if the trees of sources `S1` and `S2` are isomorphic, and otherwise terms describing the differences, such as `missing_path(Root, Path)`. |
| `make_list.lp` | `make_list(Id, E, R)` | For each `Id`, the list of the elements `E` ordered by their ranks `R`, as `aspen(return(make_list(Id), L))`. |

Invalid queries, such as `path_of_node(N)` for a term `N` that is not a
node, raise errors.

## Derived predicates

These encodings derive predicates that are useful for writing
meta-encodings. The generic ones can be included together via
`@aspen/generic/derived_predicates/include_all.lp` (or together with
all generic queries via `@aspen/generic/all.lp`), and those of clingo
via `@aspen/clingo/include_all.lp`.

| Encoding | Predicate | Meaning |
|---|---|---|
| `@aspen/generic/derived_predicates/child_index.lp` | `child_index(N, I)` | `N` is the `I`-th child of its parent, counting from 0. |
| `@aspen/generic/derived_predicates/named.lp` | `named(N)` | `N` is a named node, i.e. has a type. |
| `@aspen/generic/derived_predicates/named_child_index.lp` | `named_child_index(N, I)` | `N` is the `I`-th named child of its parent, skipping children whose types are given via `skip_named_child_index/1`. |
| `@aspen/generic/derived_predicates/next_named_sibling.lp` | `next_named_sibling(N, M)` | `M` is the next named sibling of `N`. |
| `@aspen/clingo/derived_predicates/named_child_index.lp` | `named_child_index(N, I)` | As above, skipping comments. |
| `@aspen/clingo/derived_predicates/symbol_signature.lp` | `symbol_signature(N, (Name, Arity))` | Atom or function `N` has the given name and arity. It assumes the program has no pools, which can be [compiled away](#compiling-away-pools) first. |
| `@aspen/aspcore2/derived_predicates/named_child_index.lp` | `named_child_index(N, I)` | As above for ASP-Core-2, skipping comments. |
| `@aspen/aspcore2/derived_predicates/symbol_signature.lp` | `symbol_signature(N, (Name, Arity))` | As above for ASP-Core-2. |
