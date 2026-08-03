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
- A C++ compiler with C++17 support
- GNU Make
- Git

### Tested Environment

The artifact has been tested with:

| Component | Version |
|---|---|
| Operating system | Fedora 44 |
| Linux kernel | 7.0.13 |
| GCC | 16.1.1 |
| Python | 3.14.6 |

Other recent Linux distributions and C++17-compatible compilers may also work, but have not been tested.

## Setup

Clone the repository and initialise its submodules:

```bash
git clone https://github.com/justinhuang666666/Proba_Artifact.git
cd Proba_Artifact
git submodule update --init --recursive
```

Build the ChampSim dependencies:

```bash
vcpkg/bootstrap-vcpkg.sh
vcpkg/vcpkg install
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

Each configuration takes approximately one hour on an Intel Xeon Platinum 8168 system using 40 cores. Systems with fewer cores should use a smaller value of `N`, with a corresponding increase in total execution time.

Results are written to:

```text
results/spec2017/<prefetcher>/<benchmark>/
```

Each simulation produces:

```text
<trace>.txt
<trace>.json
```

The text file contains the simulator log, while the JSON file contains the statistics used by the result-reporting script.

### Print the Main Results

After both configurations complete, run:

```bash
python3 scripts/print_results.py proba
```

The script reports:

- IPC speedup over the baseline.
- Normalised DRAM traffic.
- LLC coverage.
- Overall prefetch accuracy across both L2 and LLC, including L2 prefetches that are used or evicted after reaching the LLC.

The expected aggregate values are listed in [Expected Results](#expected-results).

## Reproducing All Evaluated Prefetchers

Running every evaluated prefetcher is optional. To reproduce the complete single-core comparison from the paper, run:

```bash
for pref in no sms bingo dspatch pmp gaze proba; do
    python3 scripts/run_experiments.py "$pref" -j N
done
```

With `N=40`, the complete experiment takes approximately seven hours on an Intel Xeon Platinum 8168 system.

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
| **proba**  |  1.0588 | 1.0840 |   0.4416 |   0.7912 |

Here, `Accuracy` denotes the overall prefetch accuracy across both L2 and LLC, ensuring a fair comparison with prefetchers that employ multilevel prefetching.

### All Evaluated Prefetchers

After running all configurations, the aggregate results should be:

| Prefetcher |    Speedup |       DRAM |   LLC cov. |   Accuracy |
| :--------- | ---------: | ---------: | ---------: | ---------: |
| sms        |     1.0413 |     1.1500 |     0.4584 |     0.7645 |
| bingo      |     1.0392 |     1.1902 |     0.4796 |     0.7494 |
| dspatch    |     1.0487 |     1.2763 |     0.3971 |     0.6856 |
| pmp        |     1.0549 |     1.3223 |     0.5697 |     0.6666 |
| gaze       |     1.0493 |     1.1413 |     0.5332 |     0.6288 |
| **proba**  | **1.0588** | **1.0840** | **0.4416** | **0.7912** |

The expected per-benchmark speedups are:

| Benchmark    |    sms |  bingo | dspatch |    pmp |   gaze |  proba |
| :----------- | -----: | -----: | ------: | -----: | -----: | -----: |
| bwaves603    | 1.1167 | 1.1168 |  1.0723 | 1.1169 | 1.1130 | 1.1153 |
| cactuBSSN607 | 1.0128 | 1.0001 |  1.5364 | 1.3244 | 1.0374 | 1.2424 |
| cam4627      | 0.9991 | 0.9985 |  1.0051 | 0.9927 | 1.0069 | 1.0049 |
| deepsjeng631 | 1.0008 | 1.0014 |  0.9986 | 1.0002 | 0.9990 | 0.9996 |
| exchange2648 | 1.0000 | 1.0000 |  1.0000 | 1.0000 | 1.0002 | 1.0000 |
| fotonik3d649 | 1.2721 | 1.2919 |  1.1755 | 1.2611 | 1.3393 | 1.2777 |
| gcc602       | 1.1381 | 1.1458 |  1.1193 | 1.1305 | 1.1165 | 1.1432 |
| imagick638   | 1.0100 | 1.0102 |  1.0037 | 1.0102 | 1.0099 | 1.0001 |
| lbm619       | 1.0578 | 1.0583 |  1.0477 | 1.0588 | 1.0630 | 1.0576 |
| leela641     | 1.0006 | 1.0006 |  1.0007 | 1.0007 | 1.0005 | 1.0000 |
| mcf605       | 0.9868 | 0.9484 |  0.9559 | 1.0016 | 0.9785 | 1.0367 |
| nab644       | 1.0550 | 1.0617 |  1.0617 | 1.0615 | 1.0575 | 1.0543 |
| omnetpp620   | 0.9816 | 0.9784 |  0.9468 | 0.8938 | 0.9586 | 0.9920 |
| perlbench600 | 1.0017 | 1.0024 |  1.0008 | 0.9960 | 1.0004 | 1.0005 |
| pop2628      | 1.0220 | 1.0220 |  1.0285 | 1.0458 | 1.0549 | 1.0368 |
| roms654      | 1.1458 | 1.1333 |  1.0715 | 1.1597 | 1.1582 | 1.1285 |
| wrf621       | 1.0717 | 1.0804 |  1.0707 | 1.0886 | 1.1008 | 1.0923 |
| x264625      | 1.0188 | 1.0204 |  1.0206 | 1.0258 | 1.0270 | 1.0142 |
| xalancbmk623 | 1.0361 | 1.0315 |  1.0345 | 1.0323 | 1.0341 | 1.0464 |
| xz657        | 0.9469 | 0.9377 |  0.9437 | 0.9822 | 0.9910 | 0.9907 |

These experiments reproduce the SPECspeed 2017 results reported in Figures 12, 13, and 14 of the paper.

## License

This artifact is licensed under the [Apache License, Version 2.0](LICENSE).

- **Proba prefetcher:** Copyright 2026 the Proba authors.
- **ChampSim simulator:** Copyright 2023 the ChampSim contributors.
