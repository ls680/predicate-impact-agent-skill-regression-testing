# PredicateImpact Run Environment

Snapshot verified inside the AutoDL container on 2026-09-06:

- Ubuntu 22.04, Linux 5.15.0-136-generic;
- cgroup CPU quota: 20 cores (`cpu.max=2000000 100000`);
- host CPU: AMD EPYC 7642, 192 host threads visible;
- cgroup memory limit: 90 GiB (`memory.max=96636764160`), no swap;
- system disk: 30 GB, 414 MB used at final audit;
- data disk: 1.1 TB, 33 GB used at final audit;
- Python 3.12.3;
- PyTorch 2.8.0+cu128, CUDA runtime 12.8;
- NVIDIA GeForce RTX 3090, 24,576 MiB, driver 595.71.05;
- ALFWorld 0.4.2, TextWorld 1.7.0, ScienceWorld 1.2.3;
- pinned ScienceWorld simulator commit `e8216d6`, SHA-256
  `e77b0fee7d68abe3ca5b12e57d86e2bfe7603f20c5200da0b0f085939faeb465`;
- OpenJDK 17.

The R22--R24 PredicateImpact experiments use native simulator execution and do
not invoke an LLM. The GPU is therefore present but unused. `nproc` reports the
192 visible host threads, so the cgroup quota, rather than `nproc`, is the
correct allocated-CPU measure.
