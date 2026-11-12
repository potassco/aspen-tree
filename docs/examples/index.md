---
hide:
  - navigation
---

# Examples

The examples transform clingo programs given on standard input. The
meta-encodings are given inline via `-s`, or in a file via `-f`; see
[meta-encodings](../reference/transformations.md) for the full
interface.

## Renaming identifiers

Replace each identifier `b` by `c`:

```console
$ printf 'a :- b.\nb.\n' | aspen transform - -l clingo \
    -s 'aspen(replace(node(N), "c")) :- type(N, "identifier"), leaf_text(N, "b").'
a :- c.
c.
```

## Inserting the text of nodes

Templates can insert the text of nodes. The following adds the body
`b; c` to each fact, where `b` is inserted as the text of the identifier
`b`, and every identifier `b` is replaced by `d`:

```
fact(L) :- type(N, "rule"), child(N, L), field(L, "head"),
           #false : child(N, M), type(M, "body").
b(N) :- type(N, "identifier"), leaf_text(N, "b").

aspen(replace(node(N), "d")) :- b(N).
aspen(replace(node(L), format("{0} :- {1}", (node(L), (join("; ", (node(N), ("c", ()))), ()))))) :-
  fact(L), b(N).
```

```console
$ printf 'a. :- b.\n' | aspen transform - -l clingo -f add_body.lp
a :- d; c. :- d.
```

The inserted text of `b` is `d`, as the replacement of `b` is applied
before the edit inserting it, see
[ordering of edits](../reference/transformations.md#ordering-of-edits).

## Swapping nodes

To insert the text of nodes before any edits, use `original(node(N))`.
This allows swapping nodes:

```console
$ printf 'a. b.\n' | aspen transform - -l clingo -s '
    swap(A, B) :- leaf_text(A, "a"), leaf_text(B, "b").
    aspen(replace(node(A), original(node(B)))) :- swap(A, B).
    aspen(replace(node(B), original(node(A)))) :- swap(A, B).'
b. a.
```

With `node(A)` and `node(B)` instead, each replacement would have to be
applied before the other, which aspen-tree reports as an error:

```
error: Transformation edits define cyclic dependencies. One such cycle:
s(0):1:3-4: replace with 'a'
a. b.
   ^
which must be applied before
s(0):1:0-1: replace with 'b'
a. b.
^
...
```

## Adding modified copies

`mutate(node(N), E)` gives the text of node `N` with the edits `E`
applied to it, without changing the source. The following adds a copy
of each rule, with its head replaced by `d`:

```console
$ printf 'a :- b, c.\n' | aspen transform - -l clingo -s '
    aspen(append(node(R), format("\n{}", (mutate(node(R), replace(node(H), "d")), ())))) :-
      type(R, "rule"), child(R, H), field(H, "head").'
a :- b, c.
d :- b, c.
```

## Compiling away pools

The bundled encoding `compile_pools.lp` compiles away all pools of a
clingo program, see [bundled encodings](../reference/encodings/index.md#compiling-away-pools):

```console
$ printf 'a(1;2) :- b(X;Y), { c(3;4) : d }.\n' | aspen transform - -l clingo \
    -s '#include "@aspen/clingo/compile_pools.lp".'
a(1) :- b(X), { c(3) : d; c(4) : d }.
a(2) :- b(X), { c(3) : d; c(4) : d }.
a(1) :- b(Y), { c(3) : d; c(4) : d }.
a(2) :- b(Y), { c(3) : d; c(4) : d }.
```

## Reporting errors and warnings

Messages located at a node show where the node is in its source.
Exceptions make the transformation fail:

```console
$ printf 'a :- b.\nc :- a, a.\n' | aspen transform - -l clingo -s '
    same(L, L2) :- type(B, "body"), child(B, L), child(B, L2), L < L2,
                   child(L, A), child(A, I), leaf_text(I, X),
                   child(L2, A2), child(A2, I2), leaf_text(I2, X).
    aspen(exception(node(L), "duplicate body literal")) :- same(L, _).'
error: s(0):2:5-6: duplicate body literal
c :- a, a.
     ^
```

Logs are shown depending on the log level, which is `warning` by
default:

```console
$ printf 'a :- b.\n' | aspen transform - -l clingo \
    -s 'aspen(log(node(N), "warning", "found a rule")) :- type(N, "rule").'
WARNING:  - s(0):1:0-7: found a rule
a :- b.
^^^^^^^
a :- b.
```

## Several steps

A transformation can consist of several steps, each of which sees the
result of the previous one. The following renames an identifier given
as a program parameter, and then prints the identifiers of the result:

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
