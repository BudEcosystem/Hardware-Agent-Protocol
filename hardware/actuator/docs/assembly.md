# BHMS Arm — printing and assembly

Every number in this guide comes from `cad/params.py`. Part files are in
`cad/out/` (STL for printing, STEP for CAD). Regenerate them with
`python cad/build.py`. Purchased parts are listed in `bom/bom.csv`.

> **Before ordering boards.** The Gerbers in `pcb/*/fab/` come from an
> autorouted layout that passed KiCad DRC with 0 errors but has not been
> reviewed by a person (docs/design.md §12, O7), and no board has been
> built. If `pcb/<board>/DO_NOT_FABRICATE.md` exists, that board is
> unfinished and has no Gerbers: do not order it. Do not rely on the E-stop
> to park the arm: it falls when power is cut (docs/design.md §9).

> **Safety first.** The servo rail carries 12 V at up to 5 A. Keep the
> E-stop wired and within reach from the first power-up onwards. With J2
> unplugged the servo rail cannot turn on; that is intentional.

## 1. Print settings

| Setting | Structural parts (PETG) | Lids, knob, coupon (PLA) | Collet, pads, tip cap (TPU 95A) |
|---|---|---|---|
| Nozzle / layer | 0.4 mm / 0.2 mm | 0.4 mm / 0.2 mm | 0.4 mm / 0.2 mm |
| Perimeters / top / bottom | 3 / 5 / 4 (the 1.2 mm shell in the mass model) | 3 / 4 / 4 | 3 / 4 / 4 |
| Infill | 30 % gyroid (mass model value). **Gears and pinions: 100 %** | 20–30 % | 100 % |
| Temperatures | 240 °C / 80 °C bed | 210 °C / 60 °C | 225 °C / 50 °C, slow (≤ 25 mm/s) |
| Supports | Only where noted in the orientation column | none | none |

* **Calibrate fits first.** Print `tolerance_coupon.stl`. It has 608 and
  624 seats at the nominal press fit and at ±0.1 mm. Press in a bearing.
  If the nominal seat is loose or splits, change `Printer.press_fit`.
  If screws or lids bind, change `Printer.fit_clearance`. Then rerun
  `cad/build.py`.
* Print gears in PETG at 100 % infill (the shoulder pinion is machined
  steel, not printed). In PLA the 17-tooth pinion creeps under sustained
  holding torque. Set the shoulder servo Max_Torque_Limit to 78 % before
  the first torque-enable (INTERFACE.md §3.1).
* Print orientations, quantities, modelled masses and print-time
  estimates are listed per part in `cad/out/parts.json`. They are also in
  the "Printed part" rows of `bom/bom.csv`. All filament together is about
  1.6 kg and roughly 51 h of printing (estimate). Most of that is the base,
  links and tool rack.

## 2. Before you start

* Tools: soldering iron with a heat-set insert tip; 1.5/2/2.5/3 mm hex
  keys; a 13 mm spanner; a 1.4 mm drill (to size the pogo bores to your
  pin barrel); a crimp tool for JST-XH; a multimeter.
* Install heat-set inserts before assembling. They go in: every servo
  cradle (4 × M3 each), the pod lid bosses (4 × M3), the PCB standoffs
  (4 × M3), the shell bosses (4 × M4 from below), both pinion stubs
  (M4), the flange detent hole (M5), the gripper racks (M3), and the
  collet hub (3 × M3).
* Program and number every servo **before** it disappears into a cradle.
  Set the ID on a bench with a single servo on the bus: 1 yaw, 2 shoulder,
  3 elbow, 4 wrist pitch, 5 wrist roll, 6 gripper, 7 knob turner,
  8 button presser. Leave the baud rate at 1 Mbps.
* Centre each servo before fitting its horn and driven part. Command raw
  position 2048, the middle of the 0–4095 range. Fit the part at the
  joint's mid-range angle. Each joint's servo span (`firmware/INTERFACE.md`
  §3.1) then lies inside one encoder turn.

## 3. Base and clamp

1. Stick the six rubber feet into the recesses under `base_plate`.
2. Slide the yaw servo (ID 1) into the cradle on `base_plate` from +y,
   with its cable toward the rear, and close it with a `servo_lid`
   (4 × M3×8).
3. Press the 6806-2RS bearing into the deck of `base_shell` from above,
   until it seats on the 1 mm lip.
4. Mount the controller PCB on the four standoffs of `base_plate` (M3×8).
   The USB-C, 12 V terminal and E-stop connectors face the rear wall
   cut-outs.
5. Route the yaw servo lead to J4 (servo chain A).
6. Lower `base_shell` over the plate and fix it with 4 × M4×12 from below.
7. Fit `pod_lid` (4 × M3×8). The hole in the lid sits over the RGB LED and
   acts as a light pipe opening.
8. Clamp: press the M8×60 hex head into `clamp_knob` and thread the bolt
   up through the captive M8 nut in `clamp_body`. Put `clamp_pad` on the
   tip. Hook the clamp's locating pin into the tongue hole. Tighten
   against the table underside (tables up to 45 mm thick).

## 4. Turret and shoulder (geared 3:1)

1. Place the shoulder servo (ID 2) in the turret cradle. Its output faces
   −y (toward the gear plane) and its lid is on top. Screw on the lid.
2. Bolt the `pinion_shoulder` (17 teeth, module 1.5, machined STEEL, not
   printed: order it to `cad/out/pinion_shoulder.step`) to the servo horn
   (4 × M2 through the pinion counterbores). Put a 624-2RS into the −y cheek seat. Insert M4×12 with
   an M4 washer from outside, through the bearing, into the pinion stub
   insert. The washer must bear on the inner race only.
3. Press a 608-2RS into each cheek, flush with the outer face.
4. Mount the turret on the yaw servo horn. The spigot goes through the
   6806 inner race. Fix it with 4 × M2 through the turret disc
   counterbores.

## 5. Upper arm (shoulder side) and elbow

1. With the shoulder servo at mid-range (raw 2048) and the upper arm at
   the middle of its range (+37.5°), slide the upper arm hub between the
   cheeks. Its 51-tooth gear meshes with the pinion.
2. Insert the M8×70 bolt with a washer from one side, through 608, hub
   and 608. Fit the washer and nyloc nut. Tighten until the bearings turn
   smoothly with no axial play. The hub spacers press only on the inner
   races.
3. Elbow: repeat §4 steps 1–3 for the elbow servo (ID 3) in the upper
   arm's clevis, then §5 step 2 for the forearm hub at elbow mid-range
   (+60°).
4. Check the gear backlash. Rock the link by hand; the free play at the
   elbow axis should be under 1°. If it is larger, reprint the pinion
   with `Gear.backlash` reduced by 0.05 mm.

## 6. Forearm, wrist and flange

1. Slide the wrist-pitch servo (ID 4) into the forearm cradle. Its horn
   faces −y; the lid is toward the back (−x). Press a 624-2RS into the
   idler boss on +y.
2. Fit the roll servo (ID 5) into the `wrist_bracket` cradle. Its output
   points along the bracket axis; the lid is on −x.
3. Bolt the bracket's left arm to the wrist-pitch horn (4 × M2), at wrist
   mid-range (0°). On the right arm, put an M4×16 through the bracket and
   a washer into the 624 inner race. Fit a nyloc nut inside the boss
   cavity.
4. Flange:
   1. Drill the six pogo bores to the barrel size of the chosen pin.
   2. Press the pins in so that 1.0 mm stands proud of the floor.
   3. Solder the 6-core harness to the tails in the `Flange.pin_names`
      order: 0 = V12_TOOL, 1 = GND, 2 = BUS, 3 = AUX1, 4 = AUX2,
      5 = TOOL_ID. Pin *i* sits at 60·*i*° counter-clockwise, seen from
      the tool side.
   4. Fit the 3 × 6 mm dowel (stop pin) and the M5 ball plunger. Set the
      ball to stand 0.8 mm proud into the socket.
   5. Bolt the flange to the roll horn at mid-range (4 × M2 from inside
      the socket).

## 7. Cabling

* Chain A runs controller J4 → yaw (ID 1) → shoulder (ID 2) → elbow
  (ID 3).
* Chain B runs J5 → wrist pitch (ID 4) → wrist roll (ID 5).
* The tool harness runs from J6 to the flange pogo pins.
* All three cables leave the base through the rear slot above the pod.
  They make a service loop of at least 150 mm, enough for ±150° of yaw,
  and are tied to the turret's rear post.
* Up the links, the cables lie in the rear grooves and are held by the
  `cable_clip`s, which snap into the clip notches every 40 mm. At each
  pitch joint, leave a loop that covers the full joint range. Bend the
  arm through the limits before tying it down.
* At the roll joint, give the tool harness a loop of at least 120 mm
  around the roll servo body (±150°). Tie it to the anchor slot on the
  wrist bridge.

## 8. Tools

* **Tool contact PCB (all tools).**
  1. Populate it per `pcb/tool_contact.py` VARIANTS (also in `bom.csv`).
  2. Solder the tool harness to the top-side pads W1–W6.
  3. Bond the board into the plug recess with epoxy. The flat goes to the
     recess flat, and the pads face out.
  4. The pads must end flush with the plug face, within 0.1 mm. Check with
     a straight edge.
* **Gripper.**
  1. Fit the servo (ID 6) with its output up, then the lid.
  2. Bolt the `gripper_pinion` to the horn with the servo at mid-range.
  3. Slide both racks into the guide channels, teeth toward the pinion.
     Rack B is the same part turned 180°.
  4. With the fingers touching (closed), fit them to the racks: tenon in
     the pocket, M3×8 into the insert.
  5. Set Max_Torque_Limit to at most 15 %.
* **Knob turner.**
  1. Glue the diametric magnet into `knob_magnet_cap` and press the cap
     onto the shaft end.
  2. Fit the lower 608 in the body and the upper 608 in the top plate.
     Slide the shaft down through `knob_output_gear` and both bearings.
     Lock the gear and the `knob_collet_hub` with M3 set screws on a flat
     ground into the shaft.
  3. Mount the servo (ID 7) with `knob_servo_gear`.
  4. Screw the TPU `knob_collet` to the hub (3 × M3×8).
  5. Calibrate. With the collet free, the AS5600 angle and the servo angle
     divided by 2 must agree within 1°. The difference under load is the
     flexure deflection; torque ≈ 0.33 N·m/rad × deflection (estimate,
     calibrate with a torque gauge).
* **Button presser.**
  1. Fit the servo (ID 8) with its horn on +x.
  2. Bolt the cam on at max lift.
  3. Thread the FSR 400 tail down the plunger groove. Seat the sensor in
     the tip pocket and push on the TPU cap.
  4. Fit the return spring over the plunger, then slide the plunger up
     through the bridge.
* **Slider pusher.** Push the TPU pad into the pocket. This tool has no
  electronics apart from R_ID.
* **Tool rack.**
  1. Screw the rack to the bench within the arm's reach. Its fork openings
     face the arm.
  2. Hang each tool plug-up, with its collar groove on the fork lip and
     the key in the collar notch.
  3. Teach the four dock poses (see `firmware/INTERFACE.md` §5).

## 9. First power-up checklist

1. With no servos plugged in, connect USB only. The board enumerates and
   the LED is blue.
2. Connect 12 V with the E-stop **pressed**. VIN reads 11.5–12.5 V and the
   servo rail stays at 0 V (INA219).
3. Release the E-stop. The rail must still be off; it is enabled only by
   command.
4. Run the boot self-test (`firmware/INTERFACE.md` §4): enable, then check
   that pressing the E-stop drops the rail within 50 ms.
5. Plug in chain A, ping IDs 1–3, and read their positions. Then do the
   same for chain B (IDs 4–5).
6. Calibrate the joint zeros: put each link in its zero pose (`docs/design.md`
   §3) and store raw_zero. Write the servo angle limits.
7. Hang a 250 g test mass in the closed gripper, 70 mm beyond the flange,
   and check the holding currents outstretched: about 1.2 A at the shoulder
   servo (the tool is the 159 g gripper, the 250 g is the object).
