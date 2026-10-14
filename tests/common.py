"""Common definitions for tests."""

import logging
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import tree_sitter_aspcore2 as ts_aspcore2
import tree_sitter_clingo as ts_clingo
import tree_sitter_metasp as ts_metasp
from tree_sitter import Language

from aspen.tree import AspenTree
from aspen.utils.log import configure_logging

asp_dir = (Path(__file__) / ".." / "asp").resolve()
encoding_dir = asp_dir / "encodings"
input_dir = asp_dir / "inputs"
output_dir = asp_dir / "outputs"

clingo_lang = Language(ts_clingo.language())
metasp_lang = Language(ts_metasp.language())
aspcore2_lang = Language(ts_aspcore2.language())

configure_logging(sys.stderr, logging.DEBUG, sys.stderr.isatty())


def spy_re_reify() -> Any:
    """Patch re-reification of AspenTree with a mock that calls
    through, to count how often re-reification is done."""
    method = AspenTree._re_reify_changed_subtrees  # pylint: disable=protected-access
    return patch.object(AspenTree, method.__name__, autospec=True, side_effect=method)
