---
icon: material/file-code
---

# Meta-encodings

A meta-encoding is a clingo program, which gets the
[fact representation](facts.md) of the sources as input. It describes
what to do with the sources by deriving terms of the form `aspen(T)`:
edits of the source text, messages, and the next transformation step.
All other predicates can be used freely.

aspen-tree grounds and solves the meta-encoding together with the facts and
processes the `aspen(T)` terms of the first stable model. Meta-encodings
are expected to have a single stable model.

## Edits

| Term | Effect |
|---|---|
| `aspen(replace(node(N), T))` | Replace the text of node `N` by the text of template `T`. |
| `aspen(prepend(node(N), T))` | Insert the text of `T` before node `N`. |
| `aspen(append(node(N), T))` | Insert the text of `T` after node `N`. |
| `aspen(delete(node(N)))` | Delete node `N`, i.e. replace it by `""`. |
| `aspen(replace(span(node(N), node(M)), T))` | Replace the text from the start of node `N` to the end of node `M` by the text of `T`, see [spans](#spans). |
| `aspen(delete(span(node(N), node(M))))` | Delete the text from the start of node `N` to the end of node `M`. |

A node may have at most one edit of each kind; multiple edits of the
same kind for a node are an error. The replacement of a node is applied
before the text prepended and appended to it, so that
`replace(node(N), "4")`, `prepend(node(N), "3+")` and
`append(node(N), "+2")` turn `f(1)` into `f(3+4+2)`.

### Spans

A span `span(node(N), node(M))` consists of node `N` and its next
siblings up to node `M`, which must be `N` itself or a later sibling of
`N`. All siblings count, including tokens such as `,` and comments
(see `next_sibling/2`). A span's text extends from the start of `N` to
the end of `M`, including the text between the nodes.

Spans can be replaced (and deleted) and inserted by templates, but
not prepended or appended to. A replacement of a span counts as a
replacement of each of its nodes, so it must not overlap with another
replacement. The first node of a replaced span may be prepended to,
and its last node appended to, which inserts the text before and after
the replacement; other edits of nodes in a replaced span are an error.
For example, in `a :- b, c, d.`, the following replaces the span
`b, c` of the body literals of `b` and `c` (and the comma between them):

```
lit(X, L) :- type(L, "body_literal"), child(L, A), child(A, I), leaf_text(I, X).
aspen(replace(span(node(B), node(C)), "x")) :- lit("b", B), lit("c", C).
```

```console
$ printf 'a :- b, c, d.\n' | aspen transform - -l clingo -f span.lp
a :- x, d.
```

### Text of edits

The text of the edits is inserted as is: it is the responsibility of
the meta-encoding to produce valid text, e.g. by adding whitespace or
separators. After the edits, the edited sources are parsed again, and
syntax errors introduced by the edits are reported as errors.

## Templates

The text of an edit, message or print is given by a template:

| Template | Text |
|---|---|
| `"..."` | The string itself. |
| `node(N)` | The text of node `N`, including the edits of `N` and its descendants (see [ordering](#ordering-of-edits)). |
| `span(node(N), node(M))` | The text of the [span](#spans) from node `N` to node `M`, including the edits of its nodes and their descendants. |
| `original(node(N))` | The text of node `N` at the start of the transformation step, before any edits. |
| `original(span(node(N), node(M)))` | The text of the span at the start of the transformation step. |
| `format(S, L)` | The Python format string `S`, with the templates of the list `L` inserted, e.g. `format("{} :- {}.", (node(H), (node(B), ())))`. |
| `join(S, L)` | The templates of the list `L`, joined by the string `S`. |
| `mutate(B, E)` | The text of `B` (a node or span, optionally wrapped in `original(...)`) as if the edits `E` were applied to it, without changing the source, see [below](#hypothetical-edits). |
| `syntax_error(node(N))` | A description of the syntax error at node `N`. |

Lists are written as nested pairs ending in the empty tuple, i.e. the
list of `a`, `b` and `c` is `(a, (b, (c, ())))`.

To insert other terms, such as numbers or constants, into a template,
convert them to strings with `@symbol_to_string(X)`, which aspen-tree
defines for all meta-encodings.

### Hypothetical edits

`mutate(B, E)` gives the text of a node (or span) with some of its
descendants changed, without changing the source. This allows
producing several modified copies of a node in one step. `B` is
`node(N)`, a [span](#spans), or either of them wrapped in
`original(...)` to start from the text before any edits. `E` is a
single edit, or a list of edits, of the form `replace(T, S)`,
`append(node(M), S)` or `prepend(node(M), S)`, where `T` is `node(M)`
or a span, and the nodes are those of `B` or their descendants. For
example, the following adds a copy of each rule with its head replaced
by `d`:

```
aspen(append(node(R), format("\n{}", (mutate(node(R), replace(node(H), "d")), ())))) :-
  type(R, "rule"), child(R, H), field(H, "head").
```

The edits follow the same rules as edits of the source: at most one
edit of each kind per node, and the replacement of a node comes before
the text prepended and appended to it. In addition, a node (or span)
that is replaced must not contain the target of another of the edits,
as the replacement would overwrite it, except that the first node of a
replaced span may be prepended to, and its last node appended to.

See the [pool compilation encoding](encodings/index.md#compiling-away-pools)
for an extensive use of hypothetical edits.

## Ordering of edits

All edits of a step are applied together, in an order that makes the
text inserted by templates well-defined:

- A template inserting `node(N)` (directly, or via `mutate(node(N), E)`)
  inserts the text of `N` after the edits of `N` and of its
  descendants. These edits are applied before the edit using the
  template, except for the edits of the nodes the edit itself targets.
  Likewise, a template inserting a span inserts its text after the
  edits of its nodes and their descendants.
- The replacement of a node (or of a span) is applied before the text
  prepended and appended to it.
- `aspen(comes_before(E1, E2))` additionally orders edit `E1` before
  edit `E2`, where both are given as the full edit terms, e.g.
  `comes_before(replace(node(3), "x"), append(node(5), "y"))`.

`original(node(N))` (and `original(span(...))`) creates no ordering, as it inserts the text before
any edits. This makes it possible, e.g., to swap two nodes, which with
`node(N)` would require each replacement to come before the other:

```
aspen(replace(node(A), original(node(B)))) :- swap(A, B).
aspen(replace(node(B), original(node(A)))) :- swap(A, B).
```

If the order is cyclic, aspen-tree reports an error showing one of the
cycles.

## Messages

| Term | Effect |
|---|---|
| `aspen(log(L, T))` | Log the text of template `T` with level `L` (`"debug"`, `"info"` or `"warning"`). |
| `aspen(log(node(N), L, T))` | Log the text of `T`, showing the location and text of node `N` in its source. |
| `aspen(print(T))` | Print the text of `T` to standard output. |
| `aspen(print(T, S))` | Append the text of `T` as a line to the end of source `S`, or print it to the text stream registered for `S` via the `textio_symbols` argument of `AspenTree`. |
| `aspen(exception(T))` | Fail the transformation with the text of `T` as error message. |
| `aspen(exception(node(N), T))` | Fail with the text of `T`, showing the location and text of node `N`. |

Messages are processed before the edits of the step, so `node(N)` in
their templates is the text of the node before the edits. If there are
exceptions, all of them are reported together, and no edits are
applied. A message located at node `N` looks as follows:

```
s(0):2:5-6: duplicate body literal
c :- a, a.
     ^
```

## Transformation steps

A transformation may consist of several steps, each of which grounds
and solves the meta-encoding with the facts of the sources as they are
after the previous step:

- The first step grounds the `base` program part, or the part given
  via `-p/--program` (`initial_program` in Python), together with
  `base`.
- `aspen(next_program(Name, Args))` requests another step, grounding
  the program part `Name` with the arguments `Args` (a tuple, e.g.
  `("X",)`) together with `base`. At most one next program may be
  derived. `aspen(next_program("base", ()))` repeats `base`.
- The transformation ends with a step that derives no next program.

For example, the following renames an identifier given as program
parameter, and then reports the identifiers of the result:

```
#program rename(old, new).
aspen(replace(node(N), new)) :- type(N, "identifier"), leaf_text(N, old).
aspen(next_program("report", ())).

#program report.
aspen(print(format("found identifier {}", (node(N), ())))) :- type(N, "identifier").
```

```console
$ printf 'a :- b.\n' | aspen transform - -l clingo -f steps.lp -p 'rename("b", "c")'
found identifier a
found identifier c
a :- c.
```

## Queries

Some bundled encodings provide *queries*: a meta-encoding derives
`aspen(query(Q))`, and the encoding answers with
`aspen(return(Q, R))` in the same step. For example, with
`#include "@aspen/generic/queries/path_of_node.lp".`,
`aspen(query(path_of_node(N)))` for a node `N` derives
`aspen(return(path_of_node(N), (S, P)))`, where `S` is the source of
`N`, and `P` is the list of child indices leading from its root to
`N`. The available queries are listed among the
[bundled encodings](encodings/index.md#queries).

## Including bundled encodings

The `#include` directive of clingo resolves relative paths with
respect to the including file. aspen-tree additionally resolves paths
starting with `@aspen/` to its [bundled encodings](encodings/index.md),
in meta-encoding files and strings, as well as in the files they
include:

```
#include "@aspen/generic/queries/path_of_node.lp".
```
