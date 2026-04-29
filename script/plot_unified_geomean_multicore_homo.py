#!/usr/bin/env python3

import argparse
import os
import json
import re
import math
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

plt.style.use('default')

# ============================================================
# CHANGED: use multicore SPEC benchmark definitions
# ============================================================
from _SPEC2017_def import (
    SPEC2017_multicore_shortcode,
    SPEC2017_shortcode,
    spec2017_ones,
    spec2006_ones,
)

try:
    from _SPEC_WEIGHTS import SPEC2017_SHORTCODE_WEIGHTS
except ImportError:
    SPEC2017_SHORTCODE_WEIGHTS = {}


# ============================================================
# CONFIG
# ============================================================

LOG_DIR = os.path.join('results', 'json')
GRAPH_DIR = 'graphs'
OUTPUT = 'png'

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

PLOT_NAME = 'spec_multicore_homogeneous'

PLOT_WIDTH = 16
PLOT_HEIGHT = 7

INCLUDE_GEOMEAN = True

BLUES = True
blues = ['#cccccc', '#348ABD', '#467821', '#D55E00', '#7A68A6', '#A60628', '#CC79A7']


# ============================================================
# ARGUMENTS
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description='Plot multicore homogeneous SPEC ChampSim results'
    )

    parser.add_argument(
        '--benchmark',
        type=str,
        required=True,
        help='Benchmark to plot: SPEC_ALL, SPEC_2017, SPEC_2006, or part of benchmark name',
    )

    parser.add_argument(
        '--num-cores',
        type=int,
        required=True,
        help='Number of cores used in the run, e.g. 4',
    )

    parser.add_argument(
        '--plot-name',
        type=str,
        default=PLOT_NAME,
        help=f'Output plot/data prefix, default: {PLOT_NAME}',
    )

    return parser.parse_args()


# ============================================================
# BENCHMARK SELECTION
# ============================================================

def get_matching_benchmarks(benchmark_arg):
    if benchmark_arg == 'SPEC_ALL':
        print('Plotting all multicore SPEC benchmarks')
        matching = SPEC2017_multicore_shortcode.copy()

    elif benchmark_arg == 'SPEC_2017':
        print('Plotting SPEC2017 multicore benchmarks')
        matching = {}

        for key in spec2017_ones:
            if key in SPEC2017_multicore_shortcode:
                matching[key] = SPEC2017_multicore_shortcode[key]

    elif benchmark_arg == 'SPEC_2006':
        print('Plotting SPEC2006 multicore benchmarks')
        matching = {}

        for key in spec2006_ones:
            if key in SPEC2017_multicore_shortcode:
                matching[key] = SPEC2017_multicore_shortcode[key]

    else:
        matching = {}

        for key in SPEC2017_multicore_shortcode:
            if benchmark_arg in key:
                matching[key] = SPEC2017_multicore_shortcode[key]

        if not matching:
            print('No benchmarks found matching:', benchmark_arg)
            print('Available benchmarks:', ', '.join(SPEC2017_multicore_shortcode.keys()))
            raise SystemExit(1)

    print(
        f'Found {len(matching)} benchmark categories with '
        f'{sum(len(v) for v in matching.values())} traces'
    )

    return matching


# ============================================================
# TRACE NAME HELPERS
# ============================================================

def normalize_trace_name(trace_path):
    """
    Converts:

        403.gcc-16B.champsimtrace.xz -> gcc-16B
        gcc-16B.json                 -> gcc-16B
        602.gcc_s-1850B.champsimtrace.xz -> gcc_s-1850B
    """
    name = os.path.basename(trace_path)

    for suffix in ['.json', '.xz', '.gz']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]

    if name.endswith('.champsimtrace'):
        name = name[:-len('.champsimtrace')]

    m = re.match(r'^\d+\.(.+)$', name)
    if m:
        name = m.group(1)

    return name


def get_trace_output_name(trace_path):
    """
    Must match the run script output name.

    Run script:
        403.gcc-16B.champsimtrace.xz -> gcc-16B.json
    """
    return normalize_trace_name(trace_path)


def benchmark_to_data_name(benchmark):
    mapped = SPEC2017_shortcode.get(benchmark)

    name = None

    if isinstance(mapped, list) and mapped:
        first_trace = os.path.basename(mapped[0])
        name = normalize_trace_name(first_trace)
        name = name.split('-')[0]

    if name is None:
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*?)(\d+)$', benchmark)
        if m:
            name = m.group(1)
        else:
            name = benchmark

    name = re.sub(r'_s$', '', name)

    alias = {
        'perlbench': 'perlbench',
        'perlbench_s': 'perlbench',
        'bzip2': 'bzip2',
        'gcc': 'gcc',
        'gcc_s': 'gcc',
        'bwaves': 'bwaves',
        'bwaves_s': 'bwaves',
        'mcf': 'mcf',
        'mcf_s': 'mcf',
        'cactusADM': 'cactus',
        'cactuBSSN': 'cactus',
        'cactuBSSN_s': 'cactus',
        'lbm': 'lbm',
        'lbm_s': 'lbm',
        'omnetpp': 'omnet',
        'omnetpp_s': 'omnet',
        'xalancbmk': 'xalan',
        'xalancbmk_s': 'xalan',
        'cam4_s': 'cam4',
        'pop2_s': 'pop2',
        'fotonik3d_s': 'fotonik3d',
        'roms_s': 'roms',
        'xz_s': 'xz',
    }

    return alias.get(name, name)


def get_weight_map(benchmark):
    """
    Returns normalized trace-name -> weight.

    If weights are unavailable, the compute function falls back to weight = 1.0.
    """
    raw_weight_map = SPEC2017_SHORTCODE_WEIGHTS.get(benchmark, {})

    normalized = {}

    for trace_name, weight in raw_weight_map.items():
        normalized[normalize_trace_name(trace_name)] = float(weight)

    return normalized


# ============================================================
# JSON HELPERS
# ============================================================

def load_json_obj(file_path):
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
    if isinstance(x, list):
        if not x:
            return 0.0
        return float(x[0])

    return float(x)


def get_counter(d, key, default=0.0):
    try:
        return scalar(d.get(key, default))
    except (TypeError, ValueError):
        return default


# ============================================================
# RESULT PATH HELPERS
# ============================================================

def result_dir_for_prefetcher(num_cores, prefetcher):
    """
    l2_sms -> 4core_l2_sms
    no     -> 4core_no
    """
    return f'{num_cores}core_{prefetcher}'


def get_expected_trace_labels(matching_benchmarks, benchmark):
    labels = []

    for trace in matching_benchmarks.get(benchmark, []):
        trace_name = get_trace_output_name(trace)
        labels.append(f'{benchmark}/{trace_name}')

    return labels


# ============================================================
# PARSERS
# ============================================================

def parse_ipc_from_file(filepath, num_cores):
    """
    CHANGED: multicore throughput IPC.

    For homogeneous multicore:
        IPC = sum(core_i.instructions) / max(core_i.cycles)

    Since every core runs the same trace, this gives total throughput IPC.
    """
    roi = get_roi(filepath)

    try:
        cores = roi['cores']

        total_instructions = 0.0
        max_cycles = 0.0

        for core in cores[:num_cores]:
            instructions = float(core.get('instructions', 0.0))
            cycles = float(core.get('cycles', 0.0))

            total_instructions += instructions
            max_cycles = max(max_cycles, cycles)

        if max_cycles <= 0:
            return None

        return total_instructions / max_cycles

    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        return None


def parse_dram_from_file(filepath, num_cores):
    roi = get_roi(filepath)

    try:
        return sum(
            get_counter(ch, 'RQ ROW_BUFFER_HIT') +
            get_counter(ch, 'RQ ROW_BUFFER_MISS') +
            get_counter(ch, 'WQ ROW_BUFFER_HIT') +
            get_counter(ch, 'WQ ROW_BUFFER_MISS')
            for ch in roi['DRAM']
        )

    except (KeyError, TypeError, ValueError):
        return None

# ============================================================
# DATA GATHERING
# ============================================================

def gather_data(parse_func, matching_benchmarks, num_cores):
    """
    Expected layout from your run script:

        results/json/4core_l2_sms/gcc403/gcc-16B.json
        results/json/4core_l2_sms/gcc403/gcc-17B.json
        results/json/4core_l2_sms/gcc403/gcc-48B.json

    Label format:

        gcc403/gcc-16B
        gcc403/gcc-17B
        gcc403/gcc-48B
    """
    data = defaultdict(dict)

    for benchmark in matching_benchmarks:
        for prefetcher in PREFETCHERS:
            folder_name = result_dir_for_prefetcher(num_cores, prefetcher)
            path = os.path.join(LOG_DIR, folder_name, benchmark)

            if not os.path.isdir(path):
                print(f'Missing directory: {path}')
                continue

            expected_trace_names = {
                get_trace_output_name(trace) for trace in matching_benchmarks[benchmark]
            }

            for filename in sorted(os.listdir(path)):
                if not filename.endswith('.json'):
                    continue

                trace_name = normalize_trace_name(filename)

                if trace_name not in expected_trace_names:
                    continue

                trace_name = normalize_trace_name(filename)
                filepath = os.path.join(path, filename)

                result = parse_func(filepath, num_cores)

                if result is not None:
                    label = f'{benchmark}/{trace_name}'
                    data[prefetcher][label] = result

    return data


# ============================================================
# METRIC COMPUTATION
# ============================================================

def weighted_harmonic_speedup(base_ipcs, test_ipcs, weights):
    """
    Correct speedup for IPC rates:

        speedup = sum(w / base_ipc) / sum(w / test_ipc)
    """
    if not base_ipcs or not test_ipcs or not weights:
        return 0.0

    base_time = 0.0
    test_time = 0.0

    for base_ipc, test_ipc, weight in zip(base_ipcs, test_ipcs, weights):
        if base_ipc <= 0 or test_ipc <= 0:
            return 0.0

        base_time += weight / base_ipc
        test_time += weight / test_ipc

    if test_time <= 0:
        return 0.0

    return base_time / test_time


def compute_metric(data, matching_benchmarks, metric_type):
    """
    For each benchmark:
      IPC:
        weighted harmonic speedup across traces

      DRAM:
        normalized DRAM = weighted sum(test DRAM) / weighted sum(base DRAM)

    Overall:
      geomean across benchmarks
    """
    metric_values = defaultdict(dict)
    plot_prefetchers = [p for p in PREFETCHERS if p != BASELINE]

    for benchmark in matching_benchmarks:
        labels = get_expected_trace_labels(matching_benchmarks, benchmark)
        weight_map = get_weight_map(benchmark)

        for prefetcher in plot_prefetchers:
            if metric_type == 'ipc':
                base_ipcs = []
                test_ipcs = []
                weights = []

                for label in labels:
                    trace_name = label.split('/', 1)[1]

                    base_value = data[BASELINE].get(label)
                    test_value = data[prefetcher].get(label)

                    if base_value is None or test_value is None:
                        continue

                    weight = weight_map.get(trace_name, 1.0)

                    base_ipcs.append(base_value)
                    test_ipcs.append(test_value)
                    weights.append(weight)

                metric_values[prefetcher][benchmark] = weighted_harmonic_speedup(
                    base_ipcs,
                    test_ipcs,
                    weights,
                )

            elif metric_type == 'dram':
                weighted_base_dram = 0.0
                weighted_test_dram = 0.0

                for label in labels:
                    trace_name = label.split('/', 1)[1]

                    base_value = data[BASELINE].get(label)
                    test_value = data[prefetcher].get(label)

                    if base_value is None or test_value is None:
                        continue

                    weight = weight_map.get(trace_name, 1.0)

                    weighted_base_dram += weight * base_value
                    weighted_test_dram += weight * test_value

                if weighted_base_dram > 0:
                    metric_values[prefetcher][benchmark] = weighted_test_dram / weighted_base_dram
                else:
                    metric_values[prefetcher][benchmark] = 0.0

    for prefetcher in plot_prefetchers:
        values = [
            metric_values[prefetcher][benchmark]
            for benchmark in matching_benchmarks
            if benchmark in metric_values[prefetcher]
        ]

        positive_values = [v for v in values if v > 0]

        if positive_values:
            metric_values[prefetcher]['geomean'] = math.exp(
                sum(math.log(v) for v in positive_values) / len(positive_values)
            )
        else:
            metric_values[prefetcher]['geomean'] = 0.0

    return metric_values, plot_prefetchers


# ============================================================
# PLOT / EXPORT
# ============================================================

def setup_plot_style():
    plt.style.use('bmh')

    if BLUES:
        plt.rcParams['axes.prop_cycle'] = plt.cycler(color=blues)

    plt.rcParams.update({
        'font.size': 14,
        'axes.labelsize': 14,
        'xtick.labelsize': 14,
        'ytick.labelsize': 14,
        'legend.fontsize': 8,
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


def export_data_file(metric_values, plot_prefetchers, matching_benchmarks, out_filename):
    os.makedirs(GRAPH_DIR, exist_ok=True)

    out_path = os.path.join(GRAPH_DIR, out_filename)

    display_prefetchers = [get_display_name(p) for p in plot_prefetchers]

    with open(out_path, 'w') as f:
        f.write('#\t' + '\t'.join(display_prefetchers) + '\n')

        for benchmark in matching_benchmarks:
            bench_name = benchmark_to_data_name(benchmark)
            vals = [metric_values[p].get(benchmark, 0.0) for p in plot_prefetchers]

            f.write(
                f'{bench_name}\t' +
                '\t'.join(f'{v:.9f}'.rstrip('0').rstrip('.') for v in vals) +
                '\n'
            )

        vals = [metric_values[p].get('geomean', 0.0) for p in plot_prefetchers]

        f.write(
            'geomean\t' +
            '\t'.join(f'{v:.9f}'.rstrip('0').rstrip('.') for v in vals) +
            '\n'
        )

    print(f'Exported: {out_path}')


def create_plot(
    metric_values,
    plot_prefetchers,
    matching_benchmarks,
    ylabel,
    filename,
    ylim_bottom=None,
    ylim_top=None,
):
    setup_plot_style()

    os.makedirs(GRAPH_DIR, exist_ok=True)

    labels = list(matching_benchmarks.keys())

    if INCLUDE_GEOMEAN:
        labels = labels + ['geomean']

    display_prefetchers = [get_display_name(p) for p in plot_prefetchers]

    x = np.arange(len(labels))
    bar_width = 0.8 / len(plot_prefetchers)

    fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))

    ax.axhline(
        1.0,
        linestyle='-',
        color='black',
        linewidth=1,
        label='Baseline',
    )

    ax.grid(True, linestyle='--', alpha=0.7, axis='y', zorder=0)

    for i, prefetcher in enumerate(plot_prefetchers):
        heights = [metric_values[prefetcher].get(label, 0.0) for label in labels]
        offsets = x + i * bar_width

        ax.bar(
            offsets,
            heights,
            width=bar_width,
            label=display_prefetchers[i],
            edgecolor='black',
            linewidth=0.5,
            zorder=1,
        )

    ax.set_xticks(x + bar_width * (len(plot_prefetchers) - 1) / 2)
    ax.set_xticklabels(
        [benchmark_to_data_name(label) for label in labels],
        rotation=35,
        ha='right',
    )

    if ylim_bottom is not None:
        ax.set_ylim(bottom=ylim_bottom)

    if ylim_top is not None:
        ax.set_ylim(top=ylim_top)

    ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=10))
    ax.set_ylabel(ylabel, fontweight='bold')
    ax.set_xlabel('Benchmark', fontweight='bold')

    ax.legend(
        loc='upper center',
        bbox_to_anchor=(0.5, 1.10),
        ncol=max(1, len(plot_prefetchers)),
        frameon=True,
        edgecolor='black',
        prop={'weight': 'bold'},
    )

    plt.tight_layout(pad=0.1)

    out_path = os.path.join(GRAPH_DIR, filename)

    if OUTPUT == 'pdf':
        plt.savefig(out_path, format='pdf', bbox_inches='tight')
    else:
        plt.savefig(out_path, format='png', dpi=300, bbox_inches='tight')

    plt.close()

    print(f'Created: {out_path}')


# ============================================================
# MAIN
# ============================================================

def main():
    args = parse_args()

    if args.num_cores <= 0:
        print('--num-cores must be >= 1')
        raise SystemExit(1)

    matching_benchmarks = get_matching_benchmarks(args.benchmark)

    print()
    print('Multicore homogeneous plot script')
    print('=================================')
    print(f'Num cores: {args.num_cores}')
    print(f'Result root: {LOG_DIR}')
    print(f'Expected layout: results/json/{args.num_cores}core_<prefetcher>/<benchmark>/<trace>.json')
    print(f'Plot name: {args.plot_name}')
    print()

    print('Gathering IPC data...')
    ipc_data = gather_data(
        parse_ipc_from_file,
        matching_benchmarks,
        args.num_cores,
    )

    print('Gathering DRAM data...')
    dram_data = gather_data(
        parse_dram_from_file,
        matching_benchmarks,
        args.num_cores,
    )

    print('Computing IPC speedup...')
    ipc_speedups, ipc_plot_prefetchers = compute_metric(
        ipc_data,
        matching_benchmarks,
        'ipc',
    )

    print('Overall IPC speedups:')
    for prefetcher in ipc_plot_prefetchers:
        print(f'> {prefetcher}: {ipc_speedups[prefetcher].get("geomean", 0.0)}')

    print()

    print('Computing normalized DRAM traffic...')
    dram_speedups, dram_plot_prefetchers = compute_metric(
        dram_data,
        matching_benchmarks,
        'dram',
    )

    print('Overall normalized DRAM traffic:')
    for prefetcher in dram_plot_prefetchers:
        print(f'> {prefetcher}: {dram_speedups[prefetcher].get("geomean", 0.0)}')

    print()

    print('Creating plots...')

    create_plot(
        ipc_speedups,
        ipc_plot_prefetchers,
        matching_benchmarks,
        ylabel='Throughput IPC Speedup',
        filename=f'{args.plot_name}_ipc.{OUTPUT}',
        ylim_bottom=0.7,
    )

    create_plot(
        dram_speedups,
        dram_plot_prefetchers,
        matching_benchmarks,
        ylabel='Normalized DRAM Traffic',
        filename=f'{args.plot_name}_dram.{OUTPUT}',
        ylim_bottom=0.9,
    )

    print()
    print('Exporting .data files...')

    export_data_file(
        ipc_speedups,
        ipc_plot_prefetchers,
        matching_benchmarks,
        f'{args.plot_name}_ipc.data',
    )

    export_data_file(
        dram_speedups,
        dram_plot_prefetchers,
        matching_benchmarks,
        f'{args.plot_name}_dram.data',
    )

    print()
    print('Done.')


if __name__ == '__main__':
    main()