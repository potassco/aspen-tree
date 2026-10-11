"""Resolve the '@aspen/...' include convention, which lets a
user-authored meta-encoding reference aspen's own bundled ASP utility
library (shipped under asp/utils) without needing to know where aspen
itself is installed, e.g.:

  #include "@aspen/clingo/derived_predicates/symbol_signature.lp".

clingo's own #include only understands paths relative to the file
containing the directive (or absolute paths), with no library search
path of its own - and no amount of relative '../..' climbing can
express "wherever aspen happens to be installed", since that varies
per installation. So the '@aspen/' prefix has to be rewritten to an
absolute path before the file ever reaches clingo; that is what this
module does, recursively following local (non-'@aspen/') #include-s
so that a user's own file three levels deep can use '@aspen/' too.
"""

import re
from pathlib import Path

ASPEN_PREFIX = "@aspen/"

_INCLUDE_RE = re.compile(r'#include\s*"([^"]*)"')


def rewrite_includes(text: str, bundled_utils_path: Path) -> str:
    """Rewrite every #include "@aspen/foo.lp" in text to the real,
    absolute location of foo.lp under bundled_utils_path. Other
    #include targets are left untouched."""

    def replace(match: re.Match[str]) -> str:
        target = match.group(1)
        if not target.startswith(ASPEN_PREFIX):
            return match.group(0)
        resolved = bundled_utils_path / target[len(ASPEN_PREFIX) :]
        return f'#include "{resolved}"'

    return _INCLUDE_RE.sub(replace, text)


def _local_include_targets(text: str, including_file: Path) -> list[Path]:
    """Files text #include-s via a local (non-'@aspen/') target,
    resolved relative to including_file's own directory - the further
    files whose own #include graph still needs checking."""
    targets = []
    for match in _INCLUDE_RE.finditer(text):
        target = match.group(1)
        if target.startswith(ASPEN_PREFIX):
            continue
        candidate = (including_file.parent / target).resolve()
        if candidate.is_file():
            targets.append(candidate)
    return targets


def _uses_aspen_prefix(text: str) -> bool:
    return any(
        match.group(1).startswith(ASPEN_PREFIX) for match in _INCLUDE_RE.finditer(text)
    )


def _needs_rewriting(path: Path, seen: set[Path]) -> bool:
    if path in seen:
        return False
    seen.add(path)
    text = path.read_text()
    return _uses_aspen_prefix(text) or any(
        _needs_rewriting(target, seen) for target in _local_include_targets(text, path)
    )


def _materialize(
    path: Path, cache_root: Path, bundled_utils_path: Path, done: dict[Path, Path]
) -> Path:
    if path in done:
        return done[path]
    text = path.read_text()
    for target in _local_include_targets(text, path):
        _materialize(target, cache_root, bundled_utils_path, done)
    mirrored = cache_root / path.relative_to(path.anchor)
    mirrored.parent.mkdir(parents=True, exist_ok=True)
    mirrored.write_text(rewrite_includes(text, bundled_utils_path))
    done[path] = mirrored
    return mirrored


def resolve_meta_encoding_file(
    path: Path, cache_root: Path, bundled_utils_path: Path
) -> Path:
    """The file aspen should load into clingo in place of path: path
    itself, unchanged, if neither it nor anything it (transitively,
    locally) #include-s uses the '@aspen/' convention; otherwise a
    rewritten copy, mirrored under cache_root at the same
    absolute-path-derived layout, so that unrelated local #include-s
    between mirrored files keep resolving exactly as they did from
    path's original location."""
    path = path.resolve()
    if not _needs_rewriting(path, set()):
        return path
    return _materialize(path, cache_root, bundled_utils_path, {})
