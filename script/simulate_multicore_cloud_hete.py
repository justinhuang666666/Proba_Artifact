#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from _CloudSuite_def import CloudSuite_shortcode, CloudSuite_path, cloudsuite_ones

WARMUP_INSTRUCTIONS = 50000000
SIMULATION_INSTRUCTIONS = 100000000

NUM_CORES = 4

PREFETCHERS = [
    'no',
    'l2_sms',
    'l2_bingo',
    'l2_dspatch',
    'l2_pmp',
    'l2_gaze',
    'l2_superproba_pc_pcoffset_offsetoffset_80_80',
]


def parse_args():
    default_parallelism = os.cpu_count() or 1

    parser = argparse.ArgumentParser(
        description="Run 4-core CloudSuite ChampSim simulations locally"
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


def build_cloudsuite_phase_list():
    """
    Converts:

        cassandra_phase0_core0
        cassandra_phase0_core1
        cassandra_phase0_core2
        cassandra_phase0_core3

    into one 4-core phase:

        cassandra/cassandra_phase0
    """
    all_phases = []

    for benchmark in cloudsuite_ones:
        traces = CloudSuite_shortcode[benchmark]

        if len(traces) % NUM_CORES != 0:
            print(f"Warning: {benchmark} has {len(traces)} traces, not divisible by {NUM_CORES}")

        for i in range(0, len(traces), NUM_CORES):
            phase_traces = traces[i:i + NUM_CORES]

            if len(phase_traces) != NUM_CORES:
                print(f"Skipping incomplete phase in {benchmark}: {phase_traces}")
                continue

            phase_name = phase_traces[0].replace("_core0.trace.xz", "")

            all_phases.append({
                "benchmark": benchmark,
                "phase_name": phase_name,
                "traces": phase_traces,
            })

    print(f"Found {len(all_phases)} CloudSuite 4-core phases")
    return all_phases


def run_cmd(cmd, stdout=None, stderr=None, dry_run=False):
    print("CMD:", " ".join(cmd))
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0)
    return subprocess.run(cmd, stdout=stdout, stderr=stderr, check=False)


def run_prefetcher(prefetcher, all_phases, parallelism, dry_run):
    binary_path = f"../bin/champsim_{NUM_CORES}core_{prefetcher}"
    folder_name = f"{NUM_CORES}core_{prefetcher}"

    if not os.path.exists(binary_path):
        print(f"Error: {binary_path} not found. Please build first.")
        return 1

    for benchmark in cloudsuite_ones:
        os.makedirs(f"results/log/{folder_name}/{benchmark}", exist_ok=True)
        os.makedirs(f"results/json/{folder_name}/{benchmark}", exist_ok=True)

    total_simulations = len(all_phases)
    actual_parallelism = min(parallelism, total_simulations)

    print("==================")
    print("Running Simulation")
    print("==================")
    print("Configuration Summary:")
    print(f"  Cores: {NUM_CORES}")
    print(f"  Prefetcher: {prefetcher}")
    print(f"  Output folder: {folder_name}")
    print(f"  Binary: {binary_path}")
    print(f"  Total phases: {total_simulations}")
    print(f"  Parallelism: {actual_parallelism}")
    print(f"  Dry run: {dry_run}")
    print()

    completed_simulations = 0
    progress_lock = threading.Lock()
    failures = []
    start_time = time.time()

    def run_phase_local(phase):
        nonlocal completed_simulations

        benchmark = phase["benchmark"]
        phase_name = phase["phase_name"]
        traces = phase["traces"]

        output_path = f"results/log/{folder_name}/{benchmark}/{phase_name}.txt"
        json_path = f"results/json/{folder_name}/{benchmark}/{phase_name}.json"

        cmd = [
            binary_path,
            f"--json={json_path}",
            "--warmup_instructions",
            str(WARMUP_INSTRUCTIONS),
            "--simulation_instructions",
            str(SIMULATION_INSTRUCTIONS),
            "-c",
        ]

        for trace in traces:
            cmd.append(os.path.join(CloudSuite_path, trace))

        print(f"Starting {benchmark}/{phase_name} ...")

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
            print(f"Completed {benchmark}/{phase_name}. [Progress: {finished} / {total_simulations}]")
        else:
            print(
                f"Failed {benchmark}/{phase_name} (exit code {returncode}). "
                f"[Progress: {finished} / {total_simulations}]"
            )

        return {
            "benchmark": benchmark,
            "phase_name": phase_name,
            "returncode": returncode,
            "output_path": output_path,
        }

    with ThreadPoolExecutor(max_workers=actual_parallelism) as executor:
        futures = [executor.submit(run_phase_local, phase) for phase in all_phases]

        for future in as_completed(futures):
            result = future.result()
            if result["returncode"] != 0:
                failures.append(result)

    elapsed_time_minutes = (time.time() - start_time) / 60.0

    print("===================")
    print("Simulation Complete")
    print("===================")
    print(f"Simulated: {folder_name}")
    print(f"Simulation time: {elapsed_time_minutes:.2f} minutes")

    if failures:
        print()
        print("Failed runs:")
        for item in failures:
            print(
                f"  - {item['benchmark']}/{item['phase_name']} -> {item['output_path']} "
                f"(exit code {item['returncode']})"
            )
        return 1

    return 0


def main():
    args = parse_args()

    if args.parallelism <= 0:
        print("--parallelism must be >= 1")
        sys.exit(1)

    all_phases = build_cloudsuite_phase_list()

    overall_rc = 0

    for prefetcher in PREFETCHERS:
        rc = run_prefetcher(
            prefetcher,
            all_phases,
            args.parallelism,
            args.dry_run,
        )

        if rc != 0:
            overall_rc = rc

    sys.exit(overall_rc)


if __name__ == "__main__":
    main()