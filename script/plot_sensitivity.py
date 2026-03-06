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

# --- CONFIGURABLE ---
LOG_DIR = 'results'
GRAPH_DIR = 'graphs'
OUTPUT = "png"  # Use PNG for PowerPoint compatibility
PLOT_NAME = 'sensitivity'

# --- BENCHMARK TYPE SELECTION ---
# 'SPEC2017' - SPEC2017 benchmarks
# 'SPEC2006' - SPEC2006 benchmarks
# 'GAP' - GAP graph benchmarks
BENCHMARK_TYPE = 'SPEC2017'  # Change to 'GAP' for GAP benchmarks

# Select benchmarks based on type
if BENCHMARK_TYPE == 'GAP':
    BENCHMARKS = gap_ones
    BENCHMARK_WEIGHTS = GAP_SHORTCODE_WEIGHTS
else:
    if BENCHMARK_TYPE == 'SPEC2006':
        BENCHMARKS = spec2006_ones
    else:  # Default to SPEC2017
        BENCHMARKS = spec2017_ones
    BENCHMARK_WEIGHTS = SPEC2017_SHORTCODE_WEIGHTS
    # Remove specific problematic benchmarks for SPEC
    BENCHMARKS = [bm for bm in BENCHMARKS if bm != 'milc433']
    BENCHMARKS = [bm for bm in BENCHMARKS if bm != 'lbm470']
    BENCHMARKS = [bm for bm in BENCHMARKS if bm != 'gromacs435']
    BENCHMARKS = [bm for bm in BENCHMARKS if bm != 'exchange2648']

# Baseline configuration
BASELINE = 'caerus-no'

# --- SENSITIVITY STUDY CONFIGURATION ---
# Define your parameters and their variants here
# Each parameter should have: name, display_name, 0.5x variant, 2x variant

SENSITIVITY_PARAMS = [
    {
        'name': 'NUM_OFFSETS',
        'display_name': 'Number of Offsets',
        'baseline': BASELINE,  # caerus-no (20 offsets)
        'half': 'caerus-no_10offsets',  # 10 offsets
        'double': 'caerus-no_40offsets',  # 40 offsets
        'half_value': '10',
        'baseline_value': '20',
        'double_value': '40',
    },
    {
        'name': 'RR_SIZE',
        'display_name': 'Recent Requests Size',
        'baseline': BASELINE,  # caerus-no (16 RR_SIZE)
        'half': 'caerus-no_8rr_8entries',  # 8 RR_SIZE
        'double': 'caerus-no_32rr_8entries',  # 32 RR_SIZE
        'half_value': '8',
        'baseline_value': '16',
        'double_value': '32',
    },
    {
        'name': 'RR_ENTRY_SIZE',
        'display_name': 'RR Entry Size',
        'baseline': BASELINE,  # caerus-no (8 entries)
        'half': 'caerus-no_16rr_4entries',  # 4 entries
        'double': 'caerus-no_16rr_16entries',  # 16 entries
        'half_value': '4',
        'baseline_value': '8',
        'double_value': '16',
    },
]

# Plot configuration
INCLUDE_GEOMEAN = True
PLOT_WIDTH = 8
PLOT_HEIGHT = 5

# Color scheme for 0.5x, 1x, 2x
colors = ['#E57373', '#348ABD', '#467821']  # Red (0.5x), Blue (1x), Green (2x)

# --- PARSING FUNCTIONS ---

def _determine_cpu_str(path):
    parts = path.split(os.sep)
    prefetcher_dir = None
    if LOG_DIR in parts:
        idx = parts.index(LOG_DIR)
        if idx + 1 < len(parts):
            prefetcher_dir = parts[idx + 1]

    if not prefetcher_dir:
        return 'cpu0_L2C'

    if prefetcher_dir == 'no-no':
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
        return 'cpu0_L1D'

def parse_ipc_from_file(filepath):
    in_roi_section = False
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if "Region of Interest Statistics" in line:
                in_roi_section = True
            elif in_roi_section and line.startswith("CPU 0 cumulative IPC:"):
                parts = line.split()
                try:
                    return float(parts[4]) 
                except (IndexError, ValueError):
                    continue
    return None

def parse_dram_from_file(filepath):
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line.startswith("LLC TOTAL"):
                parts = line.split()
                try:
                    return float(parts[7]) 
                except (IndexError, ValueError):
                    continue
    return None

def parse_cov_from_file(filepath):
    cpu_str = _determine_cpu_str(filepath)
    if cpu_str is None:
        return None

    in_roi_section = False
    useful = None
    demand_misses = None
    
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if "Region of Interest Statistics" in line:
                in_roi_section = True
            elif in_roi_section and f"{cpu_str} PREFETCH REQUESTED:" in line:
                parts = line.split()
                useful = float(parts[7])
            elif in_roi_section and f"{cpu_str} LOAD" in line:
                parts = line.split()
                demand_misses = float(parts[7])
    
    if useful is not None and demand_misses is not None:
        return useful, demand_misses
    
    return None

def parse_acc_from_file(filepath):
    cpu_str = _determine_cpu_str(filepath)
    if cpu_str is None:
        return None

    in_roi_section = False
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if "Region of Interest Statistics" in line:
                in_roi_section = True
            elif in_roi_section and f"{cpu_str} PREFETCH REQUESTED:" in line:
                parts = line.split()
                return float(parts[7]), float(parts[9])
        
    return None

# --- DATA GATHERING FUNCTIONS ---
def gather_data(parse_func, prefetcher_list):
    """Generic function to gather data using the specified parsing function"""
    data = defaultdict(dict)
    
    for benchmark in BENCHMARKS:
        for prefetcher in prefetcher_list:
            path = os.path.join(LOG_DIR, prefetcher, benchmark)
            if not os.path.isdir(path):
                print(f"Missing directory: {path}")
                continue

            for filename in os.listdir(path):
                if filename.endswith('.txt'):
                    simpoint = filename.replace('.txt', '')
                    if re.match(r'^\d+\.', simpoint):
                        simpoint = simpoint[len(re.match(r'^\d+\.', simpoint).group(0)):]
                    filepath = os.path.join(path, filename)
                    result = parse_func(filepath)
                    if result is not None:
                        label = f"{benchmark}/{simpoint}"
                        data[prefetcher][label] = result
    
    return data

# --- COMPUTE WEIGHTED MEANS ---
def weighted_geomean(values, weights):
    log_sum = 0
    for v, w in zip(values, weights):
        if v <= 0:
            return 0.0
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
    
    This correctly answers: "If I run the whole workload (approximated by weighted simpoints),
    what is the speedup?" rather than "What is the expected speedup of a random simpoint?"
    """
    if not weights or not base_ipcs or not test_ipcs:
        return 0.0
    
    # Normalize weights to sum to 1
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    
    # Compute weighted sum of times (1/IPC) for baseline and test
    weighted_baseline_time = 0.0
    weighted_test_time = 0.0
    
    for base_ipc, test_ipc, w in zip(base_ipcs, test_ipcs, weights):
        if base_ipc <= 0 or test_ipc <= 0:
            return 0.0
        normalized_w = w / total_weight
        weighted_baseline_time += normalized_w / base_ipc
        weighted_test_time += normalized_w / test_ipc
    
    if weighted_test_time == 0:
        return 0.0
    
    return weighted_baseline_time / weighted_test_time

def compute_geomean_for_config(data, metric_type, prefetcher, baseline_name=None):
    """Compute correctly weighted speedup for a single configuration.
    
    For IPC: Uses harmonic mean of speedups (via weighted sum of times) within a benchmark.
    For other metrics: Uses arithmetic mean within benchmark.
    Then geometric mean across benchmarks.
    """
    geomean_by_benchmark = {}
    
    for benchmark in BENCHMARKS:
        weight_map = BENCHMARK_WEIGHTS.get(benchmark, {})
        simpoints = list(weight_map.keys())
        
        # For IPC, collect raw values
        base_ipcs = []
        test_ipcs = []
        ipc_weights = []
        
        # For other metrics, collect computed values
        values = []
        value_weights = []
        
        for sp in simpoints:
            # For SPEC traces: strip leading "600." prefix
            # For GAP traces: use as-is (e.g., "bc-0")
            if re.match(r'^\d+\.', sp):
                sp_name = sp[len(re.match(r'^\d+\.', sp).group(0)):]
            else:
                sp_name = sp
            
            label = f"{benchmark}/{sp_name}"
            
            if metric_type == 'ipc':
                base_value = data[baseline_name].get(label) if baseline_name else None
                test_value = data[prefetcher].get(label)
                if base_value and test_value and base_value > 0 and test_value > 0:
                    weight = weight_map[sp]
                    base_ipcs.append(base_value)
                    test_ipcs.append(test_value)
                    ipc_weights.append(weight)
            
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
                    if useful == 0:
                        continue
                    coverage = useful / (useful + demand_misses)
                    weight = weight_map[sp]
                    values.append(coverage)
                    value_weights.append(weight)
            
            elif metric_type == 'accuracy':
                acc_data = data[prefetcher].get(label)
                if acc_data:
                    useful, useless = acc_data
                    if useful == 0:
                        accuracy = 1.0
                    else:
                        accuracy = useful / (useful + useless)
                    weight = weight_map[sp]
                    values.append(accuracy)
                    value_weights.append(weight)
        
        # Compute aggregate for this benchmark
        if metric_type == 'ipc':
            if base_ipcs and test_ipcs and ipc_weights:
                geomean_by_benchmark[benchmark] = weighted_harmonic_mean_speedup(
                    base_ipcs, test_ipcs, ipc_weights)
            else:
                geomean_by_benchmark[benchmark] = 0.0
        else:
            if values and value_weights:
                geomean_by_benchmark[benchmark] = weighted_arithmetic_mean(values, value_weights)
            else:
                geomean_by_benchmark[benchmark] = 0.0
    
    # Compute overall geomean across benchmarks
    valid_values = [geomean_by_benchmark[bm] for bm in BENCHMARKS if geomean_by_benchmark[bm] > 0]
    if valid_values:
        log_sum = sum(math.log(v) for v in valid_values)
        overall_geo = math.exp(log_sum / len(valid_values))
    else:
        overall_geo = 0.0
    geomean_by_benchmark["geomean"] = overall_geo
    
    return geomean_by_benchmark

# --- PLOTTING FUNCTIONS ---
def setup_plot_style():
    plt.style.use('bmh')
    plt.rcParams['axes.prop_cycle'] = plt.cycler(color=colors)
    plt.rcParams.update({
        'font.size': 13,
        'axes.labelsize': 13,
        'xtick.labelsize': 12,
        'ytick.labelsize': 12,
        'legend.fontsize': 11
    })

def create_sensitivity_plot(all_results, metric_name, ylabel, filename, 
                           include_baseline=True, ylim_bottom=None, ylim_top=None):
    """Create sensitivity study plot showing all parameters"""
    setup_plot_style()
    
    fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))
    
    if include_baseline:
        ax.axhline(1.0, linestyle='--', color='gray', linewidth=1.5, label='Baseline (1x)', zorder=1)
    
    ax.grid(True, linestyle='--', alpha=0.5, axis='y', zorder=0)
    
    # X-axis: parameters
    x = np.arange(len(SENSITIVITY_PARAMS))
    bar_width = 0.25
    
    # For each parameter, plot 3 bars with actual parameter values
    for i, param_config in enumerate(SENSITIVITY_PARAMS):
        param_results = all_results[param_config['name']]
        
        # Get geomean values
        half_value = param_results['half']['geomean']
        baseline_value = param_results['baseline']['geomean']
        double_value = param_results['double']['geomean']
        
        # Plot bars
        ax.bar(x[i] - bar_width, half_value, width=bar_width, 
               color=colors[0], edgecolor='black', linewidth=1, zorder=2)
        ax.bar(x[i], baseline_value, width=bar_width, 
               color=colors[1], edgecolor='black', linewidth=1, zorder=2)
        ax.bar(x[i] + bar_width, double_value, width=bar_width, 
               color=colors[2], edgecolor='black', linewidth=1, zorder=2)
        
        # Add text labels below x-axis showing parameter values
        ax.text(x[i] - bar_width, -0.02, param_config['half_value'], 
                ha='center', va='top', fontsize=9, transform=ax.get_xaxis_transform())
        ax.text(x[i], -0.02, param_config['baseline_value'], 
                ha='center', va='top', fontsize=9, transform=ax.get_xaxis_transform())
        ax.text(x[i] + bar_width, -0.02, param_config['double_value'], 
                ha='center', va='top', fontsize=9, transform=ax.get_xaxis_transform())
    
    # Set x-axis labels
    ax.set_xticks(x)
    ax.set_xticklabels([p['display_name'] for p in SENSITIVITY_PARAMS])
    
    if ylim_bottom is not None:
        ax.set_ylim(bottom=ylim_bottom)
    if ylim_top is not None:
        ax.set_ylim(top=ylim_top)
    
    ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=10))
    ax.set_ylabel(ylabel, fontweight='bold')
    ax.set_xlabel("Parameter", fontweight='bold')
    
    # Add note about parameter values shown below bars
    ax.text(0.5, -0.15, 'Parameter values shown below each bar', 
            ha='center', va='top', fontsize=10, style='italic',
            transform=ax.transAxes)
    
    plt.tight_layout(pad=0.3)
    if not os.path.exists(GRAPH_DIR):
        os.makedirs(GRAPH_DIR)
    
    if OUTPUT == "pdf":
        plt.savefig(os.path.join(GRAPH_DIR, filename), format='pdf', bbox_inches='tight')
    elif OUTPUT == "png":
        plt.savefig(os.path.join(GRAPH_DIR, filename), format='png', dpi=300, bbox_inches='tight')
    plt.close()

# --- MAIN EXECUTION ---
def main():
    # Collect all unique prefetchers needed
    all_prefetchers = set([BASELINE])
    for param in SENSITIVITY_PARAMS:
        all_prefetchers.add(param['half'])
        all_prefetchers.add(param['double'])
    all_prefetchers = list(all_prefetchers)
    
    print("Gathering data for sensitivity study...")
    print(f"Prefetchers: {all_prefetchers}")
    print(f"Benchmarks: {BENCHMARKS}")
    
    # Gather all data
    print("\nGathering IPC data...")
    ipc_data = gather_data(parse_ipc_from_file, all_prefetchers)
    
    print("Gathering DRAM data...")
    dram_data = gather_data(parse_dram_from_file, all_prefetchers)
    
    print("Gathering coverage data...")
    cov_data = gather_data(parse_cov_from_file, all_prefetchers)
    
    print("Gathering accuracy data...")
    acc_data = gather_data(parse_acc_from_file, all_prefetchers)
    
    # Compute results for each parameter variation
    print("\n" + "="*80)
    print("COMPUTING SENSITIVITY RESULTS")
    print("="*80)
    
    ipc_results = {}
    dram_results = {}
    cov_results = {}
    acc_results = {}
    
    for param in SENSITIVITY_PARAMS:
        param_name = param['name']
        print(f"\n--- {param['display_name']} ({param_name}) ---")
        
        # Compute IPC
        ipc_results[param_name] = {
            'half': compute_geomean_for_config(ipc_data, 'ipc', param['half'], BASELINE),
            'baseline': compute_geomean_for_config(ipc_data, 'ipc', param['baseline'], BASELINE),
            'double': compute_geomean_for_config(ipc_data, 'ipc', param['double'], BASELINE),
        }
        print(f"IPC Speedup - 0.5x: {ipc_results[param_name]['half']['geomean']:.4f}, " +
              f"1x: {ipc_results[param_name]['baseline']['geomean']:.4f}, " +
              f"2x: {ipc_results[param_name]['double']['geomean']:.4f}")
        
        # Compute DRAM
        dram_results[param_name] = {
            'half': compute_geomean_for_config(dram_data, 'dram', param['half'], BASELINE),
            'baseline': compute_geomean_for_config(dram_data, 'dram', param['baseline'], BASELINE),
            'double': compute_geomean_for_config(dram_data, 'dram', param['double'], BASELINE),
        }
        print(f"DRAM Traffic - 0.5x: {dram_results[param_name]['half']['geomean']:.4f}, " +
              f"1x: {dram_results[param_name]['baseline']['geomean']:.4f}, " +
              f"2x: {dram_results[param_name]['double']['geomean']:.4f}")
        
        # Compute Coverage
        cov_results[param_name] = {
            'half': compute_geomean_for_config(cov_data, 'coverage', param['half'], None),
            'baseline': compute_geomean_for_config(cov_data, 'coverage', param['baseline'], None),
            'double': compute_geomean_for_config(cov_data, 'coverage', param['double'], None),
        }
        print(f"Coverage - 0.5x: {cov_results[param_name]['half']['geomean']:.4f}, " +
              f"1x: {cov_results[param_name]['baseline']['geomean']:.4f}, " +
              f"2x: {cov_results[param_name]['double']['geomean']:.4f}")
        
        # Compute Accuracy
        acc_results[param_name] = {
            'half': compute_geomean_for_config(acc_data, 'accuracy', param['half'], None),
            'baseline': compute_geomean_for_config(acc_data, 'accuracy', param['baseline'], None),
            'double': compute_geomean_for_config(acc_data, 'accuracy', param['double'], None),
        }
        print(f"Accuracy - 0.5x: {acc_results[param_name]['half']['geomean']:.4f}, " +
              f"1x: {acc_results[param_name]['baseline']['geomean']:.4f}, " +
              f"2x: {acc_results[param_name]['double']['geomean']:.4f}")
    
    print("\n" + "="*80)
    
    # Create plots
    print("\nCreating sensitivity plots...")
    
    print("Creating IPC sensitivity plot...")
    create_sensitivity_plot(ipc_results, 'ipc', 'IPC Speedup', 
                           f'{PLOT_NAME}_ipc.{OUTPUT}', 
                           include_baseline=True, ylim_bottom=0.95)
    
    print("Creating DRAM sensitivity plot...")
    create_sensitivity_plot(dram_results, 'dram', 'Normalized DRAM Traffic', 
                           f'{PLOT_NAME}_dram.{OUTPUT}', 
                           include_baseline=True, ylim_bottom=0.9)
    
    print("Creating coverage sensitivity plot...")
    create_sensitivity_plot(cov_results, 'coverage', 'L1D Coverage', 
                           f'{PLOT_NAME}_coverage.{OUTPUT}', 
                           include_baseline=False, ylim_bottom=0.0)
    
    print("Creating accuracy sensitivity plot...")
    create_sensitivity_plot(acc_results, 'accuracy', 'Accuracy', 
                           f'{PLOT_NAME}_accuracy.{OUTPUT}', 
                           include_baseline=False, ylim_bottom=0.0, ylim_top=1.0)
    
    print("\nAll sensitivity plots created successfully!")

if __name__ == "__main__":
    main()

