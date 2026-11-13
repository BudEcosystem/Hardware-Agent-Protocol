"""Base: base plate with yaw-servo cradle, shell with 6806 bearing deck and
controller pod, pod lid.  Frame: world (z = 0 is the table top, yaw axis
is z).  The yaw servo spline lies on the z axis and its body extends
toward -x (the rear, where the controller pod and cable exits are).
"""

from __future__ import annotations

from build123d import Location, Part, Pos, Rot

from common import (
    CLEARANCE_D,
    INSERT_HOLE_D,
    bolt_circle,
    box,
    cyl_x,
    cyl_z,
    horn_face_z,
    servo_cradle,
    union,
)
from params import BEARING_6806, Params

SHELL_WALL = 3.0
PLATE_T = 5.0
DECK_T = 8.0
SPIGOT_LEN = BEARING_6806.width + 0.5
TONGUE_X = (-150.0, -40.0)
TONGUE_Y = 45.0
POD_X = (-127.0, -55.0)
POD_Y = 46.0
POD_TOP = 42.0
POD_WALL = 2.5
CLAMP_PIN_X = -139.0
LID_SCREW_X = (POD_X[0] + 5.0, -80.0)
SHELL_SCREW_CIRCLE = 116.0


def deck_top(p: Params) -> float:
    """World z of the deck top (0.5 mm below the turret disc)."""
    return p.arm.base_height - 0.5


def yaw_horn_face(p: Params) -> float:
    """World z of the yaw servo horn face (= turret spigot bottom)."""
    return p.arm.base_height - SPIGOT_LEN


def yaw_servo_location(p: Params) -> Location:
    """Servo frame -> world.  Output +z, body toward -x."""
    return Pos(0, 0, yaw_horn_face(p) - horn_face_z(p)) * Rot(Z=0)


def pcb_origin(p: Params) -> tuple[float, float, float]:
    """World position of the board-frame origin (rear-left, board top).

    Board u runs along world -y ... +y; board v runs from the rear edge
    (world x near POD_X[0]) toward the arm (+x)."""
    c = p.controller
    x_rear = POD_X[0] + POD_WALL + 1.5
    z_top = PLATE_T + c.standoff_h + 1.6
    return (x_rear, -c.board_u / 2, z_top)


def pcb_hole_positions(p: Params) -> list[tuple[float, float]]:
    """Board-frame (u, v) of the four M3 mounting holes."""
    c = p.controller
    i = c.hole_inset
    return [(i, i), (c.board_u - i, i), (i, c.board_v - i), (c.board_u - i, c.board_v - i)]


def base_plate(p: Params) -> Part:
    r = p.arm.base_d / 2
    plate = cyl_z(r, 0.0, PLATE_T) + box(TONGUE_X[0], TONGUE_X[1], -TONGUE_Y, TONGUE_Y, 0.0, PLATE_T)
    # Stiffening ribs under the tongue (clamp load path) on the top side.
    ribs = [box(TONGUE_X[0] + 2, -60.0, y - 2.0, y + 2.0, PLATE_T, PLATE_T + 4.0) for y in (-TONGUE_Y + 2, TONGUE_Y - 2)]
    # Yaw servo cradle, standing on the plate.
    solid, cut = servo_cradle(p)
    loc = yaw_servo_location(p)
    cradle = loc * solid
    # Pedestal from the plate up to the cradle floor.
    cb = cradle.bounding_box()
    pedestal = box(cb.min.X, cb.max.X, cb.min.Y, cb.max.Y, PLATE_T - 0.01, cb.min.Z + 0.01)
    part = union([plate, cradle, pedestal] + ribs) - loc * cut
    # Clamp locating hole, shell screws, pod standoff holes, rubber feet.
    part -= cyl_z(4.6, -1, PLATE_T + 1, x=CLAMP_PIN_X)
    for x, y in bolt_circle(4, SHELL_SCREW_CIRCLE, 45.0):
        part -= cyl_z(CLEARANCE_D[4.0] / 2, -1, PLATE_T + 1, x, y)
        part -= cyl_z(4.0, -1, 3.0, x, y)  # counterbore for M4 head (flat under base)
    ox, oy, _ = pcb_origin(p)
    for u, v in pcb_hole_positions(p):
        x, y = ox + v, oy + u
        part += cyl_z(3.5, PLATE_T - 0.01, PLATE_T + p.controller.standoff_h, x, y)
        part -= cyl_z(INSERT_HOLE_D[3.0] / 2, PLATE_T - 2.0, PLATE_T + p.controller.standoff_h + 0.01, x, y)
    for x, y in [(45, 45), (45, -45), (-45, 45), (-45, -45), (TONGUE_X[0] + 8, 37), (TONGUE_X[0] + 8, -37)]:
        part -= cyl_z(5.2, -0.01, 1.0, x, y)  # 10 mm adhesive rubber foot recess
    # Pod cable pass-through into the shell is in the shell itself.
    return part


def base_shell(p: Params) -> Part:
    r = p.arm.base_d / 2
    z_top = deck_top(p)
    z_deck = z_top - DECK_T
    tube = cyl_z(r, PLATE_T, z_top) - cyl_z(r - SHELL_WALL, PLATE_T - 1, z_deck)
    pod = box(POD_X[0], POD_X[1], -POD_Y, POD_Y, PLATE_T, POD_TOP)
    pod_void = box(POD_X[0] + POD_WALL, POD_X[1] - POD_WALL, -POD_Y + POD_WALL, POD_Y - POD_WALL, PLATE_T - 1, POD_TOP + 1)
    shell = (tube + pod) - pod_void
    shell -= cyl_z(r - SHELL_WALL, PLATE_T - 1, z_deck)
    # Opening between the pod and the tube interior for the internal cables.
    shell -= box(-r - 2, -r + 12, -30.0, 30.0, PLATE_T + 1.0, POD_TOP - 2.0)
    # Bearing seat (press fit) with a 1 mm lip under the outer race.
    b = BEARING_6806
    shell -= cyl_z(b.od / 2 + p.printer.press_fit, z_top - b.width, z_top + 0.01)
    shell -= cyl_z(36.0 / 2, z_deck - 1, z_top)
    # Shell screw bosses (M4 heat-set inserts from below).
    for x, y in bolt_circle(4, SHELL_SCREW_CIRCLE, 45.0):
        shell += cyl_z(5.5, PLATE_T, PLATE_T + 14.0, x, y)
        shell -= cyl_z(INSERT_HOLE_D[4.0] / 2, PLATE_T - 0.01, PLATE_T + 9.0, x, y)
    # Rear panel cutouts lined up with the controller connectors.
    c = p.controller
    ox, oy, oz = pcb_origin(p)
    x_wall = (POD_X[0] - 1, POD_X[0] + POD_WALL + 1)
    for u, (w, h) in ((c.usb_u, c.usb_cut), (c.power_u, c.power_cut), (c.estop_u, c.estop_cut)):
        y = oy + u
        shell -= box(x_wall[0], x_wall[1], y - w / 2, y + w / 2, oz - 0.6, oz + h)
    # Arm cable entry (service loop for +-150 deg yaw) high on the rear of
    # the tube, with a strain-relief tie bar.
    shell -= box(-r - 2, -r + SHELL_WALL + 2, -9.0, 9.0, POD_TOP + 3.0, POD_TOP + 13.0)
    shell -= cyl_x(1.6, -r - 5, -r + 15, y=-12.0, z=POD_TOP + 7.0)
    shell -= cyl_x(1.6, -r - 5, -r + 15, y=12.0, z=POD_TOP + 7.0)
    # Pod lid screw bosses.
    for x in LID_SCREW_X:
        for y in (-POD_Y + 5.0, POD_Y - 5.0):
            shell += box(x - 4, x + 4, y - 4, y + 4, POD_TOP - 10.0, POD_TOP)
            shell -= cyl_z(INSERT_HOLE_D[3.0] / 2, POD_TOP - 6.0, POD_TOP + 0.01, x, y)
    # Ventilation slots on the pod sides.
    for i in range(5):
        x = POD_X[0] + 18.0 + i * 8.0
        for ys in (-1, 1):
            shell -= box(x, x + 3.0, ys * POD_Y - 3, ys * POD_Y + 3, PLATE_T + 14.0, POD_TOP - 12.0)
    return shell


def pod_lid(p: Params) -> Part:
    r = p.arm.base_d / 2
    lid = box(POD_X[0], POD_X[1], -POD_Y, POD_Y, POD_TOP, POD_TOP + 2.4) - cyl_z(r + 0.3, POD_TOP - 1, POD_TOP + 3)
    for x in LID_SCREW_X:
        for y in (-POD_Y + 5.0, POD_Y - 5.0):
            lid -= cyl_z(CLEARANCE_D[3.0] / 2, POD_TOP - 1, POD_TOP + 3, x, y)
    # Light pipe hole above the status LED (board position in pcb/gen_board.py).
    ox, oy, _ = pcb_origin(p)
    lid -= cyl_z(2.6, POD_TOP - 1, POD_TOP + 3, ox + 20.0, oy + 44.0)
    # Label recess.
    lid -= box(POD_X[0] + 12, POD_X[0] + 50, -30, 30, POD_TOP + 1.8, POD_TOP + 2.5)
    return lid


def tongue_clamp_point(p: Params) -> tuple[float, float, float]:
    return (CLAMP_PIN_X, 0.0, PLATE_T)
