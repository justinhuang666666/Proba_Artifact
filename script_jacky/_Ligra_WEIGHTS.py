import re
from _Ligra_def import Ligra_shortcode

Ligra_SHORTCODE_WEIGHTS = {}

for benchmark, traces in Ligra_shortcode.items():
    weight_per_trace = 1.0 / len(traces)
    weights = {}
    for trace in traces:
        match = re.search(r'(drop_\d+M)', trace)
        if match:
            weights[match.group(1)] = weight_per_trace
    Ligra_SHORTCODE_WEIGHTS[benchmark] = weights
