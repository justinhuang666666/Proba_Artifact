# Weights for GAP benchmark traces
# Since GAP traces don't use simpoints like SPEC, each trace has equal weight

from _GAP_def import GAP_shortcode

# Generate weights for GAP benchmarks
# Each trace within a benchmark category gets equal weight (summing to 1.0)
# Keys are the result file names (trace name without .trace.gz extension)
GAP_SHORTCODE_WEIGHTS = {}

for benchmark, traces in GAP_shortcode.items():
    weight_per_trace = 1.0 / len(traces)
    GAP_SHORTCODE_WEIGHTS[benchmark] = {
        # Remove .trace.gz to match result file naming
        trace.replace('.trace.gz', ''): weight_per_trace for trace in traces
    }
