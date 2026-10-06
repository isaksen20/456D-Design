# SPDX-License-Identifier: LGPL-2.1-or-later

from collections import deque
import math


class DirectionTracker:
    """Infer recent drag intent with different axis-entry and exit tolerances."""

    def __init__(self):
        self.samples = deque()
        self.travel = 0.0
        self.mode = None

    def feed(self, dx, dy):
        length = math.hypot(dx, dy)
        if not length:
            return self.mode
        self.samples.append((dx, dy, length))
        self.travel += length
        while len(self.samples) > 1 and self.travel - self.samples[0][2] >= 24:
            self.travel -= self.samples.popleft()[2]
        x = abs(sum(sample[0] for sample in self.samples))
        y = abs(sum(sample[1] for sample in self.samples))
        if math.hypot(x, y) < 6:
            return self.mode
        if self.mode == "horizontal" and y <= x * math.tan(math.radians(32)):
            return self.mode
        if self.mode == "vertical" and x <= y * math.tan(math.radians(32)):
            return self.mode
        tolerance = math.tan(math.radians(18))
        self.mode = "horizontal" if y <= x * tolerance else "vertical" if x <= y * tolerance else "free"
        return self.mode


def orbit_pivot(view, placement):
    import FreeCAD as App

    node = view.getCameraNode()
    position = App.Vector(*node.position.getValue().getValue())
    forward = view.getCameraOrientation().multVec(App.Vector(0, 0, -1))
    distance = float(node.focalDistance.getValue())
    focus = position + forward * distance
    normal = placement.Rotation.multVec(App.Vector(0, 0, 1))
    denominator = forward.dot(normal)
    if abs(denominator) > 1e-6:
        intersection = (placement.Base - position).dot(normal) / denominator
        if 0 < intersection <= distance * 4:
            return position + forward * intersection, normal
    return focus - normal * (focus - placement.Base).dot(normal), normal


def level_orientation(orientation, normal):
    """Remove camera roll relative to the grid without changing viewing direction."""
    import FreeCAD as App

    forward = orientation.multVec(App.Vector(0, 0, -1))
    up = orientation.multVec(App.Vector(0, 1, 0))
    grid_up = normal - forward * normal.dot(forward)
    # A top/bottom view has no unique horizon; retain its current heading.
    if grid_up.Length < 1e-6:
        return orientation
    grid_up.normalize()
    angle = math.degrees(math.atan2(forward.dot(up.cross(grid_up)), up.dot(grid_up)))
    correction = App.Rotation(forward, angle)
    return correction.multiply(orientation)


def rotate_camera(view, pivot, normal, mode, dx, dy):
    import FreeCAD as App

    node = view.getCameraNode()
    position = App.Vector(*node.position.getValue().getValue())
    orientation = level_orientation(view.getCameraOrientation(), normal)
    offset = position - pivot
    sensitivity = 0.35
    if mode == "horizontal":
        rotation = App.Rotation(normal, -dx * sensitivity)
    elif mode == "vertical":
        axis = normal.cross(offset)
        if axis.Length < 1e-8:
            axis = orientation.multVec(App.Vector(1, 0, 0))
        rotation = App.Rotation(axis, -dy * sensitivity)
    else:
        yaw = App.Rotation(normal, -dx * sensitivity)
        right = yaw.multVec(orientation.multVec(App.Vector(1, 0, 0)))
        rotation = App.Rotation(right, -dy * sensitivity).multiply(yaw)
    position = pivot + rotation.multVec(offset)
    # The GUI setter may animate and reposition the camera asynchronously.
    # Interactive dragging must update both pose fields without that animation.
    node.orientation.setValue(*level_orientation(rotation.multiply(orientation), normal).Q)
    node.position.setValue(position.x, position.y, position.z)
