DPC4_AIML_path = "~/DPC4/AIML/"

DPC4_AIML_ones = [
    "bark",
    "biogpt",
    "clip",
    "llama2_15M",
    "llama2_42M",
    "llama2_110M",
    "rwkv",
]

DPC4_AIML_traces = {
    "bark": [
        "bark.cpp-bark-small.coarse_token_gen.1.champsimtrace.gz",
        "bark.cpp-bark-small.coarse_token_gen.2.champsimtrace.gz",
        "bark.cpp-bark-small.coarse_token_gen.4.champsimtrace.gz",
        "bark.cpp-bark-small.coarse_token_gen.5.champsimtrace.gz",
    ],
    "biogpt": [
        "biogpt.cpp-ggml-model-tocilizumab.1.champsimtrace.gz",
        "biogpt.cpp-ggml-model-tocilizumab.2.champsimtrace.gz",
        "biogpt.cpp-ggml-model-tocilizumab.3.champsimtrace.gz",
    ],
    "clip": [
        "clip_trace_1.champsimtrace.gz",
        "clip_trace_3.champsimtrace.gz",
    ],
    "llama2_15M": [
        "llama2.c-stories15M.1.champsimtrace.gz",
        "llama2.c-stories15M.2.champsimtrace.gz",
        "llama2.c-stories15M.3.champsimtrace.gz",
    ],
    "llama2_42M": [
        "llama2.c-stories42M.1.champsimtrace.gz",
        "llama2.c-stories42M.2.champsimtrace.gz",
        "llama2.c-stories42M.3.champsimtrace.gz",
    ],
    "llama2_110M": [
        "llama2.c-stories110M.1.champsimtrace.gz",
        "llama2.c-stories110M.2.champsimtrace.gz",
        "llama2.c-stories110M.3.champsimtrace.gz",
    ],
    "rwkv": [
        "rwkv_trace_1.champsimtrace.gz",
        "rwkv_trace_2.champsimtrace.gz",
        "rwkv_trace_3.champsimtrace.gz",
    ],
    "stable_diffusion": [
        "stable-diffusion.cpp-sd-v1-4.ckpt.1.champsimtrace.gz",
        "stable-diffusion.cpp-sd-v1-4.ckpt.2.champsimtrace.gz",
        "stable-diffusion.cpp-v1-5-pruned-emaonly.2.champsimtrace.gz",
        "stable-diffusion.cpp-v2-1_768-nonema-pruned.1.champsimtrace.gz",
        "stable-diffusion.cpp-v2-1_768-nonema-pruned.2.champsimtrace.gz",
        "stable-diffusion.cpp-v2-1_768-nonema-pruned.3.champsimtrace.gz",
    ],
    "vit": [
        "vit.cpp-base-ggml-model-f16.gguf.armadillo.1.champsimtrace.gz",
        "vit.cpp-large-ggml-model-f16.gguf.armadillo.1.champsimtrace.gz",
    ],
    "whisper": [
        "whisper_trace_1.champsimtrace.gz",
        "whisper_trace_2.champsimtrace.gz",
        "whisper_trace_3.champsimtrace.gz",
    ],
}