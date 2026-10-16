"""Module defining the sources processed by an AspenTree."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import tree_sitter as ts
from clingo.symbol import Symbol

StringEncoding = Literal["utf8", "utf16"]


@dataclass
class Source:
    """Source processed by an AspenTree."""

    id: Symbol
    source_bytes: bytes
    path: Optional[Path]
    encoding: StringEncoding
    parser: ts.Parser
    tree: ts.Tree
    destination: Optional[Path] = None


def source_str(source: Source) -> str:
    """The identifier to show for a source in error/log messages: its
    file path when read from one, or its source id otherwise (e.g. for
    stdin, or any other in-memory source)."""
    return str(source.path) if source.path is not None else str(source.id)
