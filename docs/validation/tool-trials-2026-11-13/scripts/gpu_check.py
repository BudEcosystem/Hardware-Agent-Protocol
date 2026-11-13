import json, time, torch
out = {"torch": torch.__version__, "cuda": torch.cuda.is_available()}
def bench(dev, n=4096, reps=5):
    a = torch.randn(n, n, device=dev); b = torch.randn(n, n, device=dev)
    (a @ b).sum().item(); t0 = time.perf_counter()
    for _ in range(reps): c = a @ b
    c.sum().item(); dt = (time.perf_counter() - t0) / reps
    return round(2 * n**3 / dt / 1e9, 1)
out["cpu_gflops"] = bench("cpu", reps=2)
if out["cuda"]:
    out["gpu"] = torch.cuda.get_device_name(0); out["gpu_gflops"] = bench("cuda")
    out["gpu_mem_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1)
    # Small vision-transformer-sized forward pass, as a stand-in for a policy/perception step.
    import torch.nn as nn
    enc = nn.TransformerEncoder(nn.TransformerEncoderLayer(768, 12, 3072, batch_first=True), 12).cuda().half().eval()
    x = torch.randn(1, 257, 768, device="cuda", dtype=torch.half)
    with torch.no_grad():
        for _ in range(3): enc(x)
        torch.cuda.synchronize(); t0 = time.perf_counter()
        for _ in range(20): enc(x)
        torch.cuda.synchronize()
    out["vit_base_forward_ms"] = round((time.perf_counter() - t0) / 20 * 1000, 1)
print(json.dumps(out))
