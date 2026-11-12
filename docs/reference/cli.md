---
icon: material/console
---

# Command line interface

```
aspen [--log {error,warning,info,debug}] [--version] {reify,transform} ...
```

The `aspen` command has two subcommands: [`reify`](#aspen-reify)
prints the [fact representation](facts.md) of sources, and
[`transform`](#aspen-transform) applies a
[meta-encoding](transformations.md) to them. `aspen -h` and
`aspen SUBCOMMAND -h` show a summary of the options.

## Global options

These options come before the subcommand, e.g.
`aspen --log info transform ...`.

`--log {error,warning,info,debug}`
:   The log level, `warning` by default. Messages of meta-encodings
    (see [messages](transformations.md#messages)) and of aspen-tree itself
    are shown on standard error if their level is at least this level,
    as e.g. `WARNING:  - message`. With `info`, aspen-tree reports what it
    parses, grounds and edits, and with `debug` additionally the facts,
    models and parser actions. With `debug`, errors are shown with
    their Python traceback.

`-v`, `--version`
:   Print the version of aspen-tree and exit.

## Sources

Both subcommands take one or more sources of the form
`SOURCE[@LANG][:DEST]`:

`SOURCE`
:   The path of a file, or `-` for standard input. Standard input can
    be given only once.

`@LANG`
:   The tree-sitter grammar to parse this source with, overriding the
    default language given via `-l/--language`, e.g. `a.lp@clingo`.

`:DEST`
:   Only for `transform`: where to write the transformed text of this
    source, a path, or `-` for standard output (the default). `@LANG`
    must come before `:DEST`, as in `a.lp@clingo:out.lp`.

The sources are identified by `s(0)`, `s(1)`, ... in the order they
are given. Since `SOURCE` is split at the first `:` and `@`, paths
containing these characters cannot be given.

A source starting with `-` other than `-` itself, such as `-:out.lp`
(standard input with a destination), must be given after `--`, as in
`aspen transform -l clingo -s '...' -- -:out.lp`.

### Languages

A language `NAME` is loaded from the installed Python package
`tree_sitter_NAME`, e.g. `clingo` from
[tree-sitter-clingo](https://pypi.org/project/tree-sitter-clingo/).
Each source must have a language, given via `@LANG` or `-l/--language`.

## Source options

The following options are accepted by both subcommands, after the
subcommand.

`-l NAME`, `--language NAME`
:   The default language of the sources.

`-e {utf8,utf16}`, `--encoding {utf8,utf16}`
:   The text encoding of the sources, `utf8` by default.

`--allow-syntax-errors`
:   Parse sources with syntax errors, and mark the erroneous nodes by
    `error/1` and `missing/1` facts. By default, syntax errors are
    reported as errors, both in the sources and in the result of
    transformations.

## `aspen reify`

```
aspen reify [-l NAME] [-e {utf8,utf16}] [--allow-syntax-errors] SOURCE[@LANG] ...
```

Parses the sources and prints the facts representing them to standard
output, one fact per line, source by source.

```console
$ printf 'a.\n' > a.lp
$ aspen reify a.lp -l clingo
language(s(0),"clingo").
source_root(s(0),0).
node(0).
type(0,"source_file").
...
```

## `aspen transform`

```
aspen transform [-l NAME] [-e {utf8,utf16}] [--allow-syntax-errors]
                [-f PATH] [-s STRING] [-p NAME(ARGS)] [-c OPTIONS] [--facts]
                SOURCE[@LANG][:DEST] ...
```

Parses the sources, applies the meta-encoding to them, and writes the
transformed text of each source to its destination, in the order the
sources are given. Sources without a destination are printed to
standard output.

`-f PATH`, `--meta-file PATH`
:   A file of the meta-encoding. Can be given several times.

`-s STRING`, `--meta-string STRING`
:   The meta-encoding as a string, in addition to the files given via
    `-f`. Can be given several times, which combines the strings in
    order. At least one of `-f` and `-s` is required.

    Bundled encodings can be included via the `@aspen/` prefix, as in
    `-s '#include "@aspen/clingo/compile_pools.lp".'`, see
    [bundled encodings](encodings/index.md).

`-p NAME(ARGS)`, `--program NAME(ARGS)`
:   The program part the transformation starts with, as a clingo term,
    e.g. `rename("b","c")` for the program part
    `#program rename(old, new).`, see
    [transformation steps](transformations.md#transformation-steps).
    `base` by default.

`-c OPTIONS`, `--control-options OPTIONS`
:   Options for clingo, as a single string that is split like a shell
    command line, e.g. `-c '--const n=3'`. A string starting with `-`
    and containing no spaces must be given as `-c=--stats`.

`--facts`
:   Print the facts representing the transformed sources to standard
    output, instead of their text. Destinations (`:DEST`) are not
    allowed together with `--facts`.

For example, the following renames `b` to `c` in `a.lp` (containing
`a :- b.`) and `c.lp` (containing `b :- c.`), writing the result for
`a.lp` to `out.lp`:

```console
$ aspen transform a.lp:out.lp c.lp -l clingo \
    -s 'aspen(replace(node(N), "c")) :- type(N, "identifier"), leaf_text(N, "b").'
c :- c.
$ cat out.lp
a :- c.
```

## Errors and exit codes

Errors are printed to standard error as `error: message`, such as
syntax errors of sources, exceptions derived by meta-encodings, and
errors of clingo:

```console
$ printf 'a :- .\n' | aspen reify - -l clingo
error: s(0):1:2: unexpected ':-'
a :- .
  ^^
```

Locations are given as `SOURCE:LINE:COLUMN`, where `SOURCE` is the
path of the source, or its identifier for standard input; lines are
counted from 1 and columns from 0.

| Exit code | Meaning |
|---|---|
| 0 | Success. |
| 1 | An error, or no subcommand was given (the help is printed). |
| 2 | Invalid command line arguments. |
