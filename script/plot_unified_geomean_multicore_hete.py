#!/usr/bin/env python3

import os
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np
import math
import json

plt.style.use('default')

# =========================
# CloudSuite 4-core config
# =========================
from _CloudSuite_def import CloudSuite_shortcode, CloudSuite_path, cloudsuite_ones

LOG_DIR = os.path.join('results', 'json')
GRAPH_DIR = 'graphs'
OUTPUT = "png"

PLOT_NAME = 'cloudsuite_4core'

NUM_CORES = 4
RESULT_PREFIX = f"{NUM_CORES}core_"

BENCHMARKS = cloudsuite_ones

BENCHMARK_SHORTCODE = {
    "cassandra": "cassandra",
    "classification": "classification",
    "cloud9": "cloud9",
    "nutch": "nutch",
    "streaming": "streaming",
}

BASELINE = 'no'

PREFETCHERS = [
    'l2_sms',
    'l2_bingo',
    'l2_dspatch',
    'l2_pmp',
    'l2_gaze',
    'l2_superproba_pc_pcoffset_offsetoffset_80_80',
]

if BASELINE not in PREFETCHERS:
    PREFETCHERS.append(BASELINE)

INCLUDE_GEOMEAN = True

PLOT_WIDTH = 14
PLOT_HEIGHT = 7

BLUES = True
blues = ['#cccccc', '#348ABD', '#467821', '#D55E00', '#7A68A6', '#A60628', '#CC79A7']


# =========================
# JSON helpers
# =========================

def load_json_obj(file_path):
    """
    Load a JSON file. Supports:
      - a normal JSON object
      - a normal JSON array
      - a file with extra text around the JSON payload
    """
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read().strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        begin = content.find('[')
        end = content.rfind(']') + 1
        if begin != -1 and end > begin:
            return json.loads(content[begin:end])

        begin = content.find('{')
        end = content.rfind('}') + 1
        if begin != -1 and end > begin:
            return json.loads(content[begin:end])

        raise


def get_roi(file_path):
    json_obj = load_json_obj(file_path)

    if isinstance(json_obj, list):
        json_obj = json_obj[0]

    return json_obj.get('roi', {})


def scalar(x):
    """
    ChampSim sometimes stores counters as scalars and sometimes as one-element lists.
    """
    if isinstance(x, list):
        if len(x) == 0:
            return 0.0
        return float(x[0])
    return float(x)


def get_counter(d, key, default=0.0):
    try:
        return scalar(d.get(key, default))
    except (TypeError, ValueError):
        return default


def result_dir_for_prefetcher(prefetcher):
    """
    Example:
        l2_sms -> 4core_l2_sms
        no     -> 4core_no
    """
    return RESULT_PREFIX + prefetcher


# =========================
# Metric parsers
# =========================

def parse_ipc_from_file(filepath):
    """
    Multicore throughput IPC.

    For one 4-core CloudSuite phase:
        IPC = sum(core_i.instructions) / max(core_i.cycles)

    This produces one IPC value per benchmark_phase JSON.
    """
    roi = get_roi(filepath)

    try:
        cores = roi['cores']

        total_instructions = 0.0
        max_cycles = 0.0

        for core in cores[:NUM_CORES]:
            instructions = float(core.get('instructions', 0.0))
            cycles = float(core.get('cycles', 0.0))

            total_instructions += instructions
            max_cycles = max(max_cycles, cycles)

        if max_cycles <= 0:
            return None

        return total_instructions / max_cycles

    except (KeyError, IndexError, TypeError, ZeroDivisionError, ValueError):
        return None


def parse_dram_from_file(filepath):
    """
    DRAM traffic = read row-buffer hits/misses + write row-buffer hits/misses.
    """
    roi = get_roi(filepath)

    try:
        dram = roi['DRAM'][0]

        dram_read_hit = get_counter(dram, 'RQ ROW_BUFFER_HIT')
        dram_read_miss = get_counter(dram, 'RQ ROW_BUFFER_MISS')
        dram_write_hit = get_counter(dram, 'WQ ROW_BUFFER_HIT')
        dram_write_miss = get_counter(dram, 'WQ ROW_BUFFER_MISS')

        return dram_read_hit + dram_read_miss + dram_write_hit + dram_write_miss

    except (KeyError, IndexError, TypeError, ValueError):
        return None


# =========================
# Data gathering
# =========================

def gather_data(parse_func, metric_name):
    """
    Expected structure:

        results/json/4core_l2_sms/cassandra/cassandra_phase0.json
        results/json/4core_l2_sms/cassandra/cassandra_phase1.json
        ...

    Data label format:

        cassandra/cassandra_phase0
        cassandra/cassandra_phase1
        ...
    """
    data = defaultdict(dict)

    for benchmark in BENCHMARKS:
        for prefetcher in PREFETCHERS:
            folder_name = result_dir_for_prefetcher(prefetcher)
            path = os.path.join(LOG_DIR, folder_name, benchmark)

            if not os.path.isdir(path):
                print(f"Missing directory: {path}")
                continue

            for filename in sorted(os.listdir(path)):
                if not filename.endswith('.json'):
                    continue

                phase_name = filename.replace('.json', '')
                filepath = os.path.join(path, filename)

                result = parse_func(filepath)

                if result is not None:
                    label = f"{benchmark}/{phase_name}"
                    data[prefetcher][label] = result

    return data


def get_phase_labels_for_benchmark(data, benchmark):
    """
    Use baseline phases as the reference.
    If baseline is missing, fall back to all available phases.
    """
    prefix = f"{benchmark}/"

    labels = sorted([
        label for label in data[BASELINE].keys()
        if label.startswith(prefix)
    ])

    if labels:
        return labels

    all_labels = set()

    for prefetcher in PREFETCHERS:
        for label in data[prefetcher].keys():
            if label.startswith(prefix):
                all_labels.add(label)

    return sorted(all_labels)


# =========================
# Metric aggregation
# =========================

def harmonic_speedup(base_ipcs, test_ipcs):
    """
    Equal-weight harmonic speedup across CloudSuite phases.

    speedup = sum(1 / base_ipc) / sum(1 / test_ipc)
    """
    if not base_ipcs or not test_ipcs:
        return 0.0

    baseline_time = 0.0
    test_time = 0.0

    for base_ipc, test_ipc in zip(base_ipcs, test_ipcs):
        if base_ipc <= 0 or test_ipc <= 0:
            return 0.0

        baseline_time += 1.0 / base_ipc
        test_time += 1.0 / test_ipc

    if test_time == 0:
        return 0.0

    return baseline_time / test_time


def compute_cloudsuite_metric(data, metric_type, baseline_name):
    """
    Computes benchmark-level results by aggregating phases.

    For IPC:
        benchmark speedup = harmonic speedup across phases

    For DRAM:
        benchmark normalized traffic = sum(test DRAM over phases) / sum(base DRAM over phases)
    """
    metric_values = defaultdict(dict)

    plot_prefetchers = [p for p in PREFETCHERS if p != baseline_name]

    for benchmark in BENCHMARKS:
        phase_labels = get_phase_labels_for_benchmark(data, benchmark)

        if not phase_labels:
            print(f"Warning: no phases found for benchmark {benchmark}")
            continue

        for prefetcher in plot_prefetchers:
            if metric_type == 'ipc':
                base_ipcs = []
                test_ipcs = []

                for label in phase_labels:
                    base_value = data[baseline_name].get(label)
                    test_value = data[prefetcher].get(label)

                    if base_value is not None and test_value is not None:
                        base_ipcs.append(base_value)
                        test_ipcs.append(test_value)

                metric_values[prefetcher][benchmark] = harmonic_speedup(base_ipcs, test_ipcs)

            elif metric_type == 'dram':
                total_base_dram = 0.0
                total_test_dram = 0.0

                for label in phase_labels:
                    base_value = data[baseline_name].get(label)
                    test_value = data[prefetcher].get(label)

                    if base_value is not None and test_value is not None:
                        total_base_dram += base_value
                        total_test_dram += test_value

                if total_base_dram > 0:
                    metric_values[prefetcher][benchmark] = total_test_dram / total_base_dram
                else:
                    metric_values[prefetcher][benchmark] = 0.0

    # Overall geomean across CloudSuite benchmarks
    for prefetcher in plot_prefetchers:
        values = [
            metric_values[prefetcher][benchmark]
            for benchmark in BENCHMARKS
            if benchmark in metric_values[prefetcher]
        ]

        positive_values = [v for v in values if v > 0]

        if positive_values:
            metric_values[prefetcher]["geomean"] = math.exp(
                sum(math.log(v) for v in positive_values) / len(positive_values)
            )
        else:
            metric_values[prefetcher]["geomean"] = 0.0

    return metric_values, plot_prefetchers


# =========================
# Plot/export helpers
# =========================

def setup_plot_style():
    plt.style.use('bmh')

    if BLUES:
        plt.rcParams['axes.prop_cycle'] = plt.cycler(color=blues)

    plt.rcParams.update({
        'font.size': 14,
        'axes.labelsize': 14,
        'xtick.labelsize': 14,
        'ytick.labelsize': 14,
        'legend.fontsize': 8
    })


def get_display_name(prefetcher):
    if prefetcher == 'l2_sms':
        return 'SMS'
    elif prefetcher == 'l2_bingo':
        return 'Bingo'
    elif prefetcher == 'l2_dspatch':
        return 'DSPatch'
    elif prefetcher == 'l2_pmp':
        return 'PMP'
    elif prefetcher == 'l2_gaze':
        return 'Gaze'
    elif prefetcher == 'l2_proba':
        return 'Proba'
    elif prefetcher == 'l2_superproba':
        return 'SuperProba'
    elif prefetcher == 'l2_superproba_offset_pc':
        return 'SuperProba Off/PC'
    elif prefetcher == 'l2_superproba_pc_pcoffset':
        return 'SuperProba PC/PCOff'
    elif prefetcher == 'l2_superproba_offset_pc_offsetoffset':
        return 'SuperProba Off/PC/OffOff'
    elif prefetcher == 'l2_superproba_offset_pcoffset_offsetoffset':
        return 'SuperProba Off/PCOff/OffOff'
    elif prefetcher == 'l2_superproba_pc_pcoffset_offsetoffset':
        return 'SuperProba PC/PCOff/OffOff'
    elif prefetcher == 'l2_superproba_pc_pcoffset_offsetoffset_80_80':
        return 'SuperProba PC/PCOff/OffOff'
    return prefetcher


def benchmark_to_data_name(benchmark):
    return BENCHMARK_SHORTCODE.get(benchmark, benchmark)


def export_data_file(metric_values, plot_prefetchers, out_filename):
    if not os.path.exists(GRAPH_DIR):
        os.makedirs(GRAPH_DIR)

    out_path = os.path.join(GRAPH_DIR, out_filename)
    display_prefetchers = [get_display_name(p) for p in plot_prefetchers]

    with open(out_path, 'w') as f:
        f.write("#\t" + "\t".join(display_prefetchers) + "\n")

        for benchmark in BENCHMARKS:
            bench_name = benchmark_to_data_name(benchmark)
            vals = [metric_values[p].get(benchmark, 0.0) for p in plot_prefetchers]

            f.write(
                f"{bench_name}\t" +
                "\t".join(f"{v:.9f}".rstrip('0').rstrip('.') for v in vals) +
                "\n"
            )

        vals = [metric_values[p].get("geomean", 0.0) for p in plot_prefetchers]

        f.write(
            "geomean\t" +
            "\t".join(f"{v:.9f}".rstrip('0').rstrip('.') for v in vals) +
            "\n"
        )

    print(f"Exported: {out_path}")


def create_plot(
    metric_values,
    plot_prefetchers,
    ylabel,
    filename,
    include_geomean=True,
    include_baseline=True,
    ylim_bottom=None,
    ylim_top=None,
):
    setup_plot_style()

    display_prefetchers = [get_display_name(p) for p in plot_prefetchers]

    all_labels = BENCHMARKS + (["geomean"] if include_geomean else [])

    x = np.arange(len(all_labels))
    bar_width = 0.8 / len(plot_prefetchers)

    fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))

    if include_baseline:
        ax.axhline(1.0, linestyle='-', color='black', linewidth=1, label='Baseline')

    ax.grid(True, linestyle='--', alpha=0.7, axis='y', zorder=0)

    for i, prefetcher in enumerate(plot_prefetchers):
        heights = [metric_values[prefetcher].get(bm, 0.0) for bm in all_labels]
        offsets = x + i * bar_width

        ax.bar(
            offsets,
            heights,
            width=bar_width,
            label=display_prefetchers[i],
            edgecolor='black',
            linewidth=0.5,
            zorder=1
        )

    ax.set_xticks(x + bar_width * (len(plot_prefetchers) - 1) / 2)
    ax.set_xticklabels(
        [benchmark_to_data_name(label) for label in all_labels],
        rotation=35,
        ha='right'
    )

    if ylim_bottom is not None:
        ax.set_ylim(bottom=ylim_bottom)

    if ylim_top is not None:
        ax.set_ylim(top=ylim_top)

    ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=10))
    ax.set_ylabel(ylabel, fontweight='bold')
    ax.set_xlabel("CloudSuite Benchmark", fontweight='bold')

    ax.legend(
        loc='upper center',
        bbox_to_anchor=(0.5, 1.10),
        ncol=max(1, len(plot_prefetchers)),
        frameon=True,
        edgecolor='black',
        prop={'weight': 'bold'}
    )

    plt.tight_layout(pad=0.1)

    if not os.path.exists(GRAPH_DIR):
        os.makedirs(GRAPH_DIR)

    out_path = os.path.join(GRAPH_DIR, filename)

    if OUTPUT == "pdf":
        plt.savefig(out_path, format='pdf', bbox_inches='tight')
    elif OUTPUT == "png":
        plt.savefig(out_path, format='png', dpi=300, bbox_inches='tight')

    plt.close()

    print(f"Created: {out_path}")


# =========================
# Main
# =========================

def main():
    print("CloudSuite 4-core plot script")
    print("============================")
    print(f"Expected result root: {LOG_DIR}")
    print(f"Expected layout: results/json/{RESULT_PREFIX}<prefetcher>/<benchmark>/<benchmark>_phaseN.json")
    print(f"Benchmarks: {', '.join(BENCHMARKS)}")
    print()

    print("Gathering IPC data...")
    ipc_data = gather_data(parse_ipc_from_file, 'ipc')

    print("Gathering DRAM data...")
    dram_data = gather_data(parse_dram_from_file, 'dram')

    print("--------------------------------")
    print("Computing throughput IPC speedup...")
    ipc_speedups, ipc_plot_prefetchers = compute_cloudsuite_metric(
        ipc_data,
        'ipc',
        BASELINE
    )

    print("Overall IPC speedups:")
    for prefetcher in ipc_plot_prefetchers:
        print(f"> {prefetcher}: {ipc_speedups[prefetcher].get('geomean', 0.0)}")

    print("--------------------------------")
    print("Computing normalized DRAM traffic...")
    dram_speedups, dram_plot_prefetchers = compute_cloudsuite_metric(
        dram_data,
        'dram',
        BASELINE
    )

    print("Overall normalized DRAM traffic:")
    for prefetcher in dram_plot_prefetchers:
        print(f"> {prefetcher}: {dram_speedups[prefetcher].get('geomean', 0.0)}")

    print("--------------------------------")
    print("Creating plots...")

    create_plot(
        ipc_speedups,
        ipc_plot_prefetchers,
        ylabel='Throughput IPC Speedup',
        filename=f'{PLOT_NAME}_ipc.{OUTPUT}',
        include_geomean=INCLUDE_GEOMEAN,
        include_baseline=True,
        ylim_bottom=0.7,
    )

    create_plot(
        dram_speedups,
        dram_plot_prefetchers,
        ylabel='Normalized DRAM Traffic',
        filename=f'{PLOT_NAME}_dram.{OUTPUT}',
        include_geomean=INCLUDE_GEOMEAN,
        include_baseline=True,
        ylim_bottom=0.9,
    )

    print("--------------------------------")
    print("Exporting .data files...")

    export_data_file(
        ipc_speedups,
        ipc_plot_prefetchers,
        f'{PLOT_NAME}_ipc.data'
    )

    export_data_file(
        dram_speedups,
        dram_plot_prefetchers,
        f'{PLOT_NAME}_dram.data'
    )

    print("--------------------------------")
    print("Done.")


if __name__ == "__main__":
    main()