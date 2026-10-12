"""Unit tests for the '@aspen/...' include-path convention."""

import tempfile
from pathlib import Path

from aspen.utils.include_resolver import resolve_meta_encoding_file, rewrite_includes
from aspen.utils.log import TestCaseWithRedirectedLogs


class TestRewriteIncludes(TestCaseWithRedirectedLogs):
    """Test the pure text-rewriting of '@aspen/' include targets."""

    def test_rewrites_aspen_prefixed_target(self) -> None:
        """Test that a '@aspen/...' target is rewritten to its real
        location under bundled_utils_path."""
        bundled = Path("/bundled/utils")
        text = '#include "@aspen/clingo/symbol_signature.lp".'
        result = rewrite_includes(text, bundled)
        self.assertEqual(
            result,
            f'#include "{bundled / "clingo/symbol_signature.lp"}".',
        )

    def test_leaves_local_target_untouched(self) -> None:
        """Test that an ordinary relative/absolute #include target
        (not using the '@aspen/' prefix) is left exactly as-is."""
        bundled = Path("/bundled/utils")
        text = '#include "./helpers.lp".'
        self.assertEqual(rewrite_includes(text, bundled), text)

    def test_rewrites_multiple_targets_in_one_text(self) -> None:
        """Test that every '@aspen/' target in a multi-line text gets
        rewritten, while local targets among them are left alone."""
        bundled = Path("/bundled/utils")
        text = (
            '#include "@aspen/a.lp".\n'
            '#include "./local.lp".\n'
            '#include "@aspen/sub/b.lp".\n'
        )
        result = rewrite_includes(text, bundled)
        self.assertEqual(
            result,
            (
                f'#include "{bundled / "a.lp"}".\n'
                '#include "./local.lp".\n'
                f'#include "{bundled / "sub/b.lp"}".\n'
            ),
        )


class TestResolveMetaEncodingFile(TestCaseWithRedirectedLogs):
    """Test resolving a meta-encoding file for loading into clingo,
    rewriting any '@aspen/' includes found anywhere in its local
    (non-'@aspen/') #include graph."""

    def test_returns_same_path_when_no_includes_at_all(self) -> None:
        """Test that a file with no #include directives at all is
        returned unchanged, with no mirroring performed."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as cache:
            tmp_path = Path(tmp)
            bundled = tmp_path / "bundled"
            meta_file = tmp_path / "meta.lp"
            meta_file.write_text("a.")
            result = resolve_meta_encoding_file(meta_file, Path(cache), bundled)
            self.assertEqual(result, meta_file.resolve())

    def test_returns_same_path_when_only_local_includes_without_aspen_prefix(
        self,
    ) -> None:
        """Test that a file whose (possibly nested) local #include-s
        never use '@aspen/' is returned unchanged."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as cache:
            tmp_path = Path(tmp)
            bundled = tmp_path / "bundled"
            leaf = tmp_path / "leaf.lp"
            leaf.write_text("b.")
            main = tmp_path / "main.lp"
            main.write_text('#include "./leaf.lp".\na.')
            result = resolve_meta_encoding_file(main, Path(cache), bundled)
            self.assertEqual(result, main.resolve())

    def test_diamond_shaped_include_graph_without_aspen_prefix_is_a_no_op(
        self,
    ) -> None:
        """Test that a diamond-shaped local #include graph (main
        includes both a and b, both of which include the same shared
        file) where nothing anywhere uses '@aspen/' is detected as
        needing no rewriting, with shared only checked once rather
        than once per parent."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as cache:
            tmp_path = Path(tmp)
            bundled = tmp_path / "bundled"
            shared = tmp_path / "shared.lp"
            shared.write_text("shared.")
            a_path = tmp_path / "a.lp"
            a_path.write_text('#include "./shared.lp".\na.')
            b_path = tmp_path / "b.lp"
            b_path.write_text('#include "./shared.lp".\nb.')
            main = tmp_path / "main.lp"
            main.write_text('#include "./a.lp".\n#include "./b.lp".\nmain.')
            result = resolve_meta_encoding_file(main, Path(cache), bundled)
            self.assertEqual(result, main.resolve())

    def test_mirrors_file_that_directly_uses_aspen_prefix(self) -> None:
        """Test that a file directly using '@aspen/' is mirrored into
        cache_root, with the include rewritten to the real bundled
        path."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as cache:
            tmp_path = Path(tmp)
            cache_path = Path(cache)
            bundled = tmp_path / "bundled"
            bundled.mkdir()
            (bundled / "symbol_signature.lp").write_text("symbol_signature(N,Name).")
            meta_file = tmp_path / "meta.lp"
            meta_file.write_text('#include "@aspen/symbol_signature.lp".\na.')
            result = resolve_meta_encoding_file(meta_file, cache_path, bundled)
            self.assertNotEqual(result, meta_file.resolve())
            self.assertTrue(result.is_relative_to(cache_path))
            rewritten_text = result.read_text()
            self.assertEqual(
                rewritten_text,
                f'#include "{bundled / "symbol_signature.lp"}".\na.',
            )

    def test_mirrors_local_file_that_transitively_uses_aspen_prefix(self) -> None:
        """Test that when a locally-#include-d file uses '@aspen/',
        the including file is mirrored too (preserving its local
        #include target unchanged), so that the mirrored pair still
        resolve relative to one another exactly as the originals
        did."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as cache:
            tmp_path = Path(tmp)
            cache_path = Path(cache)
            bundled = tmp_path / "bundled"
            bundled.mkdir()
            (bundled / "foo.lp").write_text("foo.")
            helpers = tmp_path / "helpers.lp"
            helpers.write_text('#include "@aspen/foo.lp".\nhelper.')
            main = tmp_path / "main.lp"
            main.write_text('#include "./helpers.lp".\nmain.')
            result = resolve_meta_encoding_file(main, cache_path, bundled)
            self.assertNotEqual(result, main.resolve())
            self.assertEqual(result.read_text(), '#include "./helpers.lp".\nmain.')
            mirrored_helpers = result.parent / "helpers.lp"
            self.assertTrue(mirrored_helpers.is_file())
            self.assertEqual(
                mirrored_helpers.read_text(),
                f'#include "{bundled / "foo.lp"}".\nhelper.',
            )

    def test_diamond_shaped_include_graph_materializes_shared_file_once(self) -> None:
        """Test that a file reachable via two different parents (a
        diamond: main includes both a and b, both of which include
        shared, which uses '@aspen/') is only materialized once, and
        both parents end up pointing at that same mirrored copy."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as cache:
            tmp_path = Path(tmp)
            cache_path = Path(cache)
            bundled = tmp_path / "bundled"
            bundled.mkdir()
            (bundled / "foo.lp").write_text("foo.")
            shared = tmp_path / "shared.lp"
            shared.write_text('#include "@aspen/foo.lp".\nshared.')
            a_path = tmp_path / "a.lp"
            a_path.write_text('#include "./shared.lp".\na.')
            b_path = tmp_path / "b.lp"
            b_path.write_text('#include "./shared.lp".\nb.')
            main = tmp_path / "main.lp"
            main.write_text('#include "./a.lp".\n#include "./b.lp".\nmain.')
            result = resolve_meta_encoding_file(main, cache_path, bundled)
            mirrored_shared = result.parent / "shared.lp"
            self.assertEqual(
                mirrored_shared.read_text(),
                f'#include "{bundled / "foo.lp"}".\nshared.',
            )

    def test_skips_missing_local_include_target_without_raising(self) -> None:
        """Test that a dangling local #include (pointing at a file
        that doesn't exist) is simply not followed, rather than
        raising - clingo itself is left to report that error when it
        loads the (unchanged) file."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as cache:
            tmp_path = Path(tmp)
            bundled = tmp_path / "bundled"
            meta_file = tmp_path / "meta.lp"
            meta_file.write_text('#include "./does_not_exist.lp".\na.')
            result = resolve_meta_encoding_file(meta_file, Path(cache), bundled)
            self.assertEqual(result, meta_file.resolve())
