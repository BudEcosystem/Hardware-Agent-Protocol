# TriAct_Micro_AF — Master Context & Handoff

**Project:** `TriAct_Micro_AF` — Microscope Auto-Focus Module
**Parent platform:** TriAct (Physical AI) · part of **Tri Autonomous Science Labs** (triscientist.com)
**Canonical name:** use **`TriAct_Micro_AF`** in every document, UI title, and future artifact. It
supersedes the older working name `auto_micro` (still the folder name of the software tree).
**This file:** the single source of truth. With this file plus the two code trees it points to, the
project can be rebuilt and continued on a fresh machine **with no other support.**
**Last updated:** 2026-11-20. **Hardware status:** autofocus operational across 4×/10×/40× on a real
specimen; teach-and-repeat verified. **Not a TriAct `sensnia` document** — ignore any `sensnia` refs.

---

## 0. How to use this file

1. Read §1–§3 for *what the project is* and *where it stands*.
2. §4 is the file map of both code trees. §5–§9 are the full technical reference (hardware, CAD,
   firmware, software, algorithms) — enough to modify any part.
3. §10 is the **cold-start setup** on a new computer. §11 is the **operating runbook**.
4. §12–§13 are the hard-won lessons and known issues — read before changing behaviour.
5. §14 is the forward roadmap (the portable kit). §15 is a one-screen quick reference.

---

## 1. What TriAct_Micro_AF is, and where it sits in Tri

**Tri Autonomous Science Labs** runs one loop — **Discover → Prove → Deliver**:
- **Discover · TriEvolve** — a problem-solving engine: a constrained brief in, a solution that is
  *real, verifiable and state-of-the-art* out, with the evidence behind every number.
- **Prove · TriAct** — *physical AI*. It runs experiments on real labs, instruments and production
  lines and feeds results back into the loop. **TriAct_Micro_AF is a TriAct instrument.**
- **Deliver · Tri Impact** — automated mass-market production and distribution (coming soon).

**The project:** a **reversible retrofit** that gives a **manual laboratory microscope** closed-loop,
camera-driven auto-focus. Two stepper motors turn the existing coarse and fine focus knobs through
3.94:1 spur gears; a Raspberry Pi Pico runs motion; a host program scores the live camera image with
variance-of-the-Laplacian and drives the knobs to the sharpest focus. Everything is reversible (no
drilling), the operator can take over by hand at any time, and **the live image never cuts** — even
while focusing.

**Why it matters to Tri:** autonomous science needs hands on real instruments. A microscope only a
human can focus stalls a self-driving experiment at every slide and objective change. `TriAct_Micro_AF`
removes that stall and is the **first TriAct retrofit** — a template for converting existing,
un-automated lab hardware into loop-ready instruments without replacing it.

---

## 2. Current status (2026-11-20)

**Working / proven:**
- First successful autofocus at 10× on a real specimen (green tissue section); metric ≈3.5 (empty
  field) → ≈7.9 (focused).
- Teach-and-repeat across **4× / 10× / 40×** via `focus_server.py`, verified end-to-end to an
  image-difference of 0.48, repeatable to one microstep (0.1125°).
- Single-owner `focus_server.py` interface: live MJPEG feed never cuts while focusing; camera-stall
  and Pico-USB-drop watchdogs both self-heal.
- Mechanical: direct spur-gear drive **V2** designed and mesh-verified in the parametric build
  (unprinted). Cage fixture frames + knob adapters **V1** modelled; the belt adapters were printed and
  confirmed to fit the knobs (bores opened 55.0→55.5 / 37.0→37.5 mm), then superseded by the gear drive.

**Pending / not done:**
- Gear drive V2 **not yet printed or fitted**; slotted motor brackets **still to be designed**.
- Knob **torque not measured** → the 3.94:1 ratio is unverified against the motor.
- Frame-plate thickness (sets where the pinion lands on the 16 mm shaft) unconfirmed.
- No powered acceptance test across multiple specimens/instruments yet.

**Current focus marks** (`auto_micro/focus_mark.json`, bottom-reference-relative — see §9.3; values
change each re-teach, this is a snapshot):
```json
{ "4":  { "pos1": 459.900, "score": 19.4 },
  "10": { "pos1": 506.138, "score":  9.8 },
  "40": { "pos1": 515.588, "score": 10.7 } }
```

---

## 3. The physical rig (as built)

A **Gemko Labwell** trinocular upright bench microscope (rear label reads MODEL NO ~`G.S. 725`;
binocular viewing + a separate camera/photo port; objectives 4× / 10×/0.25 / 40×; coaxial
coarse+fine knobs on both sides). A **ToupTek camera** sits on the trinocular photo tube. A welded
steel-tube **cage** now holds the microscope and is intended to carry the motors and electronics. The
host today is a Windows laptop (Acer Nitro 5) running ToupTek **ImageView**; development is on macOS.

> Beam path note: the trinocular **beam-splitter slider must be set to the camera port**, and the
> specimen must be **centred**, or the focus metric stays flat (~3.5) regardless of focus.

---

## 4. Repository map (two trees under `/Users/athul/Documents/Tri/`)

The project spans two directories. **Tree A** is the live software + firmware. **Tree B** is the TriAct
workspace holding CAD, design docs, images and durable context.

### Tree A — `auto_micro/` (software + firmware + camera SDK)
| File | Purpose |
|---|---|
| `CONTEXT.md` | Original durable notes for the software tree (this master file supersedes/encompasses it). |
| `pico_firmware.py` | **Reference copy of the firmware that runs *on the Pico* as `main.py`.** 2-axis stepper + limit-switch controller, plain-text serial protocol. Do **not** run on the laptop. |
| `knob_control.py` | Host-side `Knob` class + interactive REPL. Serial (auto-detects Pico VID 0x2E8A) or TCP (Pico W). |
| `camera.py` | `Camera` class (ToupTek SDK, pull-mode capture) + focus metrics `sharpness()` (variance of Laplacian) and `tenengrad()`. |
| `focus_server.py` | **PREFERRED interface.** One process owns camera **and** Pico; serves a browser UI (live MJPEG + focus score + log + buttons) at `http://localhost:8080`; focus routines run server-side; feed never cuts. Rebranded to `TriAct_Micro_AF`. |
| `autofocus.py` | Standalone two-stage autofocus (coarse sweep → fine hill-climb). CLI. **Opens the camera** — do not run while `focus_server` is up. |
| `safe_autofocus.py` | Crash-safe autofocus **client** — talks to `focus_server` over HTTP (never opens the camera); UP-only coarse climb from a bottom start, stops at the peak, backs off only the overshoot. |
| `approach.py` | Directed ONE-WAY focus climb (one axis, one direction, until peak/limit/cap, returns to best). Opens the camera. |
| `jog_test.py` | Safe, small, reversible focus probe (jogs one axis ± a few degrees, measures, returns). Opens the camera. |
| `viewer.py` | Standalone live MJPEG browser view with focus overlay (:8080). Superseded by `focus_server`. Opens the camera. |
| `check_setup.py` | Pre-flight: pings Pico + both motors + opens the camera. Run before standalone scripts. |
| `focus_mark.json` | Per-objective focus marks `{ "4": {pos1,score}, "10": …, "40": … }` (bottom-relative). Auto-migrates an old single-mark format. |
| `toupcam.py` | ToupTek vendor SDK Python binding (3184 lines, from the official SDK zip). |
| `libtoupcam.dylib` | ToupTek native library, universal x86_64+arm64 (macOS). Windows/Linux need the matching `toupcam.dll`/`libtoupcam.so` from the SDK. |

Root duplicates: `/Users/athul/Documents/Tri/main.py` is byte-identical to `auto_micro/pico_firmware.py`
(the file flashed to the Pico as `main.py`); `/Users/athul/Documents/Tri/knob_control.py` is identical to
`auto_micro/knob_control.py`. `Knob Actuator Build Guide (1).html` is the original hardware build guide.

### Tree B — `TriAct/projects/microscope-autofocus/` (CAD, docs, images)
| Path | Purpose |
|---|---|
| `README.md` | Project entry (retrofit intent, phase). |
| `docs/design.md` | Control architecture + staged validation plan (Stage 0–5). |
| `docs/mechanical-concept-v1.md` | Opposite-side belt-drive concept, split collars, clutch decision path, sizing relationships. |
| `docs/gear-drive-v2.md` | **Current drive:** direct spur gears 67:17, module 1.5, CD 63; full geometry, mesh checks, print notes, open questions. |
| `docs/fixture-and-adapters-v1.md` | Cage frames + knob adapters V1; archived GT2 belt parts; interpretation of the hand sketch. |
| `docs/image_assessment.md` | Per-photo observations of the eight original setup photos. |
| `docs/measurement_intake.csv` | The still-missing measurements (torque, travel, backlash, clearances). |
| `docs/portable-af-kit-brief.md` | **Engineering brief for the portable "convert-any-scope" kit** (PCB, 3D, firmware, app, BOM, validation). See §14. |
| `hardware/cad/focus_gear_drive_v2.py` | Parametric FreeCAD source for the gear drive (params at top; build asserts geometry). |
| `hardware/cad/microscope_fixture_models.py` | Parametric source for the 4 cage frames + knob adapters (+ archived belt pulley). |
| `hardware/cad/build_models.sh` | Headless FreeCAD rebuild → STL + FCStd. |
| `outputs/stl/` | Exported STLs (gear drive + fixture frames) + `previews/` renders + `archive/v1_gt2_belt/` (byte-identical belt parts). |
| `images/` | Original setup photos + cage photos + the hand dimension sketch (HEIC). Preserved; hashes in `codex/context/image_inventory.json`. |

TriAct workspace durable context (also in Tree B's parent `TriAct/`): `codex/context/project_state.md`
(current state), `codex/context/decisions_log.md` (every design decision + rationale),
`codex/STARTUP.md`, `AGENTS.md`/`CLAUDE.md` (operating rules — keep work inside TriAct, maintain the
decision log, no separate memory tree).

**Top-level deliverables** (in `/Users/athul/Documents/Tri/`): this file;
`TriAct_Micro_AF_Dossier.docx` / `.pdf` (the project dossier); the live web dossier artifact.

---

## 5. Hardware reference

### 5.1 Controller — Raspberry Pi Pico (RP2040)
- MicroPython firmware (`pico_firmware.py`, runs on-Pico as `main.py`). Works on Pico / Pico W / Pico 2.
- Host link: **USB CDC serial, 115200 baud**, Raspberry Pi **VID `0x2E8A`** (auto-detected). On the dev
  Mac it enumerates as `/dev/cu.usbmodem1301`. Optional Wi-Fi TCP **port 5005** on a Pico W with a
  `config.py` (`WIFI_SSID`, `WIFI_PASSWORD`) present.

### 5.2 Motors + drivers
- 2× **NEMA 17 `JK42HS34-0406-01`**, 1.8° → **200 full steps/rev**. (5 mm motor shaft on the real
  motors; the V2 gear CAD was parameterised for a 16 mm shaft per a user spec — reconcile before print.)
- 2× **A4988** drivers, **16× microstepping** → **0.1125°/microstep** at the motor
  (`360 / (200 × 16)`), position kept in 1/16-step "ticks" (3200 ticks/rev).
- **Axis 1 = COARSE** focus knob · **Axis 2 = FINE** focus knob. Positive angle = **UP** on both;
  both default `invert=True` (set by `FLIP`, saved to `settings.json` on the Pico).

### 5.3 Pin map (from firmware, perfboard layout)
```
             EN  MS1 MS2 MS3 STEP DIR     (GPxx)
  Axis 1 :   22   21  20   19   18   17   (driver right of the Pico)
  Axis 2 :   12   11  10    9    7    6   (driver left of the Pico)
  Limits :   TOP = GP28,  BOTTOM = GP27   (C → GND, between them GP-GND)
```
- A4988 MS truth table in firmware: 1,2,4,8,16 → (0,0,0)…(1,1,1). Microstep changeable only when idle.

### 5.4 Limit switches
- C/NO/NC microswitches wired **fail-safe NC**: `C → GND`, `NC → GP28 (TOP)` / `GP27 (BOTTOM)`,
  internal pull-up. **Normal=closed=pin reads 0. Pressed OR broken wire = reads 1 = "hit".**
- Debounce: trip after 1 ms pressed, release after 150 ms (`TRIP_US=1000`, `RELEASE_US=150000`).
- A hit TOP switch instantly stops a guarded axis moving UP and refuses new UP moves (DOWN still
  allowed to back away), and vice versa. After a normal stop on a switch the motor backs off
  `RELEASE_DEG=3°`. Hitting the *wrong* switch (moved UP, hit BOTTOM) raises a **direction fault** →
  send `<axis> FLIP` once (saved).
- **The physical TOP limit switch was removed** by the user (2026-11-20); it still reads clear, so
  up-moves work but there is **no hardware stop at the top** — rely on stopping at the focus peak.
  The **BOTTOM switch is the critical reference** for re-sync (§9.3).

### 5.5 Camera — ToupTek `UCMOS03100KPA`
- 3.1 MP; resolutions 2048×1536 / 1024×768 / 680×510; opens at the SDK default (1024×768 in ImageView).
- **NOT a UVC webcam** — OpenCV/AVFoundation cannot open it. USB vendor "TT" `0x0547`. Driven through
  the **ToupTek SDK** (`toupcam.py` + `libtoupcam.dylib`) in **pull mode** (native callback →
  `PullImageV4`), wrapped synchronously in `camera.py`. SDK gives RGB on macOS; `camera.py` flips to
  BGR for OpenCV. The SDK talks USB directly, so the macOS Camera-permission (TCC) wall does **not**
  apply to this camera. (A *standard UVC* camera on this Mac would need Terminal granted Camera access.)
- SDK provenance: official `toupcamsdk.20261024.zip` from touptekphotonics.com/download. If the dylib
  was freshly downloaded, clear quarantine: `xattr -c libtoupcam.dylib`.
- Only **one process** can hold the camera open at a time (the core reason for the single-owner server).

---

## 6. Mechanical / CAD reference

All CAD is **parametric** (FreeCAD, Python source with a PARAMETERS block, headless build to STL+FCStd).
The gear-drive build **refuses to export** on any geometric violation (interference, wrong centre
distance, pinion over the frame-mount limit, a height that isn't a whole 0.2 mm layer, grub screw
missing the shaft, bore not a clean full-length profile). Printer: **Bambu Lab A1**, 0.2 mm layers,
support-free.

### 6.1 Direct spur-gear drive V2 (current) — `docs/gear-drive-v2.md`
- Involute spur, **module 1.5, 20°**, standard addendum/dedendum, 0.10 mm tooth thinning/gear.
- **67:17 = 3.94:1** at **centre distance 63 mm** (coaxial knobs, motors on opposite sides). 17T is the
  smallest 20° pinion with no undercut; knob gear 67T (Ø103.5), pinion Ø28.5 (< 35 mm frame-mount limit).
- Both gears **13 mm wide**. Motor pinion: 13 mm teeth + Ø20×10 hub on the shaft, bore 5.15, two M3
  grub screws (M3×6) in OD-4 brass inserts (Ø4.2 pockets). Knob gears keep the V1 bores (coarse root
  55.5 / 72 keying teeth; fine root 37.5 / 50 teeth), 13 mm grip.
- **Per knob turn: 788 full steps / 12 612 microsteps** (1/16). Knob torque ≈3.8× motor torque after
  losses (**unverified** — torque unmeasured). Mesh: zero overlap over a pitch, backlash 0.20 mm
  (≈0.23° at the knob), tip clearance 0.375, contact ratio 1.66. Approach final focus from one
  direction to beat backlash. Motor mount needs centre-line slots to close the mesh.
- Open before fabrication: knob torque; frame-plate thickness (sets gear position on the shaft; build
  checks screw-on-shaft up to t≈5 mm); slotted motor brackets (undesigned); whether 13 mm grip is enough.

### 6.2 Cage fixture frames + knob adapters V1 — `docs/fixture-and-adapters-v1.md`
- Four hollow printed **frames** (10 mm walls, 30 deep, one 10 mm support bar) locate the microscope in
  the welded cage: `block_back_support` (120 × 275/145 sloped; also a 2-piece snap-fit set for the
  200×200 bed), two side frames (161×185, one with switch cut-outs), a front frame (70×140). Print flat,
  PLA fine, 3 walls / 20 % infill.
- **Knob adapters** keyed to the knob grip ridges. Belt (V1) adapters printed at 55.0/37.0 bore were
  tight → opened to **55.5/37.5** and confirmed to fit ("perfect"). The outer drive feature is now the
  V2 spur gear, not a GT2 belt. FDM bores print ≈0.2 mm undersize — bake that in.
- **Archived belt drive** (superseded): STLs byte-identical in `outputs/stl/archive/v1_gt2_belt/`;
  regenerate by setting `EXPORT_GT2_BELT_PARTS=True`. Motor pulley was 20T GT2, bore 5.15.

---

## 7. Firmware reference (`pico_firmware.py` → Pico `main.py`)

**Serial protocol** — one command per line, case-insensitive, **axis number first** (no number ⇒ axis 1;
`ALL` ⇒ both). Replies: `OK <axis> …` immediately, `DONE <axis> pos=<deg>` on completion, `ERR …` on error.

| Command | Meaning |
|---|---|
| `MOVE <deg>` | Relative move (± degrees). |
| `GOTO <deg>` | Absolute move to angle from zero. |
| `STEPS <n>` | Relative move in microsteps. |
| `SPEED <dps>` | Max speed (default **90**). |
| `ACCEL <dps²>` | Acceleration (default **360**). |
| `MICRO <1\|2\|4\|8\|16>` | Microstep mode (default **16**, only when idle). |
| `ZERO` | Current position becomes 0°. |
| `POS` | Report position. |
| `STOP` | Decelerate and stop (preempts the queued move). |
| `EN 1` / `EN 0` | Energise (hold) / release (free to hand-turn). |
| `HOME` | Drive DOWN to the BOTTOM switch, back off, set 0°. |
| `FINDTOP` | Drive UP to the TOP switch, report travel, back off. |
| `LIMITS [ON\|OFF]` | Report / toggle the switch guard (OFF for bench testing only). |
| `FLIP` | Reverse this motor's direction (saved to `settings.json`), clears a fault. |
| `CLEAR` | Clear a direction fault without flipping. |
| `STATUS`, `HELP` | Status line / command help. |

- Motion is a trapezoidal accel/cruise/decel profile; `start_move` sets direction with `invert` XOR.
- Defaults: `HOME_SPEED=30`, `BACKOFF_DEG=10`, `RELEASE_DEG=3`, `min_dps=5`, `SEARCH_MAX_DEG=7200`.
- `settings.json` on the Pico persists per-axis `invert`. `HOME` handles the "already on the bottom
  switch" case by backing off first; the firmware's debounce race can make `HOME` report
  "bottom-switch-still-pressed" — the host `resync` works around it (§9.3).
- **Flashing:** install MicroPython UF2 on the Pico, then copy `pico_firmware.py` to the Pico as
  `main.py` (e.g. via Thonny or `mpremote`). It runs on boot. Close Thonny before using the host scripts
  (one serial owner).

---

## 8. Host software reference

### 8.1 `knob_control.Knob` (host motor API)
```python
from knob_control import Knob
k = Knob(port=None)        # auto-detect Pico over USB; or Knob(host="192.168.1.50") for Pico W
k.home(axis=1)             # bottom switch -> 0 deg
top = k.find_top(axis=1)   # degrees from bottom to top switch
k.move(1, 90); k.goto(2, -45); k.wait_all()
print(k.pos(1), k.pos(2), k.limits())   # limits -> {"top":bool,"bottom":bool}
k.flip(1); k.cmd("1 SPEED 45")
```
- Non-blocking moves (both axes can run together); `wait_all()` blocks until every started move reports
  `DONE`. A background reader thread queues replies; `cmd()` drains stale lines but remembers finished
  moves. Raises `RuntimeError` on `ERR`, `TimeoutError` on no reply.

### 8.2 `camera.Camera` (ToupTek capture + focus metric)
```python
from camera import Camera, sharpness, tenengrad
cam = Camera(index=0, auto_expo=True, warmup=1.0, roi=None)  # roi=(x,y,w,h) fractions 0..1, None=whole frame
frame = cam.grab()                 # fresh BGR numpy frame, waits for a new one
score = cam.focus(samples=3, metric=sharpness)   # median over N frames
age = cam.frame_age()              # seconds since last frame (watchdog)
cam.reopen()                       # recover a stalled SDK stream
```
- `sharpness` = **variance of the Laplacian** (default; higher = sharper). `tenengrad` = Sobel gradient
  energy (steadier under noise, alternative).
- `python camera.py --list` enumerates ToupTek cameras; `--index N --preview` shows a live window + score.

### 8.3 `focus_server.py` — the preferred interface
`python focus_server.py --cam 0 --mag 10 --port 8080` → `http://localhost:8080`. **One process owns the
camera (streaming thread) and the Pico**; focus routines read sharpness from the shared live frames so
the browser feed never goes dark.

HTTP API:
| Method · path | Action |
|---|---|
| `GET /` | Browser UI (`TriAct_Micro_AF` branded). |
| `GET /stream` | MJPEG live view with focus+mag overlay. |
| `GET /focus` | Current focus score (`(working...)` while a routine runs). |
| `GET /power` | `held` / `released` / `?`. |
| `GET /obj` | Current objective mag label. |
| `GET /status` | `pos1 pos2 {limits}` (or `busy`). |
| `GET /log` | Rolling activity log. |
| `POST /fine` | **Fine refine** — hill-climb axis 2 only (`amp=15°, step=5°`). Coarse untouched → safe at 40×/100×. |
| `POST /coarse` | **Coarse refine** — symmetric sweep of axis 1 (`amp=24°, step=6°`). Low-mag only (UI confirms). |
| `POST /jog?axis=&deg=` | Nudge an axis by hand-sized steps. |
| `POST /enable?on=0\|1` | Release (hand-turn) / energise (hold). |
| `POST /home?axis=` | Drive DOWN to the BOTTOM switch and zero. |
| `POST /resync` | **Re-establish axis-1 position** at the bottom reference (after a hand-turn). |
| `POST /mark?obj=` | **Teach** the current focus for an objective (bottom-relative). |
| `POST /gotomark?obj=` | Jump axis 1 to a saved objective's mark (absolute GOTO). |
| `POST /mag?v=` | Set the overlay magnification. |
| `POST /reconnect` | Rebuild the Pico serial link (USB drop). |

Self-healing: the **grabber** reopens the camera if the stream stalls (`frame_age > 2.5 s`); the
**knob_watchdog** probes `1 STATUS` every 3 s and reconnects the Pico on a USB drop (errno 6) — both
without a restart or a feed cut. `_knob_lock` serialises motor access; `_busy` guards routines.

### 8.4 `autofocus.py` — standalone two-stage (opens the camera)
`python autofocus.py --cam 1 --coarse-range 48 --coarse-step 6 --fine-step 8 --fine-min 1`
CLI defaults: `--coarse-range 720 --coarse-step 30 --fine-step 15 --fine-min 1 --settle 0.25
--metric laplacian`. **Stage 1** coarse sweep of axis 1 across the range, return to the sharpest stop.
**Stage 2** fine hill-climb on axis 2 with halving step down to `fine-min`. Each measurement:
`wait_all()` → settle → median of a few frames.

### 8.5 Clients / helpers
- `safe_autofocus.py` — crash-safe UP-only coarse climb that drives through `focus_server`'s HTTP API
  (never opens the camera). Use this to autofocus without risking the feed.
- `approach.py` — directed one-way climb, `--dir +` (up, guarded); never sweep `-` blindly toward the slide.
- `jog_test.py` — tiny reversible ± probe. `check_setup.py` — pre-flight pings. `viewer.py` — legacy
  live view (superseded by `focus_server`). The last four **open the camera** → do not run them while
  `focus_server` is up.

---

## 9. Autofocus & teach-and-repeat — concepts

### 9.1 Focus metric
Variance of the Laplacian over the (optionally ROI-cropped) grayscale frame; median of several settled
frames per sample to beat sensor noise. A centre ROI can read flat if the specimen texture is at the
edges — allow multi-region. Reject blank/clipped frames. A black frame (mean ≈1) is a **light** fault
(beam-splitter not on the camera port, or lamp off), not a focus fault.

### 9.2 The peak is narrow and noisy
At 10× the camera-focus peak is only **~4–6° of knob wide**; a 6° coarse step walks right over it and
reads "blurry". Single reads jitter a lot (same spot read 6 and 11). **Search wide first (±~90°) to
locate the peak, then refine with ~2° steps and ≥9-sample averaging.** Validate a peak against its
neighbours; a flat curve or an edge-of-window maximum returns **"focus not found"**, never a blind
re-sweep. **Camera focus ≠ eyepiece focus** (parfocality is not guaranteed; keep a manual reference).
At 4× the coarse knob dominates and the fine knob barely shifts the plane; at 40× the fine knob matters.

### 9.3 Open-loop position & the bottom reference (critical)
The steppers have **no encoder** — the Pico counts only the steps it commands. **Hand-turning the
coarse knob while de-energised makes the count stale**, so "go to mark" would see zero delta and not
move. Solution: anchor everything to a repeatable **BOTTOM-switch reference**.
- **Re-sync** (`/resync`): drive axis 1 DOWN to the bottom switch, back off to "release-edge + 5°", and
  **zero** there (`_drive_down_to_reference`). This works around the firmware debounce race. Repeatable
  to <0.5 image-diff.
- **Marks are stored relative to this bottom reference.** `mark_here` is **hand-turn-tolerant**: it
  zeroes at the current focus, drives down to the reference (image dips), reads the offset, re-zeros the
  reference, drives back up to focus, and saves that offset. So you can hand-focus and just click Mark.
- Workflow — **teach:** rotate turret, hand-focus sharp, click **Mark Nx**. **Recall after any
  hand-turn:** click **Re-sync once**, then the objective button. Rotating the objective **turret** is
  always safe (it never touches the focus motor). The coarse coupling can **slip** when hand-turning
  with the motor released (symptom: coarse moves stop changing the image) → re-seat it.

### 9.4 Safety model
Firmware starts guarded; rejects guarded moves outside the envelope; limit switches fail-safe NC;
`STOP` preempts. Host side: never sweep coarse blindly toward the slide (down); climb UP only, stop at
the peak, and (with the TOP switch removed) never exceed the focus mark. Manual movement, slip, reset
or power loss invalidate the open-loop count → re-sync. Log commanded steps separately from measured
position.

---

## 10. Cold-start setup on a NEW system

1. **Get the code:** copy both trees — `auto_micro/` (software+firmware+SDK) and
   `TriAct/projects/microscope-autofocus/` (CAD+docs) — plus this file.
2. **Python deps:** Python 3.11+. `pip install pyserial opencv-python numpy`. (numpy 2.x is fine; some
   unrelated local packages may warn — harmless.)
3. **ToupTek SDK per-OS:** `auto_micro/` ships the macOS `libtoupcam.dylib`. On **Windows** copy
   `toupcam.dll` (and on Linux `libtoupcam.so`) next to `toupcam.py` from the official SDK zip
   (`toupcamsdk.<date>.zip`, touptekphotonics.com/download). macOS only: if freshly downloaded, run
   `xattr -c libtoupcam.dylib` to clear quarantine. Close **ImageView** before running (one camera owner).
   A standard UVC camera (not this one) would also need Terminal granted Camera access in macOS Privacy.
4. **Flash the Pico:** install the MicroPython UF2, then copy `pico_firmware.py` to the Pico as
   `main.py` (Thonny or `mpremote fs cp pico_firmware.py :main.py`). It runs on boot. Close Thonny after.
5. **Find the ports:** `python auto_micro/camera.py --list` (camera index); the Pico auto-detects by VID
   `0x2E8A` (or pass `--port-serial /dev/cu.usbmodemXXXX` / `COM5`). `python auto_micro/check_setup.py`
   pings everything.
6. **Run the interface:** `cd auto_micro && python focus_server.py --cam <N> --mag 10` → open
   `http://localhost:8080`. Set the beam-splitter to the camera port; centre the specimen. The header
   shows motor power, focus score and objective.
7. **First teach:** energise, hand-focus each objective sharp, click **Mark 4×/10×/40×**. Thereafter:
   **Re-sync once** after any coarse hand-turn, then an objective button recalls focus.

Hardware note: on the mechanical side, re-print the gear drive (`TriAct/projects/microscope-autofocus/
hardware/cad/build_models.sh` with FreeCAD 1.1.4 headless) only after confirming the open items in §6.1.

---

## 11. Operating runbook

- **Normal autofocus:** in `focus_server`, use **Fine refine** (safe at any mag — coarse untouched).
  Use **Coarse refine** only at low mag (UI warns; coarse moves can crash the objective at high mag).
- **Recall a known objective:** click 4×/10×/40×. If the coarse knob was hand-turned since: click
  **Re-sync** once first.
- **Hand-focusing:** click **De-energize**, focus by eye; then either **Mark Nx** (to teach) or
  **Re-sync** (to restore the count). Hand-turning **only the fine** knob is safe.
- **Recovery:** stalled image → the camera watchdog reopens it (~2.5 s). Pico USB drop → the knob
  watchdog reconnects (or POST `/reconnect`). Black frame → light/beam-splitter problem, not focus.
  Direction fault on a motor → `<axis> FLIP` once.
- **Never** run `autofocus.py`/`jog_test.py`/`approach.py`/`viewer.py` while `focus_server` is up (they
  open the camera and would cut the feed). Use `safe_autofocus.py` (HTTP client) instead.

---

## 12. Hard-won lessons (consolidated — read before changing behaviour)
1. **Never cut the live feed.** The user requires the stream stay up even while focusing → always drive
   focus through the single-owner `focus_server`, never a second camera opener.
2. **The peak is narrow and noisy** (§9.2): search wide, refine small, average heavily.
3. **Camera focus ≠ eyepiece focus** — keep a manual reference; validate peaks against neighbours.
4. **Open-loop, no encoder** — coarse moves are *relative*; absolute counts are meaningless after a
   hand-turn. Re-sync to the bottom reference; marks are bottom-relative.
5. **Beam-splitter + centring** — must be on the camera port with the specimen centred, or the metric
   stays flat ~3.5. A black frame is a light fault.
6. **Coupling slip** — the coarse coupling can slip when hand-turning with the motor released; re-seat.
7. **TOP limit switch removed** — no hardware stop at the top; stop at the peak, never exceed the mark.
8. **One camera owner** — ToupTek allows a single open handle; close ImageView and any viewer first.

## 13. Known issues / gotchas
- ToupTek stream can freeze if the USB/rig is jostled (frozen image / stuck score) → `reopen()` /
  watchdog recovers. Harmless `[link error] Bad file descriptor` can print when `Knob.close()` races the
  reader thread on shutdown. The firmware `HOME` debounce race → use the host `resync`. Gear-drive V2 is
  geometry-verified only (no print tolerance / deflection / wear modelled). Motor shaft diameter: real
  motor 5 mm vs the V2 CAD's 16 mm spec — reconcile before printing pinions.

---

## 14. Roadmap — the portable "convert-any-scope" kit

The bench build proves the loop on one microscope. The product is to make it **portable**: a
plug-and-play kit that converts **any** manual microscope to auto-focus (no soldering, no code,
reversible). Full brief: **`TriAct/projects/microscope-autofocus/docs/portable-af-kit-brief.md`**,
covering a custom controller PCB, parametric 3D mount + knob-adapter family + enclosure, firmware, a
switchable host/onboard app, autofocus spec, BOM and staged validation.

**Locked decisions (2026-11-20):**
1. **Topology** — *switchable*: an onboard compute brain (web UI over Wi-Fi, no laptop) **and** an
   optional host-laptop mode, both driving the same RP2040 motion board.
2. **Camera** — support the proven **ToupTek SDK** path **and** a **generic UVC/USB** adapter behind one interface.
3. **Electronics** — **RP2040 + A4988**, socketed drivers, 1/16 microstepping; bottom limit switch is the homing reference.
4. **Market** — **open-source / maker kit**: documented BOM, fully 3D-printed enclosure, off-the-shelf
   parts, no-solder assembly; no formal certification in v1, but design cleanly for a later commercial rev.

**Secondary defaults (confirm when convenient):** onboard brain = Raspberry Pi Zero 2 W; keep NEMA 17 +
spur gears on an adjustable baseplate-plus-body-clamp mount; ship coarse+fine; 12 V barrel jack + USB-PD
option; MicroPython firmware (C/Pico-SDK as a stretch).

**Immediate next actions (hardware):** measure knob torque (4× and 10× coarse) and verify the 3.94:1
ratio against the motor; get the frame-plate thickness; print one pinion + a 4 mm knob-gear slice and
test the mesh at CD 63.0; design the slotted motor brackets; then print and fit the V2 drive.

---

## 15. Quick reference (one screen)

```
NAME           TriAct_Micro_AF  (use everywhere; old folder name: auto_micro)
RUN            cd auto_micro && python focus_server.py --cam <N> --mag 10   ->  http://localhost:8080
DEPS           pip install pyserial opencv-python numpy   (+ ToupTek SDK: toupcam.py + native lib)
PICO           MicroPython; pico_firmware.py -> Pico main.py; USB 115200, VID 0x2E8A, TCP 5005 (Pico W)
MOTORS         2x NEMA17 JK42HS34 + A4988, 16x ustep = 0.1125 deg/ustep; axis1=COARSE axis2=FINE; +=UP
PINS           A1 EN22 MS21/20/19 STEP18 DIR17 | A2 EN12 MS11/10/9 STEP7 DIR6 | TOP GP28 BOTTOM GP27 (NC,C->GND)
GEARS          67:17 module1.5 CD63 = 3.94:1; 788 full / 12612 ustep per knob turn; backlash 0.20mm
CAMERA         ToupTek UCMOS03100KPA (0x0547), SDK pull-mode, NOT UVC; one owner; beam-splitter->cam port
METRIC         variance of Laplacian (camera.sharpness); median of samples; search wide then refine 2deg
MARKS          focus_mark.json, bottom-reference-relative; Re-sync once after any coarse hand-turn
FW CMDS        MOVE GOTO STEPS SPEED(90) ACCEL(360) MICRO(16) ZERO POS STOP EN HOME FINDTOP LIMITS FLIP CLEAR
SERVER POST    /fine /coarse /jog /enable /home /resync /mark /gotomark /mag /reconnect   GET /stream /focus /status /log
RULES          never cut the feed; firmware distrusts the host; climb UP only; re-sync is relative
CAD            FreeCAD parametric, Bambu A1 0.2mm, build asserts geometry; gear V2 unprinted
DOCS           auto_micro/CONTEXT.md | TriAct/.../docs/{design,gear-drive-v2,fixture-and-adapters-v1,portable-af-kit-brief}.md
```

---
*TriAct_Micro_AF · master context compiled 2026-11-20 · keep this file current as the single handoff.*
