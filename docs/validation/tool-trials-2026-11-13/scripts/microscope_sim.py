"""Microscope twin smoke test with python-microscope simulators: stage-aware camera, z-dependent blur, autofocus sweep."""
import json, sys, tempfile, os
import numpy as np
out = {}
try:
    import microscope
    from PIL import Image
    from microscope.simulators.stage_aware_camera import simulated_setup_from_image
    out["python_microscope"] = getattr(microscope, "__version__", "unknown")
    rng = np.random.default_rng(7)
    # Synthetic specimen: sparse bright blobs on dark field, 3 channels.
    h = w = 2048; img = np.zeros((h, w, 3), np.uint8)
    for _ in range(900):
        y, x, rad = rng.integers(20, h - 20), rng.integers(20, w - 20), rng.integers(2, 7)
        yy, xx = np.ogrid[-rad:rad + 1, -rad:rad + 1]
        img[y - rad:y + rad + 1, x - rad:x + rad + 1, rng.integers(0, 3)][yy**2 + xx**2 <= rad**2] = rng.integers(120, 255)
    path = os.path.join(tempfile.mkdtemp(), "specimen.tif"); Image.fromarray(img).save(path)
    devs = simulated_setup_from_image(path)
    out["devices"] = sorted(devs)
    cam, stage = devs["camera"], devs["stage"]
    for dev in devs.values():
        try: dev.initialize()
        except Exception: pass
    cam.enable(); stage.enable() if hasattr(stage, "enable") else None
    out["axes"] = {k: [float(v.limits.lower), float(v.limits.upper)] for k, v in stage.axes.items()}
    def snap():
        data, _ts = cam.grab_next_data()
        a = np.asarray(data)
        return a if a.ndim == 2 else a.reshape(a.shape[-2], a.shape[-1])
    def sharp(a):
        a = a.astype(float); gy, gx = np.gradient(a); return float((gx**2 + gy**2).mean())
    zs = np.linspace(-8, 8, 17); scores = []
    for z in zs:
        stage.move_to({"z": float(z)}); a = snap(); scores.append(sharp(a))
    best = float(zs[int(np.argmax(scores))])
    out.update(frame_shape=list(a.shape), sweep=[round(s, 3) for s in scores], best_focus_z=best,
               focus_contrast_ratio=round(max(scores) / (min(scores) + 1e-9), 1), ok=True)
except Exception as e:
    import traceback
    out.update(ok=False, error=f"{type(e).__name__}: {e}"[:500], tb=traceback.format_exc()[-900:])
print(json.dumps(out))
