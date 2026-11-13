"""The microscope imaging model: a specimen image, focus-dependent blur, exposure and sensor noise.

Pure numpy. A specimen is a 2048 x 2048 grid at 1 um per pixel (bright blobs of several sizes over fine texture, the
same kind of target the python-microscope trial used). A frame is a crop of the specimen at the stage position, sampled
at ``10 / magnification`` um per camera pixel, blurred by a Gaussian whose width grows with the distance from the
specimen's focal plane, scaled by exposure and corrupted by shot and read noise, quantised to 12 bits. With nothing on
the stage the frame is an empty illuminated field (background and noise only), which has no focus peak.

Reference: a thin-lens defocus blur grows linearly with the axial distance from the focal plane; the circle-of-confusion
radius is combined in quadrature with the optical blur (``OPTICAL_SIGMA_PX``).
"""

from __future__ import annotations

import numpy as np

FRAME_PX = 256
SPECIMEN_PX = 2048
OBJECTIVES = (4, 10, 20, 40)  # magnifications
OPTICAL_SIGMA_PX = 0.8
DEFOCUS_PX_PER_UM = 0.25  # blur sigma (camera px) per um of defocus at 10x
BACKGROUND_COUNTS = 200.0
FULL_SCALE = 4095.0
PEAK_COUNTS = 3600.0
REFERENCE_EXPOSURE_MS = 20.0
READ_NOISE_COUNTS = 1.5


def make_specimen(rng: np.random.Generator) -> np.ndarray:
    """A synthetic specimen in [0, 1]: sparse blobs (radius 2-10 um) over fine texture."""
    yy, xx = np.mgrid[0:SPECIMEN_PX, 0:SPECIMEN_PX].astype(np.float32)
    image = np.zeros((SPECIMEN_PX, SPECIMEN_PX), np.float32)
    count = 2600
    cy, cx = rng.integers(0, SPECIMEN_PX, count), rng.integers(0, SPECIMEN_PX, count)
    radius, level = rng.integers(2, 11, count), rng.uniform(0.35, 1.0, count)
    for y, x, r, v in zip(cy, cx, radius, level, strict=True):
        y0, y1, x0, x1 = max(0, y - r), min(SPECIMEN_PX, y + r + 1), max(0, x - r), min(SPECIMEN_PX, x + r + 1)
        patch = image[y0:y1, x0:x1]
        mask = (yy[y0:y1, x0:x1] - y) ** 2 + (xx[y0:y1, x0:x1] - x) ** 2 <= r * r
        patch[mask] = np.maximum(patch[mask], v)
    texture = rng.normal(0.0, 0.04, image.shape).astype(np.float32)
    return np.clip(image + texture * (image > 0), 0.0, 1.0)


def _gaussian_blur(image: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur with edge replication; sigma in pixels."""
    if sigma < 0.05:
        return image
    radius = int(min(60, np.ceil(4 * sigma)))
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    kernel /= kernel.sum()
    out = image
    for axis in (0, 1):
        padded = np.pad(out, [(radius, radius) if a == axis else (0, 0) for a in (0, 1)], mode="edge")
        acc = np.zeros_like(out)
        for k, weight in enumerate(kernel):
            acc += weight * (padded[k:k + out.shape[0], :] if axis == 0 else padded[:, k:k + out.shape[1]])
        out = acc
    return out


def defocus_sigma_px(dz_um: float, magnification: float) -> float:
    """Total blur (camera pixels) at axial distance ``dz_um`` from the focal plane."""
    defocus = DEFOCUS_PX_PER_UM * abs(dz_um) * (magnification / 10.0) ** 2
    return float(np.hypot(OPTICAL_SIGMA_PX, defocus))


def render_frame(specimen: np.ndarray | None, *, x_um: float, y_um: float, dz_um: float, magnification: float,
                 exposure_ms: float, rng: np.random.Generator) -> np.ndarray:
    """One camera frame (uint16, 12-bit). ``specimen=None`` renders the empty field."""
    if specimen is None:
        signal = np.zeros((FRAME_PX, FRAME_PX), np.float32)
    else:
        um_per_px = 10.0 / magnification
        axis = np.arange(FRAME_PX) - FRAME_PX / 2
        cols = np.clip(np.round(x_um + axis * um_per_px).astype(int), 0, SPECIMEN_PX - 1)
        rows = np.clip(np.round(y_um + axis * um_per_px).astype(int), 0, SPECIMEN_PX - 1)
        signal = _gaussian_blur(specimen[np.ix_(rows, cols)], defocus_sigma_px(dz_um, magnification))
    scale = exposure_ms / REFERENCE_EXPOSURE_MS
    counts = scale * (BACKGROUND_COUNTS + PEAK_COUNTS * signal)
    noisy = counts + rng.normal(0.0, 1.0, counts.shape) * np.sqrt(np.maximum(counts, 0.0)) * 0.3 \
        + rng.normal(0.0, READ_NOISE_COUNTS, counts.shape)
    return np.clip(np.round(noisy), 0, FULL_SCALE).astype(np.uint16)


def sharpness(frame: np.ndarray) -> float:
    """Focus score: mean squared gradient of the frame (higher is sharper)."""
    image = frame.astype(np.float64)
    gy, gx = np.gradient(image)
    return float((gx * gx + gy * gy).mean())
