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

Example:

    python benchmarks/metasp.py --copies 1 20 80 --repeat 3
    python benchmarks/metasp.py --cases 'tel/*' 'generated/*'
"""

import argparse
import logging
import re
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from fnmatch import fnmatch
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


@contextmanager
def record_ground_times() -> Iterator[list[tuple[str, float]]]:
    """Record the program parts and duration of each clingo grounding
    call made within the context."""
    times: list[tuple[str, float]] = []
    original_ground = Control.ground

    def timed_ground(self: Control, *args: Any, **kwargs: Any) -> None:
        parts = kwargs.get("parts", args[0] if args else [("base", ())])
        start = time.perf_counter()
        original_ground(self, *args, **kwargs)
        times.append((", ".join(name for name, _ in parts), time.perf_counter() - start))

    Control.ground = timed_ground  # type: ignore[method-assign]
    try:
        yield times
    finally:
        Control.ground = original_ground  # type: ignore[method-assign]


def run(case: Case) -> tuple[float, list[tuple[str, float]]]:
    """Transform the files of the given case, returning the total time
    and the time of each grounding step."""
    tree = AspenTree(default_language=metasp_lang)
    for path in case.syntax + case.files:
        tree.parse(path)
    with StringIO() as fact_buf, record_ground_times() as ground_times:
        start = time.perf_counter()
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
            )
        else:
            tree.transform(
                meta_files=[metasp_enc_dir / "metasp_remove_ampersand.lp"],
                initial_program=("metasp_remove_ampersand", ()),
            )
        total = time.perf_counter() - start
    return total, ground_times


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
            total, ground_times = min(
                (run(case) for _ in range(args.repeat)), key=lambda r: r[0]
            )
            print(f"{case.name} ({case.stage}): transform {total:.3f}s")
            for parts, duration in ground_times:
                print(f"  ground {duration:.3f}s  [{parts}]")


if __name__ == "__main__":
    main()
