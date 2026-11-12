---
hide:
  - navigation
  - toc
---

# aspen

*aspen* analyzes and transforms programs written in any language with a
[tree-sitter](https://tree-sitter.github.io/) grammar, with
transformations written in answer set programming (ASP). It is mostly
used for the [clingo](https://potassco.org/clingo/) ASP language
itself.

aspen has two main functionality:

1. **Reify.** Each source is parsed by tree-sitter, and its syntax tree
   is turned into facts such as `node(3)`, `type(3, "rule")` and
   `child(3, 4)`.
2. **Transform.** A *meta-encoding*, an ordinary clingo program over
   these facts, derives terms like `aspen(replace(node(N), "c"))` that
   describe edits of the source text, and messages to report via printing, exceptions or logging.

The edits defined via a transformation are applied to the text, so everything not edited (layout,
comments) stays as it was. For example, renaming the identifier `b` to
`c` in a clingo program takes one rule:

```console
$ printf 'a :- b.\nb.\n' | aspen transform - -l clingo \
    -s 'aspen(replace(node(N), "c")) :- type(N, "identifier"), leaf_text(N, "b").'
a :- c.
c.
```

- [Getting started](getting_started.md) explains installation and the
  command line and Python interfaces.
- [Examples](examples/index.md) shows common kinds of transformations.
- The [reference](reference/index.md) describes the
  [fact representation](reference/facts.md), the
  [meta-encoding interface](reference/transformations.md) and the
  [bundled encodings](reference/encodings/index.md), such as one
  compiling away the pools of clingo programs.

!!! info
    *aspen* is part of the [Potassco](https://potassco.org) suite.
