#!/usr/bin/env python3
"""
Plotting script for multicore ChampSim simulations.
Computes geometric mean of IPC across all cores for each mix.
"""

import os
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np
import math
import re

plt.style.use('default')

# --- CONFIGURABLE ---
LOG_DIR = 'results_multicore'
GRAPH_DIR = 'graphs'
OUTPUT = "png"  # Use PNG for PowerPoint compatibility
PLOT_NAME = 'multicore_cloudsuite'
NUM_CORES = 4  # Number of cores in the simulation

PRINT_BENCH_STATS = False

# --- IPC MEAN TYPE SELECTION ---
# 'geomean' - Use geometric mean for IPC speedups (traditional approach)
# 'harmonic' - Use harmonic mean for IPC speedups (time-weighted, more accurate for rates)
IPC_MEAN_TYPE = 'harmonic'

# --- BENCHMARK TYPE SELECTION ---
# 'SPEC' - Random SPEC benchmark mixes (mix_000_4core.txt, mix_001_4core.txt, ...)
# 'CLOUDSUITE' - CloudSuite phase-based mixes (cassandra_phase0_4core.txt, ...)
# 'GAP' - GAP benchmark mixes (bc-0_4core.txt, bfs-10_4core.txt, ...)
BENCHMARK_TYPE = 'SPEC'  # Change to 'CLOUDSUITE', 'GAP', or 'SPEC' for different workloads

# If True and BENCHMARK_TYPE is CLOUDSUITE, group results by application and compute geomean across phases
GROUP_CLOUDSUITE_BY_APP = True

# Prefetcher configurations to compare
BASELINE = 'no-no'
PREFETCHERS = ['berti-no', 'mlop-no', 'caerus-no']

if BASELINE not in PREFETCHERS:
    PREFETCHERS.append(BASELINE)

INCLUDE_GEOMEAN = True
ONLY_GEOMEAN_BAR = False
HIGHLIGHT_LAST = False

# If True, exclude mixes where any prefetcher is missing results
# This ensures all prefetchers are compared on the same set of mixes
REQUIRE_ALL_PREFETCHERS = False

PLOT_WIDTH = 16
PLOT_HEIGHT = 6

if ONLY_GEOMEAN_BAR:
    PLOT_WIDTH = 4
    PLOT_HEIGHT = 6

# Color scheme
blues = ['#348ABD', '#F8B6B6', '#E57373', '#B53636', '#A60628']

# --- CLOUDSUITE GROUPING FUNCTIONS ---

def extract_cloudsuite_app(mix_name):
    """Extract the application name from a CloudSuite mix name.
    E.g., 'cassandra_phase0_4core' -> 'cassandra'
    """
    match = re.match(r'^([a-zA-Z0-9]+)_phase\d+', mix_name)
    if match:
        return match.group(1)
    return mix_name


def get_cloudsuite_apps(mix_names):
    """Get unique CloudSuite application names from mix names, preserving order."""
    seen = set()
    apps = []
    for mix_name in mix_names:
        app = extract_cloudsuite_app(mix_name)
        if app not in seen:
            seen.add(app)
            apps.append(app)
    return apps


def group_by_cloudsuite_app(data, mix_names, metric_type='ipc'):
    """Group data by CloudSuite application and compute mean across phases.
    
    For IPC: Uses harmonic mean across phases because IPC is a rate (instructions/cycle).
             When combining phases of the same workload, harmonic mean gives the correct
             overall IPC as if running all phases together.
    For other metrics: Uses geometric mean (ratios) or arithmetic mean (coverage/accuracy).
    
    Args:
        data: dict of {prefetcher: {mix_name: value}}
        mix_names: list of mix names
        metric_type: 'ipc', 'dram', 'coverage', or 'accuracy'
    
    Returns:
        grouped_data: dict of {prefetcher: {app_name: aggregated_value}}
        app_names: list of unique application names
    """
    app_names = get_cloudsuite_apps(mix_names)
    grouped_data = defaultdict(dict)
    
    for prefetcher, mix_values in data.items():
        for app in app_names:
            # Collect all phase values for this app
            phase_values = []
            for mix_name, value in mix_values.items():
                if extract_cloudsuite_app(mix_name) == app and value is not None and value > 0:
                    phase_values.append(value)
            
            if phase_values:
                if metric_type == 'ipc':
                    # Use harmonic mean for IPC (rate metric)
                    # Harmonic mean of IPC values gives the correct combined IPC
                    # when phases represent parts of the same workload
                    grouped_data[prefetcher][app] = compute_harmonic_mean(phase_values)
                elif metric_type in ['coverage', 'accuracy']:
                    # Use arithmetic mean for percentages/proportions
                    grouped_data[prefetcher][app] = sum(phase_values) / len(phase_values)
                else:
                    # Use geometric mean for ratios (dram, etc.)
                    grouped_data[prefetcher][app] = compute_geomean(phase_values)
            else:
                grouped_data[prefetcher][app] = 0.0
    
    return grouped_data, app_names


# --- PARSING FUNCTIONS ---

def parse_multicore_ipc_from_file(filepath, num_cores=4):
    """
    Parse IPC values for all cores from a multicore simulation result file.
    Returns a list of IPC values for each core, or None if parsing fails.
    """
    in_roi_section = False
    ipc_values = {}
    
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if "Region of Interest Statistics" in line:
                in_roi_section = True
                continue
            
            if in_roi_section:
                # Match lines like "CPU 0 cumulative IPC: 0.2918 instructions: ..."
                match = re.match(r'CPU (\d+) cumulative IPC: ([\d.]+)', line)
                if match:
                    cpu_id = int(match.group(1))
                    ipc = float(match.group(2))
                    ipc_values[cpu_id] = ipc
    
    # Check if we got all cores
    if len(ipc_values) >= num_cores:
        return [ipc_values[i] for i in range(num_cores)]
    
    return None


def compute_geomean(values):
    """Compute geometric mean of a list of values."""
    if not values or any(v <= 0 for v in values):
        return 0.0
    log_sum = sum(math.log(v) for v in values)
    return math.exp(log_sum / len(values))


def compute_harmonic_mean(values):
    """Compute harmonic mean of a list of values.
    
    For IPC values, harmonic mean is appropriate because it correctly combines
    rates when aggregating across phases/simpoints of the same workload.
    Harmonic mean of IPCs = n / sum(1/IPC_i) = n / sum(time_i per instruction)
    """
    if not values or any(v <= 0 for v in values):
        return 0.0
    return len(values) / sum(1.0 / v for v in values)


def compute_harmonic_mean_speedup(base_values, test_values):
    """
    Compute speedup using harmonic mean of times (inverse of IPC).
    
    This computes: sum(1/base_ipc) / sum(1/test_ipc) = total_base_time / total_test_time
    
    This correctly answers: "If I run all these workloads, what is the overall speedup?"
    """
    if not base_values or not test_values:
        return 0.0
    if any(v <= 0 for v in base_values) or any(v <= 0 for v in test_values):
        return 0.0
    
    total_base_time = sum(1.0 / v for v in base_values)
    total_test_time = sum(1.0 / v for v in test_values)
    
    if total_test_time == 0:
        return 0.0
    
    return total_base_time / total_test_time


def compute_geomean_speedup(base_values, test_values):
    """
    Compute speedup using geometric mean of individual speedups.
    
    This computes the geometric mean of (test_ipc / base_ipc) for each workload.
    """
    if not base_values or not test_values or len(base_values) != len(test_values):
        return 0.0
    
    speedups = []
    for base, test in zip(base_values, test_values):
        if base <= 0 or test <= 0:
            return 0.0
        speedups.append(test / base)
    
    return compute_geomean(speedups)


def parse_multicore_dram_from_file(filepath):
    """Parse total DRAM accesses from multicore simulation."""
    total_dram = 0
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line.startswith("LLC TOTAL"):
                parts = line.split()
                try:
                    total_dram += float(parts[7])  # MISS count
                except (IndexError, ValueError):
                    continue
    return total_dram if total_dram > 0 else None


def _determine_cpu_str_multicore(path, cpu_id=0):
    """Determine which cache level to look at for prefetcher stats."""
    parts = path.split(os.sep)

    # Extract the prefetcher directory
    prefetcher_dir = None
    if LOG_DIR in parts:
        idx = parts.index(LOG_DIR)
        if idx + 1 < len(parts):
            prefetcher_dir = parts[idx + 1]

    if not prefetcher_dir:
        return f'cpu{cpu_id}_L2C'

    if prefetcher_dir == 'no-no':
        return None

    comps = prefetcher_dir.split('-')
    if len(comps) >= 2:
        l1_pref, l2_pref = comps[0], comps[1]
        l2_is_no = l2_pref.startswith('no')
        l1_is_no = l1_pref.startswith('no')
        
        if not l2_is_no:
            return f'cpu{cpu_id}_L2C'
        elif not l1_is_no:
            return f'cpu{cpu_id}_L1D'
        else:
            return None
    else:
        return f'cpu{cpu_id}_L1D'


def parse_multicore_coverage_from_file(filepath, num_cores=4):
    """Parse coverage data for all cores."""
    in_roi_section = False
    coverage_data = {}
    
    for cpu_id in range(num_cores):
        cpu_str = _determine_cpu_str_multicore(filepath, cpu_id)
        if cpu_str is None:
            continue
        
        useful = None
        demand_misses = None
        
        with open(filepath) as f:
            in_roi_section = False
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
            coverage_data[cpu_id] = (useful, demand_misses)
    
    if coverage_data:
        return coverage_data
    return None


def parse_multicore_accuracy_from_file(filepath, num_cores=4):
    """Parse accuracy data for all cores."""
    in_roi_section = False
    accuracy_data = {}
    
    for cpu_id in range(num_cores):
        cpu_str = _determine_cpu_str_multicore(filepath, cpu_id)
        if cpu_str is None:
            continue
        
        with open(filepath) as f:
            in_roi_section = False
            for line in f:
                line = line.strip()
                if "Region of Interest Statistics" in line:
                    in_roi_section = True
                elif in_roi_section and f"{cpu_str} PREFETCH REQUESTED:" in line:
                    parts = line.split()
                    accuracy_data[cpu_id] = (float(parts[7]), float(parts[9]))  # USEFUL, USELESS
                    break
    
    if accuracy_data:
        return accuracy_data
    return None


# --- DATA GATHERING FUNCTIONS ---

def get_mix_files(prefetcher):
    """Get all mix result files for a prefetcher, filtered by BENCHMARK_TYPE."""
    mix_dir = os.path.join(LOG_DIR, prefetcher, f'mixes_{NUM_CORES}core')
    if not os.path.isdir(mix_dir):
        return []
    
    files = []
    for filename in os.listdir(mix_dir):
        if not filename.endswith('.txt'):
            continue
        
        # Filter based on benchmark type
        if BENCHMARK_TYPE == 'SPEC':
            # SPEC mixes are named like mix_000_4core.txt
            if filename.startswith('mix_'):
                files.append(os.path.join(mix_dir, filename))
        elif BENCHMARK_TYPE == 'CLOUDSUITE':
            # CloudSuite mixes are named like cassandra_phase0_4core.txt
            # They do NOT start with 'mix_' and are not GAP benchmarks
            if not filename.startswith('mix_') and not any(filename.startswith(gap) for gap in ['bc-', 'bfs-', 'cc-', 'pr-', 'sssp-']):
                files.append(os.path.join(mix_dir, filename))
        elif BENCHMARK_TYPE == 'GAP':
            # GAP mixes are named like bc-0_4core.txt, bfs-10_4core.txt, etc.
            if any(filename.startswith(gap) for gap in ['bc-', 'bfs-', 'cc-', 'pr-', 'sssp-']):
                files.append(os.path.join(mix_dir, filename))
        else:
            # Include all files if BENCHMARK_TYPE is not recognized
            files.append(os.path.join(mix_dir, filename))
    
    return sorted(files)


def gather_multicore_data():
    """Gather IPC data from all multicore simulation results."""
    data = defaultdict(dict)
    
    # Get all mix names from baseline
    baseline_files = get_mix_files(BASELINE)
    mix_names = [os.path.basename(f).replace('.txt', '') for f in baseline_files]
    
    for prefetcher in PREFETCHERS:
        mix_files = get_mix_files(prefetcher)
        
        for filepath in mix_files:
            mix_name = os.path.basename(filepath).replace('.txt', '')
            ipc_values = parse_multicore_ipc_from_file(filepath, NUM_CORES)
            
            if ipc_values:
                # Compute geometric mean of all core IPCs
                geomean_ipc = compute_geomean(ipc_values)
                data[prefetcher][mix_name] = geomean_ipc
            else:
                print(f"Warning: Could not parse IPC from {filepath}")
    
    # Filter out mixes where any prefetcher is missing results
    if REQUIRE_ALL_PREFETCHERS:
        filtered_mix_names = []
        excluded_mixes = []
        for mix_name in mix_names:
            has_all = all(mix_name in data[p] for p in PREFETCHERS)
            if has_all:
                filtered_mix_names.append(mix_name)
            else:
                excluded_mixes.append(mix_name)
                missing_prefetchers = [p for p in PREFETCHERS if mix_name not in data[p]]
                print(f"Excluding {mix_name}: missing data from {', '.join(missing_prefetchers)}")
        
        if excluded_mixes:
            print(f"Excluded {len(excluded_mixes)} mixes due to missing prefetcher results")
        mix_names = filtered_mix_names
    
    return data, mix_names


def gather_multicore_dram_data():
    """Gather DRAM data from all multicore simulation results."""
    data = defaultdict(dict)
    
    for prefetcher in PREFETCHERS:
        mix_files = get_mix_files(prefetcher)
        
        for filepath in mix_files:
            mix_name = os.path.basename(filepath).replace('.txt', '')
            dram_value = parse_multicore_dram_from_file(filepath)
            
            if dram_value:
                data[prefetcher][mix_name] = dram_value
    
    return data


def gather_multicore_coverage_data():
    """Gather coverage data from all multicore simulation results."""
    data = defaultdict(dict)
    
    for prefetcher in PREFETCHERS:
        if prefetcher == BASELINE:
            continue
            
        mix_files = get_mix_files(prefetcher)
        
        for filepath in mix_files:
            mix_name = os.path.basename(filepath).replace('.txt', '')
            cov_data = parse_multicore_coverage_from_file(filepath, NUM_CORES)
            
            if cov_data:
                # Aggregate coverage across all cores
                total_useful = sum(c[0] for c in cov_data.values())
                total_misses = sum(c[1] for c in cov_data.values())
                if total_useful > 0:
                    coverage = total_useful / (total_useful + total_misses)
                    data[prefetcher][mix_name] = coverage
    
    return data


def gather_multicore_accuracy_data():
    """Gather accuracy data from all multicore simulation results."""
    data = defaultdict(dict)
    
    for prefetcher in PREFETCHERS:
        if prefetcher == BASELINE:
            continue
            
        mix_files = get_mix_files(prefetcher)
        
        for filepath in mix_files:
            mix_name = os.path.basename(filepath).replace('.txt', '')
            acc_data = parse_multicore_accuracy_from_file(filepath, NUM_CORES)
            
            if acc_data:
                # Aggregate accuracy across all cores
                total_useful = sum(a[0] for a in acc_data.values())
                total_useless = sum(a[1] for a in acc_data.values())
                if total_useful + total_useless > 0:
                    accuracy = total_useful / (total_useful + total_useless)
                    data[prefetcher][mix_name] = accuracy
    
    return data


# --- COMPUTE SPEEDUPS ---

def compute_speedups(data, mix_names, baseline_name, metric_type='ipc'):
    """Compute speedups relative to baseline for each mix and overall mean.
    
    For IPC, uses IPC_MEAN_TYPE setting to determine whether to use
    geometric mean or harmonic mean for the overall speedup.
    """
    speedups = defaultdict(dict)
    
    plot_prefetchers = [p for p in PREFETCHERS if p != baseline_name]
    
    for prefetcher in plot_prefetchers:
        valid_base_values = []
        valid_test_values = []
        
        for mix_name in mix_names:
            base_value = data[baseline_name].get(mix_name)
            test_value = data[prefetcher].get(mix_name)
            
            if base_value and test_value and base_value > 0:
                speedup = test_value / base_value
                speedups[prefetcher][mix_name] = speedup
                valid_base_values.append(base_value)
                valid_test_values.append(test_value)
            else:
                speedups[prefetcher][mix_name] = 0.0
        
        # Compute overall mean based on IPC_MEAN_TYPE setting (for IPC metric)
        if valid_base_values and valid_test_values:
            if metric_type == 'ipc' and IPC_MEAN_TYPE == 'harmonic':
                # Harmonic mean speedup: sum(1/base) / sum(1/test)
                speedups[prefetcher]["geomean"] = compute_harmonic_mean_speedup(
                    valid_base_values, valid_test_values)
            else:
                # Geometric mean of individual speedups (default)
                speedups[prefetcher]["geomean"] = compute_geomean_speedup(
                    valid_base_values, valid_test_values)
        else:
            speedups[prefetcher]["geomean"] = 0.0
    
    return speedups, plot_prefetchers


def compute_absolute_metrics(data, mix_names, baseline_name=None):
    """Compute absolute metrics (coverage, accuracy) with geomean."""
    metrics = defaultdict(dict)
    
    plot_prefetchers = [p for p in PREFETCHERS if p != baseline_name]
    
    for prefetcher in plot_prefetchers:
        valid_values = []
        
        for mix_name in mix_names:
            value = data[prefetcher].get(mix_name)
            
            if value is not None:
                metrics[prefetcher][mix_name] = value
                valid_values.append(value)
            else:
                metrics[prefetcher][mix_name] = 0.0
        
        # Compute arithmetic mean for coverage/accuracy
        if valid_values:
            metrics[prefetcher]["geomean"] = sum(valid_values) / len(valid_values)
        else:
            metrics[prefetcher]["geomean"] = 0.0
    
    return metrics, plot_prefetchers


# --- PLOTTING FUNCTIONS ---

def setup_plot_style():
    plt.style.use('bmh')
    plt.rcParams.update({
        'font.size': 12,
        'axes.labelsize': 12,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'legend.fontsize': 10
    })


def get_display_name(prefetcher):
    """Convert prefetcher name to display name."""
    name_map = {
        'no-bop': 'BOP',
        'bop-no': 'BOP',
        'berti-no': 'Berti',
        'ip_stride-no': 'Stride',
        'mlop-no': 'MLOP',
        'caerus-no': 'Caerus',
        'chimera-no': 'Chimera',
    }
    return name_map.get(prefetcher, prefetcher)


def create_plot(speedups, plot_prefetchers, mix_names, metric_name, ylabel, filename,
                include_geomean=True, include_baseline=True, ylim_bottom=None, ylim_top=None,
                only_geomean_bar=False):
    """Create bar plot for multicore results."""
    setup_plot_style()
    
    display_prefetchers = [get_display_name(p) for p in plot_prefetchers]
    
    if only_geomean_bar:
        # Create bar plot for geomean only
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))
        
        if include_baseline:
            ax.axhline(1.0, linestyle='-', color='black', linewidth=1, label='Baseline')
        
        ax.grid(True, linestyle='--', alpha=0.7, axis='y', zorder=0)
        ax.xaxis.grid(False)
        
        x_positions = np.arange(len(plot_prefetchers))
        geomean_values = [speedups[prefetcher].get("geomean", 0.0) for prefetcher in plot_prefetchers]
        
        for i, (x, val) in enumerate(zip(x_positions, geomean_values)):
            edge_color = 'black'
            line_width = 2 if HIGHLIGHT_LAST and i == len(plot_prefetchers) - 1 else 1
            ax.bar(x, val, width=0.5, edgecolor=edge_color, linewidth=line_width)
        
        ax.set_xticks(x_positions)
        ax.set_xticklabels(display_prefetchers, rotation=45, ha='right')
        
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
        # Create full bar plot with all mixes
        all_labels = mix_names + (["geomean"] if include_geomean else [])
        x = np.arange(len(all_labels))
        bar_width = 0.8 / len(plot_prefetchers)
        
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH, PLOT_HEIGHT))
        
        if include_baseline:
            ax.axhline(1.0, linestyle='-', color='black', linewidth=1, label='Baseline')
        
        ax.grid(True, linestyle='--', alpha=0.7, axis='y', zorder=0)
        ax.xaxis.grid(False)
        
        for i, prefetcher in enumerate(plot_prefetchers):
            heights = [speedups[prefetcher].get(label, 0.0) for label in all_labels]
            offsets = x + i * bar_width
            
            edge_color = 'black'
            line_width = 1.5 if HIGHLIGHT_LAST and i == len(plot_prefetchers) - 1 else 1
            
            ax.bar(offsets, heights, width=bar_width, label=display_prefetchers[i],
                   edgecolor=edge_color, linewidth=line_width, zorder=1)
        
        ax.set_xticks(x + bar_width * (len(plot_prefetchers) - 1) / 2)
        ax.set_xticklabels(all_labels, rotation=45, ha='right', fontsize=8)
        
        if ylim_bottom is not None:
            ax.set_ylim(bottom=ylim_bottom)
        if ylim_top is not None:
            ax.set_ylim(top=ylim_top)
        
        ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=10))
        ax.set_ylabel(ylabel, fontweight='bold')
        ax.set_xlabel("Workload Mix", fontweight='bold')
        
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.12), ncol=len(plot_prefetchers),
                 frameon=True, edgecolor='black', prop={'weight': 'bold'})
    
    plt.tight_layout(pad=0.1)
    if not os.path.exists(GRAPH_DIR):
        os.makedirs(GRAPH_DIR)
    
    if OUTPUT == "pdf":
        plt.savefig(os.path.join(GRAPH_DIR, filename), format='pdf', bbox_inches='tight')
    elif OUTPUT == "png":
        plt.savefig(os.path.join(GRAPH_DIR, filename), format='png', dpi=300, bbox_inches='tight')
    plt.close()


def print_stats_csv(speedups, plot_prefetchers, mix_names, metric_name):
    """Print per-mix statistics in CSV format."""
    print(f"\n{metric_name.upper()} Statistics (CSV):")
    
    header = "Mix, " + ", ".join([get_display_name(p) for p in plot_prefetchers])
    print(header)
    
    for mix_name in mix_names:
        values = [f"{speedups[p].get(mix_name, 0.0):.4f}" for p in plot_prefetchers]
        print(f"{mix_name}, " + ", ".join(values))
    
    geomean_values = [f"{speedups[p].get('geomean', 0.0):.4f}" for p in plot_prefetchers]
    print(f"geomean, " + ", ".join(geomean_values))


# --- MAIN EXECUTION ---

def main():
    # Determine plot name based on benchmark type
    plot_name = f"{PLOT_NAME}_{BENCHMARK_TYPE.lower()}"
    
    print("="*80)
    print(f"MULTICORE SIMULATION ANALYSIS ({NUM_CORES} cores)")
    print(f"Benchmark Type: {BENCHMARK_TYPE}")
    print(f"IPC Mean Type: {IPC_MEAN_TYPE}")
    print(f"Results directory: {LOG_DIR}")
    print(f"Baseline: {BASELINE}")
    print(f"Prefetchers: {', '.join(PREFETCHERS)}")
    print("="*80)
    
    # Gather IPC data
    print("\nGathering IPC data...")
    ipc_data, mix_names = gather_multicore_data()
    
    if not mix_names:
        print(f"Error: No {BENCHMARK_TYPE} mix files found!")
        return
    
    print(f"Found {len(mix_names)} workload mixes")
    
    # Group by CloudSuite application if enabled
    if BENCHMARK_TYPE == 'CLOUDSUITE' and GROUP_CLOUDSUITE_BY_APP:
        print("\nGrouping CloudSuite results by application (harmonic mean for IPC across phases)...")
        app_names = get_cloudsuite_apps(mix_names)
        print(f"Found {len(app_names)} CloudSuite applications: {', '.join(app_names)}")
        
        # Group IPC data using harmonic mean (correct for rate metrics)
        ipc_data, _ = group_by_cloudsuite_app(ipc_data, mix_names, metric_type='ipc')
        plot_mix_names = app_names
    else:
        plot_mix_names = mix_names
    
    # Compute IPC speedups
    print(f"\nComputing IPC speedups (using {IPC_MEAN_TYPE} mean)...")
    ipc_speedups, ipc_plot_prefetchers = compute_speedups(ipc_data, plot_mix_names, BASELINE, metric_type='ipc')
    
    print(f"Overall IPC speedups ({IPC_MEAN_TYPE} mean):")
    for prefetcher in ipc_plot_prefetchers:
        geomean = ipc_speedups[prefetcher].get('geomean', 0.0)
        print(f"  {get_display_name(prefetcher)}: {geomean:.4f}")
    
    # Gather and compute DRAM data
    print("\nGathering DRAM data...")
    dram_data = gather_multicore_dram_data()
    if BENCHMARK_TYPE == 'CLOUDSUITE' and GROUP_CLOUDSUITE_BY_APP:
        dram_data, _ = group_by_cloudsuite_app(dram_data, mix_names, metric_type='dram')
    dram_speedups, dram_plot_prefetchers = compute_speedups(dram_data, plot_mix_names, BASELINE, metric_type='dram')
    
    print("Geomean DRAM traffic (normalized):")
    for prefetcher in dram_plot_prefetchers:
        geomean = dram_speedups[prefetcher].get('geomean', 0.0)
        print(f"  {get_display_name(prefetcher)}: {geomean:.4f}")
    
    # Gather coverage data
    print("\nGathering coverage data...")
    cov_data = gather_multicore_coverage_data()
    if BENCHMARK_TYPE == 'CLOUDSUITE' and GROUP_CLOUDSUITE_BY_APP:
        cov_data, _ = group_by_cloudsuite_app(cov_data, mix_names, metric_type='coverage')
    cov_metrics, cov_plot_prefetchers = compute_absolute_metrics(cov_data, plot_mix_names, BASELINE)
    
    print("Average coverage:")
    for prefetcher in cov_plot_prefetchers:
        avg = cov_metrics[prefetcher].get('geomean', 0.0)
        print(f"  {get_display_name(prefetcher)}: {avg:.4f}")
    
    # Gather accuracy data
    print("\nGathering accuracy data...")
    acc_data = gather_multicore_accuracy_data()
    if BENCHMARK_TYPE == 'CLOUDSUITE' and GROUP_CLOUDSUITE_BY_APP:
        acc_data, _ = group_by_cloudsuite_app(acc_data, mix_names, metric_type='accuracy')
    acc_metrics, acc_plot_prefetchers = compute_absolute_metrics(acc_data, plot_mix_names, BASELINE)
    
    print("Average accuracy:")
    for prefetcher in acc_plot_prefetchers:
        avg = acc_metrics[prefetcher].get('geomean', 0.0)
        print(f"  {get_display_name(prefetcher)}: {avg:.4f}")
    
    # Print CSV stats if enabled
    if PRINT_BENCH_STATS:
        print("\n" + "="*80)
        print("STATISTICS (CSV FORMAT)")
        print("="*80)
        print_stats_csv(ipc_speedups, ipc_plot_prefetchers, plot_mix_names, 'ipc')
        print_stats_csv(dram_speedups, dram_plot_prefetchers, plot_mix_names, 'dram')
        print_stats_csv(cov_metrics, cov_plot_prefetchers, plot_mix_names, 'coverage')
        print_stats_csv(acc_metrics, acc_plot_prefetchers, plot_mix_names, 'accuracy')
    
    # Create plots
    print("\n" + "-"*40)
    print("Creating plots...")
    
    # Update plot name to indicate grouping
    if BENCHMARK_TYPE == 'CLOUDSUITE' and GROUP_CLOUDSUITE_BY_APP:
        plot_name = f"{PLOT_NAME}_cloudsuite_apps"
    
    print("Creating IPC speedup plot...")
    create_plot(ipc_speedups, ipc_plot_prefetchers, plot_mix_names, 'ipc', 'IPC Speedup',
                f'{plot_name}_ipc.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN,
                include_baseline=True, ylim_bottom=0.9, only_geomean_bar=ONLY_GEOMEAN_BAR)
    
    print("Creating DRAM traffic plot...")
    create_plot(dram_speedups, dram_plot_prefetchers, plot_mix_names, 'dram', 'Normalized DRAM Traffic',
                f'{plot_name}_dram.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN,
                include_baseline=True, ylim_bottom=0.8, only_geomean_bar=ONLY_GEOMEAN_BAR)
    
    print("Creating coverage plot...")
    create_plot(cov_metrics, cov_plot_prefetchers, plot_mix_names, 'coverage', 'Coverage',
                f'{plot_name}_coverage.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN,
                include_baseline=False, ylim_bottom=0.0, ylim_top=1.0,
                only_geomean_bar=ONLY_GEOMEAN_BAR)
    
    print("Creating accuracy plot...")
    create_plot(acc_metrics, acc_plot_prefetchers, plot_mix_names, 'accuracy', 'Accuracy',
                f'{plot_name}_accuracy.{OUTPUT}', include_geomean=INCLUDE_GEOMEAN,
                include_baseline=False, ylim_bottom=0.0, ylim_top=1.0,
                only_geomean_bar=ONLY_GEOMEAN_BAR)
    
    print("\nAll plots created successfully!")
    print(f"Output directory: {GRAPH_DIR}")


if __name__ == "__main__":
    main()

