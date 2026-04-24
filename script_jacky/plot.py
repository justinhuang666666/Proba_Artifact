import os
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np
import math
import re
import json

plt.style.use('default')

from _SPEC2017_def import SPEC2017_shortcode, spec2017_ones, spec2006_ones, memint2017_ones
from _SPEC_WEIGHTS import SPEC2017_SHORTCODE_WEIGHTS
from _GAP_def import GAP_shortcode, gap_ones
from _GAP_WEIGHTS import GAP_SHORTCODE_WEIGHTS
from _Ligra_def import Ligra_shortcode, ligra_ones
from _Ligra_WEIGHTS import Ligra_SHORTCODE_WEIGHTS
from _PARSEC_def import PARSEC_shortcode, parsec_ones
from _PARSEC_WEIGHTS import PARSEC_SHORTCODE_WEIGHTS

# --- CONFIGURABLE ---
# ChampSim logs: results/<suite>/ <prefetcher> / <benchmark> / *.txt|*.json
# Output graphs:  graphs/<suite>/
_SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, '..'))
OUTPUT = "png"  # Use PNG for PowerPoint compatibility
PLOT_NAME = 'proba'

EXPORT_BENCH_STATS = True
PRINT_BENCH_STATS = False
TRUNCATE_SPEC_BENCH_NAMES = True  # Omit last 3 chars when printing bench stats (SPEC only)

# --- IPC MEAN TYPE SELECTION ---
# 'geomean' - Use geometric mean for IPC speedups (traditional approach)
# 'harmonic' - Use harmonic mean for IPC speedups (time-weighted, more accurate for rates)
IPC_MEAN_TYPE = 'harmonic'

# --- BENCHMARK TYPE SELECTION ---
# Sets benchmark list, weights, and the subdirectory under results/ and graphs/
#   SPEC2017 -> results/spec2017, graphs/spec2017
#   SPEC2006 -> spec2006 | LIGRA -> ligra | PARSEC -> parsec | GAP -> gap
#   SPEC_ALL -> spec2017 (change _results_graph_subdir if your layout differs)
# 'SPEC2017' - SPEC2017 benchmarks
# 'SPEC2006' - SPEC2006 benchmarks
# 'SPEC_ALL' - All SPEC benchmarks
# 'GAP' - GAP graph benchmarks
# 'LIGRA' - Ligra graph benchmarks
# 'PARSEC' - PARSEC benchmarks
BENCHMARK_TYPE = 'LIGRA'

# Select benchmarks based on type
if BENCHMARK_TYPE == 'GAP':
    BENCHMARKS = gap_ones
    BENCHMARK_WEIGHTS = GAP_SHORTCODE_WEIGHTS
    BENCHMARK_SHORTCODE = GAP_shortcode
elif BENCHMARK_TYPE == 'LIGRA':
    BENCHMARKS = ligra_ones
    BENCHMARK_WEIGHTS = Ligra_SHORTCODE_WEIGHTS
    BENCHMARK_SHORTCODE = Ligra_shortcode
elif BENCHMARK_TYPE == 'PARSEC':
    BENCHMARKS = parsec_ones
    BENCHMARK_WEIGHTS = PARSEC_SHORTCODE_WEIGHTS
    BENCHMARK_SHORTCODE = PARSEC_shortcode
elif BENCHMARK_TYPE == 'SPEC2006':
    BENCHMARKS = spec2006_ones
    BENCHMARK_WEIGHTS = SPEC2017_SHORTCODE_WEIGHTS
    BENCHMARK_SHORTCODE = SPEC2017_shortcode
elif BENCHMARK_TYPE == 'SPEC_ALL':
    BENCHMARKS = list(SPEC2017_shortcode.keys())
    BENCHMARK_WEIGHTS = SPEC2017_SHORTCODE_WEIGHTS
    BENCHMARK_SHORTCODE = SPEC2017_shortcode
else:  # Default to SPEC2017
    BENCHMARKS = spec2017_ones
    BENCHMARK_WEIGHTS = SPEC2017_SHORTCODE_WEIGHTS
    BENCHMARK_SHORTCODE = SPEC2017_shortcode

# results/ and graphs/ subfolder (must match BENCHMARK_TYPE)
def _results_graph_subdir(benchmark_type):
    return {
        'SPEC2017': 'spec2017',
        'SPEC2006': 'spec2006',
        'SPEC_ALL': 'spec2017',  # change if you keep SPEC_ALL under another tree
        'LIGRA': 'ligra',
        'PARSEC': 'parsec',
        'GAP': 'gap',
    }.get(benchmark_type, 'spec2017')

_SUBDIR = _results_graph_subdir(BENCHMARK_TYPE)
RESULTS_ROOT = os.path.join(_REPO_ROOT, 'results_jacky', _SUBDIR)
GRAPH_DIR = os.path.join(_REPO_ROOT, 'graphs_jacky', _SUBDIR)

# Directory names under results/<_SUBDIR>/ (per-benchmark ChampSim logs: .txt with JSON ROI, or .json).
BASELINE = 'ip_stride-no'
# List every run directory to compare (e.g. 'spectra-no' once it has <benchmark>/ dirs).
PREFETCHERS = ['ip_stride-l2_sms', 'ip_stride-l2_bingo', 'ip_stride-l2_dspatch', 'ip_stride-l2_pmp', 'ip_stride-l2_gaze', 'ip_stride-l2_superproba_pc_pcoffset_offsetoffset_40_40']

if BASELINE not in PREFETCHERS:
    PREFETCHERS.append(BASELINE)

INCLUDE_GEOMEAN = True
PLOT_TRACE_IPC = False  # Plot raw IPC values from simpoints instead of geomean
PLOT_TRACE_DRAM = False  # Plot raw DRAM traffic from simpoints instead of geomean
ONLY_GEOMEAN_BAR = False
HIGHLIGHT_LAST = False

ONLY_GEOMEAN_LINE = False # BROKEN! 


PLOT_WIDTH = 30
PLOT_HEIGHT = 8

if ONLY_GEOMEAN_BAR:
    PLOT_WIDTH = 4
    PLOT_HEIGHT = 6

BLUES = True

blues = ['#84a1f5', '#4e70d4', '#3052b8', '#0A2472']
blues = ['#0A114A', '#1A4FDB', '#3A7BFF', '#6EC8F7']
blues = ['#A3D1FF', '#4E8EFF', '#2A5CFF', '#0A2472']
blues = ['#FE9D52', '#FFCEA9', '#BBBBBB', '#9ECBED', '#3C97DA'] # Emphasize last color
blues = ['#cccccc', '#348ABD', '#467821', '#D55E00','#7A68A6', '#A60628', '#CC79A7'] 
# blues = ['#348ABD', '#467821', '#7A68A6'] 

# blues = ['#348ABD', '#F8B6B6', '#E57373', '#B53636', '#A60628']


# reds = ['#F8B6B6', '#E57373', '#B53636', '#A60628']

# --- PARSING FUNCTIONS (JSON ROI; matches script/plot_unified_geomean.py) ---

def load_json_obj(file_path):
    """
    Load a JSON file. Supports:
      - a normal JSON object
      - a normal JSON array
      - a file with extra text around the JSON payload (e.g. ChampSim .txt logs)
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


def _determine_cpu_str(path):
    # Path shape: …/results/spec2017/<run_id>/<benchmark>/<simpoint>.(txt|json)
    norm = os.path.normpath(path)
    bench_dir = os.path.dirname(norm)
    prefetcher_dir = os.path.basename(os.path.dirname(bench_dir))

    if not prefetcher_dir:
        return 'cpu0_L2C'

    if prefetcher_dir == 'no-no':
        return None

    # One hyphen separates L1 config from L2 (e.g. ip_stride-l2_sms, ip_stride-no)
    if '-' not in prefetcher_dir:
        return 'cpu0_L2C'

    l1_pref, l2_pref = prefetcher_dir.split('-', 1)
    l2_is_no = l2_pref.startswith('no')
    l1_is_no = l1_pref.startswith('no')

    if not l2_is_no:
        return 'cpu0_L2C'
    if not l1_is_no:
        return 'cpu0_L1D'
    return None


def parse_ipc_from_file(filepath):
    roi = get_roi(filepath)
    try:
        instructions = roi['cores'][0]['instructions']
        cycles = roi['cores'][0]['cycles']
        if cycles == 0:
            return None
        return instructions / cycles
    except (KeyError, IndexError, TypeError, ZeroDivisionError):
        return None


def parse_dram_from_file(filepath):
    roi = get_roi(filepath)
    try:
        dram_read_hit = roi['DRAM'][0]['RQ ROW_BUFFER_HIT']
        dram_read_miss = roi['DRAM'][0]['RQ ROW_BUFFER_MISS']
        dram_write_hit = roi['DRAM'][0]['WQ ROW_BUFFER_HIT']
        dram_write_miss = roi['DRAM'][0]['WQ ROW_BUFFER_MISS']
        return dram_read_hit + dram_read_miss + dram_write_hit + dram_write_miss
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def parse_cov_from_file(filepath):
    cpu_str = _determine_cpu_str(filepath)
    if cpu_str is None:
        return None

    roi = get_roi(filepath)
    try:
        if cpu_str in ('cpu0_L1D', 'cpu0_L2C', 'LLC'):
            useful = roi[cpu_str]['prefetch useful']
            demand_misses = roi[cpu_str]['LOAD']['miss']
        else:
            return None
        if useful is None or demand_misses is None:
            return None
        return float(useful), float(demand_misses)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    
def parse_llc_cov_from_file(filepath):
    """
    For LLC coverage, return raw LLC load misses.
    JSON format stores LLC hit/miss as 1-element lists.
    """
    roi = get_roi(filepath)

    try:
        llc_load_miss = roi['LLC']['LOAD']['miss']
        if isinstance(llc_load_miss, list):
            return float(llc_load_miss[0])
        return float(llc_load_miss)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def parse_acc_from_file(filepath):
    cpu_str = _determine_cpu_str(filepath)
    if cpu_str is None:
        return None

    roi = get_roi(filepath)
    try:
        if cpu_str in ('cpu0_L1D', 'cpu0_L2C', 'LLC'):
            useful = roi[cpu_str]['prefetch useful']
            useless = roi[cpu_str]['prefetch useless']
        else:
            return None
        if useful is None or useless is None:
            return None
        return float(useful), float(useless)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    
def parse_overall_acc_from_file(filepath):
    roi = get_roi(filepath)

    useful = roi['cpu0_L2C']['prefetch useful'] + roi['LLC']['pf_useful_at_llc_from_l2']
    useless = roi['cpu0_L2C']['prefetch useless'] + roi['LLC']['pf_useless_at_llc_from_l2']
    if useful is None or useless is None:
        return None

    return float(useful), float(useless)


def parse_eog_from_file(filepath):
    # Re-use the same helper logic as in parse_cov_from_file

    cpu_str = _determine_cpu_str(filepath)

    if cpu_str is None:
        return None

    roi = get_roi(filepath)

    try:
        if cpu_str == 'cpu0_L1D':
            eog_updates = roi[cpu_str]['num of end of generation updates']
            updates = roi[cpu_str]['num of pht updates']

        elif cpu_str == 'cpu0_L2C':
            eog_updates = roi[cpu_str]['num of end of generation updates']
            updates = roi[cpu_str]['num of pht updates']

        elif cpu_str == 'LLC':
            eog_updates = roi[cpu_str]['num of end of generation updates']
            updates = roi[cpu_str]['num of pht updates']

        else:
            return None

        if eog_updates is None or updates is None:
            return None

        return float(eog_updates), float(updates)

    except (KeyError, IndexError, TypeError, ValueError):
        return None

# --- DATA GATHERING FUNCTIONS ---
def gather_data(parse_func, metric_name):
    """Generic function to gather data using the specified parsing function"""
    data = defaultdict(dict)
    
    for benchmark in BENCHMARKS:
        for prefetcher in PREFETCHERS:
            path = os.path.join(RESULTS_ROOT, prefetcher, benchmark)
            if not os.path.isdir(path):
                print(f"Missing directory: {path}")
                continue

            for filename in os.listdir(path):
                if filename.endswith('.json'):
                    simpoint = filename[:-5]
                elif filename.endswith('.txt'):
                    simpoint = filename[:-4]
                else:
                    continue
                # Quick and dirty hack, sorry Jacob :(
                if re.match(r'^\d+\.', simpoint):
                    simpoint = simpoint[len(re.match(r'^\d+\.', simpoint).group(0)):]
                # PARSEC / Ligra: weight maps use drop_####M, not the full log/trace stem
                if BENCHMARK_TYPE in ('PARSEC', 'LIGRA'):
                    m = re.search(r'(drop_\d+M)', simpoint)
                    if m:
                        simpoint = m.group(1)
                filepath = os.path.join(path, filename)
                try:
                    result = parse_func(filepath)
                except (json.JSONDecodeError, OSError, UnicodeError):
                    result = None
                if result is not None:
                    label = f"{benchmark}/{simpoint}"
                    display_name = prefetcher
                    if prefetcher == 'bop':
                        display_name = 'BOP'
                    elif prefetcher == 'berti_stride':
                        display_name = 'Berti'
                    data[display_name][label] = result

    return data

# --- COMPUTE WEIGHTED MEANS ---
def weighted_geomean(values, weights):
    """Compute weighted geometric mean (unweighted if weights not normalized)."""
    log_sum = 0
    for v, w in zip(values, weights):
        if v <= 0:
            return 0.0  # invalid speedup
        log_sum += math.log(v) * w
    return math.exp(log_sum)

def weighted_arithmetic_mean(values, weights):
    """Computes the weighted arithmetic mean."""
    if not weights:
        return sum(values) / len(values) if values else 0.0
    
    total_weight = sum(weights)
    if total_weight == 0:
        return sum(values) / len(values) if values else 0.0
        
    weighted_sum = sum(v * w for v, w in zip(values, weights))
    return weighted_sum / total_weight

def weighted_harmonic_mean_speedup(base_ipcs, test_ipcs, weights):
    """
    Compute the correct speedup using weighted harmonic mean of speedups.
    
    This works by computing weighted sum of times (1/IPC) for both baseline and test,
    then computing speedup as (baseline_time / test_time).
    
    This is mathematically equivalent to:
        speedup = sum(w_i / baseline_ipc_i) / sum(w_i / test_ipc_i)
    
    Note: Weights are NOT normalized to match plot_freeze.py behavior.
    """
    if not weights or not base_ipcs or not test_ipcs:
        print(f"Warning: weights or base_ipcs or test_ipcs is None")
        return 0.0

    # Compute weighted sum of times (1/IPC) for baseline and test
    weighted_baseline_time = 0.0
    weighted_test_time = 0.0
    
    for base_ipc, test_ipc, w in zip(base_ipcs, test_ipcs, weights):
        if base_ipc <= 0 or test_ipc <= 0:
            return 0.0
        weighted_baseline_time += w / base_ipc
        weighted_test_time += w / test_ipc
    
    if weighted_test_time == 0:
        return 0.0
    
    # Speedup = baseline_time / test_time (less time = higher speedup)
    return weighted_baseline_time / weighted_test_time


def weighted_geomean_speedup(base_ipcs, test_ipcs, weights):
    """
    Compute speedup using weighted geometric mean of individual speedups.
    
    This computes speedup_i = test_ipc_i / base_ipc_i for each simpoint,
    then takes the weighted geometric mean of these speedups.
    
    Note: Weights are NOT normalized to match plot_freeze.py behavior.
    """
    if not weights or not base_ipcs or not test_ipcs:
        print(f"Warning: weights or base_ipcs or test_ipcs is None")
        return 0.0
    
    log_sum = 0.0
    for base_ipc, test_ipc, w in zip(base_ipcs, test_ipcs, weights):
        if base_ipc <= 0 or test_ipc <= 0:
            return 0.0
        speedup = test_ipc / base_ipc
        log_sum += math.log(speedup) * w
    
    return math.exp(log_sum)
def compute_geomean_speedups(data, metric_type, baseline_name=None):
    """Compute correctly weighted benchmark-level metrics."""
    geomean_speedups = defaultdict(dict)

    for benchmark in BENCHMARKS:
        weight_map = BENCHMARK_WEIGHTS.get(benchmark, {})
        simpoints = list(weight_map.keys())

        display_prefetchers = []
        for p in PREFETCHERS:
            if p == baseline_name and metric_type in ['coverage', 'accuracy']:
                continue
            else:
                display_prefetchers.append(p)

        for prefetcher in display_prefetchers:
            # IPC
            base_ipcs = []
            test_ipcs = []
            weights = []

            # Count-first accumulators
            weighted_base_dram = 0.0
            weighted_test_dram = 0.0

            weighted_base_llc_load_miss = 0.0
            weighted_test_llc_load_miss = 0.0

            weighted_useful = 0.0
            weighted_useless = 0.0

            weighted_eog_updates = 0.0
            weighted_updates = 0.0

            for sp in simpoints:
                if re.match(r'^\d+\.', sp):
                    sp_name = sp[len(re.match(r'^\d+\.', sp).group(0)):]
                else:
                    sp_name = sp

                label = f"{benchmark}/{sp_name}"
                weight = weight_map[sp]

                if metric_type == 'ipc':
                    base_value = data[baseline_name].get(label) if baseline_name else None
                    test_value = data[prefetcher].get(label)
                    if base_value and test_value and base_value > 0 and test_value > 0:
                        base_ipcs.append(base_value)
                        test_ipcs.append(test_value)
                        weights.append(weight)

                elif metric_type == 'dram':
                    base_value = data[baseline_name].get(label) if baseline_name else None
                    test_value = data[prefetcher].get(label)
                    if base_value is not None and test_value is not None:
                        weighted_base_dram += weight * base_value
                        weighted_test_dram += weight * test_value

                elif metric_type == 'coverage':
                    base_value = data[baseline_name].get(label) if baseline_name else None
                    test_value = data[prefetcher].get(label)
                    if base_value is not None and test_value is not None:
                        weighted_base_llc_load_miss += weight * base_value
                        weighted_test_llc_load_miss += weight * test_value

                elif metric_type == 'accuracy':
                    acc_data = data[prefetcher].get(label)
                    if acc_data is not None:
                        useful, useless = acc_data
                        weighted_useful += weight * useful
                        weighted_useless += weight * useless

                elif metric_type == 'eog':
                    eog_data = data[prefetcher].get(label)
                    if eog_data is not None:
                        eog_updates, updates = eog_data
                        weighted_eog_updates += weight * eog_updates
                        weighted_updates += weight * updates

            if metric_type == 'ipc':
                if base_ipcs and test_ipcs and weights:
                    if IPC_MEAN_TYPE == 'harmonic':
                        geomean_speedups[prefetcher][benchmark] = weighted_harmonic_mean_speedup(
                            base_ipcs, test_ipcs, weights
                        )
                    else:
                        geomean_speedups[prefetcher][benchmark] = weighted_geomean_speedup(
                            base_ipcs, test_ipcs, weights
                        )
                else:
                    geomean_speedups[prefetcher][benchmark] = 0.0

            elif metric_type == 'dram':
                if weighted_base_dram > 0:
                    geomean_speedups[prefetcher][benchmark] = weighted_test_dram / weighted_base_dram
                else:
                    geomean_speedups[prefetcher][benchmark] = 0.0

            elif metric_type == 'coverage':
                if weighted_base_llc_load_miss > 0:
                    miss_ratio = weighted_test_llc_load_miss / weighted_base_llc_load_miss
                    geomean_speedups[prefetcher][benchmark] = (1.0 - miss_ratio) if miss_ratio < 1.0 else 0.0
                else:
                    geomean_speedups[prefetcher][benchmark] = 0.0

            elif metric_type == 'accuracy':
                denom = weighted_useful + weighted_useless
                if denom > 0:
                    geomean_speedups[prefetcher][benchmark] = weighted_useful / denom
                else:
                    geomean_speedups[prefetcher][benchmark] = 1.0

            elif metric_type == 'eog':
                if weighted_updates > 0:
                    geomean_speedups[prefetcher][benchmark] = weighted_eog_updates / weighted_updates
                else:
                    geomean_speedups[prefetcher][benchmark] = 0.0

    plot_prefetchers = [p for p in display_prefetchers if p != baseline_name] if baseline_name else display_prefetchers

    for prefetcher in plot_prefetchers:
        values = [
            geomean_speedups[prefetcher][bm]
            for bm in BENCHMARKS
            if bm in geomean_speedups[prefetcher]
        ]

        if not values:
            overall_value = 0.0
        elif metric_type in ['accuracy', 'coverage', 'eog']:
            overall_value = sum(values) / len(values)
        else:
            positive_values = [v for v in values if v > 0]
            if positive_values:
                log_sum = sum(math.log(v) for v in positive_values)
                overall_value = math.exp(log_sum / len(positive_values))
            else:
                overall_value = 0.0

        geomean_speedups[prefetcher]["geomean"] = overall_value

    return geomean_speedups, plot_prefetchers

def compute_trace_speedups(data, metric_type, baseline_name=None):
    """Compute speedups for individual simpoints (traces) instead of geomean across benchmarks"""
    trace_speedups = defaultdict(dict)
    all_trace_labels = []
    
    for benchmark in BENCHMARKS:
        weight_map = BENCHMARK_WEIGHTS.get(benchmark, {})
        simpoints = list(weight_map.keys())
        
        # Get display names for prefetchers
        display_prefetchers = []
        for p in PREFETCHERS:
            if p == baseline_name and metric_type in ['coverage', 'accuracy']:
                continue
            else:
                display_prefetchers.append(p)
        
        for sp in simpoints:
            # Quick and dirty hack, sorry Jacob :(
            if re.match(r'^\d+\.', sp):
                sp_name = sp[len(re.match(r'^\d+\.', sp).group(0)):]
            else:
                sp_name = sp
            
            label = f"{benchmark}/{sp_name}"
            all_trace_labels.append(label)
            
            for prefetcher in display_prefetchers:
                if metric_type == 'ipc':
                    base_value = data[baseline_name].get(label) if baseline_name else None
                    test_value = data[prefetcher].get(label)
                    if base_value and test_value:
                        speedup = test_value / base_value
                        trace_speedups[prefetcher][label] = speedup
                    else:
                        trace_speedups[prefetcher][label] = 0.0
                elif metric_type == 'dram':
                    base_value = data[baseline_name].get(label) if baseline_name else None
                    test_value = data[prefetcher].get(label)
                    if base_value and test_value:
                        ratio = test_value / base_value
                        trace_speedups[prefetcher][label] = ratio
                    else:
                        trace_speedups[prefetcher][label] = 0.0
    
    # Remove baseline from plot prefetchers
    plot_prefetchers = [p for p in display_prefetchers if p != baseline_name] if baseline_name else display_prefetchers
    
    return trace_speedups, plot_prefetchers, all_trace_labels

# --- PLOTTING FUNCTIONS ---
def setup_plot_style():
    plt.style.use('bmh')
    if BLUES:
        plt.rcParams['axes.prop_cycle'] = plt.cycler(color=blues)
    plt.rcParams.update({
        'font.size': 14,
        'axes.labelsize': 14,
        'xtick.labelsize': 14,
        'ytick.labelsize': 14,
        'legend.fontsize': 12
    })

def get_display_name(prefetcher):
    if prefetcher == 'ip_stride-l2_sms':
        return 'SMS'
    elif prefetcher == 'ip_stride-l2_bingo':
        return 'Bingo'
    elif prefetcher == 'ip_stride-l2_dspatch':
        return 'DSPatch'
    elif prefetcher == 'ip_stride-l2_pmp':
        return 'PMP'
    elif prefetcher == 'ip_stride-l2_gaze':
        return 'Gaze'
    elif prefetcher == 'ip_stride-l2_superproba_pc_pcoffset_offsetoffset':
        return 'SuperProba'

    return prefetcher


def print_benchmark_stats_csv(geomean_speedups, plot_prefetchers, metric_name):
    """Print per-benchmark statistics in CSV format"""
    print(f"\n{metric_name.upper()} Benchmark Statistics (CSV):")

    display_prefetchers = [get_display_name(p) for p in plot_prefetchers]
    header = "# " + " ".join(display_prefetchers)
    print(header)

    for benchmark in BENCHMARKS:
        values = []
        for prefetcher in plot_prefetchers:
            value = geomean_speedups[prefetcher].get(benchmark, 0.0)
            values.append(f"{value:.4f}")

        bench_display = (
            benchmark[:-3] if (TRUNCATE_SPEC_BENCH_NAMES and BENCHMARK_TYPE in ('SPEC2017', 'SPEC2006', 'SPEC_ALL'))
            else benchmark[len('ligra_'):] if (BENCHMARK_TYPE == 'LIGRA' and benchmark.startswith('ligra_'))
            else benchmark[len('parsec_'):] if (BENCHMARK_TYPE == 'PARSEC' and benchmark.startswith('parsec_'))
            else benchmark
        )

        print(f"{bench_display} " + " ".join(values))

    geomean_values = []
    for prefetcher in plot_prefetchers:
        value = geomean_speedups[prefetcher].get("geomean", 0.0)
        geomean_values.append(f"{value:.4f}")

    if metric_name == 'accuracy' or metric_name == 'coverage' or metric_name == 'eog':
        print(f"average " + " ".join(geomean_values))
    else:
        print(f"geomean " + " ".join(geomean_values))


def export_benchmark_stats_data(geomean_speedups, plot_prefetchers, metric_name, out_filename):
    """Export per-benchmark statistics in the same format as print_benchmark_stats_csv."""
    if not os.path.exists(GRAPH_DIR):
        os.makedirs(GRAPH_DIR)

    out_path = os.path.join(GRAPH_DIR, out_filename)

    with open(out_path, 'w') as f:
        display_prefetchers = [get_display_name(p) for p in plot_prefetchers]
        header = "# " + " ".join(display_prefetchers)
        f.write(header + "\n")

        for benchmark in BENCHMARKS:
            values = []
            for prefetcher in plot_prefetchers:
                value = geomean_speedups[prefetcher].get(benchmark, 0.0)
                values.append(f"{value:.4f}")

            bench_display = (
                benchmark[:-3] if (TRUNCATE_SPEC_BENCH_NAMES and BENCHMARK_TYPE in ('SPEC2017', 'SPEC2006', 'SPEC_ALL'))
                else benchmark[len('ligra_'):] if (BENCHMARK_TYPE == 'LIGRA' and benchmark.startswith('ligra_'))
                else benchmark[len('parsec_'):] if (BENCHMARK_TYPE == 'PARSEC' and benchmark.startswith('parsec_'))
                else benchmark
            )

            f.write(f"{bench_display} " + " ".join(values) + "\n")

        geomean_values = []
        for prefetcher in plot_prefetchers:
            value = geomean_speedups[prefetcher].get("geomean", 0.0)
            geomean_values.append(f"{value:.4f}")

        if metric_name == 'accuracy' or metric_name == 'coverage':
            f.write(f"average " + " ".join(geomean_values) + "\n")
        else:
            f.write(f"geomean " + " ".join(geomean_values) + "\n")

def create_plot(geomean_speedups, plot_prefetchers, metric_name, ylabel, filename, 
                include_geomean=True, include_baseline=True, ylim_bottom=None, ylim_top=None, 
                legend_position='right', only_geomean_bar=False, only_geomean_line=False, 
                plot_traces=False, trace_labels=None):
    """Generic plotting function"""
    setup_plot_style()

    display_prefetchers = [get_display_name(p) for p in plot_prefetchers]
    
    if plot_traces and trace_labels:
        # Create trace plot showing individual simpoint results
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))
        
        if include_baseline:
            ax.axhline(1.0, linestyle='-', color='black', linewidth=1, label='Baseline')
        
        ax.grid(True, linestyle='--', alpha=0.7, axis='y', zorder=0)
        
        x = np.arange(len(trace_labels))
        bar_width = 0.5 / len(plot_prefetchers)
        
        for i, prefetcher in enumerate(plot_prefetchers):
            heights = [geomean_speedups[prefetcher].get(label, 0.0) for label in trace_labels]
            offsets = x + i * bar_width
            
            # Determine edge color based on HIGHLIGHT_LAST setting
            edge_color = 'black'
            line_width = 1
            if HIGHLIGHT_LAST and i == len(plot_prefetchers) - 1:
                edge_color = 'black'
                line_width = 2
            
            ax.bar(offsets, heights, width=bar_width, label=display_prefetchers[i], 
                   edgecolor=edge_color, linewidth=line_width, zorder=1)
        
        ax.set_xticks(x + bar_width * (len(plot_prefetchers) - 1) / 2)
        # Rotate trace labels for better readability
        ax.set_xticklabels(trace_labels, rotation=90, ha='center', fontsize=10)
        
        if ylim_bottom is not None:
            ax.set_ylim(bottom=ylim_bottom)
        if ylim_top is not None:
            ax.set_ylim(top=ylim_top)
        
        ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=10))
        ax.set_ylabel(ylabel, fontweight='bold')
        ax.set_xlabel("Simpoint Trace", fontweight='bold')
        
        # Adjust legend position
        if legend_position == 'left':
            ax.legend(loc='upper left', bbox_to_anchor=(0.05, 1), ncol=1, 
                     frameon=True, edgecolor='black', prop={'weight': 'bold'})
        elif legend_position == 'top':
            n_leg = len(plot_prefetchers) + (1 if include_baseline else 0)
            ncol_leg = (n_leg + 1) // 2  # two rows: half the entries per row (ceil n/2)
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.14), ncol=ncol_leg, 
                     frameon=True, edgecolor='black', prop={'weight': 'bold'})
        else:  # right
            ax.legend(loc='upper right', bbox_to_anchor=(0.5, 1), ncol=1, 
                     frameon=True, edgecolor='black', prop={'weight': 'bold'})
    
    elif only_geomean_line:
        # Create line plot for geomean only
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))
        
        if include_baseline:
            ax.axhline(1.0, linestyle='-', color='black', linewidth=1, label='baseline')
            # Add legend only for baseline
            loc = 'upper left' if legend_position == 'left' else 'upper right'
            ax.legend(loc=loc, frameon=True, edgecolor='black', prop={'weight': 'bold'})
        
        ax.grid(True, linestyle='--', alpha=0.7, axis='y', zorder=0)        
        
        # Plot each prefetcher as a point
        x_positions = np.arange(len(plot_prefetchers))
        geomean_values = [geomean_speedups[prefetcher].get("geomean", 0.0) for prefetcher in plot_prefetchers]
        
        ax.plot(x_positions, geomean_values, 'x-', markersize=10, linewidth=1.5, markeredgewidth=1.5, color='purple')
        
        # If name contains stride, extract the number
        for i, prefetcher in enumerate(plot_prefetchers):
            if 'stride' in prefetcher:
                plot_prefetchers[i] = prefetcher.split('_')[1]
        
        # Set x-axis labels to prefetcher names
        ax.set_xticks(x_positions)
        ax.set_xticklabels(plot_prefetchers, rotation=45, ha='right')
        
        if ylim_bottom is not None:
            ax.set_ylim(bottom=ylim_bottom)
        if ylim_top is not None:
            ax.set_ylim(top=ylim_top)
        
        ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=10))
        ax.set_ylabel(ylabel, fontweight='bold')
        # ax.set_xlabel("Prefetcher", fontweight='bold')
        ax.set_xlabel("Degree", fontweight='bold')

    elif only_geomean_bar:
        # Create bar plot for geomean only
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))

        if include_baseline:
            ax.axhline(1.0, linestyle='-', color='black', linewidth=1, label='Baseline')
        
        ax.grid(True, linestyle='--', alpha=0.7, axis='y', zorder=0)
        
        # Plot each prefetcher as a point
        x_positions = np.arange(len(plot_prefetchers))

        geomean_values = [geomean_speedups[prefetcher].get("geomean", 0.0) for prefetcher in plot_prefetchers]

        for i, (x, val) in enumerate(zip(x_positions, geomean_values)):
            # Determine edge color based on HIGHLIGHT_LAST setting
            edge_color = 'black'
            line_width = 1
            if HIGHLIGHT_LAST and i == len(plot_prefetchers) - 1:
                edge_color = 'black'
                line_width = 2
            
            # ax.bar(x, val, width=0.5, label='Geomean', color=blues[i % len(blues)])
            ax.bar(x, val, width=0.5, label='Geomean', edgecolor=edge_color, linewidth=line_width)
        
        ax.set_xticks(x_positions)
        ax.set_xticklabels(display_prefetchers, rotation=45, ha='right')
        
        # Make the last x-axis label bold if HIGHLIGHT_LAST is enabled
        if HIGHLIGHT_LAST:
            labels = ax.get_xticklabels()
            labels[-1].set_weight('bold')

        if ylim_bottom is not None:
            ax.set_ylim(bottom=ylim_bottom)
        if ylim_top is not None:
            ax.set_ylim(top=ylim_top)
        
        ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=10))
        ax.set_ylabel(ylabel, fontweight='bold')
        ax.set_xlabel("Prefetcher", fontweight='bold')

    else:
        # Original bar plot code
        all_labels = BENCHMARKS + (["geomean"] if include_geomean else [])
        x = np.arange(len(all_labels))
        bar_width = 0.5 / len(plot_prefetchers)
        
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))
        
        if include_baseline:
            ax.axhline(1.0, linestyle='-', color='black', linewidth=1, label='Baseline')
        
        ax.grid(True, linestyle='--', alpha=0.7, axis='y', zorder=0)
        
        for i, prefetcher in enumerate(plot_prefetchers):
            heights = [geomean_speedups[prefetcher].get(bm, 0.0) for bm in all_labels]
            offsets = x + i * bar_width
            
            # Determine edge color based on HIGHLIGHT_LAST setting
            edge_color = 'black'
            line_width = 1
            if HIGHLIGHT_LAST and i == len(plot_prefetchers) - 1:
                edge_color = 'black'
                line_width = 1.5
            
            ax.bar(offsets, heights, width=bar_width, label=display_prefetchers[i], 
                   edgecolor=edge_color, linewidth=line_width, zorder=1)
        
        ax.set_xticks(x + bar_width * (len(plot_prefetchers) - 1) / 2)
        ax.set_xticklabels(all_labels, rotation=45, ha='right')
        
        if ylim_bottom is not None:
            ax.set_ylim(bottom=ylim_bottom)
        if ylim_top is not None:
            ax.set_ylim(top=ylim_top)
        
        ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=10))
        ax.set_ylabel(ylabel, fontweight='bold')
        ax.set_xlabel("Benchmark", fontweight='bold')
        
        # Adjust legend position based on legend_position parameter
        if legend_position == 'left':
            ax.legend(loc='upper left', bbox_to_anchor=(0.05, 1), ncol=1, 
                     frameon=True, edgecolor='black', prop={'weight': 'bold'})
        elif legend_position == 'top':
            n_leg = len(plot_prefetchers) + (1 if include_baseline else 0)
            ncol_leg = (n_leg + 1) // 2  # two rows: half the entries per row (ceil n/2)
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.14), ncol=ncol_leg, 
                     frameon=True, edgecolor='black', prop={'weight': 'bold'})
        else:  # right
            if metric_name in ['coverage', 'accuracy']:
                ax.legend(loc='upper left', bbox_to_anchor=(0.86, 1), ncol=1, 
                         frameon=True, edgecolor='black', prop={'weight': 'bold'})
            else:
                ax.legend(loc='upper left', bbox_to_anchor=(0.44, 1), ncol=7, 
                         frameon=True, edgecolor='black', prop={'weight': 'bold'})
    
    plt.tight_layout(pad=0.1)  # Reduce padding around the plot
    if not os.path.exists(GRAPH_DIR):
        os.makedirs(GRAPH_DIR)
    # increase dpi
    if OUTPUT == "pdf":
        plt.savefig(os.path.join(GRAPH_DIR, filename), format='pdf', bbox_inches='tight')  # Trim excess whitespace
    elif OUTPUT == "png":
        plt.savefig(os.path.join(GRAPH_DIR, filename), format='png', dpi=300, bbox_inches='tight')  # Trim excess whitespace
    plt.close()

# --- MAIN EXECUTION ---
def main():
    print(f"BENCHMARK_TYPE={BENCHMARK_TYPE}  ->  results/{_SUBDIR}  graphs/{_SUBDIR}")
    print(f"  {RESULTS_ROOT}\n  {GRAPH_DIR}\n")
    # Gather all data
    print("Gathering IPC data...")
    ipc_data = gather_data(parse_ipc_from_file, 'ipc')
    
    print("Gathering DRAM data...")
    dram_data = gather_data(parse_dram_from_file, 'dram')
    
    print("Gathering coverage data...")
    cov_data = gather_data(parse_llc_cov_from_file, 'coverage')
    
    print("Gathering accuracy data...")
    acc_data = gather_data(parse_overall_acc_from_file, 'accuracy')

    print("Gathering eog data...")
    acc_data = gather_data(parse_eog_from_file, 'accuracy')
    
    # Compute geomean speedups for each metric
    print("--------------------------------")
    print(f"IPC Mean Type: {IPC_MEAN_TYPE}")
    if PLOT_TRACE_IPC:
        print("Computing IPC trace speedups...")
        ipc_speedups, ipc_plot_prefetchers, ipc_trace_labels = compute_trace_speedups(ipc_data, 'ipc', BASELINE)
        print("IPC trace speedups computed for individual simpoints")
    else:
        print(f"Computing IPC speedups (using {IPC_MEAN_TYPE} mean)...")
        ipc_speedups, ipc_plot_prefetchers = compute_geomean_speedups(ipc_data, 'ipc', BASELINE)
        ipc_trace_labels = None
        # print("IPC speedups:", dict(ipc_speedups))\
        print(f"Overall IPC speedups ({IPC_MEAN_TYPE} mean):")
        for prefetcher in ipc_plot_prefetchers:
            print(f"> {prefetcher}: {ipc_speedups[prefetcher].get('geomean', 0.0)}")
    print("--------------------------------")

    if PLOT_TRACE_DRAM:
        print("Computing DRAM trace ratios...")
        dram_speedups, dram_plot_prefetchers, dram_trace_labels = compute_trace_speedups(dram_data, 'dram', BASELINE)
        print("DRAM trace ratios computed for individual simpoints")
    else:
        print("Computing DRAM traffic...")
        dram_speedups, dram_plot_prefetchers = compute_geomean_speedups(dram_data, 'dram', BASELINE)
        dram_trace_labels = None
        print("Geomean DRAM traffic:")
        for prefetcher in dram_plot_prefetchers:
            print(f"> {prefetcher}: {dram_speedups[prefetcher].get('geomean', 0.0)}")
    print("--------------------------------")
    
    print("Computing coverage...")
    cov_speedups, cov_plot_prefetchers = compute_geomean_speedups(cov_data, 'coverage', BASELINE)
    # print("Coverage values:", dict(cov_speedups))
    print("Geomean coverage:")
    for prefetcher in cov_plot_prefetchers:
        print(f"> {prefetcher}: {cov_speedups[prefetcher].get('geomean', 0.0)}")
    print("--------------------------------")
    
    print("Computing accuracy...")
    acc_speedups, acc_plot_prefetchers = compute_geomean_speedups(acc_data, 'accuracy', BASELINE)
    # print("Accuracy values:", dict(acc_speedups))
    print("Geomean accuracy:")
    for prefetcher in acc_plot_prefetchers:
        print(f"> {prefetcher}: {acc_speedups[prefetcher].get('geomean', 0.0)}")
    print("--------------------------------")

    eog_speedups, eog_plot_prefetchers = compute_geomean_speedups(acc_data, 'eog', BASELINE)

    # Print benchmark statistics in CSV format if enabled
    if PRINT_BENCH_STATS:
        print("\n" + "="*80)
        print("BENCHMARK STATISTICS (CSV FORMAT)")
        print("="*80)
        print_benchmark_stats_csv(ipc_speedups, ipc_plot_prefetchers, 'ipc')
        print_benchmark_stats_csv(dram_speedups, dram_plot_prefetchers, 'dram')
        print_benchmark_stats_csv(cov_speedups, cov_plot_prefetchers, 'coverage')
        print_benchmark_stats_csv(acc_speedups, acc_plot_prefetchers, 'accuracy')
        print("="*80 + "\n")

    # Export benchmark statistics in data format if enabled
    if PRINT_BENCH_STATS:
        print("\n" + "="*80)
        print("EXPORT DATA")
        print("="*80)
        export_benchmark_stats_data(ipc_speedups, ipc_plot_prefetchers, 'ipc')
        export_benchmark_stats_data(dram_speedups, dram_plot_prefetchers, 'dram')
        export_benchmark_stats_data(cov_speedups, cov_plot_prefetchers, 'coverage')
        export_benchmark_stats_data(acc_speedups, acc_plot_prefetchers, 'accuracy')
        export_benchmark_stats_data(eog_speedups, acc_plot_prefetchers, 'eog')
        print("="*80 + "\n")

    # # Create all plots
    # print("Creating IPC plot...")
    # if PLOT_TRACE_IPC:
    #     create_plot(ipc_speedups, ipc_plot_prefetchers, 'ipc', 'IPC Speedup', 
    #                 f'{PLOT_NAME}_ipc_traces.{OUTPUT}', include_geomean=False, include_baseline=True, 
    #                 ylim_bottom=0.9, legend_position='top', plot_traces=True, trace_labels=ipc_trace_labels)
    # else:
    #     create_plot(ipc_speedups, ipc_plot_prefetchers, 'ipc', 'IPC Speedup', 
    #                 f'{PLOT_NAME}_ipc.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=True, 
    #                 ylim_bottom=0.98, only_geomean_bar=ONLY_GEOMEAN_BAR, legend_position='right')
    
    # print("Creating DRAM plot...")
    # create_plot(dram_speedups, dram_plot_prefetchers, 'dram', 'Normalized DRAM Traffic', 
    #             f'{PLOT_NAME}_dram.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=True, ylim_bottom=0.9, only_geomean_bar=ONLY_GEOMEAN_BAR, only_geomean_line=ONLY_GEOMEAN_LINE, legend_position='right')
    
    # print("Creating coverage plot...")
    # create_plot(cov_speedups, cov_plot_prefetchers, 'coverage', 'L1D Coverage', 
    #             f'{PLOT_NAME}_coverage.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=False, 
    #             ylim_bottom=0.0, only_geomean_bar=ONLY_GEOMEAN_BAR, legend_position='right')
    
    # print("Creating accuracy plot...")
    # create_plot(acc_speedups, acc_plot_prefetchers, 'accuracy', 'Accuracy', 
    #             f'{PLOT_NAME}_accuracy.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=False, 
    #             ylim_bottom=0.0, ylim_top=1.0, only_geomean_bar=ONLY_GEOMEAN_BAR, legend_position='right')
    

    print("Creating unified plot...")    
    print("Creating IPC plot...")
    if PLOT_TRACE_IPC:
        create_plot(ipc_speedups, ipc_plot_prefetchers, 'ipc', 'IPC Speedup', 
                    f'{PLOT_NAME}_ipc_traces.{OUTPUT}', include_geomean=False, include_baseline=True, 
                    ylim_bottom=0.9, legend_position='top', plot_traces=True, trace_labels=ipc_trace_labels)
    else:
        create_plot(ipc_speedups, ipc_plot_prefetchers, 'ipc', 'IPC Speedup', 
                    f'{PLOT_NAME}_ipc.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=True, 
                    ylim_bottom=0.9, only_geomean_bar=ONLY_GEOMEAN_BAR, legend_position='top')
    
    print("Creating DRAM plot...")
    if PLOT_TRACE_DRAM:
        create_plot(dram_speedups, dram_plot_prefetchers, 'dram', 'Normalized DRAM Traffic', 
                    f'{PLOT_NAME}_dram_traces.{OUTPUT}', include_geomean=False, include_baseline=True, 
                    ylim_bottom=0.9, legend_position='top', plot_traces=True, trace_labels=dram_trace_labels)
    else:
        create_plot(dram_speedups, dram_plot_prefetchers, 'dram', 'Normalized DRAM Traffic', 
                    f'{PLOT_NAME}_dram.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=True, ylim_bottom=0.9, only_geomean_bar=ONLY_GEOMEAN_BAR, only_geomean_line=ONLY_GEOMEAN_LINE, legend_position='top')
    
    print("Creating coverage plot...")
    create_plot(cov_speedups, cov_plot_prefetchers, 'coverage', 'LLC Coverage', 
                f'{PLOT_NAME}_coverage.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=False, 
                ylim_bottom=0.0, only_geomean_bar=ONLY_GEOMEAN_BAR, legend_position='top')
    
    print("Creating accuracy plot...")
    create_plot(acc_speedups, acc_plot_prefetchers, 'accuracy', 'Overall Accuracy', 
                f'{PLOT_NAME}_accuracy.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=False, 
                ylim_bottom=0.0, ylim_top=1.0, only_geomean_bar=ONLY_GEOMEAN_BAR, legend_position='top')
    
    print("All plots created successfully!")

if __name__ == "__main__":
    main() 