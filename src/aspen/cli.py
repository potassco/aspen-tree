"""Command line commands exposing AspenTree's reify and transform
functionality."""

import importlib
import sys
from argparse import Namespace
from pathlib import Path
from typing import Optional

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
    """Run the `aspen reify` subcommand: parse a source and print its
    reified ASP fact representation."""
    language = resolve_language(args.language)
    tree = AspenTree(default_language=language, default_encoding=args.encoding)
    tree.parse(_read_source(args.source))
    _write_output(_format_facts(tree.facts), args.output)


def cmd_transform(args: Namespace) -> None:
    """Run the `aspen transform` subcommand: parse a source, apply a
    transformation meta-encoding to it, and print the result."""
    if not args.meta_file and not args.meta_string:
        raise ValueError(
            "transform requires at least one of --meta-file or --meta-string."
        )
    language = resolve_language(args.language)
    tree = AspenTree(default_language=language, default_encoding=args.encoding)
    source_symb = tree.parse(_read_source(args.source))
    tree.transform(
        meta_files=args.meta_file,
        meta_string=args.meta_string,
        initial_program=_parse_program(args.program),
        control_options=args.control_option,
    )
    parts: list[str] = []
    if args.show in ("source", "both"):
        source = tree.sources[source_symb]
        parts.append(source.source_bytes.decode(source.encoding))
    if args.show in ("facts", "both"):
        parts.append(_format_facts(tree.facts))
    _write_output("\n".join(parts), args.output)


# the broad except in main() relies on this to tell genuine usage
# errors apart from bugs - keep it in sync with what cmd_reify/
# cmd_transform (and what they call) can actually raise for bad input
CLI_ERRORS = (ValueError, OSError, TransformError)
