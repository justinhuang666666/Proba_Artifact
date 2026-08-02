#!/usr/bin/env python3
"""
Print Speedup / normalized DRAM traffic / LLC coverage / overall accuracy
for one or more L2 prefetchers from ChampSim JSON result files.

Metric definitions:
  Speedup:
      weighted baseline execution time / weighted test execution time
      = sum(weight / baseline_IPC) / sum(weight / test_IPC)

  Normalized DRAM traffic:
      weighted test DRAM requests / weighted baseline DRAM requests

  LLC coverage:
      max(0, 1 - weighted test LLC load misses
                    / weighted baseline LLC load misses)

  Overall accuracy:
      weighted useful prefetches
      / (weighted useful prefetches + weighted useless prefetches)

Overall summaries:
  - Speedup and DRAM traffic: geometric mean across benchmarks.
  - LLC coverage and overall accuracy: arithmetic mean across benchmarks.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

_NUM_PREFIX_RE = re.compile(r"^\d+\.")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_suite(suite_name: str) -> dict[str, Any]:
    path = repo_root() / "scripts" / "suites" / f"{suite_name}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"suite definition not found: {path} "
            f"(expected scripts/suites/{suite_name}.json)"
        )
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_json_obj(file_path: str | Path) -> Any:
    """
    Load a ChampSim JSON result.

    Supports:
      - a normal JSON object;
      - a normal JSON array;
      - a JSON array/object embedded in surrounding text.
    """
    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
        content = fh.read().strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        array_begin = content.find("[")
        array_end = content.rfind("]") + 1
        if array_begin != -1 and array_end > array_begin:
            return json.loads(content[array_begin:array_end])

        object_begin = content.find("{")
        object_end = content.rfind("}") + 1
        if object_begin != -1 and object_end > object_begin:
            return json.loads(content[object_begin:object_end])

        raise


def get_roi(file_path: str | Path) -> dict[str, Any]:
    json_obj = load_json_obj(file_path)

    # The old ChampSim JSON writer commonly emits: [{"roi": {...}}].
    if isinstance(json_obj, list):
        if not json_obj:
            return {}
        json_obj = json_obj[0]

    if not isinstance(json_obj, dict):
        return {}

    roi = json_obj.get("roi", {})
    return roi if isinstance(roi, dict) else {}


def _scalar(value: Any) -> float:
    """Convert a scalar or one-element ChampSim JSON list to float."""
    if isinstance(value, list):
        if not value:
            raise ValueError("empty metric list")
        value = value[0]
    return float(value)


def parse_ipc(filepath: str | Path, _prefetcher: str | None = None) -> float | None:
    roi = get_roi(filepath)
    try:
        instructions = _scalar(roi["cores"][0]["instructions"])
        cycles = _scalar(roi["cores"][0]["cycles"])
        return instructions / cycles if cycles > 0 else None
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        return None


def parse_dram(filepath: str | Path, _prefetcher: str | None = None) -> float | None:
    roi = get_roi(filepath)
    try:
        dram = roi["DRAM"][0]
        return sum(
            _scalar(dram[key])
            for key in (
                "RQ ROW_BUFFER_HIT",
                "RQ ROW_BUFFER_MISS",
                "WQ ROW_BUFFER_HIT",
                "WQ ROW_BUFFER_MISS",
            )
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def parse_llc_load_misses(
    filepath: str | Path,
    _prefetcher: str | None = None,
) -> float | None:
    roi = get_roi(filepath)
    try:
        return _scalar(roi["LLC"]["LOAD"]["miss"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def parse_overall_accuracy(
    filepath: str | Path,
    _prefetcher: str | None = None,
) -> tuple[float, float] | None:
    roi = get_roi(filepath)
    try:
        useful = (
            _scalar(roi["cpu0_L2C"]["prefetch useful"])
            + _scalar(roi["LLC"]["pf_useful_at_llc_from_l2"])
        )
        useless = (
            _scalar(roi["cpu0_L2C"]["prefetch useless"])
            + _scalar(roi["LLC"]["pf_useless_at_llc_from_l2"])
        )
        return useful, useless
    except (KeyError, IndexError, TypeError, ValueError):
        return None

METRICS: dict[str, dict[str, Any]] = {
    "speedup": {
        "parse": parse_ipc,
        "aggregate": "speedup",
        "summary": "geomean",
        "label": "Speedup",
    },
    "dram": {
        "parse": parse_dram,
        "aggregate": "count_ratio",
        "summary": "geomean",
        "label": "Normalized DRAM Traffic",
    },
    "coverage": {
        "parse": parse_llc_load_misses,
        "aggregate": "llc_miss_coverage",
        "summary": "arithmetic",
        "label": "LLC Coverage",
    },
    "accuracy": {
        "parse": parse_overall_accuracy,
        "aggregate": "count_fraction",
        "summary": "arithmetic",
        "label": "Overall Accuracy",
    },
}


# ---------------------------------------------------------------------------
# Gather results
# ---------------------------------------------------------------------------

def _strip_numeric_prefix(name: str) -> str:
    match = _NUM_PREFIX_RE.match(name)
    return name[match.end():] if match else name


def _result_prefetcher_dir(
    results_dir: Path,
    suite_name: str,
    prefetcher: str,
) -> Path | None:
    candidates = (
        results_dir / suite_name / prefetcher,
        results_dir / prefetcher,
        results_dir / "json" / prefetcher,
        results_dir / suite_name / "json" / prefetcher,
    )
    return next((path for path in candidates if path.is_dir()), None)


def gather_data(
    results_dir: Path,
    suite_name: str,
    prefetchers: list[str],
    parse_fn: Callable[[str | Path, str | None], Any],
    bench_map: dict[str, dict[str, float]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    data: dict[str, dict[str, Any]] = defaultdict(dict)
    unparsed: dict[str, list[str]] = defaultdict(list)

    for prefetcher in prefetchers:
        pref_dir = _result_prefetcher_dir(results_dir, suite_name, prefetcher)
        if pref_dir is None:
            print(
                f"  warning: no result directory found for '{prefetcher}' "
                f"under {results_dir}"
            )
            continue

        for benchmark in bench_map:
            bench_dir = pref_dir / benchmark
            if not bench_dir.is_dir():
                print(f"  warning: missing benchmark directory: {bench_dir}")
                continue

            for filepath in sorted(bench_dir.iterdir()):
                if filepath.suffix != ".json":
                    continue

                simpoint = _strip_numeric_prefix(filepath.stem)
                value = parse_fn(filepath, prefetcher)
                if value is None:
                    unparsed[prefetcher].append(f"{benchmark}/{simpoint}")
                    continue

                data[prefetcher][f"{benchmark}/{simpoint}"] = value

    return dict(data), dict(unparsed)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _effective_simpoint_weight(weight: Any) -> float | None:
    if weight is None:
        return 1.0
    numeric = float(weight)
    return numeric if numeric > 0 else None


def _weighted_harmonic_speedup(
    baseline_ipcs: list[float],
    test_ipcs: list[float],
    weights: list[float],
) -> float | None:
    if not baseline_ipcs or not test_ipcs or not weights:
        return None

    baseline_time = sum(
        weight / ipc for ipc, weight in zip(baseline_ipcs, weights)
    )
    test_time = sum(
        weight / ipc for ipc, weight in zip(test_ipcs, weights)
    )
    return baseline_time / test_time if test_time > 0 else None


def _geomean(values: list[float]) -> float | None:
    positive = [value for value in values if value > 0]
    if not positive:
        return None
    return math.exp(sum(math.log(value) for value in positive) / len(positive))


def _arithmetic_mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate(
    data: dict[str, dict[str, Any]],
    bench_map: dict[str, dict[str, float]],
    prefetchers: list[str],
    baseline: str,
    metric_spec: dict[str, Any],
) -> tuple[dict[str, dict[str, float | None]], list[str], list[str]]:
    benchmark_order = list(bench_map)
    mode = metric_spec["aggregate"]
    plot_prefetchers = [name for name in prefetchers if name != baseline]
    results: dict[str, dict[str, float | None]] = defaultdict(dict)

    for benchmark, weight_map in bench_map.items():
        for prefetcher in plot_prefetchers:
            if mode == "speedup":
                baseline_ipcs: list[float] = []
                test_ipcs: list[float] = []
                weights: list[float] = []

                for simpoint, raw_weight in weight_map.items():
                    label = f"{benchmark}/{_strip_numeric_prefix(simpoint)}"
                    baseline_value = data.get(baseline, {}).get(label)
                    test_value = data.get(prefetcher, {}).get(label)
                    weight = _effective_simpoint_weight(raw_weight)

                    if (
                        baseline_value is None
                        or test_value is None
                        or weight is None
                        or baseline_value <= 0
                        or test_value <= 0
                    ):
                        continue

                    baseline_ipcs.append(float(baseline_value))
                    test_ipcs.append(float(test_value))
                    weights.append(weight)

                results[prefetcher][benchmark] = _weighted_harmonic_speedup(
                    baseline_ipcs,
                    test_ipcs,
                    weights,
                )

            elif mode == "count_ratio":
                weighted_baseline = 0.0
                weighted_test = 0.0
                found = False

                for simpoint, raw_weight in weight_map.items():
                    label = f"{benchmark}/{_strip_numeric_prefix(simpoint)}"
                    baseline_value = data.get(baseline, {}).get(label)
                    test_value = data.get(prefetcher, {}).get(label)
                    weight = _effective_simpoint_weight(raw_weight)

                    if (
                        baseline_value is None
                        or test_value is None
                        or weight is None
                    ):
                        continue

                    weighted_baseline += weight * float(baseline_value)
                    weighted_test += weight * float(test_value)
                    found = True

                results[prefetcher][benchmark] = (
                    weighted_test / weighted_baseline
                    if found and weighted_baseline > 0
                    else None
                )

            elif mode == "llc_miss_coverage":
                weighted_baseline_misses = 0.0
                weighted_test_misses = 0.0
                found = False

                for simpoint, raw_weight in weight_map.items():
                    label = f"{benchmark}/{_strip_numeric_prefix(simpoint)}"
                    baseline_misses = data.get(baseline, {}).get(label)
                    test_misses = data.get(prefetcher, {}).get(label)
                    weight = _effective_simpoint_weight(raw_weight)

                    if (
                        baseline_misses is None
                        or test_misses is None
                        or weight is None
                    ):
                        continue

                    weighted_baseline_misses += weight * float(baseline_misses)
                    weighted_test_misses += weight * float(test_misses)
                    found = True

                if found and weighted_baseline_misses > 0:
                    miss_ratio = weighted_test_misses / weighted_baseline_misses
                    results[prefetcher][benchmark] = max(0.0, 1.0 - miss_ratio)
                else:
                    results[prefetcher][benchmark] = None

            elif mode == "count_fraction":
                weighted_useful = 0.0
                weighted_useless = 0.0
                found = False

                for simpoint, raw_weight in weight_map.items():
                    label = f"{benchmark}/{_strip_numeric_prefix(simpoint)}"
                    raw_counts = data.get(prefetcher, {}).get(label)
                    weight = _effective_simpoint_weight(raw_weight)

                    if raw_counts is None or weight is None:
                        continue

                    useful, useless = raw_counts
                    weighted_useful += weight * float(useful)
                    weighted_useless += weight * float(useless)
                    found = True

                denominator = weighted_useful + weighted_useless
                if not found:
                    results[prefetcher][benchmark] = None
                elif denominator > 0:
                    results[prefetcher][benchmark] = weighted_useful / denominator
                else:
                    # Match the reference plot: no generated prefetches is
                    # treated as vacuously accurate.
                    results[prefetcher][benchmark] = 1.0

            else:
                raise ValueError(f"unknown aggregate mode: {mode}")

    summary_type = metric_spec["summary"]
    for prefetcher in plot_prefetchers:
        valid_values = [
            value
            for benchmark in benchmark_order
            if (value := results[prefetcher].get(benchmark)) is not None
        ]

        if summary_type == "geomean":
            summary = _geomean(valid_values)
        elif summary_type == "arithmetic":
            summary = _arithmetic_mean(valid_values)
        else:
            raise ValueError(f"unknown summary mode: {summary_type}")

        results[prefetcher]["summary"] = summary

    return dict(results), plot_prefetchers, benchmark_order


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def _format_value(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def print_benchmark_stats(
    results: dict[str, dict[str, float | None]],
    plot_prefetchers: list[str],
    benchmark_order: list[str],
    metric_label: str,
) -> None:
    headers = plot_prefetchers
    label_width = max(
        len("Benchmark"),
        *(len(benchmark) for benchmark in benchmark_order),
    )
    column_widths = [max(len(header), 8) for header in headers]

    def format_row(label: str, values: list[str]) -> str:
        cells = [f"{label:<{label_width}}"]
        cells.extend(
            f"{value:>{width}}"
            for value, width in zip(values, column_widths)
        )
        return "  ".join(cells)

    print()
    print("=" * 72)
    print(f"> {metric_label} per benchmark")
    print("=" * 72)
    print(format_row("Benchmark", headers))
    print(
        format_row(
            "-" * label_width,
            ["-" * width for width in column_widths],
        )
    )

    for benchmark in benchmark_order:
        print(
            format_row(
                benchmark,
                [
                    _format_value(results[prefetcher].get(benchmark))
                    for prefetcher in plot_prefetchers
                ],
            )
        )


def print_summary(
    summaries_by_metric: dict[str, dict[str, float | None]],
    plot_prefetchers: list[str],
) -> None:
    label_width = max(len("Prefetcher"), *(len(p) for p in plot_prefetchers))

    print()
    print("=" * 72)
    print("> Overall summary")
    print("=" * 72)
    print(
        f"{'Prefetcher':<{label_width}}  "
        f"{'Speedup':>10}  "
        f"{'DRAM':>10}  "
        f"{'LLC cov.':>10}  "
        f"{'Accuracy':>10}"
    )
    print(
        f"{'-' * label_width}  "
        f"{'-' * 10}  {'-' * 10}  {'-' * 10}  {'-' * 10}"
    )

    for prefetcher in plot_prefetchers:
        print(
            f"{prefetcher:<{label_width}}  "
            f"{_format_value(summaries_by_metric['speedup'].get(prefetcher)):>10}  "
            f"{_format_value(summaries_by_metric['dram'].get(prefetcher)):>10}  "
            f"{_format_value(summaries_by_metric['coverage'].get(prefetcher)):>10}  "
            f"{_format_value(summaries_by_metric['accuracy'].get(prefetcher)):>10}"
        )

    print()
    print("Speedup and DRAM are geometric means across benchmarks.")
    print("LLC coverage and overall accuracy are arithmetic means.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_SUITE = "spec2017"
BASELINE = "no"


def validate_prefetcher(root: Path, name: str) -> None:
    pref_root = root / "prefetcher"
    pref_dir = pref_root / name

    if not pref_dir.is_dir():
        available = sorted(
            path.name for path in pref_root.iterdir() if path.is_dir()
        ) if pref_root.is_dir() else []

        print(
            f"error: unknown L2 prefetcher '{name}' "
            f"(expected a directory under prefetcher/)\n"
            f"available: {', '.join(available)}",
            file=sys.stderr,
        )
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Print speedup, normalized DRAM traffic, LLC coverage, and "
            "overall accuracy from ChampSim JSON results."
        )
    )
    parser.add_argument(
        "prefetchers",
        nargs="+",
        metavar="PREFETCHER",
        help="L2 prefetcher module name(s)",
    )
    parser.add_argument(
        "--suite",
        default=DEFAULT_SUITE,
        help=f"suite definition name (default: {DEFAULT_SUITE})",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help=(
            "results root; supports results/<suite>/<prefetcher>/... and "
            "results/json/<prefetcher>/... "
            "(default: <repo>/results)"
        ),
    )
    args = parser.parse_args()

    root = repo_root()
    requested_prefetchers = list(dict.fromkeys(args.prefetchers))

    for name in requested_prefetchers:
        validate_prefetcher(root, name)
        if name == BASELINE:
            print(
                "error: 'no' is automatically used as the baseline; "
                "do not pass it as a comparison prefetcher",
                file=sys.stderr,
            )
            return 1

    results_dir = (
        args.results_dir.expanduser().resolve()
        if args.results_dir
        else root / "results"
    )

    try:
        suite = load_suite(args.suite)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    bench_map = suite.get("benchmarks")
    if not isinstance(bench_map, dict) or not bench_map:
        print(
            "error: suite JSON must contain a non-empty 'benchmarks' object",
            file=sys.stderr,
        )
        return 1

    prefetchers = requested_prefetchers + [BASELINE]

    print("=" * 72)
    print("ChampSim JSON evaluation results")
    print("=" * 72)
    print(f"Suite:       {args.suite}")
    print(f"Results:     {results_dir}")
    print(f"Baseline:    {BASELINE}")
    print(f"Prefetchers: {', '.join(requested_prefetchers)}")

    summaries_by_metric: dict[str, dict[str, float | None]] = {}
    final_plot_prefetchers = requested_prefetchers

    for metric_name in ("speedup", "dram", "coverage", "accuracy"):
        metric_spec = METRICS[metric_name]
        data, unparsed = gather_data(
            results_dir,
            args.suite,
            prefetchers,
            metric_spec["parse"],
            bench_map,
        )

        if unparsed:
            total_unparsed = sum(len(items) for items in unparsed.values())
            print(
                f"  warning: {total_unparsed} JSON result(s) could not be "
                f"parsed for {metric_spec['label']}"
            )

        results, plot_prefetchers, benchmark_order = aggregate(
            data,
            bench_map,
            prefetchers,
            BASELINE,
            metric_spec,
        )
        final_plot_prefetchers = plot_prefetchers

        print_benchmark_stats(
            results,
            plot_prefetchers,
            benchmark_order,
            metric_spec["label"],
        )

        summaries_by_metric[metric_name] = {
            prefetcher: results[prefetcher].get("summary")
            for prefetcher in plot_prefetchers
        }

    print_summary(summaries_by_metric, final_plot_prefetchers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
