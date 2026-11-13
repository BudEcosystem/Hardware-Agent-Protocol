"""Micro-Manager demo microscope via pymmcore-plus and prebuilt test adapters: camera, XY stage, Z focus, objective, shutter."""
import json, traceback
out = {}
try:
    import numpy as np, mm_test_adapters, pymmcore_plus
    from pymmcore_plus import CMMCorePlus
    path = mm_test_adapters.device_adapter_path
    path = path() if callable(path) else path
    core = CMMCorePlus(); core.setDeviceAdapterSearchPaths([str(path)])
    out.update(pymmcore_plus=pymmcore_plus.__version__, core=core.getVersionInfo(), api=core.getAPIVersionInfo(),
               adapters=sorted(core.getDeviceAdapterNames())[:12])
    for label, dev in (("Camera", "DCam"), ("Z", "DStage"), ("XY", "DXYStage"), ("Objective", "DObjective"), ("Shutter", "DShutter"), ("Autofocus", "DAutoFocus")):
        core.loadDevice(label, "DemoCamera", dev)
    core.initializeAllDevices()
    core.setCameraDevice("Camera"); core.setFocusDevice("Z"); core.setXYStageDevice("XY"); core.setShutterDevice("Shutter"); core.setAutoFocusDevice("Autofocus")
    core.setExposure(10.0); core.setPosition(12.5); core.waitForDevice("Z"); core.setXYPosition(100.0, 200.0); core.waitForDevice("XY")
    core.snapImage(); img = core.getImage()
    out.update(devices=list(core.getLoadedDevices()), z=core.getPosition(), xy=list(core.getXYPosition()),
               image_shape=list(img.shape), image_dtype=str(img.dtype), image_mean=round(float(np.mean(img)), 1),
               objective_states=core.getNumberOfStates("Objective"), exposure_ms=core.getExposure(), ok=True)
    # Run a small multi-dimensional acquisition (z-stack) through the acquisition engine.
    from useq import MDASequence
    frames = []
    core.mda.events.frameReady.connect(lambda im, ev, *a: frames.append((ev.index.get("z"), float(np.mean(im)))))
    core.mda.run(MDASequence(z_plan={"range": 4, "step": 1}))
    out["mda_frames"] = len(frames)
except Exception as e:
    out.update(ok=False, error=f"{type(e).__name__}: {e}"[:500], tb=traceback.format_exc()[-900:])
print(json.dumps(out))
