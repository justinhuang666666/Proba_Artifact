#!/usr/bin/env python3
"""
Run SPECspeed2017 ChampSim experiments for one L2 prefetcher.

Use -j N to run N simulations in parallel.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import shutil

from download_spec2017_traces import DEFAULT_TRACES_DIR

WARMUP_INSTRUCTIONS = 200_000_000
SIMULATION_INSTRUCTIONS = 200_000_000
SUITE_NAME = "spec2017"
BASE_CONFIG_REL = Path("params") / "baseline.json"
SUITE_JSON_REL = Path("scripts") / "suites" / "spec2017.json"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def deep_merge(base: dict, overrides: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def flatten_traces(suite: dict) -> list[tuple[str, str, str]]:
    ext = suite["trace_ext"]
    traces = []
    for benchmark, simpoints in suite["benchmarks"].items():
        for trace_name in simpoints:
            traces.append((benchmark, trace_name, ext))
    return traces


def validate_prefetcher(root: Path, name: str) -> None:
    prefetcher_root = root / "prefetcher"
    prefetcher_dir = prefetcher_root / name

    if prefetcher_dir.is_dir():
        return

    available = (
        sorted(path.name for path in prefetcher_root.iterdir() if path.is_dir())
        if prefetcher_root.is_dir()
        else []
    )

    print(
        f"error: unknown L2 prefetcher '{name}'\n"
        f"available: {', '.join(available)}",
        file=sys.stderr,
    )
    raise SystemExit(1)


def validate_traces(
    traces_dir: Path,
    jobs: list[tuple[str, str, str]],
) -> list[tuple[str, str, Path]]:
    if not traces_dir.is_dir():
        print(
            f"error: traces directory not found: {traces_dir}\n"
            "place the SPECspeed2017 traces there or pass --traces-dir",
            file=sys.stderr,
        )
        raise SystemExit(1)

    resolved = []
    missing = []

    for benchmark, trace_name, ext in jobs:
        trace_path = traces_dir / f"{trace_name}{ext}"
        if trace_path.is_file():
            resolved.append((benchmark, trace_name, trace_path))
        else:
            missing.append(trace_path)

    if missing:
        print(
            f"error: {len(missing)} trace file(s) missing under {traces_dir}:",
            file=sys.stderr,
        )
        for path in missing[:10]:
            print(f"  {path}", file=sys.stderr)
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more", file=sys.stderr)
        raise SystemExit(1)

    return resolved

def build_champsim(root: Path, config: dict, jobs: int) -> Path:
    executable_name = f"champsim_{uuid.uuid4().hex[:8]}"
    build_config = copy.deepcopy(config)
    build_config["executable_name"] = executable_name

    gcc = shutil.which("gcc-11")
    gxx = shutil.which("g++-11")

    if gcc is None or gxx is None:
        print(
            "error: GCC 11 is required but gcc-11/g++-11 were not found.\n"
            "Run ./scripts/setup.sh first.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    env = os.environ.copy()
    env["CC"] = gcc
    env["CXX"] = gxx

    print(f"C compiler     : {gcc}")
    print(f"C++ compiler   : {gxx}")

    fd, temporary_path = tempfile.mkstemp(
        suffix=".json",
        prefix="run_exp_cfg_",
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(build_config, fh, indent=4)

        print(f"Configuring with {temporary_path}...")
        result = subprocess.run(
            ["./config.sh", temporary_path],
            cwd=root,
            env=env,
            check=False,
        )

        if result.returncode != 0:
            print("error: configuration failed", file=sys.stderr)
            raise SystemExit(1)

        print(f"Building {executable_name} with make -j {jobs}...")
        result = subprocess.run(
            ["make", "-j", str(jobs)],
            cwd=root,
            env=env,
            check=False,
        )

        if result.returncode != 0:
            print("error: build failed", file=sys.stderr)
            raise SystemExit(1)

    finally:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass

    binary = root / "bin" / executable_name

    if not binary.is_file():
        print(f"error: binary not found: {binary}", file=sys.stderr)
        raise SystemExit(1)

    return binary


def run_one(
    binary: Path,
    trace_path: Path,
    log_path: Path,
    json_path: Path,
    warmup: int,
    simulation: int,
) -> tuple[bool, str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        log_path.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)
    except OSError as exc:
        return False, f"could not remove stale output: {exc}"

    command = [
        str(binary),
        f"--json={json_path}",
        "--warmup_instructions",
        str(warmup),
        "--simulation_instructions",
        str(simulation),
        str(trace_path),
    ]

    try:
        with log_path.open("w", encoding="utf-8") as output:
            process = subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            )
    except OSError as exc:
        return False, str(exc)

    if process.returncode != 0:
        return False, f"exit {process.returncode}"

    if not json_path.is_file():
        return False, "JSON result was not generated"

    if json_path.stat().st_size == 0:
        return False, "JSON result is empty"

    try:
        with json_path.open(encoding="utf-8") as fh:
            json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid JSON result: {exc}"

    return True, "ok"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build ChampSim for one L2 prefetcher and run all "
            "SPECspeed2017 traces locally."
        )
    )
    parser.add_argument(
        "prefetcher",
        help="L2 prefetcher module name, such as l2_gaze, l2_pmp, or no",
    )
    parser.add_argument(
        "-j",
        type=int,
        default=1,
        metavar="N",
        help="parallel simulations and make jobs (default: 1)",
    )
    parser.add_argument(
        "--traces-dir",
        type=Path,
        default=DEFAULT_TRACES_DIR,
        help=f"SPECspeed2017 traces directory (default: {DEFAULT_TRACES_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="rerun even if a non-empty JSON result already exists",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.j < 1:
        print("error: -j must be at least 1", file=sys.stderr)
        return 1

    root = repo_root()
    validate_prefetcher(root, args.prefetcher)

    base_config_path = root / BASE_CONFIG_REL
    suite_path = root / SUITE_JSON_REL

    if not base_config_path.is_file():
        print(
            f"error: base config not found: {base_config_path}",
            file=sys.stderr,
        )
        return 1

    if not suite_path.is_file():
        print(
            f"error: suite definition not found: {suite_path}",
            file=sys.stderr,
        )
        return 1

    base_config = load_json(base_config_path)
    variant = {
        "L1D": {
            "prefetcher": "ip_stride",
            "virtual_prefetch": False,
        },
        "L2C": {
            "prefetcher": args.prefetcher,
        },
    }
    config = deep_merge(base_config, variant)

    suite = load_json(suite_path)
    traces_dir = args.traces_dir.expanduser().resolve()
    traces = validate_traces(traces_dir, flatten_traces(suite))

    results_root = root / "results" / SUITE_NAME / args.prefetcher
    pending: list[tuple[str, str, Path, Path, Path]] = []
    skipped = 0

    for benchmark, trace_name, trace_path in traces:
        log_path = results_root / benchmark / f"{trace_name}.txt"
        json_path = results_root / benchmark / f"{trace_name}.json"

        if (
            json_path.is_file()
            and json_path.stat().st_size > 0
            and not args.force
        ):
            skipped += 1
            continue

        pending.append(
            (
                benchmark,
                trace_name,
                trace_path,
                log_path,
                json_path,
            )
        )

    print(f"L2 prefetcher : {args.prefetcher}")
    print(f"Traces dir     : {traces_dir}")
    print(f"Results dir    : {results_root}")
    print(
        f"Warmup / sim   : "
        f"{WARMUP_INSTRUCTIONS} / {SIMULATION_INSTRUCTIONS}"
    )
    print(f"Parallelism    : {args.j}")
    print(f"Jobs           : {len(pending)} to run, {skipped} skipped")
    print()

    if not pending:
        print("Nothing to do.")
        return 0

    binary = build_champsim(root, config, args.j)
    print(f"Binary         : {binary}\n")

    total = len(pending)
    succeeded = 0
    failed = 0
    completed = 0

    with ThreadPoolExecutor(max_workers=args.j) as pool:
        futures = {
            pool.submit(
                run_one,
                binary,
                trace_path,
                log_path,
                json_path,
                WARMUP_INSTRUCTIONS,
                SIMULATION_INSTRUCTIONS,
            ): (benchmark, trace_name)
            for (
                benchmark,
                trace_name,
                trace_path,
                log_path,
                json_path,
            ) in pending
        }

        for future in as_completed(futures):
            benchmark, trace_name = futures[future]
            completed += 1

            try:
                ok, detail = future.result()
            except Exception as exc:
                ok = False
                detail = f"worker exception: {exc}"

            if ok:
                succeeded += 1
                status = "ok"
            else:
                failed += 1
                status = f"FAIL ({detail})"

            print(
                f"  [{completed}/{total}] "
                f"{benchmark}/{trace_name} -> {status}"
            )

    print()
    print(
        f"Done: {succeeded} succeeded, "
        f"{failed} failed, {skipped} skipped"
    )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())