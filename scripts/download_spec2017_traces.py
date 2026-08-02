#!/usr/bin/env python3
"""
Download all SPECspeed 2017 traces.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu/"
SCRIPTS_DIR = Path(__file__).resolve().parent
SUITE_JSON = SCRIPTS_DIR / "suites" / "spec2017.json"
DEFAULT_TRACES_DIR = SCRIPTS_DIR.parent / "traces" / "spec2017"
CHUNK_SIZE = 1024 * 1024


def load_traces(suite_path: Path) -> list[str]:
    with open(suite_path) as fh:
        suite = json.load(fh)
    ext = suite["trace_ext"]
    traces = []
    for simpoints in suite["benchmarks"].values():
        for trace_name in simpoints:
            traces.append(f"{trace_name}{ext}")
    return sorted(traces)


def download(url: str, dest: Path, verbose: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    try:
        with urllib.request.urlopen(url) as response, open(tmp, "wb") as out:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if verbose and total_size > 0:
                    pct = min(100, downloaded * 100 // total_size)
                    sys.stdout.write(f"\r  {pct:3d}% ")
                    sys.stdout.flush()
        tmp.replace(dest)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise

    if verbose:
        sys.stdout.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download all SPEC CPU2017 (SPECspeed2017) ChampSim traces."
    )
    parser.add_argument(
        "destination",
        nargs="?",
        type=Path,
        default=DEFAULT_TRACES_DIR,
        help=(
            "directory where .champsimtrace.xz files will be saved "
            f"(default: {DEFAULT_TRACES_DIR})"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show per-file download progress",
    )
    args = parser.parse_args()

    traces = load_traces(SUITE_JSON)
    num_traces = len(traces)
    dest_dir = args.destination
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"Download SPECspeed 2017 traces [0/{num_traces}] ")
    for num, trace in enumerate(traces, start=1):
        url = BASE_URL + trace
        dest = dest_dir / trace
        try:
            download(url, dest, args.verbose)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            print(f"\nerror: failed to download {trace}: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Download SPECspeed 2017 traces [{num}/{num_traces}]")

    print(f"Download SPECspeed 2017 traces \033[0;32m[{num_traces}/{num_traces}]\033[0m")


if __name__ == "__main__":
    main()
