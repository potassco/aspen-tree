# Changes

## v0.2.0

- add the `aspen` command line interface, with the subcommands `reify` and
  `transform`, sources of the form `SOURCE[@LANG][:DEST]`, and the options
  `--log` and `--log-parser`
- rename the edit operator `aspen(edit(...))` to `aspen(replace(...))`, and add
  the operators `append`, `prepend` and `delete`; a node may have one edit of
  each kind
- add the templates `original(node(N))`, to insert the text of a node before
  any edits, and `mutate(B, E)`, to insert the text of a node with hypothetical
  edits applied
- add spans of sibling nodes, `span(node(N), node(M))`, as targets of
  replacements and as templates
- order edits automatically, so that inserted nodes include the edits of their
  descendants, and report cyclic orders
- show the location and text of nodes in messages located at them, and report
  syntax errors with descriptive messages while parsing, by default
- add the `@aspen/` prefix to include bundled encodings, and the bundled
  encoding `@aspen/clingo/compile_pools.lp`, which compiles away the pools of
  clingo programs
- improve performance, e.g. by re-reifying only changed parts of sources, and
  only when needed
- add documentation
- fix include paths, CLI sources and written line endings on Windows

## v0.1.0

- create project
