"""Benchmark the metasp preprocessing pipeline.

The pipeline mirrors the two aspen transformations performed by the
metasp system, using the metasp encodings of the test suite:

- preprocess: the syntax definitions and programs are transformed
  together, rewriting show statements, generating externals, writing
  the type facts and finally removing ampersands;
- semantics: the ampersands are removed from semantics encodings.

The cases consist of the metasp examples in the metasp directory next
to this script, and of generated programs consisting of copies of the
metasp integration test input with predicates renamed apart, which
allow measuring how the pipeline scales.

Besides the total time, the time spent in the phases of a run is
reported: parsing and reification of the sources, and, for each
transformation step, loading facts into clingo, grounding, solving, the
python model callbacks processing the results (symbol dispatch,
editing and reparsing the sources), and re-reification of the edited
subtrees. Only phases taking a significant share of the total time are
shown (see --min-share).

Example:

    python benchmarks/metasp.py --copies 1 20 80 --repeat 3
    python benchmarks/metasp.py --cases 'tel/*' 'generated/*'
"""

import argparse
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from fnmatch import fnmatch
from functools import wraps
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

import tree_sitter_metasp as ts_metasp
from clingo import Control, Function
from tree_sitter import Language

from aspen.tree import AspenTree
from aspen.utils.log import configure_logging

benchmark_dir = (Path(__file__).parent / "metasp").resolve()
asp_dir = (Path(__file__).parent / ".." / "tests" / "asp").resolve()
metasp_enc_dir = asp_dir / "encodings" / "metasp"
metasp_inp_dir = asp_dir / "inputs" / "metasp"

metasp_lang = Language(ts_metasp.language())

renamed_predicates = re.compile(r"\b(light|green|push|red)\(")


@dataclass
class Case:
    """A benchmark case: files transformed together in one stage."""

    name: str
    stage: Literal["preprocess", "semantics"]
    files: list[Path]
    syntax: list[Path] = field(default_factory=list)


def example_cases() -> list[Case]:
    """Return the cases built from the metasp examples."""
    b = benchmark_dir
    return [
        Case("tel/paper-lights", "preprocess",
             [b / "tel/instances/paper-lights.lp"], [b / "tel/syntax.lp"]),
        Case("bool/simple", "preprocess",
             [b / "bool/instances/simple.lp"], [b / "bool/syntax.lp"]),
        Case("del/paper-lights", "preprocess",
             [b / "del/instances/paper-lights.lp"],
             [b / "del/syntax.lp", b / "tel/syntax.lp"]),
        Case("del/elevator", "preprocess",
             [b / "del/instances/elevator/encoding.lp",
              b / "del/instances/elevator/instance.lp"],
             [b / "del/syntax.lp", b / "tel/syntax.lp"]),
        Case("num/simple", "preprocess",
             [b / "num/instances/simple.lp"], [b / "num/syntax.lp"]),
        Case("mel/paper-lights", "preprocess",
             [b / "mel/instances/paper-lights.lp"], [b / "mel/syntax.lp"]),
        Case("mel/paper-lights-constraint", "preprocess",
             [b / "mel/instances/paper-lights-constraint.lp"], [b / "mel/syntax.lp"]),
        Case("mel/dentist", "preprocess",
             [b / "mel/instances/dentist.lp"], [b / "mel/syntax.lp"]),
        *[Case(f"mel/job-shop-{i}", "preprocess",
               [b / "mel/instances/job-shop/encoding.lp",
                b / f"mel/instances/job-shop/instances/{i}.lp"],
               [b / "mel/syntax.lp"])
          for i in ("small", "ft06", "ft10")],
        Case("mel/mapf-empty_x6_y6", "preprocess",
             [b / "mel/instances/mapf/encoding.lp",
              b / "mel/instances/mapf/instances/empty_x6_y6.lp"],
             [b / "mel/syntax.lp"]),
        Case("tel/semantics", "semantics", [b / "tel/semantics.lp"]),
        Case("bool/semantics", "semantics", [b / "bool/semantics.lp"]),
        Case("num/semantics", "semantics", [b / "num/semantics.lp"]),
        Case("mel/semantics", "semantics", [b / "mel/semantics.lp"]),
        Case("del/semantics", "semantics",
             [b / "del/flc.lp", b / "del/semantics.lp", b / "tel/semantics.lp"]),
    ]  # fmt: skip


def generate_input(copies: int) -> str:
    """Return a program consisting of the given number of copies of
    the metasp integration test input, with predicates renamed apart."""
    template = (metasp_inp_dir / "metasp_integration.lp").read_text()
    return "\n".join(
        renamed_predicates.sub(rf"\g<1>{i}(", template) for i in range(copies)
    )


def generated_case(copies: int, input_dir: Path) -> Case:
    """Write a generated input to the given directory and return its case."""
    input_file = input_dir / f"metasp_integration_x{copies}.lp"
    input_file.write_text(generate_input(copies))
    return Case(
        f"generated/x{copies}",
        "preprocess",
        [input_file],
        [metasp_inp_dir / "telingo_type.lp"],
    )


Phase = tuple[str, ...]


class PhaseTimer:
    """Accumulate the wall-clock time spent in nested phases.

    Phases are identified by their path of enclosing phases, so that
    e.g. grounding during re-reification is reported separately from
    grounding of the transformation encodings."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.times: dict[Phase, float] = defaultdict(float)
        self.calls: Counter[Phase] = Counter()

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Attribute the time spent within the context to the given phase."""
        self.stack.append(name)
        key = tuple(self.stack)
        start = time.perf_counter()
        try:
            yield
        finally:
            self.times[key] += time.perf_counter() - start
            self.calls[key] += 1
            self.stack.pop()

    def children(self, key: Phase) -> list[Phase]:
        """Return the direct sub-phases of the given phase, slowest first."""
        return sorted(
            (k for k in self.times if len(k) == len(key) + 1 and k[:-1] == key),
            key=lambda k: -self.times[k],
        )

    def report(self, total: float, min_share: float) -> Iterator[str]:
        """Yield report lines for all phases that took at least the
        given share of the total time. The time of a phase not spent
        in any of its sub-phases is reported as (self)."""

        def line(depth: int, name: str, duration: float, calls: int = 1) -> str:
            label = "  " * depth + name + (f" x{calls}" if calls > 1 else "")
            return f"  {label:<52}{duration:8.3f}s {duration / total:6.1%}"

        def visit(key: Phase) -> Iterator[str]:
            duration = self.times[key]
            if duration < min_share * total:
                return
            yield line(len(key) - 1, key[-1], duration, self.calls[key])
            children = self.children(key)
            for child in children:
                yield from visit(child)
            rest = duration - sum(self.times[c] for c in children)
            if children and rest >= min_share * total:
                yield line(len(key), "(self)", rest)

        for key in self.children(()):
            yield from visit(key)


@contextmanager
def instrument(timer: PhaseTimer) -> Iterator[None]:
    """Record the time spent in the parts of aspen and clingo where
    significant time is spent during a transformation."""
    patched: list[tuple[type, str, Any]] = []

    def patch(cls: type, attr: str, wrapper: Callable[..., Any]) -> None:
        original = getattr(cls, attr)
        patched.append((cls, attr, original))
        setattr(cls, attr, wraps(original)(wrapper(original)))

    def timed(name: str) -> Callable[..., Any]:
        def wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
            def call(*args: Any, **kwargs: Any) -> Any:
                with timer.phase(name):
                    return original(*args, **kwargs)

            return call

        return wrapper

    def timed_ground(original: Callable[..., Any]) -> Callable[..., Any]:
        def call(self: Control, *args: Any, **kwargs: Any) -> Any:
            parts = kwargs.get("parts", args[0] if args else [("base", ())])
            with timer.phase(f"ground [{', '.join(n for n, _ in parts)}]"):
                return original(self, *args, **kwargs)

        return call

    def timed_solve(original: Callable[..., Any]) -> Callable[..., Any]:
        def call(self: Control, *args: Any, **kwargs: Any) -> Any:
            on_model = kwargs.get("on_model")
            if on_model is not None:

                def timed_on_model(model: Any) -> Any:
                    with timer.phase("model callback (python)"):
                        return on_model(model)

                kwargs["on_model"] = timed_on_model
            with timer.phase("solve"):
                return original(self, *args, **kwargs)

        return call

    def timed_backend(original: Callable[..., Any]) -> Callable[..., Any]:
        @contextmanager
        def call(self: Control) -> Iterator[Any]:
            with timer.phase("add facts"), original(self) as backend:
                yield backend

        return call

    patch(AspenTree, "parse", timed("parse"))
    patch(AspenTree, "_reify_ts_tree", timed("reify tree"))
    patch(AspenTree, "transform", timed("transform"))
    patch(AspenTree, "_topological_sort_edits", timed("sort edits"))
    patch(AspenTree, "_edit_sources_from_symbs", timed("edit sources"))
    patch(AspenTree, "_reparse_sources", timed("reparse sources"))
    patch(AspenTree, "_re_reify_changed_subtrees", timed("re-reify"))
    patch(AspenTree, "_reify_changed_siblings", timed("reify changed subtrees"))
    patch(Control, "load", timed("load encodings"))
    patch(Control, "backend", timed_backend)
    patch(Control, "ground", timed_ground)
    patch(Control, "solve", timed_solve)
    try:
        yield
    finally:
        for cls, attr, original in reversed(patched):
            setattr(cls, attr, original)


def run(case: Case, skip_final_re_reify: bool = False) -> tuple[float, PhaseTimer]:
    """Parse and transform the files of the given case, returning the
    total time and the times of the phases."""
    timer = PhaseTimer()
    with StringIO() as fact_buf, instrument(timer):
        start = time.perf_counter()
        tree = AspenTree(default_language=metasp_lang)
        for path in case.syntax + case.files:
            tree.parse(path)
        if case.stage == "preprocess":
            tree.textio_symbols[Function("fact_file", [])] = fact_buf
            tree.transform(
                meta_files=[
                    metasp_enc_dir / "metasp_all.lp",
                    metasp_enc_dir / "metasp_generate_type_facts.lp",
                    metasp_enc_dir / "metasp_remove_ampersand.lp",
                ],
                meta_string=(
                    "#program metasp_preprocess. "
                    'aspen(next_program("metasp_remove_ampersand", ())).'
                ),
                initial_program=("metasp_preprocess", ()),
                skip_final_re_reify=skip_final_re_reify,
            )
        else:
            tree.transform(
                meta_files=[metasp_enc_dir / "metasp_remove_ampersand.lp"],
                initial_program=("metasp_remove_ampersand", ()),
                skip_final_re_reify=skip_final_re_reify,
            )
        total = time.perf_counter() - start
    return total, timer


def main(argv: Sequence[str] | None = None) -> None:
    """Run the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--cases",
        nargs="+",
        default=["*"],
        metavar="PATTERN",
        help="glob patterns selecting the cases to run (default: all)",
    )
    parser.add_argument(
        "--copies",
        type=int,
        nargs="*",
        default=[1, 20, 80],
        help="numbers of copies for the generated cases (default: 1 20 80)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="number of runs per case; the fastest is reported",
    )
    parser.add_argument(
        "--keep-inputs",
        type=Path,
        metavar="DIR",
        help="write the generated inputs to this directory",
    )
    parser.add_argument(
        "--min-share",
        type=float,
        default=5.0,
        metavar="PERCENT",
        help="hide phases taking less than this share of the total (default: 5)",
    )
    parser.add_argument(
        "--skip-final-re-reify",
        action="store_true",
        help=(
            "skip re-reification after the final transformation step, as "
            "the aspen command line does when the facts are not printed"
        ),
    )
    parser.add_argument(
        "--list", action="store_true", help="list the selected cases and exit"
    )
    args = parser.parse_args(argv)
    configure_logging(sys.stderr, logging.WARNING, sys.stderr.isatty())

    with TemporaryDirectory() as tmp_dir:
        input_dir = args.keep_inputs or Path(tmp_dir)
        input_dir.mkdir(parents=True, exist_ok=True)
        cases = example_cases() + [generated_case(n, input_dir) for n in args.copies]
        cases = [c for c in cases if any(fnmatch(c.name, p) for p in args.cases)]
        for case in cases:
            if args.list:
                print(f"{case.name} ({case.stage})")
                continue
            total, timer = min(
                (run(case, args.skip_final_re_reify) for _ in range(args.repeat)),
                key=lambda r: r[0],
            )
            print(f"{case.name} ({case.stage}): total {total:.3f}s")
            for line in timer.report(total, args.min_share / 100):
                print(line)


if __name__ == "__main__":
    main()
