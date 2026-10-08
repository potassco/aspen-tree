"""Unit tests for the aspen.cli module (the `aspen reify`/`aspen
transform` command implementations)."""

import io
import re
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
    _parse_control_options,
    _parse_program,
    _parse_source_spec,
    _read_source,
    cmd_reify,
    cmd_transform,
    resolve_language,
)
from aspen.tree import TransformError
from aspen.utils.log import TestCaseWithRedirectedLogs

from .common import encoding_dir


def _reify_namespace(**overrides: object) -> Namespace:
    """Default Namespace for cmd_reify, with any field overridden."""
    defaults: dict[str, object] = {
        "language": "clingo",
        "encoding": "utf8",
        "allow_syntax_errors": False,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def _transform_namespace(**overrides: object) -> Namespace:
    """Default Namespace for cmd_transform, with any field overridden."""
    defaults: dict[str, object] = {
        "language": "clingo",
        "encoding": "utf8",
        "allow_syntax_errors": False,
        "meta_file": None,
        "meta_string": None,
        "program": "base",
        "control_options": None,
        "facts": False,
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


class TestParseControlOptions(TestCaseWithRedirectedLogs):
    """Test _parse_control_options."""

    def test_parse_control_options_none(self) -> None:
        """Test that omitting -c/--control-options means no extra
        options at all."""
        self.assertEqual(_parse_control_options(None), [])

    def test_parse_control_options_empty_string(self) -> None:
        """Test that an empty string also means no extra options."""
        self.assertEqual(_parse_control_options(""), [])

    def test_parse_control_options_single(self) -> None:
        """Test that a single option becomes a one-element list."""
        self.assertEqual(_parse_control_options("--stats"), ["--stats"])

    def test_parse_control_options_multiple(self) -> None:
        """Test that multiple space-separated options, including one
        with its own value, are split into individual tokens - this
        is the whole point: one argument listing every option."""
        self.assertEqual(_parse_control_options("-n 0 --stats"), ["-n", "0", "--stats"])

    def test_parse_control_options_quoted_value(self) -> None:
        """Test that a quoted value keeps its embedded spaces, the
        same way a shell would handle it."""
        self.assertEqual(
            _parse_control_options('--opt "a value with spaces"'),
            ["--opt", "a value with spaces"],
        )

    def test_parse_control_options_malformed_quoting(self) -> None:
        """Test that malformed quoting is reported as a clear error,
        not a raw shlex traceback."""
        with self.assertRaises(ValueError):
            _parse_control_options('--opt "unterminated')


class TestParseSourceSpec(TestCaseWithRedirectedLogs):
    """Test _parse_source_spec."""

    def test_parse_source_spec_plain(self) -> None:
        """Test that a bare source has no language override and
        defaults to stdout."""
        self.assertEqual(
            _parse_source_spec("a.lp", allow_dest=True), ("a.lp", None, None)
        )

    def test_parse_source_spec_with_lang(self) -> None:
        """Test that '@LANG' is split off as a language override."""
        self.assertEqual(
            _parse_source_spec("a.lp@clingo", allow_dest=True),
            ("a.lp", "clingo", None),
        )

    def test_parse_source_spec_explicit_stdout(self) -> None:
        """Test that ':-' makes the default to stdout explicit."""
        self.assertEqual(
            _parse_source_spec("a.lp:-", allow_dest=True), ("a.lp", None, None)
        )

    def test_parse_source_spec_file_destination(self) -> None:
        """Test that ':DEST' routes to a file destination."""
        self.assertEqual(
            _parse_source_spec("a.lp:a-trans.lp", allow_dest=True),
            ("a.lp", None, Path("a-trans.lp")),
        )

    def test_parse_source_spec_lang_and_destination(self) -> None:
        """Test that '@LANG' and ':DEST' combine, in that order."""
        self.assertEqual(
            _parse_source_spec("a.lp@clingo:a-trans.lp", allow_dest=True),
            ("a.lp", "clingo", Path("a-trans.lp")),
        )

    def test_parse_source_spec_reversed_order_rejected(self) -> None:
        """Test that ':DEST@LANG' (destination before language) is
        rejected, since only SOURCE[@LANG][:DEST] is accepted."""
        with self.assertRaisesRegex(ValueError, "@LANG.*:DEST"):
            _parse_source_spec("a.lp:a-trans.lp@clingo", allow_dest=True)

    def test_parse_source_spec_destination_rejected_when_disallowed(self) -> None:
        """Test that ':DEST' is rejected outright when allow_dest is
        False, e.g. for reify."""
        with self.assertRaisesRegex(ValueError, "not accepted here"):
            _parse_source_spec("a.lp:out.lp", allow_dest=False)

    def test_parse_source_spec_lang_allowed_when_dest_disallowed(self) -> None:
        """Test that '@LANG' alone is still accepted when allow_dest
        is False."""
        self.assertEqual(
            _parse_source_spec("a.lp@clingo", allow_dest=False),
            ("a.lp", "clingo", None),
        )

    def test_parse_source_spec_stdin_plain(self) -> None:
        """Test that bare stdin ('-') has no language override and
        defaults to stdout."""
        self.assertEqual(_parse_source_spec("-", allow_dest=True), ("-", None, None))

    def test_parse_source_spec_stdin_with_lang_and_destination(self) -> None:
        """Test that stdin can combine '@LANG' and ':DEST', just
        like a file source."""
        self.assertEqual(
            _parse_source_spec("-@clingo:out.lp", allow_dest=True),
            ("-", "clingo", Path("out.lp")),
        )


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


class TestCmdReify(TestCaseWithRedirectedLogs):
    """Test the `aspen reify` command."""

    def test_cmd_reify(self) -> None:
        """Test that cmd_reify parses the given source and prints its
        reified facts."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a.")
            args = _reify_namespace(source=[str(source_path)])
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_reify(args)
            output = buf.getvalue()
        self.assertIn('language(s(0),"clingo").', output)
        self.assertIn('type(0,"source_file").', output)

    def test_cmd_reify_stdin(self) -> None:
        """Test that cmd_reify also accepts '-' for stdin."""
        args = _reify_namespace(source=["-"])
        buf = io.StringIO()
        with patch.object(sys, "stdin") as mock_stdin:
            mock_stdin.buffer = io.BytesIO(b"a.")
            with redirect_stdout(buf):
                cmd_reify(args)
        self.assertIn('language(s(0),"clingo").', buf.getvalue())

    def test_cmd_reify_multiple_sources(self) -> None:
        """Test that cmd_reify parses multiple sources in order and
        prints their combined fact base, sharing one identifier
        namespace."""
        with tempfile.TemporaryDirectory() as tmp:
            first_path = Path(tmp) / "first.lp"
            first_path.write_text("a.")
            second_path = Path(tmp) / "second.lp"
            second_path.write_text("b.")
            args = _reify_namespace(source=[str(first_path), str(second_path)])
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_reify(args)
            output = buf.getvalue()
        self.assertIn('language(s(0),"clingo").', output)
        self.assertIn('language(s(1),"clingo").', output)

    def test_cmd_reify_stdin_twice_rejected(self) -> None:
        """Test that using '-' more than once is rejected with a
        clear error, rather than silently reading an empty source the
        second time."""
        args = _reify_namespace(source=["-", "-"])
        with self.assertRaisesRegex(ValueError, "stdin"):
            cmd_reify(args)

    def test_cmd_reify_source_lang_override(self) -> None:
        """Test that a source's '@LANG' suffix overrides the default
        -l/--language for that source."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a.")
            args = _reify_namespace(source=[f"{source_path}@aspcore2"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_reify(args)
        self.assertIn('language(s(0),"aspcore2").', buf.getvalue())

    def test_cmd_reify_no_default_language_needed_when_overridden(self) -> None:
        """Test that -l/--language can be omitted entirely as long as
        every source specifies its own '@LANG'."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a.")
            args = _reify_namespace(source=[f"{source_path}@clingo"], language=None)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_reify(args)
        self.assertIn('language(s(0),"clingo").', buf.getvalue())

    def test_cmd_reify_missing_language_rejected(self) -> None:
        """Test that a source with no '@LANG' and no default
        -l/--language raises a clear error, rather than crashing."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a.")
            args = _reify_namespace(source=[str(source_path)], language=None)
            with self.assertRaisesRegex(ValueError, "[Nn]o.*language"):
                cmd_reify(args)

    def test_cmd_reify_rejects_destination_suffix(self) -> None:
        """Test that reify rejects a ':DEST' suffix on any source:
        reify always writes its combined output to stdout."""
        args = _reify_namespace(source=["a.lp:out.lp"])
        with self.assertRaisesRegex(ValueError, "not accepted here"):
            cmd_reify(args)

    def test_cmd_reify_raises_syntax_error_by_default(self) -> None:
        """Test that a source with a syntax error raises immediately,
        by default, rather than silently reifying it - and that the
        message is prefixed with the source's own file path, so the
        user can tell which file it came from."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b")
            args = _reify_namespace(source=[str(source_path)])
            expected_path = re.escape(str(source_path.resolve()))
            with self.assertRaisesRegex(
                TransformError, f"^{expected_path}:1:6: missing '\\.'"
            ):
                cmd_reify(args)

    def test_cmd_reify_raises_syntax_error_stdin(self) -> None:
        """Test that a syntax error from a stdin source is prefixed
        with its source id (e.g. 's(0)'), rather than a file path,
        since stdin has none - so the user can tell it came from
        stdin."""
        args = _reify_namespace(source=["-"])
        with patch.object(sys, "stdin") as mock_stdin:
            mock_stdin.buffer = io.BytesIO(b"a :- b")
            with self.assertRaisesRegex(TransformError, r"^s\(0\):1:6: missing '\.'"):
                cmd_reify(args)

    def test_cmd_reify_allow_syntax_errors(self) -> None:
        """Test that --allow-syntax-errors lets reify succeed on a
        source with a syntax error, instead of raising."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b")
            args = _reify_namespace(source=[str(source_path)], allow_syntax_errors=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_reify(args)
        self.assertIn("missing(", buf.getvalue())


class TestCmdTransform(TestCaseWithRedirectedLogs):
    """Test the `aspen transform` command."""

    def test_cmd_transform_requires_meta_source(self) -> None:
        """Test that transform refuses to run with neither --meta-file
        nor --meta-string given."""
        args = _transform_namespace(source=["unused"])
        with self.assertRaisesRegex(ValueError, "meta-file.*meta-string"):
            cmd_transform(args)

    def test_cmd_transform_raises_syntax_error_by_default(self) -> None:
        """Test that a source with a syntax error raises immediately,
        by default, rather than silently transforming it."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b")
            args = _transform_namespace(
                source=[str(source_path)],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
            )
            with self.assertRaisesRegex(TransformError, "missing '\\.'"):
                cmd_transform(args)

    def test_cmd_transform_allow_syntax_errors(self) -> None:
        """Test that --allow-syntax-errors lets transform succeed on a
        source with a syntax error, instead of raising."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b")
            args = _transform_namespace(
                source=[str(source_path)],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
                allow_syntax_errors=True,
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
        self.assertEqual(buf.getvalue(), "a(X) :- b(X)\n")

    def test_cmd_transform_prints_transformed_source_by_default(self) -> None:
        """Test that transform reifies the source, applies the given
        meta-encoding, and by default prints the resulting source
        text - this is the "transform also takes care of first
        reifying the input" behavior."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b.")
            args = _transform_namespace(
                source=[str(source_path)],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
        self.assertEqual(buf.getvalue(), "a(X) :- b(X).\n")

    def test_cmd_transform_facts_flag(self) -> None:
        """Test that --facts prints the fact base instead of the
        source text."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b.")
            args = _transform_namespace(
                source=[str(source_path)],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
                facts=True,
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
            output = buf.getvalue()
        self.assertIn('language(s(0),"clingo").', output)
        self.assertNotIn("a(X) :- b(X).", output)

    def test_cmd_transform_facts_flag_rejects_destination(self) -> None:
        """Test that --facts rejects a ':DEST' on any source: it
        makes no sense there, since the combined fact base always
        goes to stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b.")
            args = _transform_namespace(
                source=[f"{source_path}:{Path(tmp) / 'out.lp'}"],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
                facts=True,
            )
            with self.assertRaisesRegex(ValueError, ":DEST.*--facts"):
                cmd_transform(args)

    def test_cmd_transform_facts_flag_allows_explicit_stdout(self) -> None:
        """Test that --facts tolerates an explicit ':-' (stdout) on a
        source, since it doesn't actually request a destination."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b.")
            args = _transform_namespace(
                source=[f"{source_path}:-"],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
                facts=True,
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
        self.assertIn('language(s(0),"clingo").', buf.getvalue())

    def test_cmd_transform_with_meta_string(self) -> None:
        """Test that --meta-string works without any --meta-file."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a.")
            args = _transform_namespace(
                source=[str(source_path)],
                meta_string='aspen(print("hi")) :- #true.',
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
            output = buf.getvalue()
        self.assertIn("hi", output)
        self.assertIn("a.", output)

    def test_cmd_transform_control_options(self) -> None:
        """Test that a -c/--control-options string listing several
        clingo options in one go is split and passed through to the
        underlying clingo Control without breaking the transform."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b.")
            args = _transform_namespace(
                source=[str(source_path)],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
                control_options="--stats --warn no-atom-undefined",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
        self.assertEqual(buf.getvalue(), "a(X) :- b(X).\n")

    def test_cmd_transform_multiple_sources_default_to_stdout(self) -> None:
        """Test that with no ':DEST' suffix at all, every source's
        result is printed to stdout, in order."""
        with tempfile.TemporaryDirectory() as tmp:
            first_path = Path(tmp) / "first.lp"
            first_path.write_text("a :- b.")
            second_path = Path(tmp) / "second.lp"
            second_path.write_text("c :- d.")
            args = _transform_namespace(
                source=[str(first_path), str(second_path)],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
        self.assertEqual(buf.getvalue(), "a(X) :- b(X).\nc(X) :- d(X).\n")

    def test_cmd_transform_multiple_sources_separate_destinations(self) -> None:
        """Test that a ':DEST' suffix on each source, in order, sends
        each source's result to its own file instead of stdout, while
        a source with no suffix still defaults to stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            first_path = Path(tmp) / "first.lp"
            first_path.write_text("a :- b.")
            second_path = Path(tmp) / "second.lp"
            second_path.write_text("c :- d.")
            first_out = Path(tmp) / "first.out.lp"
            args = _transform_namespace(
                source=[f"{first_path}:{first_out}", str(second_path)],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
            self.assertEqual(first_out.read_text(), "a(X) :- b(X).\n")
            self.assertEqual(buf.getvalue(), "c(X) :- d(X).\n")

    def test_cmd_transform_source_explicit_stdout(self) -> None:
        """Test that ':-' explicitly routes a source's result to
        stdout, same as omitting the suffix entirely."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b.")
            args = _transform_namespace(
                source=[f"{source_path}:-"],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_transform(args)
        self.assertEqual(buf.getvalue(), "a(X) :- b(X).\n")

    def test_cmd_transform_stdin_with_destination(self) -> None:
        """Test that stdin's result can be routed to a file via
        '-:DEST', just like any other source."""
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.lp"
            args = _transform_namespace(
                source=[f"-:{out_path}"],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
            )
            with patch.object(sys, "stdin") as mock_stdin:
                mock_stdin.buffer = io.BytesIO(b"a :- b.")
                cmd_transform(args)
            self.assertEqual(out_path.read_text(), "a(X) :- b(X).\n")

    def test_cmd_transform_mixed_sources_and_destinations(self) -> None:
        """Test a mix of stdin and file sources, each independently
        defaulting to stdout or routed to its own file."""
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "file.lp"
            file_path.write_text("c :- d.")
            file_out = Path(tmp) / "file.out.lp"
            args = _transform_namespace(
                source=["-", f"{file_path}:{file_out}"],
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
            )
            buf = io.StringIO()
            with patch.object(sys, "stdin") as mock_stdin:
                mock_stdin.buffer = io.BytesIO(b"a :- b.")
                with redirect_stdout(buf):
                    cmd_transform(args)
            self.assertEqual(buf.getvalue(), "a(X) :- b(X).\n")
            self.assertEqual(file_out.read_text(), "c(X) :- d(X).\n")

    def test_cmd_transform_source_lang_override(self) -> None:
        """Test that a source's '@LANG' suffix overrides the default
        -l/--language for just that source, combined with ':DEST'."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a :- b.")
            out_path = Path(tmp) / "out.lp"
            args = _transform_namespace(
                source=[f"{source_path}@clingo:{out_path}"],
                language=None,
                meta_file=[encoding_dir / "add_var.lp"],
                program='add_var_to_atoms("X")',
            )
            cmd_transform(args)
            self.assertEqual(out_path.read_text(), "a(X) :- b(X).\n")

    def test_cmd_transform_reversed_order_rejected(self) -> None:
        """Test that ':DEST@LANG' (destination before language) is
        rejected with a clear error."""
        args = _transform_namespace(
            source=["a.lp:out.lp@clingo"],
            meta_file=[encoding_dir / "add_var.lp"],
            program='add_var_to_atoms("X")',
        )
        with self.assertRaisesRegex(ValueError, "@LANG.*:DEST"):
            cmd_transform(args)

    def test_cmd_transform_stdin_twice_rejected(self) -> None:
        """Test that using '-' more than once is rejected with a
        clear error, rather than silently reading an empty source the
        second time."""
        args = _transform_namespace(
            source=["-", "-"],
            meta_string='aspen(print("hi")) :- #true.',
        )
        with self.assertRaisesRegex(ValueError, "stdin"):
            cmd_transform(args)
