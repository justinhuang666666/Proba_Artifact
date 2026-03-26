import os
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np
import math
import re
import json

plt.style.use('default')

from _SPEC2017_def_memint import (
    SPEC2017_shortcode, spec2017_ones, spec2006_ones, memint2017_ones,
    memint2006_ones, memint_spec_ones, memint_SPEC_shortcode
)
from _SPEC_WEIGHTS import SPEC2017_SHORTCODE_WEIGHTS
from _GAP_def import GAP_shortcode, gap_ones
from _GAP_WEIGHTS import GAP_SHORTCODE_WEIGHTS

# --- CONFIGURABLE ---
LOG_DIR = os.path.join('results', 'json') 
GRAPH_DIR = 'graphs'
OUTPUT = "png"  # Use PNG for PowerPoint compatibility
PLOT_NAME = 'proba'

PRINT_BENCH_STATS = False

# --- IPC MEAN TYPE SELECTION ---
# 'geomean' - Use geometric mean for IPC speedups (traditional approach)
# 'harmonic' - Use harmonic mean for IPC speedups (time-weighted, more accurate for rates)
IPC_MEAN_TYPE = 'harmonic'

# --- BENCHMARK TYPE SELECTION ---
# 'SPEC2017' - SPEC2017 benchmarks
# 'SPEC2006' - SPEC2006 benchmarks  
# 'SPEC_ALL' - All SPEC benchmarks
# 'SPEC_MEMINT' - Only memory-intensive SPEC traces listed in workloads.py
# 'GAP' - GAP graph benchmarks
BENCHMARK_TYPE = 'SPEC_MEMINT'  # Change to 'SPEC_MEMINT' for memory-intensive SPEC traces

# Build safe weight maps for each SPEC subset.
def build_spec_weight_maps():
    try:
        from _SPEC_WEIGHTS import SPEC2006_SHORTCODE_WEIGHTS
    except ImportError:
        SPEC2006_SHORTCODE_WEIGHTS = None

    spec2006_weights = (
        SPEC2006_SHORTCODE_WEIGHTS
        if SPEC2006_SHORTCODE_WEIGHTS is not None
        else {k: v for k, v in SPEC2017_SHORTCODE_WEIGHTS.items() if k in spec2006_ones}
    )
    spec2017_weights = {k: v for k, v in SPEC2017_SHORTCODE_WEIGHTS.items() if k in spec2017_ones}
    spec_all_weights = dict(spec2006_weights)
    spec_all_weights.update(spec2017_weights)
    spec_memint_weights = {k: v for k, v in spec_all_weights.items() if k in memint_spec_ones}
    return spec2006_weights, spec2017_weights, spec_all_weights, spec_memint_weights

SPEC2006_WEIGHTS, SPEC2017_WEIGHTS, SPEC_ALL_WEIGHTS, SPEC_MEMINT_WEIGHTS = build_spec_weight_maps()

# Select benchmarks based on type
if BENCHMARK_TYPE == 'GAP':
    BENCHMARKS = gap_ones
    BENCHMARK_WEIGHTS = GAP_SHORTCODE_WEIGHTS
    BENCHMARK_SHORTCODE = GAP_shortcode
elif BENCHMARK_TYPE == 'SPEC2006':
    BENCHMARKS = spec2006_ones
    BENCHMARK_WEIGHTS = SPEC2006_WEIGHTS
    BENCHMARK_SHORTCODE = SPEC2017_shortcode
elif BENCHMARK_TYPE == 'SPEC_ALL':
    BENCHMARKS = list(SPEC2017_shortcode.keys())
    BENCHMARK_WEIGHTS = SPEC_ALL_WEIGHTS
    BENCHMARK_SHORTCODE = SPEC2017_shortcode
elif BENCHMARK_TYPE == 'SPEC_MEMINT':
    BENCHMARKS = memint_spec_ones
    BENCHMARK_WEIGHTS = SPEC_MEMINT_WEIGHTS
    BENCHMARK_SHORTCODE = memint_SPEC_shortcode
else:  # Default to SPEC2017
    BENCHMARKS = spec2017_ones
    BENCHMARK_WEIGHTS = SPEC2017_WEIGHTS
    BENCHMARK_SHORTCODE = SPEC2017_shortcode

# Keep exclusions explicit and empty by default for memory-intensive plots.
EXCLUDED_BENCHMARKS = set()
if BENCHMARK_TYPE != 'GAP' and EXCLUDED_BENCHMARKS:
    BENCHMARKS = [bm for bm in BENCHMARKS if bm not in EXCLUDED_BENCHMARKS]

BASELINE = 'no'

# ABLATION STUDY
# Match the directory names produced by simulate.py.
PREFETCHERS = [
    'l2_sms_eviction',
    'l2_bingo_eviction',
    'l2_dspatch_eviction',
    'l2_pmp_eviction',
    'l2_gaze_eviction',
    'l2_proba_eviction',
    'l2_proba_eog_jail_sampling_1',
    'l2_proba_eog_jail_sampling_1_calibration',
    'l2_proba_pmp_eog_jail_sampling_1',
]
if BASELINE not in PREFETCHERS:
    PREFETCHERS.append(BASELINE)

INCLUDE_GEOMEAN = True
PLOT_TRACE_IPC = False  # Plot raw IPC values from simpoints instead of geomean
ONLY_GEOMEAN_BAR = False
HIGHLIGHT_LAST = False

ONLY_GEOMEAN_LINE = False # BROKEN! 


PLOT_WIDTH = 20
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
        # Fallback 1: array embedded in text
        begin = content.find('[')
        end = content.rfind(']') + 1
        if begin != -1 and end > begin:
            return json.loads(content[begin:end])

        # Fallback 2: object embedded in text
        begin = content.find('{')
        end = content.rfind('}') + 1
        if begin != -1 and end > begin:
            return json.loads(content[begin:end])

        raise


def get_roi(file_path):
    json_obj = load_json_obj(file_path)

    # Reference code uses json_obj[0]['roi']
    if isinstance(json_obj, list):
        json_obj = json_obj[0]

    return json_obj.get('roi', {})


def normalize_trace_name(name):
    name = os.path.basename(name)
    name = re.sub(r'\.(json|txt)$', '', name)
    name = re.sub(r'\.champsimtrace(\.xz)?$', '', name)
    if re.match(r'^\d+\.', name):
        name = name.split('.', 1)[1]
    return name

# --- PARSING FUNCTIONS ---

def _determine_cpu_str(path):
    parts = path.split(os.sep)

    prefetcher_dir = None
    if 'json' in parts:
        idx = parts.index('json')
        if idx + 1 < len(parts):
            prefetcher_dir = parts[idx + 1]

    if not prefetcher_dir:
        return 'cpu0_L2C'

    if prefetcher_dir == 'no-no' or prefetcher_dir == 'no':
        return None

    comps = prefetcher_dir.split('-')
    if len(comps) >= 2:
        l1_pref, l2_pref = comps[0], comps[1]
        l2_is_no = l2_pref.startswith('no')
        l1_is_no = l1_pref.startswith('no')

        if not l2_is_no:
            return 'cpu0_L2C'
        elif not l1_is_no:
            return 'cpu0_L1D'
        else:
            return None
    else:
        # Single component prefetcher names like l2_bingo_eviction
        return 'cpu0_L2C'

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
    # Determine which cache level to use based on prefetcher configuration in the path

    cpu_str = _determine_cpu_str(filepath)

    # Skip paths where there is no prefetcher (e.g., no-no)
    if cpu_str is None:
        return None

    roi = get_roi(filepath)

    try:
        if cpu_str == 'cpu0_L1D':
            useful = roi[cpu_str]['prefetch useful']
            demand_misses = roi[cpu_str]['LOAD']['miss']

        elif cpu_str == 'cpu0_L2C':
            # Match reference code first if present, otherwise fall back
            useful = roi[cpu_str]['prefetch useful']
            demand_misses = roi[cpu_str]['LOAD']['miss']

        elif cpu_str == 'LLC':
            useful = roi[cpu_str].get('prefetch useful')
            demand_misses = roi[cpu_str]['LOAD']['miss']

        else:
            return None

        if useful is None or demand_misses is None:
            return None

        return float(useful), float(demand_misses)

    except (KeyError, IndexError, TypeError, ValueError):
        return None

def parse_acc_from_file(filepath):
    # Re-use the same helper logic as in parse_cov_from_file

    cpu_str = _determine_cpu_str(filepath)

    if cpu_str is None:
        return None

    roi = get_roi(filepath)

    try:
        if cpu_str == 'cpu0_L1D':
            useful = roi[cpu_str]['prefetch useful']
            useless = roi[cpu_str]['prefetch useless']

        elif cpu_str == 'cpu0_L2C':
            useful = roi[cpu_str]['prefetch useful']
            useless = roi[cpu_str]['prefetch useless']

        elif cpu_str == 'LLC':
            useful = roi[cpu_str]['prefetch useful']
            useless = roi[cpu_str]['prefetch useless']

        else:
            return None

        if useful is None or useless is None:
            return None

        return float(useful), float(useless)

    except (KeyError, IndexError, TypeError, ValueError):
        return None

# --- DATA GATHERING FUNCTIONS ---
# def gather_data(parse_func, metric_name):
#     """Generic function to gather data using the specified parsing function"""
#     data = defaultdict(dict)
    
#     for benchmark in BENCHMARKS:
#         for prefetcher in PREFETCHERS:
#             path = os.path.join(LOG_DIR, prefetcher, benchmark)
#             if not os.path.isdir(path):
#                 print(f"Missing directory: {path}")
#                 continue

#             for filename in os.listdir(path):
#                 if filename.endswith('.txt'):
#                     simpoint = filename.replace('.txt', '')
#                     # Quick and dirty hack, sorry Jacob :(
#                     if re.match(r'^\d+\.', simpoint):
#                         simpoint = simpoint[len(re.match(r'^\d+\.', simpoint).group(0)):]
#                     filepath = os.path.join(path, filename)
#                     result = parse_func(filepath)
#                     if result is not None:
#                         label = f"{benchmark}/{simpoint}"
#                         # Standardize prefetcher names for display
#                         display_name = prefetcher
#                         if prefetcher == 'bop':
#                             display_name = 'BOP'
#                         elif prefetcher == 'berti_stride':
#                             display_name = 'Berti'
#                         data[display_name][label] = result
    
#     return data

def gather_data(parse_func, metric_name):
    data = defaultdict(dict)

    for benchmark in BENCHMARKS:
        for prefetcher in PREFETCHERS:
            path = os.path.join(LOG_DIR, prefetcher, benchmark)   # now results/json/...

            if not os.path.isdir(path):
                print(f"Missing directory: {path}")
                continue

            for filename in os.listdir(path):
                if filename.endswith('.json'):
                    simpoint = normalize_trace_name(filename)

                    filepath = os.path.join(path, filename)
                    result = parse_func(filepath)

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
    """Compute correctly weighted speedups for different metric types.
    
    For IPC: Uses harmonic mean of speedups (via weighted sum of times) within a benchmark,
             then geometric mean across benchmarks.
    For other metrics: Uses arithmetic mean within benchmark, geometric mean across benchmarks.
    """
    geomean_speedups = defaultdict(dict)
    
    for benchmark in BENCHMARKS:
        weight_map = BENCHMARK_WEIGHTS.get(benchmark, {})
        allowed_simpoints = set(BENCHMARK_SHORTCODE.get(benchmark, weight_map.keys()))
        simpoints = [sp for sp in weight_map.keys() if sp in allowed_simpoints]
        
        # Get display names for prefetchers. For coverage/accuracy we skip the baseline ("no-no").
        display_prefetchers = []
        for p in PREFETCHERS:
            # Optionally skip baseline for non-relative metrics
            if p == baseline_name and metric_type in ['coverage', 'accuracy']:
                continue
            else:
                display_prefetchers.append(p)
        
        for prefetcher in display_prefetchers:
            # For IPC, we need to collect raw IPC values to compute harmonic mean properly
            base_ipcs = []
            test_ipcs = []
            weights = []
            
            # For other metrics, we collect the computed values
            values = []
            value_weights = []
            
            for sp in simpoints:
                sp_name = normalize_trace_name(sp)
                label = f"{benchmark}/{sp_name}"
                
                if metric_type == 'ipc':
                    base_value = data[baseline_name].get(label) if baseline_name else None
                    test_value = data[prefetcher].get(label)
                    if base_value and test_value and base_value > 0 and test_value > 0:
                        weight = weight_map[sp]
                        base_ipcs.append(base_value)
                        test_ipcs.append(test_value)
                        weights.append(weight)
                
                elif metric_type == 'dram':
                    base_value = data[baseline_name].get(label) if baseline_name else None
                    test_value = data[prefetcher].get(label)
                    if base_value and test_value:
                        ratio = test_value / base_value
                        weight = weight_map[sp]
                        values.append(ratio)
                        value_weights.append(weight)
                
                elif metric_type == 'coverage':
                    cov_data = data[prefetcher].get(label)
                    if cov_data:
                        useful, demand_misses = cov_data
                        coverage = useful / (useful + demand_misses)
                        weight = weight_map[sp]
                        values.append(coverage)
                        value_weights.append(weight)
                
                elif metric_type == 'accuracy':
                    acc_data = data[prefetcher].get(label)
                    if acc_data:
                        useful, useless = acc_data
                        if useful == 0:
                            accuracy = 1.0  # No prefetches issued
                        else:
                            accuracy = useful / (useful + useless)
                        weight = weight_map[sp]
                        values.append(accuracy)
                        value_weights.append(weight)
            
            # Compute the aggregate value for this benchmark
            if metric_type == 'ipc':
                if base_ipcs and test_ipcs and weights:
                    # Use the selected mean type for IPC speedups
                    if IPC_MEAN_TYPE == 'harmonic':
                        geomean_speedups[prefetcher][benchmark] = weighted_harmonic_mean_speedup(
                            base_ipcs, test_ipcs, weights)
                    else:  # geomean
                        geomean_speedups[prefetcher][benchmark] = weighted_geomean_speedup(
                            base_ipcs, test_ipcs, weights)
                else:
                    print(f"Incomplete data for benchmark: {benchmark} prefetcher: {prefetcher}")
                    geomean_speedups[prefetcher][benchmark] = 0.0
            else:
                if values and value_weights:
                    # Use weighted arithmetic mean for DRAM, coverage, accuracy
                    geomean_speedups[prefetcher][benchmark] = weighted_arithmetic_mean(values, value_weights)
                else:
                    print(f"Incomplete data for benchmark: {benchmark} prefetcher: {prefetcher}")
                    geomean_speedups[prefetcher][benchmark] = 0.0
    
    # Compute overall geomean across benchmarks (geometric mean is appropriate here
    # since benchmarks are different workloads, not weighted parts of the same workload)
    plot_prefetchers = [p for p in display_prefetchers if p != baseline_name] if baseline_name else display_prefetchers
    
    for prefetcher in plot_prefetchers:
        values = [geomean_speedups[prefetcher][bm] for bm in BENCHMARKS if geomean_speedups[prefetcher][bm] > 0]
        if values:
            log_sum = sum(math.log(v) for v in values)
            overall_geo = math.exp(log_sum / len(values))
        else:
            overall_geo = 0.0
        geomean_speedups[prefetcher]["geomean"] = overall_geo
    
    return geomean_speedups, plot_prefetchers

def compute_trace_speedups(data, metric_type, baseline_name=None):
    """Compute speedups for individual simpoints (traces) instead of geomean across benchmarks"""
    trace_speedups = defaultdict(dict)
    all_trace_labels = []
    
    for benchmark in BENCHMARKS:
        weight_map = BENCHMARK_WEIGHTS.get(benchmark, {})
        allowed_simpoints = set(BENCHMARK_SHORTCODE.get(benchmark, weight_map.keys()))
        simpoints = [sp for sp in weight_map.keys() if sp in allowed_simpoints]
        
        # Get display names for prefetchers
        display_prefetchers = []
        for p in PREFETCHERS:
            if p == baseline_name and metric_type in ['coverage', 'accuracy']:
                continue
            else:
                display_prefetchers.append(p)
        
        for sp in simpoints:
            sp_name = normalize_trace_name(sp)
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
        'legend.fontsize': 8
    })

def print_benchmark_stats_csv(geomean_speedups, plot_prefetchers, metric_name):
    """Print per-benchmark statistics in CSV format"""
    print(f"\n{metric_name.upper()} Benchmark Statistics (CSV):")
    
    # Print header
    header = "# " + ", ".join(plot_prefetchers)
    print(header)
    
    # Print each benchmark
    for benchmark in BENCHMARKS:
        values = []
        for prefetcher in plot_prefetchers:
            value = geomean_speedups[prefetcher].get(benchmark, 0.0)
            values.append(f"{value:.4f}")
        print(f"{benchmark}, " + ", ".join(values))
    
    # Print geomean row
    geomean_values = []
    for prefetcher in plot_prefetchers:
        value = geomean_speedups[prefetcher].get("geomean", 0.0)
        geomean_values.append(f"{value:.4f}")
    print(f"geomean, " + ", ".join(geomean_values))

def create_plot(geomean_speedups, plot_prefetchers, metric_name, ylabel, filename, 
                include_geomean=True, include_baseline=True, ylim_bottom=None, ylim_top=None, 
                legend_position='right', only_geomean_bar=False, only_geomean_line=False, 
                plot_traces=False, trace_labels=None):
    """Generic plotting function"""
    setup_plot_style()

    # Create a new list of prefetchers with the display names
    display_prefetchers = []
    # Change the names of the prefetchers to the display names
    for prefetcher in plot_prefetchers:
        if prefetcher == 'l2_sms_eviction':
            display_prefetchers.append('L2 SMS')
        elif prefetcher == 'l2_bingo_eviction':
            display_prefetchers.append('L2 Bingo')
        elif prefetcher == 'l2_dspatch_eviction':
            display_prefetchers.append('L2 DSPatch')
        elif prefetcher == 'l2_pmp_eviction':
            display_prefetchers.append('L2 PMP')
        elif prefetcher == 'l2_gaze_eviction':
            display_prefetchers.append('L2 Gaze')
        elif prefetcher == 'l2_proba_eviction':
            display_prefetchers.append('L2 Proba')
        elif prefetcher == 'l2_proba_eog_jail_sampling_1':
            display_prefetchers.append('L2 Proba EOG Jail Sampling')
        elif prefetcher == 'l2_proba_eog_jail_sampling_1_calibration':
            display_prefetchers.append('L2 Proba EOG Jail Sampling Calibration')
        elif prefetcher == 'l2_proba_pmp_eog_jail_sampling_1':
            display_prefetchers.append('L2 Proba+PMP EOG Jail Sampling')
        else:
            display_prefetchers.append(prefetcher)
    
    if plot_traces and trace_labels:
        # Create trace plot showing individual simpoint results
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))
        
        if include_baseline:
            ax.axhline(1.0, linestyle='-', color='black', linewidth=1, label='Baseline')
        
        ax.grid(True, linestyle='--', alpha=0.7, axis='y', zorder=0)
        
        x = np.arange(len(trace_labels))
        bar_width = 0.8 / len(plot_prefetchers)
        
        for i, prefetcher in enumerate(plot_prefetchers):
            heights = [geomean_speedups[prefetcher].get(label, 0.0) for label in trace_labels]
            offsets = x + i * bar_width
            
            # Determine edge color based on HIGHLIGHT_LAST setting
            edge_color = 'black'
            line_width = 0.5
            if HIGHLIGHT_LAST and i == len(plot_prefetchers) - 1:
                edge_color = 'black'
                line_width = 1
            
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
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.07), ncol=len(plot_prefetchers), 
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
            line_width = 0.5
            if HIGHLIGHT_LAST and i == len(plot_prefetchers) - 1:
                edge_color = 'black'
                line_width = 1
            
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
        bar_width = 0.8 / len(plot_prefetchers)
        
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))
        
        if include_baseline:
            ax.axhline(1.0, linestyle='-', color='black', linewidth=1, label='Baseline')
        
        ax.grid(True, linestyle='--', alpha=0.7, axis='y', zorder=0)
        
        for i, prefetcher in enumerate(plot_prefetchers):
            heights = [geomean_speedups[prefetcher].get(bm, 0.0) for bm in all_labels]
            offsets = x + i * bar_width
            
            # Determine edge color based on HIGHLIGHT_LAST setting
            edge_color = 'black'
            line_width = 0.5
            if HIGHLIGHT_LAST and i == len(plot_prefetchers) - 1:
                edge_color = 'black'
                line_width = 1
            
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
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.07), ncol=9, 
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
    # Gather all data
    print("Gathering IPC data...")
    ipc_data = gather_data(parse_ipc_from_file, 'ipc')
    
    print("Gathering DRAM data...")
    dram_data = gather_data(parse_dram_from_file, 'dram')
    
    print("Gathering coverage data...")
    cov_data = gather_data(parse_cov_from_file, 'coverage')
    
    print("Gathering accuracy data...")
    acc_data = gather_data(parse_acc_from_file, 'accuracy')

    print("Available data summary:")
    for prefetcher in PREFETCHERS:
        count = len(ipc_data.get(prefetcher, {}))
        print(f"  {prefetcher}: {count} IPC files matched")
    
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

    print("Computing DRAM traffic...")
    dram_speedups, dram_plot_prefetchers = compute_geomean_speedups(dram_data, 'dram', BASELINE)
    # print("DRAM speedups:", dict(dram_speedups))
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
    create_plot(dram_speedups, dram_plot_prefetchers, 'dram', 'Normalized DRAM Traffic', 
                f'{PLOT_NAME}_dram.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=True, ylim_bottom=0.9, only_geomean_bar=ONLY_GEOMEAN_BAR, only_geomean_line=ONLY_GEOMEAN_LINE, legend_position='top')
    
    print("Creating coverage plot...")
    create_plot(cov_speedups, cov_plot_prefetchers, 'coverage', 'L2C Coverage', 
                f'{PLOT_NAME}_coverage.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=False, 
                ylim_bottom=0.0, only_geomean_bar=ONLY_GEOMEAN_BAR, legend_position='top')
    
    print("Creating accuracy plot...")
    create_plot(acc_speedups, acc_plot_prefetchers, 'accuracy', 'Accuracy', 
                f'{PLOT_NAME}_accuracy.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN, include_baseline=False, 
                ylim_bottom=0.0, ylim_top=1.0, only_geomean_bar=ONLY_GEOMEAN_BAR, legend_position='top')
    
    print("All plots created successfully!")

if __name__ == "__main__":
    main() 