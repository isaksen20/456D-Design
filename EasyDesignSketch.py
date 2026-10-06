# SPDX-License-Identifier: LGPL-2.1-or-later

"""Planar sketch geometry shared by viewport previews and committed sketches."""

import math

import FreeCAD as App
import Part


TOOLS = {
    "Sketcher_CreateRectangle": "rectangle",
    "Sketcher_CreateCircle": "circle",
    "Sketcher_CreatePolyline": "line",
    "Sketcher_CreateEllipseByCenter": "ellipse",
    "Sketcher_CreateRegularPolygon": "polygon",
    "Sketcher_CreateBSpline": "spline",
    "Sketcher_CreateArc": "center_arc",
    "Sketcher_Create3PointArc": "arc3",
    "Sketcher_CreateFillet": "sketch_fillet",
    "Sketcher_Trimming": "trim",
    "Sketcher_Extend": "extend",
    "Sketcher_Offset": "offset",
}
EDIT_TOOLS = ("sketch_fillet", "trim", "extend", "offset")


def geometry(kind, points, sides=6):
    points = [App.Vector(p.x, p.y, 0) for p in points]
    a, b = points[:2]
    delta = b - a
    if delta.Length < .01:
        raise ValueError("The points must be at least 0.01 mm apart.")
    if kind == "line":
        return [Part.LineSegment(a, b)]
    if kind == "rectangle":
        if abs(delta.x) < .01 or abs(delta.y) < .01:
            raise ValueError("The rectangle needs a width and height.")
        vertices = [a, App.Vector(b.x, a.y, 0), b, App.Vector(a.x, b.y, 0)]
        return [Part.LineSegment(p, vertices[(i + 1) % 4]) for i, p in enumerate(vertices)]
    if kind == "circle":
        return [Part.Circle(a, App.Vector(0, 0, 1), delta.Length)]
    if kind == "polygon":
        count = int(sides)
        if count != sides or not 3 <= count <= 128:
            raise ValueError("Choose between 3 and 128 polygon sides.")
        angle = math.atan2(delta.y, delta.x)
        vertices = [a + App.Vector(math.cos(angle + i * math.tau / count),
                                   math.sin(angle + i * math.tau / count), 0) * delta.Length
                    for i in range(count)]
        return [Part.LineSegment(p, vertices[(i + 1) % count]) for i, p in enumerate(vertices)]
    if kind == "arc3":
        if len(points) != 3 or delta.cross(points[2] - a).Length < 1e-7:
            raise ValueError("Place the arc's middle point away from the straight chord.")
        return [Part.Arc(a, points[2], b)]
    if kind == "center_arc":
        if len(points) != 3:
            raise ValueError("Choose the end of the arc.")
        end = points[2] - a
        if end.Length < .01:
            raise ValueError("The arc needs an end point.")
        start = math.atan2(delta.y, delta.x)
        sweep = (math.atan2(end.y, end.x) - start) % math.tau
        if sweep < 1e-7:
            raise ValueError("The arc needs a nonzero sweep.")
        circle = Part.Circle(a, App.Vector(0, 0, 1), delta.Length)
        return [Part.ArcOfCircle(circle, start, start + sweep)]
    if kind == "ellipse":
        if len(points) != 3:
            raise ValueError("Choose the ellipse's second radius.")
        axis = delta / delta.Length
        perpendicular = App.Vector(-axis.y, axis.x, 0)
        second = abs((points[2] - a).dot(perpendicular))
        if second < .01:
            raise ValueError("Both ellipse radii must be at least 0.01 mm.")
        # OCC requires the major radius first; either user-picked axis may be larger.
        major = axis if delta.Length >= second else perpendicular
        ellipse = Part.Ellipse(a, max(delta.Length, second), min(delta.Length, second))
        ellipse.XAxis = major
        return [ellipse]
    if kind == "spline":
        closed = len(points) > 3 and (points[-1] - points[0]).Length < 1e-7
        values = points[:-1] if closed else points
        if any((p - q).Length < .01 for p, q in zip(values, values[1:])):
            raise ValueError("Spline points must be at least 0.01 mm apart.")
        spline = Part.BSplineCurve()
        spline.interpolate(Points=values, PeriodicFlag=closed)
        return [spline]
    raise ValueError("Unknown sketch tool: " + kind)


def preview(kind, points, sides=6):
    try:
        curves = geometry(kind, points, sides)
        return [curve.toShape().discretize(Deflection=.05) for curve in curves]
    except (ValueError, RuntimeError, Part.OCCError):
        return [points]


def offset_geometry(sketch, index, distance):
    if abs(distance) < .01:
        raise ValueError("Enter a nonzero offset.")
    indexed = [(i, g.toShape()) for i, g in enumerate(sketch.Geometry) if not sketch.getConstruction(i)]
    target = next((edge for i, edge in indexed if i == index), None)
    if target is None:
        raise ValueError("Choose a non-construction outline to offset.")
    edges = [edge for _, edge in indexed]
    wires = [Part.Wire(group) for group in Part.sortEdges(edges)]
    wire = next((w for w in wires if any(e.isSame(target) for e in w.Edges)), None)
    if wire is None:
        raise ValueError("Choose a non-construction outline to offset.")
    if len(wire.Edges) == 1 and isinstance(sketch.Geometry[index], Part.LineSegment):
        line = sketch.Geometry[index]
        direction = (line.EndPoint - line.StartPoint).normalize()
        shift = App.Vector(direction.y, -direction.x, 0) * distance
        return [Part.LineSegment(line.StartPoint + shift, line.EndPoint + shift)]
    result = (Part.Face(wire) if wire.isClosed() else wire).makeOffset2D(distance, join=0)
    if result.isNull() or not result.isValid() or not result.Edges:
        raise ValueError("That offset does not produce a valid outline.")
    from DraftGeomUtils import orientEdge
    return [orientEdge(edge, App.Vector(0, 0, 1), make_arc=True) for edge in result.Edges]


def extend_delta(sketch, index, point, endpoint):
    curve = sketch.Geometry[index]
    if not isinstance(curve, Part.LineSegment):
        raise ValueError("Choose a line endpoint to extend.")
    start, end = curve.StartPoint, curve.EndPoint
    direction = (end - start).normalize()
    return (point - end).dot(direction) if endpoint == 2 else (start - point).dot(direction)


def fillet_pair(sketch, index, endpoint):
    curve = sketch.Geometry[index]
    if not isinstance(curve, Part.LineSegment) or endpoint not in (1, 2):
        raise ValueError("Choose a corner between two sketch lines.")
    corner = curve.StartPoint if endpoint == 1 else curve.EndPoint
    others = [(i, g) for i, g in enumerate(sketch.Geometry) if i != index and
              not sketch.getConstruction(i) and isinstance(g, Part.LineSegment) and
              min((g.StartPoint - corner).Length, (g.EndPoint - corner).Length) < 1e-6]
    if len(others) != 1:
        raise ValueError("Choose a corner shared by exactly two sketch lines.")
    other_index, other = others[0]
    return other_index, (curve.StartPoint + curve.EndPoint) * .5, (other.StartPoint + other.EndPoint) * .5


def fillet_preview(sketch, index, endpoint, radius):
    other, first, second = fillet_pair(sketch, index, endpoint)
    curve = sketch.Geometry[index]
    corner = curve.StartPoint if endpoint == 1 else curve.EndPoint
    u, v = (first - corner).normalize(), (second - corner).normalize()
    angle = math.acos(max(-1, min(1, u.dot(v))))
    if radius < .01 or angle < 1e-7 or abs(angle - math.pi) < 1e-7:
        raise ValueError("This corner cannot be filleted.")
    setback = radius / math.tan(angle / 2)
    if setback >= min(curve.length(), sketch.Geometry[other].length()):
        raise ValueError("The fillet radius is too large for this corner.")
    center = corner + (u + v).normalize() * (radius / math.sin(angle / 2))
    middle = center + (corner - center).normalize() * radius
    return [Part.Arc(corner + u * setback, middle, corner + v * setback)]


def edit(sketch, kind, target, value=1):
    index, point, endpoint = target
    if kind == "trim":
        sketch.trim(index, point)
    elif kind == "extend":
        curve = sketch.Geometry[index]
        if not isinstance(curve, Part.LineSegment) or curve.length() + value < .01:
            raise ValueError("That extension would remove the line.")
        sketch.extend(index, value, endpoint)
    elif kind == "sketch_fillet":
        if value < .01:
            raise ValueError("Enter a positive fillet radius.")
        fillet_preview(sketch, index, endpoint, value)
        other, first, second = fillet_pair(sketch, index, endpoint)
        sketch.fillet(index, other, first, second, value)
    elif kind == "offset":
        sketch.addGeometry(offset_geometry(sketch, index, value), False)
    else:
        raise ValueError("Unknown sketch edit tool.")
    sketch.Document.recompute()
