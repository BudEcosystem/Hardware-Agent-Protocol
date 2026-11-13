"""Single source of truth for every BHMS Arm dimension.

All CAD parts, the MJCF generator, the torque budget and the BOM read
their numbers from here, so the printed arm and the simulated arm cannot
drift apart.  Lengths are millimetres, angles degrees, masses grams,
unless a name says otherwise.

Values marked ESTIMATE are not taken from a datasheet and must be checked
against a physical part before printing; everything else is either a
design choice or a datasheet value with the source named in the comment.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Printer:
    """FDM process parameters.  Clearances are applied by the CAD code."""

    nozzle: float = 0.4
    layer: float = 0.2
    # Radial clearance added to holes and pockets for a sliding/close fit.
    fit_clearance: float = 0.20
    # Radial interference for press fits of bearings (negative clearance).
    # Tune per printer with cad/out/tolerance_coupon.stl.
    press_fit: float = -0.05
    # Clearance for a part that must slide freely (bayonet lugs, rack).
    slide_clearance: float = 0.30
    # Walls/top/bottom shell thickness used in the mass model (3 perimeters).
    shell: float = 1.2
    infill: float = 0.30
    # Material density (g/cm^3).  PLA 1.24; PETG 1.27; TPU 1.21.
    density_pla: float = 1.24
    density_petg: float = 1.27
    density_tpu: float = 1.21
    # Rough throughput for the print-time estimate (mm^3/s of extrudate,
    # averaged over perimeters, infill and travel on a stock bed-slinger).
    flow_mm3_s: float = 7.0
    layer_overhead_s: float = 1.5


@dataclass(frozen=True)
class Servo:
    """Feetech STS3215 12 V variant (SO-100/SO-101 class)."""

    # Body envelope: datasheet 45.2 x 24.7 x 35.0 mm (L x W x H, H along
    # the output axis, horn not included).
    length: float = 45.2
    width: float = 24.7
    height: float = 35.0
    # Output spline axis distance from the front short face. ESTIMATE.
    spline_from_front: float = 11.3
    # Height of the output spline boss above the body top face. ESTIMATE.
    boss_height: float = 4.0
    boss_d: float = 9.0
    # Supplied aluminium disc horn. ESTIMATE (verify on the physical horn).
    horn_d: float = 21.0
    horn_thickness: float = 3.0
    horn_bolt_circle_d: float = 14.0
    horn_bolt_d: float = 2.0  # M2 screws
    # Cable exit on the back short face; channel kept clear.
    cable_exit_w: float = 8.0
    mass_g: float = 55.0  # datasheet
    stall_torque_nm: float = 2.94  # 30 kg*cm at 12 V, datasheet
    rated_torque_nm: float = 0.98  # ~1/3 of stall: continuous duty rule of thumb
    no_load_speed_rad_s: float = 4.7  # 0.222 s/60 deg at 12 V, datasheet
    stall_current_a: float = 2.7  # datasheet, 12 V variant
    idle_current_a: float = 0.15  # ESTIMATE
    encoder_counts: int = 4096
    bus_baud: int = 1_000_000


@dataclass(frozen=True)
class Bearing:
    """Deep-groove ball bearing (catalogue dimensions)."""

    name: str
    bore: float
    od: float
    width: float
    mass_g: float


BEARING_608 = Bearing("608-2RS", 8.0, 22.0, 7.0, 12.0)
BEARING_624 = Bearing("624-2RS", 4.0, 13.0, 5.0, 3.1)
BEARING_6806 = Bearing("6806-2RS", 30.0, 42.0, 7.0, 26.0)


@dataclass(frozen=True)
class Gear:
    """Printed spur gear pair, module m.  Ratio = gear_teeth / pinion_teeth."""

    module: float = 2.0
    pinion_teeth: int = 17  # >= 17 avoids undercut at 20 deg
    gear_teeth: int = 34
    face_width: float = 14.0
    pressure_angle_deg: float = 20.0
    backlash: float = 0.15  # tooth-thickness reduction per flank (mm)
    efficiency: float = 0.92  # printed spur pair, greased; conservative

    @property
    def ratio(self) -> float:
        return self.gear_teeth / self.pinion_teeth

    @property
    def center_distance(self) -> float:
        return self.module * (self.pinion_teeth + self.gear_teeth) / 2.0


@dataclass(frozen=True)
class Joint:
    name: str
    lower_deg: float
    upper_deg: float
    ratio: float  # servo turns per joint turn
    servo_id: int

    @property
    def servo_span_deg(self) -> float:
        return (self.upper_deg - self.lower_deg) * self.ratio


@dataclass(frozen=True)
class Arm:
    """Kinematic layout.  Zero pose is the 'candle': every link vertical."""

    base_height: float = 70.0  # table to turret interface plane
    shoulder_height: float = 80.0  # turret plane to shoulder axis
    l_upper: float = 180.0  # shoulder axis to elbow axis
    l_fore: float = 140.0  # elbow axis to wrist-pitch axis
    # Wrist-pitch axis to tool-flange face (socket floor).  Long enough for
    # the roll servo to sit beyond the swept envelope of the pitch servo.
    l_wrist: float = 80.0
    flange_floor: float = 6.0  # flange floor thickness under the socket
    wrist_bridge: tuple[float, float] = (25.0, 31.0)  # bridge z-span, wrist frame
    base_d: float = 130.0
    turret_d: float = 110.0
    link_width: float = 34.0  # outer width (along joint axis)
    link_depth: float = 32.0  # outer depth (in the swing plane)
    link_wall: float = 2.4
    cable_channel: tuple[float, float] = (10.0, 7.0)
    payload_g: float = 250.0
    payload_offset: float = 50.0  # payload CoM beyond the flange face
    joints: tuple[Joint, ...] = (
        Joint("base_yaw", -150.0, 150.0, 1.0, 1),
        Joint("shoulder_pitch", -75.0, 95.0, 2.0, 2),
        Joint("elbow_pitch", -5.0, 125.0, 2.0, 3),
        Joint("wrist_pitch", -100.0, 100.0, 1.0, 4),
        Joint("wrist_roll", -150.0, 150.0, 1.0, 5),
    )

    @property
    def reach(self) -> float:
        """Shoulder (= yaw) axis to flange face, fully outstretched."""
        return self.l_upper + self.l_fore + self.l_wrist


@dataclass(frozen=True)
class Flange:
    """Universal quick-change tool flange (3-lug bayonet + 6 pogo pins)."""

    socket_od: float = 56.0
    socket_id: float = 42.0  # bore that receives the tool plug
    socket_depth: float = 12.0  # floor top to socket mouth
    lug_count: int = 3
    lug_width_deg: float = 24.0
    lug_radial: float = 3.0
    lug_thickness: float = 3.0
    lock_angle_deg: float = 30.0  # twist from entry to locked
    plug_od: float = 41.4  # tool plug, slide fit in socket_id
    lip_height: float = 8.7  # lip top sits 0.3 mm under the lugs
    collar_z0: float = 12.5  # collar starts 0.5 mm above the socket mouth
    collar_r: float = 24.0
    collar_height: float = 10.0
    collar_groove: tuple[float, float, float] = (15.5, 19.5, 20.0)  # z0, z1, root radius
    rack_key_w: float = 4.0  # anti-rotation key/notch width at tool angle +90 deg
    detent_ball_d: float = 3.0  # M5 ball spring plunger (3 mm ball class)
    detent_thread: float = 5.0
    detent_angle_deg: float = 30.0
    detent_z: float = 4.4
    stop_pin_r: float = 17.5
    stop_pin_d: float = 3.0
    lug_angles_deg: tuple[float, ...] = (90.0, 210.0, 330.0)
    neck_clearance: float = 0.3
    pogo_count: int = 6
    pogo_circle_r: float = 12.0  # outside the horn (r 10.5) and its bolt heads
    # Through-hole spring contact, 2.0 mm barrel, ~8 mm long (Mill-Max 0906
    # class).  Exact MPN selected at order time; the hole is drilled to the
    # chosen barrel diameter after printing.
    pogo_barrel_d: float = 2.0
    pogo_length: float = 8.0
    pogo_protrusion: float = 1.0  # compressed stroke engaged on the pad
    # Pin i sits at flange angle 60*i deg (counter-clockwise about +z,
    # looking from the arm toward the tool).
    pin_names: tuple[str, ...] = ("V12_TOOL", "GND", "BUS", "AUX1", "AUX2", "TOOL_ID")
    contact_pcb_d: float = 28.0
    # Keying flat of the contact PCB: chord at this distance from the axis,
    # normal at this tool-frame angle (between pads 3 and 4, clear of both).
    contact_pcb_flat_dist: float = 12.6
    contact_pcb_flat_angle_deg: float = 210.0
    contact_pcb_t: float = 1.6


@dataclass(frozen=True)
class Tools:
    gripper_stroke: float = 30.0  # per jaw; 0..60 mm opening
    gripper_pinion_module: float = 1.0
    gripper_pinion_teeth: int = 24
    gripper_finger_len: float = 55.0
    collet_bore_min: float = 8.0
    collet_bore_max: float = 28.0
    collet_fingers: int = 6
    magnet_d: float = 6.0  # diametric N35 6 x 2.5 mm for AS5600
    magnet_h: float = 2.5
    magnet_to_sensor_gap: float = 1.5  # AS5600 datasheet range 0.5..3 mm
    presser_stroke: float = 8.0
    presser_tip_d: float = 10.0
    fsr_d: float = 7.6  # Interlink FSR 400 active area diameter (5.6) + margin
    pusher_pad: tuple[float, float] = (40.0, 12.0)
    # Tool identity: R_ID on the tool contact PCB, read through the 10 k
    # pull-up on the controller (ADC ratio = R_ID / (10k + R_ID)).  Open
    # circuit = no tool; < 0.04 = short/fault.  Codes 5-8 are reserved.
    tool_ids: tuple[tuple[int, str, float], ...] = (
        (1, "gripper", 1_000.0),
        (2, "knob_turner", 3_300.0),
        (3, "button_presser", 10_000.0),
        (4, "slider_pusher", 33_000.0),
        (5, "reserved", 2_000.0),
        (6, "reserved", 5_600.0),
        (7, "reserved", 18_000.0),
        (8, "reserved", 100_000.0),
    )
    tool_id_pullup: float = 10_000.0


@dataclass(frozen=True)
class Clamp:
    table_max: float = 45.0  # maximum table-top thickness
    throat: float = 55.0
    screw_d: float = 8.0  # M8 thumbscrew
    width: float = 40.0


@dataclass(frozen=True)
class Controller:
    """Controller PCB outline and the connector positions that the base
    electronics pod must line up with.  Board frame: u along the long
    edge, v along the short edge, v=0 is the rear edge (faces the cable
    side of the pod), origin at the rear-left corner seen from above."""

    board_u: float = 80.0
    board_v: float = 56.0
    hole_inset: float = 3.5
    hole_d: float = 3.2  # M3
    standoff_h: float = 5.0
    # Rear-edge connector centres along u (mm) and their panel cutouts
    # (width, height above board top).
    usb_u: float = 62.0
    usb_cut: tuple[float, float] = (10.0, 4.5)
    power_u: float = 14.0
    power_cut: tuple[float, float] = (12.0, 11.0)
    estop_u: float = 38.0
    estop_cut: tuple[float, float] = (11.0, 7.0)
    # Front-edge (arm side) connector centres along u.
    servo1_u: float = 20.0
    servo2_u: float = 32.0
    tool_u: float = 56.0


@dataclass(frozen=True)
class Params:
    printer: Printer = field(default_factory=Printer)
    servo: Servo = field(default_factory=Servo)
    gear: Gear = field(default_factory=Gear)
    arm: Arm = field(default_factory=Arm)
    flange: Flange = field(default_factory=Flange)
    tools: Tools = field(default_factory=Tools)
    clamp: Clamp = field(default_factory=Clamp)
    controller: Controller = field(default_factory=Controller)


DEFAULT = Params()


def joint(name: str, p: Params = DEFAULT) -> Joint:
    for j in p.arm.joints:
        if j.name == name:
            return j
    raise KeyError(name)
