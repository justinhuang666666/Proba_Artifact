import re
from _PARSEC_def import PARSEC_shortcode

PARSEC_SHORTCODE_WEIGHTS = {}

for benchmark, traces in PARSEC_shortcode.items():
    weight_per_trace = 1.0 / len(traces)
    weights = {}
    for trace in traces:
        match = re.search(r'(drop_\d+M)', trace)
        if match:
            weights[match.group(1)] = weight_per_trace
    PARSEC_SHORTCODE_WEIGHTS[benchmark] = weights
