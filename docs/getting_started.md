---
hide:
  - navigation
---

# Getting started

## Installation

=== "Pip"

    ```console
    pip install aspen-tree-5
    ```

=== "Development mode"

    ```console
    git clone https://github.com/potassco/aspen-tree.git
    cd aspen-tree
    pip install -e .[dev]
    ```

    !!! warning
        Use only for development purposes

aspen-tree parses sources with tree-sitter grammars, which are installed as
separate Python packages. A grammar named `NAME` is loaded from the
package `tree_sitter_NAME`; for clingo programs, install
[tree-sitter-clingo](https://pypi.org/project/tree-sitter-clingo/):

```console
pip install tree-sitter-clingo
```

## Command line interface

The `aspen` command has two subcommands, which take one or more
sources: paths to files, or `-` for standard input. The grammar to parse
them with is given via `-l/--language`, or per source as a suffix, as
in `a.lp@clingo`.

### Reifying sources

`aspen reify` prints the [fact representation](reference/facts.md) of
the sources:

```console
$ printf 'a :- b.\n' | aspen reify - -l clingo
language(s(0),"clingo").
source_root(s(0),0).
node(0).
type(0,"source_file").
child(0,1).
node(1).
type(1,"rule").
...
```

### Transforming sources

`aspen transform` applies a [meta-encoding](reference/transformations.md)
to the sources, and prints the transformed text of each source:

```console
$ printf 'a :- b.\nb.\n' | aspen transform - -l clingo \
    -s 'aspen(replace(node(N), "c")) :- type(N, "identifier"), leaf_text(N, "b").'
a :- c.
c.
```

The meta-encoding is given as files (`-f/--meta-file`) and/or as
strings (`-s/--meta-string`), both of which can be repeated. Bundled encodings can be
included via the `@aspen/` prefix, as in
`-s '#include "@aspen/clingo/compile_pools.lp".'`, see
[bundled encodings](reference/encodings/index.md).

Other options:

- `-p/--program NAME(ARGS)` sets the program part the transformation
  starts with (`base` by default), e.g. `-p 'rename("b","c")'`, see
  [transformation steps](reference/transformations.md#transformation-steps).
- A source followed by `:DEST`, as in `a.lp:a-out.lp`, writes the
  transformed text of that source to `DEST` instead of standard output.
- `--facts` prints the fact representation of the transformed sources
  instead of their text.
- `-c/--control-options` passes options to clingo, e.g. `-c '--const n=3'`.

### Common options

- `--allow-syntax-errors` parses sources with syntax errors, instead of
  reporting them as errors. The erroneous nodes are then marked by
  `error/1` and `missing/1` facts.
- `-e/--encoding` sets the text encoding of the sources (`utf8` or
  `utf16`).
- `--log {error,warning,info,debug}`, given before the subcommand as
  in `aspen --log info transform ...`, sets the log level (`warning` by
  default). Log messages of meta-encodings at or above this level are
  shown. With `debug`, errors are shown with their Python traceback.

The [command line reference](reference/cli.md) details all options.

## Python interface

The [`AspenTree`](reference/api/index.md) class holds a set of sources
and their fact representation:

```python
import io

import tree_sitter_clingo
from clingo.symbol import Function
from tree_sitter import Language

from aspen.tree import AspenTree

report = io.StringIO()
tree = AspenTree(
    default_language=Language(tree_sitter_clingo.language()),
    # text streams that aspen(print(Text, Target)) can print to
    textio_symbols={Function("report"): report},
)
source = tree.parse("a :- b.\nb.")
tree.transform(meta_string="""
aspen(replace(node(N), "c")) :- type(N, "identifier"), leaf_text(N, "b").
aspen(print(format("renamed {}", (node(N), ())), report)) :- leaf_text(N, "b").
""")
print(tree.sources[source].source_bytes.decode())  # a :- c.\nc.
print(report.getvalue())  # renamed b (twice, once per identifier)
print(tree.facts)  # the facts of the transformed source
```

- `parse()` accepts a string, bytes or a `pathlib.Path`, and returns
  the identifier of the source (`s(0)`, `s(1)`, ... by default).
- `transform()` takes `meta_files` and/or a `meta_string`, an
  `initial_program`, and `control_options` for clingo. With
  `skip_final_re_reify=True`, the facts are only updated if they are
  accessed afterwards, which saves time if only the text is needed.
- `write()` writes each source to the destination given to `parse()`,
  or prints it.
- Errors derived by meta-encodings are raised as
  `aspen.tree.TransformError`.
