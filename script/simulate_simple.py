#!/bin/python3

# Launch ChampSim simulations locally on a single server
# Update config -> Build ChampSim -> Execute locally -> Store results

import argparse
import sys
import os
import subprocess
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from _SPEC2017_def import SPEC2017_shortcode, SPEC2017_path

# Define the warmup and instructions to run
WARMUP_INSTRUCTIONS = 50000000
SIMULATION_INSTRUCTIONS = 200000000


def parse_args():
    default_parallelism = os.cpu_count() or 1

    parser = argparse.ArgumentParser(
        description="Run ChampSim on SPEC benchmarks locally"
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        required=True,
        help='Benchmark to run (use "SPEC_ALL", "SPEC_2017", "SPEC_2006", or part of a benchmark name)',
    )
    parser.add_argument(
        "--name",
        type=str,
        required=False,
        help="Directory name to store the result",
    )
    parser.add_argument(
        "--config",
        type=str,
        required=False,
        help="Configuration file",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        required=False,
        help="Clean the build before make",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        required=False,
        help="Skip configuration and build process",
    )
    parser.add_argument(
        "--parallelism",
        "--max-cpu",
        dest="parallelism",
        type=int,
        default=default_parallelism,
        required=False,
        help=f"Maximum number of concurrent local simulations (default: {default_parallelism})",
    )
    parser.add_argument(
        "--script",
        action="store_true",
        required=False,
        help="Run in script mode without confirmation prompt",
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
    parts = trace_file.split(".")
    if len(parts) > 1:
        return parts[1]
    return os.path.splitext(trace_file)[0]


def run_cmd(cmd):
    print(cmd)
    # return subprocess.run(cmd)


def run_or_exit(cmd, fail_msg):
    result = run_cmd(cmd)
    if result.returncode != 0:
        print(fail_msg)
        sys.exit(1)


def main():
    args = parse_args()

    if args.parallelism <= 0:
        print("--parallelism must be >= 1")
        sys.exit(1)

    matching_benchmarks = get_matching_benchmarks(args.benchmark)

    prefetchers = ["no", "l2_sms_eviction", "l2_bingo_eviction"]

    for prefetcher in prefetchers:

    dir_name = prefetcher
    binary_path = f"./bin/champsim_1core_{prefetcher}"

    if not args.run:
        print("======================")
        print("Updating Configuration")
        print("======================")
        run_or_exit(["./config.sh", config_path], "Configuration failed")

        with open(config_path) as config_file:
            config = json.load(config_file)
            prefetcher_l1 = config["L1D"]["prefetcher"]
            prefetcher_l2 = config["L2C"]["prefetcher"]

        print("**********************")
        print(f"L1D : {prefetcher_l1}")
        print(f"L2C : {prefetcher_l2}")
        print(f"Name: {prefetcher}")
        print("**********************")

        if not args.script:
            confirm = input("Continue? [Y/n]: ")
            if not (confirm.lower() in ["y", "yes"] or confirm == ""):
                sys.exit(0)

        print("=================")
        print("Building ChampSim")
        print("=================")
        if args.clean:
            run_or_exit(["make", "clean"], "Clean failed")
        run_or_exit(["make"], "Build failed")

    else:
        if not os.path.exists(binary_path):
            print("Error: No existing binary found. Please build first or run without --run.")
            sys.exit(1)

    print("==================")
    print("Running Simulation")
    print("==================")

    all_benchmarks = []
    for category, benchmarks in matching_benchmarks.items():
        os.makedirs(f"results/{prefetcher}/{category}", exist_ok=True)
        for benchmark in benchmarks:
            all_benchmarks.append((benchmark, category))

    total_simulations = len(all_benchmarks)
    parallelism = min(args.parallelism, total_simulations) if total_simulations > 0 else 1

    print("Configuration Summary:")
    print(f"  Prefetcher Directory: {prefetcher}")
    print(f"  Total Benchmarks: {total_simulations}")
    print(f"  Parallelism: {parallelism}")
    print()

    completed_simulations = 0
    progress_lock = threading.Lock()
    start_time = time.time()

    def run_benchmark_local(benchmark_tuple):
        nonlocal completed_simulations

        benchmark, category = benchmark_tuple
        trace_name = get_trace_output_name(benchmark)
        trace_path = f"{SPEC2017_path}{benchmark}"
        output_path = f"results/{prefetcher}/{category}/{trace_name}.txt"

        cmd = [
            binary_path,
            "--warmup-instructions",
            str(WARMUP_INSTRUCTIONS),
            "--simulation-instructions",
            str(SIMULATION_INSTRUCTIONS),
            trace_path,
        ]

        print(f"Starting {benchmark} ...")
        with open(output_path, "w") as out_file:
            result = subprocess.run(cmd, stdout=out_file, stderr=subprocess.STDOUT)

        with progress_lock:
            completed_simulations += 1
            finished = completed_simulations

        if result.returncode == 0:
            print(f"Completed {benchmark}. [Progress: {finished} / {total_simulations}]")
        else:
            print(
                f"Failed {benchmark} (exit code {result.returncode}). "
                f"[Progress: {finished} / {total_simulations}]"
            )

        return {
            "benchmark": benchmark,
            "category": category,
            "trace_name": trace_name,
            "returncode": result.returncode,
            "output_path": output_path,
        }

    failures = []

    with ThreadPoolExecutor(max_workers=parallelism) as executor:
        futures = [executor.submit(run_benchmark_local, item) for item in all_benchmarks]

        for future in as_completed(futures):
            result = future.result()
            if result["returncode"] != 0:
                failures.append(result)

    print("===================")
    print("Simulation Complete")
    print("===================")

    elapsed_time_minutes = (time.time() - start_time) / 60.0
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
        sys.exit(1)


if __name__ == "__main__":
    main()