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


def _add_source_arguments(subparser: ArgumentParser) -> None:
    """Arguments shared by both subcommands: what to parse, and how."""
    subparser.add_argument(
        "source", help="path to the source file to parse, or '-' for stdin"
    )
    subparser.add_argument(
        "-l",
        "--language",
        required=True,
        metavar="NAME",
        help=(
            "tree-sitter grammar to parse with, e.g. 'clingo' "
            "(loads the installed tree_sitter_clingo package)"
        ),
    )
    subparser.add_argument(
        "--encoding",
        choices=["utf8", "utf16"],
        default="utf8",
        help="text encoding of the source file [%(default)s]",
    )
    subparser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="write output to this file instead of stdout",
    )


def _add_reify_parser(subparsers: "_SubParsersAction[ArgumentParser]") -> None:
    reify_parser = subparsers.add_parser(
        "reify",
        help="Parse a source and print its reified ASP fact representation.",
    )
    _add_source_arguments(reify_parser)
    reify_parser.set_defaults(func=cmd_reify)


def _add_transform_parser(subparsers: "_SubParsersAction[ArgumentParser]") -> None:
    transform_parser = subparsers.add_parser(
        "transform",
        help=(
            "Parse a source, apply a transformation meta-encoding to it, "
            "and print the result."
        ),
    )
    _add_source_arguments(transform_parser)
    transform_parser.add_argument(
        "-f",
        "--meta-file",
        type=Path,
        action="append",
        metavar="PATH",
        help="a meta-encoding file to apply (repeatable)",
    )
    transform_parser.add_argument(
        "-e",
        "--meta-string",
        metavar="SOURCE",
        help="inline meta-encoding source to apply, in addition to any --meta-file",
    )
    transform_parser.add_argument(
        "--program",
        default="base",
        metavar="NAME(ARGS)",
        help=(
            "the meta-encoding's entry program part, as a clingo term giving its "
            "name and arguments, e.g. 'base' or 'acid(42,d)' [%(default)s]"
        ),
    )
    transform_parser.add_argument(
        "--control-option",
        action="append",
        metavar="OPTION",
        help="an extra option to pass to the underlying clingo Control (repeatable)",
    )
    transform_parser.add_argument(
        "--show",
        choices=["source", "facts", "both"],
        default="source",
        help="what to print after transforming [%(default)s]",
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

            Use one of the subcommands below to reify a source into its
            ASP fact representation, or transform it via a meta-encoding.
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
