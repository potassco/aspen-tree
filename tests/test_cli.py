"""Unit tests for the aspen.cli module (the `aspen reify`/`aspen
transform` command implementations)."""

import io
import sys
import tempfile
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from clingo.symbol import Function, Number, String

from aspen.cli import (
    _format_facts,
    _parse_program,
    _read_source,
    _write_output,
    cmd_reify,
    cmd_transform,
    resolve_language,
)
from aspen.utils.log import TestCaseWithRedirectedLogs

from .common import encoding_dir


def _transform_namespace(**overrides: object) -> Namespace:
    """Default Namespace for cmd_transform, with any field overridden."""
    defaults: dict[str, object] = {
        "language": "clingo",
        "encoding": "utf8",
        "output": None,
        "meta_file": None,
        "meta_string": None,
        "program": "base",
        "control_option": None,
        "show": "source",
    }
    defaults.update(overrides)
    return Namespace(**defaults)


class TestParseProgram(TestCaseWithRedirectedLogs):
    """Test _parse_program."""

    def test_parse_program_bare_name(self) -> None:
        """Test that a bare name with no parentheses means no args."""
        self.assertEqual(_parse_program("base"), ("base", ()))

    def test_parse_program_single_arg(self) -> None:
        """Test that a single parenthesized argument becomes a
        one-element argument tuple."""
        self.assertEqual(_parse_program("acid(42)"), ("acid", (Number(42),)))

    def test_parse_program_multiple_args(self) -> None:
        """Test that multiple comma-separated arguments, of possibly
        different term types, become an argument tuple in order."""
        self.assertEqual(
            _parse_program('acid(42,"d")'),
            ("acid", (Number(42), String("d"))),
        )

    def test_parse_program_syntax_error(self) -> None:
        """Test that a malformed term is reported as a clear error,
        not a raw clingo RuntimeError."""
        with self.assertRaisesRegex(ValueError, "Invalid --program term"):
            _parse_program("acid(")

    def test_parse_program_non_function_term(self) -> None:
        """Test that a term with no name, such as a bare number or
        string, is rejected with a clear error."""
        with self.assertRaisesRegex(ValueError, "Invalid --program term"):
            _parse_program("42")


class TestResolveLanguage(TestCaseWithRedirectedLogs):
    """Test resolve_language."""

    def test_resolve_language_success(self) -> None:
        """Test that a known, installed grammar resolves to a Language
        with a matching name."""
        language = resolve_language("clingo")
        self.assertEqual(language.name, "clingo")

    def test_resolve_language_missing_module(self) -> None:
        """Test that an unknown grammar name raises a clear error."""
        with self.assertRaisesRegex(ValueError, "tree_sitter_no_such_grammar"):
            resolve_language("no_such_grammar")

    def test_resolve_language_no_language_function(self) -> None:
        """Test that a module that doesn't expose language() raises a
        clear error, distinct from an import failure."""
        fake_module = ModuleType("tree_sitter_fake")
        with patch("aspen.cli.importlib.import_module", return_value=fake_module):
            with self.assertRaisesRegex(ValueError, "does not expose"):
                resolve_language("fake")


class TestReadSource(TestCaseWithRedirectedLogs):
    """Test _read_source."""

    def test_read_source_stdin(self) -> None:
        """Test that "-" reads raw bytes from stdin."""
        with patch.object(sys, "stdin") as mock_stdin:
            mock_stdin.buffer = io.BytesIO(b"a :- b.")
            self.assertEqual(_read_source("-"), b"a :- b.")

    def test_read_source_file(self) -> None:
        """Test that any other argument is treated as a file path."""
        self.assertEqual(_read_source("foo.lp"), Path("foo.lp"))


class TestFormatFacts(TestCaseWithRedirectedLogs):
    """Test _format_facts."""

    def test_format_facts(self) -> None:
        """Test that facts are rendered one per line, each a loadable
        ASP fact ending in '.'."""
        facts = [Function("a", []), Function("b", [Number(1)])]
        self.assertEqual(_format_facts(facts), "a.\nb(1).")


class TestWriteOutput(TestCaseWithRedirectedLogs):
    """Test _write_output."""

    def test_write_output_stdout(self) -> None:
        """Test that output=None prints to stdout."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            _write_output("hello", None)
        self.assertEqual(buf.getvalue(), "hello\n")

    def test_write_output_file(self) -> None:
        """Test that a given output path is written to instead."""
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.txt"
            _write_output("hello", out_path)
            self.assertEqual(out_path.read_text(), "hello\n")


class TestCmdReify(TestCaseWithRedirectedLogs):
    """Test the `aspen reify` command."""

    def test_cmd_reify(self) -> None:
        """Test that cmd_reify parses the given source and prints its
        reified facts."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a.")
            args = Namespace(
                source=str(source_path), language="clingo", encoding="utf8", output=None
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_reify(args)
            output = buf.getvalue()
        self.assertIn('language(s(0),"clingo").', output)
        self.assertIn('type(0,"source_file").', output)

    def test_cmd_reify_stdin(self) -> None:
        """Test that cmd_reify also accepts '-' for stdin."""
        args = Namespace(source="-", language="clingo", encoding="utf8", output=None)
        buf = io.StringIO()
        with patch.object(sys, "stdin") as mock_stdin:
            mock_stdin.buffer = io.BytesIO(b"a.")
            with redirect_stdout(buf):
                cmd_reify(args)
        self.assertIn('language(s(0),"clingo").', buf.getvalue())


class TestCmdTransform(TestCaseWithRedirectedLogs):
    """Test the `aspen transform` command."""

    def test_cmd_transform_requires_meta_source(self) -> None:
        """Test that transform refuses to run with neither --meta-file
        nor --meta-string given."""
        args = _transform_namespace(source="unused")
        with self.assertRaisesRegex(ValueError, "meta-file.*meta-string"):
            cmd_transform(args)

    def test_cmd_transform_prints_transformed_source_by_default(self) -> None:
        """Test that transform reifies the source, applies the given
        meta-encoding, and by default prints the resulting source
        text - this is the "transform also takes care of first
        reifying the input" behavior."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b.")
            args = _transform_namespace(
                source=str(source_path),
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
        self.assertEqual(buf.getvalue(), "a(X) :- b(X).\n")

    def test_cmd_transform_show_facts(self) -> None:
        """Test that --show facts prints the fact base instead of the
        source text."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b.")
            args = _transform_namespace(
                source=str(source_path),
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
                show="facts",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
            output = buf.getvalue()
        self.assertIn('language(s(0),"clingo").', output)
        self.assertNotIn("a(X) :- b(X).", output)

    def test_cmd_transform_show_both(self) -> None:
        """Test that --show both prints the source text and the fact
        base, in that order."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b.")
            args = _transform_namespace(
                source=str(source_path),
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
                show="both",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
            output = buf.getvalue()
        source_part, facts_part = output.split("\n", 1)
        self.assertEqual(source_part, "a(X) :- b(X).")
        self.assertIn('language(s(0),"clingo").', facts_part)

    def test_cmd_transform_with_meta_string(self) -> None:
        """Test that --meta-string works without any --meta-file."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a.")
            args = _transform_namespace(
                source=str(source_path),
                meta_string='aspen(print("hi")) :- #true.',
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
            output = buf.getvalue()
        self.assertIn("hi", output)
        self.assertIn("a.", output)
