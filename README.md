# aspen-tree

aspen-tree analyzes and transforms programs written in any language with a
[tree-sitter](https://tree-sitter.github.io/) grammar, with transformations
written in answer set programming (ASP). It is mostly used for the
[clingo](https://potassco.org/clingo/) ASP language itself.

aspen-tree turns the syntax tree of a program into facts, and applies a
*meta-encoding*, an ordinary clingo program over these facts, which describes
edits of the program text. Everything not edited, such as layout and comments,
stays as it was. For example, renaming the identifier `b` to `c`:

```console
$ printf 'a :- b.\nb.\n' | aspen transform - -l clingo \
    -s 'aspen(replace(node(N), "c")) :- type(N, "identifier"), leaf_text(N, "b").'
a :- c.
c.
```

## Installation

To install the project, together with the grammar for clingo programs, run

```bash
pip install aspen-tree-5 tree-sitter-clingo
```

## Documentation

The documentation is available at <https://docs.potassco.org/aspen-tree/>. It
can also be built locally with

```bash
pip install .[doc]
mkdocs serve
```
