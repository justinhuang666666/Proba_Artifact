# Proba Artifact (PACT 2026)

This repository contains the artifact for:

> **Proba: A High-Performance, Low-Traffic Probabilistic Spatial Memory Streaming Prefetcher**  
> International Conference on Parallel Architectures and Compilation Techniques (PACT 2026)

The artifact provides the ChampSim implementation and evaluation framework used to evaluate Proba and several Spatial Memory Streaming (SMS) prefetchers on SPECspeed 2017.

## Repository Contents

The repository includes:

- The Proba implementation in `prefetcher/proba/`.
- Implementations of SMS, Bingo, DSPatch, PMP, and Gaze in `prefetcher/`.
- The ChampSim version and system configuration used for the evaluation.
- Scripts for downloading SPECspeed 2017 traces, running simulations, and reporting results in `scripts/`.
- The baseline configuration in `params/baseline.json`.

## Requirements

The artifact requires:

- Python 3.9 or later
- GCC/G++ 11
- GNU Make
- Git

### Tested Environment

The artifact has been tested with:

| Component | Version |
| --- | --- |
| Operating system | Ubuntu 22.04.5 LTS |
| Linux kernel | 5.15.0 |
| GCC/G++ | 11.4.0 |
| Python | 3.10.12 |

GCC/G++ 11 is required to compile the artifact. Newer compiler
versions are not currently supported.

The required compiler and other dependencies can be installed
automatically using the setup script below.

## Setup

Clone the repository and initialise the artifact:

```bash
git clone https://github.com/justinhuang666666/Proba_Artifact.git
cd Proba_Artifact
./scripts/setup.sh
```

Download the SPECspeed 2017 traces:

```bash
python3 scripts/download_spec2017_traces.py
```

By default, the traces are stored in:

```text
traces/spec2017/
```

## Reproducing the Main Result

The baseline uses:

- A degree-3 stride prefetcher at L1D.
- No prefetcher at L2C.

Therefore, the `no` configuration means **no L2 prefetching**, rather than no prefetching anywhere in the cache hierarchy.

Replace `N` with the number of simulations to execute in parallel:

```bash
python3 scripts/run_experiments.py no -j N
python3 scripts/run_experiments.py proba -j N
```

Each configuration takes approximately 3 hours on an Intel Xeon Platinum 8168 system using 40 cores. Systems with fewer cores should use a smaller value of `N`, with a corresponding increase in total execution time.

Each simulation produces a text file containing the simulator log and a JSON file containing the statistics used by the result-reporting script:

```text
results/spec2017/<prefetcher>/<benchmark>/<trace>.txt
results/spec2017/<prefetcher>/<benchmark>/<trace>.json
```

### Print the Main Results

After both configurations complete, run:

```bash
python3 scripts/print_results.py proba
```

The script reports:

- IPC speedup over the baseline.
- Normalised DRAM traffic.
- LLC coverage.
- Overall prefetch accuracy across both L2 and LLC, ensuring a fair comparison with prefetchers that employ multilevel prefetching.

The expected aggregate values are listed in [Expected Results](#expected-results).

## Reproducing All Evaluated Prefetchers

Running every evaluated prefetcher is optional. To reproduce the complete single-core comparison from the paper, run:

```bash
for pref in no sms bingo dspatch pmp gaze proba; do
    python3 scripts/run_experiments.py "$pref" -j N
done
```

With `N=40`, the complete experiment takes approximately 21 hours on an Intel Xeon Platinum 8168 system.

After all simulations complete, print the comparison tables with:

```bash
python3 scripts/print_results.py \
    sms \
    bingo \
    dspatch \
    pmp \
    gaze \
    proba
```

## Evaluated Prefetchers
| Configuration | Description                                                                                                                                                               |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `no`          | Evaluation baseline: degree-3 L1D stride prefetcher and no L2C prefetcher                                                                                                 |
| `ip_stride`   | Instruction-pointer-based stride prefetcher used at L1D                                                                                                                   |
| `sms`         | Spatial Memory Streaming, ISCA 2006. [Paper](https://web.eecs.umich.edu/~twenisch/papers/isca06.pdf)                                                                      |
| `bingo`       | Bingo Spatial Data Prefetcher, HPCA 2019. [Paper](https://doi.org/10.1109/HPCA.2019.00053)                                                                                |
| `dspatch`     | DSPatch: Dual Spatial Pattern Prefetcher, MICRO 2019. [Paper](https://arxiv.org/abs/1910.03075)                                                                           |
| `pmp`         | Merging Similar Patterns for Hardware Prefetching, MICRO 2022. [Paper](https://doi.org/10.1109/MICRO56248.2022.00071)                                                     |
| `gaze`        | Gaze into the Pattern: Characterizing Spatial Patterns with Internal Temporal Correlations for Hardware Prefetching, HPCA 2025. [Paper](https://arxiv.org/abs/2412.05211) |
| `proba`       | Proba: A High-Performance, Low-Traffic Probabilistic Spatial Memory Streaming Prefetcher, PACT 2026                                                                       |

The SMS, Bingo, DSPatch, PMP, and Gaze implementations are adapted from the [Gaze artifact](https://github.com/SJTU-Storage-Lab/Gaze-Spatial-Prefetcher). Their evaluated configurations correspond to those reported in Table 3 of the Proba paper.

## Expected Results

Small numerical differences may occur because of compiler, operating-system, or host-platform differences. However, the overall trends and conclusions should remain consistent.

### Proba Versus the Baseline

After running `no` and `proba`, the aggregate results should be:

| Prefetcher | Speedup |   DRAM | LLC cov. | Accuracy |
| :--------- | ------: | -----: | -------: | -------: |
| **proba**  |  1.0659 | 1.0845 |   0.5088 |   0.8068 |

Here, `Accuracy` denotes the overall prefetch accuracy across both L2 and LLC.

### All Evaluated Prefetchers

After running all configurations, the aggregate results should be:

| Prefetcher |    Speedup |       DRAM |   LLC cov. |   Accuracy |
| :--------- | ---------: | ---------: | ---------: | ---------: |
| sms        |     1.0456 |     1.1316 |     0.4622 |     0.7699 |
| bingo      |     1.0446 |     1.1638 |     0.4808 |     0.7516 |
| dspatch    |     1.0544 |     1.2772 |     0.4247 |     0.7042 |
| pmp        |     1.0559 |     1.2806 |     0.5751 |     0.6629 |
| gaze       |     1.0497 |     1.1236 |     0.5372 |     0.6285 |
| **proba**  | **1.0659** | **1.0845** | **0.5088** | **0.8068** |

The expected per-benchmark speedups are:

| Benchmark    |    sms |  bingo | dspatch |    pmp |   gaze |  proba |
| :----------- | -----: | -----: | ------: | -----: | -----: | -----: |
| bwaves603    | 1.1170 | 1.1170 |  1.0732 | 1.1174 | 1.1113 | 1.1153 |
| cactuBSSN607 | 1.0078 | 1.0043 |  1.6025 | 1.2635 | 1.0160 | 1.2684 |
| cam4627      | 1.0004 | 1.0009 |  1.0059 | 0.9906 | 1.0058 | 1.0076 |
| deepsjeng631 | 1.0038 | 1.0058 |  1.0063 | 1.0068 | 0.9998 | 1.0003 |
| exchange2648 | 1.0000 | 1.0000 |  1.0000 | 1.0000 | 1.0001 | 1.0000 |
| fotonik3d649 | 1.2646 | 1.2760 |  1.1625 | 1.2431 | 1.3350 | 1.2707 |
| gcc602       | 1.1562 | 1.1694 |  1.1453 | 1.1619 | 1.1387 | 1.1646 |
| imagick638   | 1.0052 | 1.0052 |  1.0028 | 1.0052 | 1.0049 | 1.0001 |
| lbm619       | 1.0561 | 1.0566 |  1.0460 | 1.0572 | 1.0612 | 1.0560 |
| leela641     | 0.9981 | 0.9984 |  0.9918 | 0.9935 | 0.9975 | 1.0009 |
| mcf605       | 0.9808 | 0.9548 |  0.9553 | 0.9919 | 0.9539 | 1.0329 |
| nab644       | 1.0550 | 1.0615 |  1.0596 | 1.0618 | 1.0571 | 1.0569 |
| omnetpp620   | 0.9839 | 0.9797 |  0.9448 | 0.8884 | 0.9603 | 0.9947 |
| perlbench600 | 0.9991 | 0.9998 |  0.9975 | 0.9866 | 0.9953 | 0.9987 |
| pop2628      | 1.0224 | 1.0315 |  1.0492 | 1.0674 | 1.0645 | 1.0693 |
| roms654      | 1.2195 | 1.1939 |  1.1003 | 1.2264 | 1.2144 | 1.1914 |
| wrf621       | 1.0931 | 1.1037 |  1.0755 | 1.1145 | 1.1157 | 1.1203 |
| x264625      | 1.0092 | 1.0104 |  1.0153 | 1.0144 | 1.0164 | 1.0103 |
| xalancbmk623 | 1.0221 | 1.0148 |  1.0226 | 1.0155 | 1.0195 | 1.0282 |
| xz657        | 0.9739 | 0.9675 |  0.9730 | 0.9956 | 0.9974 | 0.9992 |

These experiments reproduce the SPECspeed 2017 results reported in Figures 12, 13, and 14 of the paper.

## License

This artifact is licensed under the [Apache License, Version 2.0](LICENSE).

- **Proba prefetcher:** Copyright 2026 the Proba authors.
- **ChampSim simulator:** Copyright 2023 the ChampSim contributors.
