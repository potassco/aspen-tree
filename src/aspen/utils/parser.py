"""
The command line parser for the project.
"""

import logging
from argparse import ArgumentParser, _SubParsersAction
from importlib import metadata
from pathlib import Path
from textwrap import dedent
from typing import Any, Optional, cast

from aspen.cli import cmd_reify, cmd_transform

__all__ = ["get_parser"]

VERSION = metadata.version("aspen-tree-5")


def _add_source_arguments(subparser: ArgumentParser, source_help: str) -> None:
    """Arguments shared by both subcommands: what to parse, and how."""
    subparser.add_argument(
        "source", nargs="+", help=source_help, metavar="SOURCE[@LANG][:DEST]"
    )
    subparser.add_argument(
        "-l",
        "--language",
        default=None,
        metavar="NAME",
        help=(
            "default tree-sitter grammar to parse sources with, e.g. 'clingo' "
            "(loads the installed tree_sitter_clingo package); a source may "
            "override this for itself with its own '@LANG' suffix"
        ),
    )
    subparser.add_argument(
        "-e",
        "--encoding",
        choices=["utf8", "utf16"],
        default="utf8",
        help="text encoding of the source file(s) [%(default)s]",
    )


def _add_reify_parser(subparsers: "_SubParsersAction[ArgumentParser]") -> None:
    reify_parser = subparsers.add_parser(
        "reify",
        help=(
            "Parse one or more sources and print their combined reified "
            "ASP fact representation."
        ),
    )
    _add_source_arguments(
        reify_parser,
        (
            "SOURCE specifies a path to a source file to parse, or '-' for stdin; each "
            "may optionally be followed by '@LANG' (e.g. 'a.lp@clingo') to "
            "parse that source with a different language than the default "
            "(-l/--language)"
        ),
    )
    reify_parser.set_defaults(func=cmd_reify)


def _add_transform_parser(subparsers: "_SubParsersAction[ArgumentParser]") -> None:
    transform_parser = subparsers.add_parser(
        "transform",
        help=(
            "Parse one or more sources, apply a transformation meta-encoding "
            "to them, and print or write out each source's result."
        ),
    )
    _add_source_arguments(
        transform_parser,
        (
            "SOURCE specifies a path to a source file to parse, or '-' for stdin; each "
            "may optionally be followed by '@LANG' (e.g. 'a.lp@clingo') to "
            "override the default language (-l/--language) for that source, "
            "and/or by ':DEST' (e.g. 'a.lp@clingo:a-trans.lp') to send that "
            "source's transformed output to DEST instead of stdout. "
            "':DEST' is only meaningful without --facts; "
            "if a source starts with '-' (e.g. '-:out.lp' for stdin with a "
            "destination), put it after a literal '--'"
        ),
    )
    transform_parser.add_argument(
        "-f",
        "--meta-file",
        type=Path,
        action="append",
        metavar="PATH",
        help="a meta-encoding file to apply (repeatable)",
    )
    transform_parser.add_argument(
        "-s",
        "--meta-string",
        metavar="STRING",
        help="inline meta-encoding to apply, in addition to any --meta-file",
    )
    transform_parser.add_argument(
        "-p",
        "--program",
        default="base",
        metavar="NAME(ARGS)",
        help=(
            "the meta-encoding's entry program part, as a clingo term giving its "
            "name and arguments, e.g. 'base' or 'acid(42,d)' [%(default)s]"
        ),
    )
    transform_parser.add_argument(
        "-c",
        "--control-options",
        metavar="OPTIONS",
        help=(
            "extra options to pass to the underlying clingo Control, as a "
            "single string (e.g. '-n 0 --stats'), split the same way a shell "
            "would - quote an individual option containing spaces"
        ),
    )
    transform_parser.add_argument(
        "--facts",
        action="store_true",
        help=(
            "print the combined fact base to stdout instead of writing each "
            "source's transformed text to its own destination (see the "
            "':DEST' source syntax)"
        ),
    )
    transform_parser.set_defaults(func=cmd_transform)


def get_parser() -> ArgumentParser:
    """
    Return the parser for command line options.
    """
    parser = ArgumentParser(
        prog="aspen",
        description=dedent(
            """\
            aspen is a tool for analyzing and manipulating ASTs in the
            clingo ASP language, powered by tree-sitter.

            Use one of the subcommands below to reify sources into their
            ASP fact representation, or transform them via a meta-encoding.
            """
        ),
    )
    levels = [
        ("error", logging.ERROR),
        ("warning", logging.WARNING),
        ("info", logging.INFO),
        ("debug", logging.DEBUG),
    ]

    def get(levels: list[tuple[str, int]], name: str) -> Optional[int]:
        for key, val in levels:
            if key == name:
                return val
        return None  # nocoverage

    parser.add_argument(
        "--log",
        default="warning",
        choices=[val for _, val in levels],
        metavar=f"{{{','.join(key for key, _ in levels)}}}",
        help="set log level [%(default)s]",
        type=cast(Any, lambda name: get(levels, name)),
    )

    parser.add_argument(
        "--version", "-v", action="version", version=f"%(prog)s {VERSION}"
    )

    subparsers = parser.add_subparsers(dest="command", metavar="{reify,transform}")
    _add_reify_parser(subparsers)
    _add_transform_parser(subparsers)

    return parser
