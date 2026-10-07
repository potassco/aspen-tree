"""Command line commands exposing AspenTree's reify and transform
functionality."""

import importlib
import sys
from argparse import Namespace
from pathlib import Path
from typing import Optional, Sequence

import tree_sitter as ts
from clingo.symbol import Symbol, SymbolType, parse_term

from aspen.tree import AspenTree, SourceInput, TransformError

__all__ = ["cmd_reify", "cmd_transform", "resolve_language"]


def resolve_language(name: str) -> ts.Language:
    """Load a tree-sitter Language by short name: "clingo" loads the
    installed tree_sitter_clingo package, and so on for any other
    installed tree-sitter grammar."""
    module_name = f"tree_sitter_{name}"
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ValueError(
            f"Could not import grammar package '{module_name}' for language "
            f"'{name}'. Is it installed? (e.g. `pip install tree-sitter-{name}`)"
        ) from exc
    try:
        return ts.Language(module.language())
    except AttributeError as exc:
        raise ValueError(
            f"Module '{module_name}' does not expose a language() function, "
            "so it doesn't look like a tree-sitter grammar package."
        ) from exc


def _read_source(source_arg: str) -> SourceInput:
    """Turn a CLI source argument into something AspenTree.parse
    accepts: a real Path when possible, so that error messages can
    show the actual file name, or raw bytes when reading from stdin
    ("-"), where there is no file name to show."""
    if source_arg == "-":
        return sys.stdin.buffer.read()
    return Path(source_arg)


def _format_facts(facts: list[Symbol]) -> str:
    """Render facts as loadable ASP source, one fact per line."""
    return "\n".join(f"{fact}." for fact in facts)


def _write_output(text: str, output: Optional[Path]) -> None:
    if output is None:
        print(text)
    else:
        output.write_text(text + "\n")


def _parse_sources(tree: AspenTree, sources: Sequence[str]) -> list[Symbol]:
    """Parse each given source in order, returning their identifiers.
    "-" (stdin) can only be given once, since the stream can only be
    read once."""
    if sources.count("-") > 1:
        raise ValueError("stdin ('-') can only be given as a source once.")
    return [tree.parse(_read_source(source)) for source in sources]


def _parse_source_spec(spec: str) -> tuple[str, Optional[Path]]:
    """Parse a transform source argument of the form SOURCE[:DEST]:
    SOURCE is a path, or '-' for stdin, exactly as for reify; the
    optional DEST after a single ':' is where that source's
    transformed output goes - a path, or '-' (or omitted entirely,
    i.e. no ':' at all) for stdout."""
    source, sep, dest = spec.partition(":")
    if not sep or dest == "-":
        return source, None
    return source, Path(dest)


def _parse_program(program_arg: str) -> tuple[str, tuple[Symbol, ...]]:
    """Parse a CLI program specifier such as "acid(42,d)" (or a bare
    name like "base") into the (name, args) pair AspenTree.transform
    expects, by parsing it as a clingo term and splitting it into its
    function name and arguments."""
    try:
        symbol = parse_term(program_arg)
    except RuntimeError as exc:
        raise ValueError(f"Invalid --program term '{program_arg}': {exc}") from exc
    if symbol.type is not SymbolType.Function:
        raise ValueError(
            f"Invalid --program term '{program_arg}': expected a program name "
            "optionally followed by arguments in parentheses, e.g. 'base' or "
            "'acid(42,d)'."
        )
    return symbol.name, tuple(symbol.arguments)


def cmd_reify(args: Namespace) -> None:
    """Run the `aspen reify` subcommand: parse one or more sources and
    print their combined reified ASP fact representation."""
    language = resolve_language(args.language)
    tree = AspenTree(default_language=language, default_encoding=args.encoding)
    _parse_sources(tree, args.source)
    _write_output(_format_facts(tree.facts), args.output)


def cmd_transform(args: Namespace) -> None:
    """Run the `aspen transform` subcommand: parse one or more
    SOURCE[:DEST] sources, apply a transformation meta-encoding to
    them, and either write out each source's transformed text to its
    own DEST (--show source) or print the combined fact base to
    stdout (--show facts)."""
    if not args.meta_file and not args.meta_string:
        raise ValueError(
            "transform requires at least one of --meta-file or --meta-string."
        )
    specs = [_parse_source_spec(spec) for spec in args.source]
    if args.show == "facts" and any(dest is not None for _, dest in specs):
        raise ValueError(
            "transform does not accept a ':DEST' output destination on any "
            "source when --show is 'facts': the combined fact base is "
            "always printed to stdout."
        )
    language = resolve_language(args.language)
    tree = AspenTree(default_language=language, default_encoding=args.encoding)
    source_symbs = _parse_sources(tree, [source for source, _ in specs])
    tree.transform(
        meta_files=args.meta_file,
        meta_string=args.meta_string,
        initial_program=_parse_program(args.program),
        control_options=args.control_option,
    )
    if args.show == "facts":
        _write_output(_format_facts(tree.facts), None)
        return
    for source_symb, (_, dest) in zip(source_symbs, specs):
        source = tree.sources[source_symb]
        _write_output(source.source_bytes.decode(source.encoding), dest)


# the broad except in main() relies on this to tell genuine usage
# errors apart from bugs - keep it in sync with what cmd_reify/
# cmd_transform (and what they call) can actually raise for bad input
CLI_ERRORS = (ValueError, OSError, TransformError)
