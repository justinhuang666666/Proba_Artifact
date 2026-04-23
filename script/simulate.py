#!/usr/bin/env python3

# Launch ChampSim simulations locally on a single server

import argparse
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from _SPEC2017_def import SPEC2017_shortcode, SPEC2017_path

WARMUP_INSTRUCTIONS = 50000000
SIMULATION_INSTRUCTIONS = 100000000

PREFETCHERS = ['l2_sms','l2_sms_train_on_misstaghit','l2_proba_pc_offset','l2_proba_pcoffset_eog_jail_sampling','l2_proba_pc_pcoffset_offsetoffset_eog_jail_sampling','l2_superproba_pc_pcoffset_offsetoffset']
def parse_args():
    default_parallelism = os.cpu_count() or 1

    parser = argparse.ArgumentParser(
        description="Run ChampSim on SPEC benchmarks locally"
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        required=True,
        help='Benchmark to run ("SPEC_ALL", "SPEC_2017", "SPEC_2006", or part of a benchmark name)',
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=default_parallelism,
        help=f"Maximum number of concurrent local simulations (default: {default_parallelism})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without actually running them",
    )
    return parser.parse_args()


def get_matching_benchmarks(benchmark_arg):
    if benchmark_arg == "SPEC_ALL":
        print("Running ALL SPEC 2006 + 2017 benchmarks")
        matching = SPEC2017_shortcode.copy()

    elif benchmark_arg == "SPEC_2017":
        print("Running SPEC2017 benchmarks")
        from _SPEC2017_def import spec2017_ones

        matching = {}
        for key in spec2017_ones:
            if key in SPEC2017_shortcode:
                matching[key] = SPEC2017_shortcode[key]

    elif benchmark_arg == "SPEC_2006":
        print("Running SPEC2006 benchmarks")
        from _SPEC2017_def import spec2006_ones

        matching = {}
        for key in spec2006_ones:
            if key in SPEC2017_shortcode:
                matching[key] = SPEC2017_shortcode[key]

    else:
        matching = {}
        for key in SPEC2017_shortcode:
            if benchmark_arg in key:
                matching[key] = SPEC2017_shortcode[key]

        if not matching:
            print("No benchmarks found matching:", benchmark_arg)
            print("Available benchmarks:", ", ".join(SPEC2017_shortcode.keys()))
            print('Use "SPEC_ALL", "SPEC_2017", or "SPEC_2006"')
            sys.exit(1)

        print(f"Found {len(matching)} matching benchmark categories:")
        for key in matching:
            print(f"  - {key} ({len(matching[key])} traces)")

    print(
        f"Found {len(matching)} benchmark categories with "
        f"{sum(len(traces) for traces in matching.values())} total traces"
    )
    return matching


def get_trace_output_name(trace_path):
    trace_file = os.path.basename(trace_path)

    if trace_file.endswith(".xz"):
        trace_file = trace_file[:-3]
    elif trace_file.endswith(".gz"):
        trace_file = trace_file[:-3]

    parts = trace_file.split(".")
    if len(parts) > 1:
        return parts[1]
    return os.path.splitext(trace_file)[0]


def build_benchmark_list(matching_benchmarks):
    all_benchmarks = []
    for category, benchmarks in matching_benchmarks.items():
        for benchmark in benchmarks:
            all_benchmarks.append((benchmark, category))
    return all_benchmarks


def run_cmd(cmd, stdout=None, stderr=None, dry_run=False):
    print("CMD:", " ".join(cmd))
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0)
    return subprocess.run(cmd, stdout=stdout, stderr=stderr, check=False)


def run_prefetcher(prefetcher, all_benchmarks, parallelism, dry_run):
    binary_path = f"../bin/champsim_1core_{prefetcher}"

    if not os.path.exists(binary_path):
        print(f"Error: {binary_path} not found. Please build first.")
        return 1

    categories = {category for _, category in all_benchmarks}
    for category in categories:
        os.makedirs(f"results/log/{prefetcher}/{category}", exist_ok=True)
        os.makedirs(f"results/json/{prefetcher}/{category}", exist_ok=True)

    total_simulations = len(all_benchmarks)
    if total_simulations == 0:
        print(f"No benchmarks to run for {prefetcher}")
        return 0

    actual_parallelism = min(parallelism, total_simulations)

    print("==================")
    print("Running Simulation")
    print("==================")
    print("Configuration Summary:")
    print(f"  Prefetcher: {prefetcher}")
    print(f"  Binary: {binary_path}")
    print(f"  Total Benchmarks: {total_simulations}")
    print(f"  Parallelism: {actual_parallelism}")
    print(f"  Dry run: {dry_run}")
    print()

    completed_simulations = 0
    progress_lock = threading.Lock()
    failures = []
    start_time = time.time()

    def run_benchmark_local(benchmark_tuple):
        nonlocal completed_simulations

        benchmark, category = benchmark_tuple
        trace_name = get_trace_output_name(benchmark)
        trace_path = os.path.join(SPEC2017_path, benchmark)
        output_path = f"results/log/{prefetcher}/{category}/{trace_name}.txt"
        json_path = f"results/json/{prefetcher}/{category}/{trace_name}.json"

        cmd = [
            binary_path,
            f'--json={json_path}',
            "--warmup_instructions",
            str(WARMUP_INSTRUCTIONS),
            "--simulation_instructions",
            str(SIMULATION_INSTRUCTIONS),
            trace_path,
        ]

        print(f"Starting {benchmark} ...")

        try:
            with open(output_path, "w") as out_file:
                result = run_cmd(
                    cmd,
                    stdout=out_file,
                    stderr=subprocess.STDOUT,
                    dry_run=dry_run,
                )
            returncode = result.returncode
        except Exception as e:
            returncode = -1
            with open(output_path, "a") as out_file:
                out_file.write(f"\n[launcher error] {e}\n")

        with progress_lock:
            completed_simulations += 1
            finished = completed_simulations

        if returncode == 0:
            print(f"Completed {benchmark}. [Progress: {finished} / {total_simulations}]")
        else:
            print(
                f"Failed {benchmark} (exit code {returncode}). "
                f"[Progress: {finished} / {total_simulations}]"
            )

        return {
            "benchmark": benchmark,
            "category": category,
            "trace_name": trace_name,
            "returncode": returncode,
            "output_path": output_path,
        }

    with ThreadPoolExecutor(max_workers=actual_parallelism) as executor:
        futures = [executor.submit(run_benchmark_local, item) for item in all_benchmarks]

        for future in as_completed(futures):
            result = future.result()
            if result["returncode"] != 0:
                failures.append(result)

    elapsed_time_minutes = (time.time() - start_time) / 60.0

    print("===================")
    print("Simulation Complete")
    print("===================")
    print(f"Simulated: {prefetcher}")
    print(f"Simulation time: {elapsed_time_minutes:.2f} minutes")

    if failures:
        print()
        print("Failed runs:")
        for item in failures:
            print(
                f"  - {item['benchmark']} -> {item['output_path']} "
                f"(exit code {item['returncode']})"
            )
        return 1

    return 0


def main():
    args = parse_args()

    if args.parallelism <= 0:
        print("--parallelism must be >= 1")
        sys.exit(1)

    matching_benchmarks = get_matching_benchmarks(args.benchmark)
    all_benchmarks = build_benchmark_list(matching_benchmarks)

    overall_rc = 0
    for prefetcher in PREFETCHERS:
        rc = run_prefetcher(prefetcher, all_benchmarks, args.parallelism, args.dry_run)
        if rc != 0:
            overall_rc = rc

    sys.exit(overall_rc)


if __name__ == "__main__":
    main()
