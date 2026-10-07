"""
Test cases for main application functionality.
"""

import logging
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aspen.__main__ import main
from aspen.cli import cmd_reify, cmd_transform
from aspen.utils.log import TestCaseWithRedirectedLogs, configure_logging, get_logger
from aspen.utils.parser import get_parser


class TestMain(TestCaseWithRedirectedLogs):
    """
    Test cases for main application functionality.
    """

    def test_logger(self) -> None:
        """
        Test the logger.
        """
        sio = StringIO()
        configure_logging(sio, logging.INFO, True)
        log = get_logger("main")
        with self.assertLogs("main", level=logging.INFO):
            log.info("test123")

    def test_parser(self) -> None:
        """
        Test the parser.
        """
        parser = get_parser()
        ret = parser.parse_args(["--log", "info"])
        self.assertEqual(ret.log, logging.INFO)

    def test_parser_no_command(self) -> None:
        """Test that no subcommand leaves func unset, rather than
        argparse requiring one - main() checks for this itself."""
        parser = get_parser()
        ret = parser.parse_args([])
        self.assertFalse(hasattr(ret, "func"))

    def test_parser_reify_subcommand(self) -> None:
        """Test that the reify subcommand's arguments parse as
        expected, with their documented defaults."""
        parser = get_parser()
        ret = parser.parse_args(["reify", "foo.lp", "-l", "clingo"])
        self.assertEqual(ret.command, "reify")
        self.assertEqual(ret.source, ["foo.lp"])
        self.assertEqual(ret.language, "clingo")
        self.assertEqual(ret.encoding, "utf8")
        self.assertIs(ret.func, cmd_reify)

    def test_parser_reify_language_defaults_to_none(self) -> None:
        """Test that -l/--language is optional: with every source
        giving its own '@LANG', no default is required."""
        parser = get_parser()
        ret = parser.parse_args(["reify", "foo.lp@clingo"])
        self.assertIsNone(ret.language)
        self.assertEqual(ret.source, ["foo.lp@clingo"])

    def test_parser_reify_multiple_sources(self) -> None:
        """Test that reify accepts multiple source positionals."""
        parser = get_parser()
        ret = parser.parse_args(["reify", "foo.lp", "bar.lp", "-l", "clingo"])
        self.assertEqual(ret.source, ["foo.lp", "bar.lp"])

    def test_parser_reify_encoding_short_flag(self) -> None:
        """Test that -e is the short form of --encoding for reify."""
        parser = get_parser()
        ret = parser.parse_args(["reify", "foo.lp", "-l", "clingo", "-e", "utf16"])
        self.assertEqual(ret.encoding, "utf16")

    def test_parser_transform_subcommand(self) -> None:
        """Test that the transform subcommand's arguments - including
        the ones specific to it - parse as expected, using their
        short flags."""
        parser = get_parser()
        ret = parser.parse_args(
            [
                "transform",
                "foo.lp@clingo:foo.out.lp",
                "bar.lp:-",
                "-l",
                "clingo",
                "-e",
                "utf16",
                "-f",
                "a.lp",
                "-f",
                "b.lp",
                "-s",
                'aspen(print("hi")).',
                "-p",
                'my_program("X")',
                "--control-option",
                "-n 0",
                "--facts",
            ]
        )
        self.assertEqual(ret.command, "transform")
        self.assertEqual(ret.source, ["foo.lp@clingo:foo.out.lp", "bar.lp:-"])
        self.assertEqual(ret.encoding, "utf16")
        self.assertEqual(ret.meta_file, [Path("a.lp"), Path("b.lp")])
        self.assertEqual(ret.meta_string, 'aspen(print("hi")).')
        self.assertEqual(ret.program, 'my_program("X")')
        self.assertEqual(ret.control_option, ["-n 0"])
        self.assertTrue(ret.facts)
        self.assertIs(ret.func, cmd_transform)

    def test_parser_transform_facts_defaults_false(self) -> None:
        """Test that --facts defaults to off, i.e. the transformed
        source text is written out by default."""
        parser = get_parser()
        ret = parser.parse_args(["transform", "foo.lp", "-l", "clingo"])
        self.assertFalse(ret.facts)

    def test_main_runs_reify(self) -> None:
        """Test that main() dispatches to the reify command and
        prints its output."""
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "in.lp"
            source_path.write_text("a.")
            buf = StringIO()
            with (
                patch.object(
                    sys, "argv", ["aspen", "reify", str(source_path), "-l", "clingo"]
                ),
                patch.object(sys, "stdout", buf),
            ):
                main()
        self.assertIn('language(s(0),"clingo").', buf.getvalue())

    def test_main_no_command_shows_help_and_exits(self) -> None:
        """Test that running with no subcommand prints help and exits
        with a non-zero status, rather than silently doing nothing."""
        buf = StringIO()
        with patch.object(sys, "argv", ["aspen"]), patch.object(sys, "stdout", buf):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("usage:", buf.getvalue())

    def test_main_reports_errors_and_exits(self) -> None:
        """Test that an error raised by the dispatched command (here:
        an unknown grammar) is reported on stderr, not as a raw
        traceback, and exits with a non-zero status."""
        out_buf = StringIO()
        err_buf = StringIO()
        with (
            patch.object(
                sys, "argv", ["aspen", "reify", "foo.lp", "-l", "no_such_grammar"]
            ),
            patch.object(sys, "stdout", out_buf),
            patch.object(sys, "stderr", err_buf),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("error:", err_buf.getvalue())
        self.assertIn("tree_sitter_no_such_grammar", err_buf.getvalue())
