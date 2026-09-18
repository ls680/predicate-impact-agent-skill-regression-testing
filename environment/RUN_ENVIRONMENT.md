# Final run environment

## Immutable inputs

- source SHA-256:
  `e98e6cd716bbeca3825a06641d03dba7a96f300d49af1d35d75665579fdaf5dd`
- Tier-C manifest SHA-256:
  `9a17e166c91ce55c4b7a01ea31f0fba9347819227e634ac2b226d675ab8192b8`
- incident-definition SHA-256:
  `c15195c3aaddfda1edc7fb8d4d17c201e4a6e674d3b9447542c811fe5df93863`

Each formal directory contains the same values in `run_spec.json`; resumption
fails if the current files differ.

## Machine

- provider: AutoDL
- operating system: Ubuntu 22.04.5 LTS, Linux 5.15
- execution: provider container, no nested Docker
- CPU quota visible to Python: 20 logical CPUs (`nproc`)
- host CPU: AMD EPYC 7642, two 48-core sockets / 192 host threads
- memory cgroup limit: 90 GiB (host `/proc` reports 755 GiB); no swap
- GPU: NVIDIA GeForce RTX 3090, 24,576 MiB, compute capability 8.6
- driver: 595.71.05
- system disk: 30 GB (778 MB used during the formal runs; under 1 GB / 3%)
- data disk: approximately 1.1 TB (33 GB used after all three model downloads)

All virtual environments, model weights, benchmark data, and caches are under
`/root/autodl-tmp`; the system disk contains no model cache.

## Software

- Python: 3.12.3
- PyTorch: 2.8.0+cu128
- CUDA runtime used by PyTorch: 12.8
- Transformers: 4.57.6
- Accelerate: 1.14.0
- ALFWorld: 0.4.2
- TextWorld: 1.7.0
- ScienceWorld: 1.2.3
- json-repair: 0.63.4
- Java: OpenJDK 17

## Models

- `Qwen/Qwen3-4B-Instruct-2507`:
  `cdbee75f17c01a7cc42f958dc650907174af0554`
- `microsoft/Phi-4-mini-instruct`:
  `cfbefacb99257ffa30c83adab238a50856ac3083`
- `mistralai/Mistral-7B-Instruct-v0.3`:
  `c170c708c41dac9275d15a8fff4eca08d52bab71`

All runs use greedy decoding and each model's native loaded dtype. Values below
come directly from the formal run metadata. Inference hours sum recorded model
call latency across authoring, development, and test; they are not rental wall
time.

| Model | Parameters | Dtype | Peak GPU GiB | Logged inference hours | Test-stage elapsed |
|---|---:|---|---:|---:|---:|
| Qwen3-4B-Instruct-2507 | 4,022,468,096 | bfloat16 | 12.393 | 1.521 | 3,821.8 s |
| Phi-4-mini-instruct | 3,836,021,760 | bfloat16 | 11.871 | 1.734 | 4,411.0 s |
| Mistral-7B-Instruct-v0.3 | 7,248,023,552 | bfloat16 | 23.217 | 2.484 | 5,980.3 s |

Mistral-7B is close to the 24GB card limit but completed without quantization
or CPU offload. The formal experiment therefore supports single-RTX-3090
reproduction under the pinned software stack.
