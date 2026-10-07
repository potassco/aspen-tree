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


def _parse_sources(
    tree: AspenTree, sources: Sequence[tuple[str, Optional[str]]]
) -> list[Symbol]:
    """Parse each given (source, lang) pair in order, returning their
    identifiers: a source's own language (its '@LANG' suffix, already
    split off by _parse_source_spec) overrides the tree's default
    language when given. "-" (stdin) can only be given once, since
    the stream can only be read once."""
    if sum(1 for source, _ in sources if source == "-") > 1:
        raise ValueError("stdin ('-') can only be given as a source once.")
    return [
        tree.parse(
            _read_source(source),
            language=resolve_language(lang) if lang is not None else None,
        )
        for source, lang in sources
    ]


def _parse_source_spec(
    spec: str, *, allow_dest: bool
) -> tuple[str, Optional[str], Optional[Path]]:
    """Parse a CLI source argument of the form SOURCE[@LANG][:DEST]:
    SOURCE is a path, or '-' for stdin; the optional '@LANG' suffix
    overrides the default language (-l/--language) for just this
    source; the optional ':DEST' suffix (only accepted when
    allow_dest, i.e. for transform) says where this source's
    transformed output goes - a path, or '-' (or omitted entirely)
    for stdout. '@LANG' must come before ':DEST', not after."""
    pre, sep, dest_str = spec.partition(":")
    if sep and not allow_dest:
        raise ValueError(
            f"Invalid source '{spec}': a ':DEST' destination is not accepted "
            "here; only an optional '@LANG' suffix is allowed."
        )
    if "@" in dest_str:
        raise ValueError(
            f"Invalid source '{spec}': '@LANG' must come before ':DEST', not " "after it."
        )
    source, lang_sep, lang = pre.partition("@")
    dest = None if not sep or dest_str == "-" else Path(dest_str)
    return source, (lang if lang_sep else None), dest


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
    """Run the `aspen reify` subcommand: parse one or more
    SOURCE[@LANG] sources and print their combined reified ASP fact
    representation to stdout."""
    default_language = resolve_language(args.language) if args.language else None
    tree = AspenTree(default_language=default_language, default_encoding=args.encoding)
    specs = [_parse_source_spec(spec, allow_dest=False) for spec in args.source]
    _parse_sources(tree, [(source, lang) for source, lang, _ in specs])
    _write_output(_format_facts(tree.facts), None)


def cmd_transform(args: Namespace) -> None:
    """Run the `aspen transform` subcommand: parse one or more
    SOURCE[@LANG][:DEST] sources, apply a transformation
    meta-encoding to them, and either write out each source's
    transformed text to its own DEST (the default) or print the
    combined fact base to stdout (--facts)."""
    if not args.meta_file and not args.meta_string:
        raise ValueError(
            "transform requires at least one of --meta-file or --meta-string."
        )
    specs = [_parse_source_spec(spec, allow_dest=True) for spec in args.source]
    if args.facts and any(dest is not None for _, _, dest in specs):
        raise ValueError(
            "transform does not accept a ':DEST' output destination on any "
            "source when --facts is given: the combined fact base is always "
            "printed to stdout."
        )
    default_language = resolve_language(args.language) if args.language else None
    tree = AspenTree(default_language=default_language, default_encoding=args.encoding)
    source_symbs = _parse_sources(tree, [(source, lang) for source, lang, _ in specs])
    tree.transform(
        meta_files=args.meta_file,
        meta_string=args.meta_string,
        initial_program=_parse_program(args.program),
        control_options=args.control_option,
    )
    if args.facts:
        _write_output(_format_facts(tree.facts), None)
        return
    for source_symb, (_, _, dest) in zip(source_symbs, specs):
        source = tree.sources[source_symb]
        _write_output(source.source_bytes.decode(source.encoding), dest)


# the broad except in main() relies on this to tell genuine usage
# errors apart from bugs - keep it in sync with what cmd_reify/
# cmd_transform (and what they call) can actually raise for bad input
CLI_ERRORS = (ValueError, OSError, TransformError)
