# GB10 hub deployment evidence — provisional

The six bounded NVIDIA pages in the [local archive](../research/deployment/gb10-followup/README.md)
were acquired and read on 2026-11-06. They support a candidate ARM64 inference
hub profile, not an executed HMS deployment. No model, container, SDK sample,
GPU program, device driver or physical endpoint ran in this review.

## Published constraints

The hardware page describes a 20-core CPU, shared LPDDR5x memory, NVMe storage,
USB-C and network interfaces. Its listed 128 GB configuration has 273 GB/s
memory bandwidth; the supply is 240 W and the stated ideal ambient range is
5–30°C. The rear-panel figure distinguishes the power connector from three
other USB-C connectors. These are vendor specifications, not measured HMS
capacity, peripheral power availability or deadline bounds. The archived page
is byte-identical to the earlier hardware acquisition. [Hardware overview](https://docs.nvidia.com/dgx/dgx-spark/hardware.html).

The porting overview identifies ARM64, heterogeneous cores, shared CPU/GPU
physical memory and Ubuntu-based DGX OS. It also flags differences in memory
ordering. Its broad data-sharing language must be read with the narrower CUDA
restrictions below. The hardware and porting pages disagree on Bluetooth
version (5.4 versus 5.3); the overview's cluster description also does not
justify inventing a Linux affinity map. Resolve installed topology and device
details on the actual unit. [Porting overview](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/latest/overview.html).

NVIDIA's CUDA page says GPUDirect RDMA is unavailable on Spark: allocations
such as those returned by `cudaMalloc` cannot be coherently accessed by the CPU
or PCIe peripherals in the described path. It recommends capability queries
and an appropriate fallback, with host-allocated communication buffers as an
example. HMS cannot equate unified memory, a ConnectX NIC or a shared address
with valid zero-copy camera/network transfer. Buffer ownership, allocation
kind, synchronization and transport support remain explicit contracts.
[CUDA porting restrictions](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/latest/porting/cuda.html).

The dependency table reports support by package and minimum version. It lists
Container Toolkit and selected inference/vision libraries, while marking
cuCIM, CV-CUDA, DOCA and HPC SDK unsupported. Some supported rows have an
undetermined minimum version. Its internal update date is April 15, although
the page footer is October 21. Treat that table as a dated publisher claim;
check the exact chosen package, architecture and release before installation.
It does not establish that a model's full dependency closure works.
[Dependencies and tools](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/latest/porting/dependencies.html).

The November 4 release-note snapshot lists DGX OS 7.6.0, driver 580.178.04 and
CUDA 13.0.3, explicitly for Founders Edition. Partner updates may differ. Its
October release supports both 64 GB and 128 GB configurations and changes
display-memory reservation. It records prior memory-pressure improvements and
a headless fan-control fix. Thus SKU, available memory, firmware and software
revision belong in a deployment record; “GB10” alone is insufficient. These
notes do not prove an installation is patched or free of remaining faults.
[Release notes](https://docs.nvidia.com/dgx/dgx-spark/release-notes.html).

The single-device vLLM playbook treats checkpoint, image, cache, parser and
server options as one recipe. Weights, KV cache, request length and concurrency
share capacity; a maximum context and sequence count do not prove their joint
fit. Startup may download, compile and tune. Health, chat and tool-call checks
establish different stages of readiness. The tool-call example returns a call
for a client to execute; it does not itself execute or authorize a hardware
operation. The page also distinguishes loopback/SSH access from an exposed
unauthenticated bind. [Local serving playbook](https://build.nvidia.com/spark/vllm/advanced).

## Consequences for HMS

The following are HMS design inferences and required future tests:

| Boundary | Proposed implementation obligation | Evidence still needed |
|---|---|---|
| Installation | Pin unit/SKU, ARM64 userspace, native dependencies, image digest, firmware and model revision; reject unsupported profile combinations | ARM64 package build and exact-device smoke tests |
| Memory | Budget model/runtime/KV cache together with imaging buffers, journal and operating-system headroom; admission limits must cover aggregate concurrent work | Loaded and stressed measurements, including allocation failures and recovery |
| Authority | Keep inference as a client of the checked HMS runtime; a model token, parser or API connection grants no device authority | Real local model → Harness → runtime validation and rejection tests |
| Timing | Keep servo, watchdog and independent stop behavior at qualified endpoints; rate-limit hub work and bound queues | Tail latency, controller service gaps and stop behavior during saturated CPU/GPU/I/O, thermal load and hub loss |
| Data | Negotiate supported allocation/transport paths and preserve ownership, acquisition time and visible gaps | Actual camera/DAQ/network path, fallback and resource-lifetime tests |
| Recovery | Pre-stage pinned offline artifacts; separate model-service readiness from accepted hardware-operation recovery | Cold boot, crash, storage pressure, interrupted update and partition tests |

No result here establishes ARM64 runtime execution, on-device model quality,
physical stop, electrical protection, a qualified clock, simultaneous maximum
model capacity, or universal device support. The remaining porting sections,
known-issues page, full container/model dependency trees, multi-node recipes
and actual GB10 hardware measurements remain further work.
