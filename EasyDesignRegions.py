# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD as App
import Part


def profile_regions(sketch):
    faces = [Part.Face(wire) for wire in sketch.Shape.Wires if wire.isClosed()]
    if not faces:
        return []
    # Open lines partition faces without becoming extrusion boundaries themselves.
    result, _ = faces[0].generalFuse(faces[1:] + list(sketch.Shape.Edges), 1e-7)
    return [face for face in result.Faces if face.Area > 1e-7 and face.isValid()]


def region_at(sketch, local_point):
    point = sketch.Placement.multVec(local_point)
    candidates = [face for face in profile_regions(sketch)
                  if face.isInside(point, 1e-7, True)]
    if not candidates:
        raise ValueError("The selected sketch region no longer exists.")
    return min(candidates, key=lambda face: face.Area)


def combined_profile(sketches):
    if len(sketches) < 2 or len(set(sketches)) != len(sketches):
        raise ValueError("Select at least two different sketches.")
    anchor = sketches[0].getGlobalPlacement()
    normal = anchor.Rotation.multVec(App.Vector(0, 0, 1))
    plane = Part.Plane(App.Vector(), App.Vector(0, 0, 1))
    faces = []
    for sketch in sketches:
        if not sketch.isDerivedFrom("Sketcher::SketchObject") or sketch.Document != sketches[0].Document:
            raise ValueError("Select sketches in the same document only.")
        placement = sketch.getGlobalPlacement()
        if (abs(normal.dot(placement.Rotation.multVec(App.Vector(0, 0, 1)))) < 1 - 1e-7
                or abs(normal.dot(placement.Base - anchor.Base)) > 1e-5):
            raise ValueError("The selected sketches must lie on the same plane. Use Loft for different planes.")
        wires = [wire for wire in sketch.Shape.Wires if wire.isClosed()]
        if not wires:
            raise ValueError("Each selected sketch must contain a closed profile.")
        profile = Part.makeFace(wires, "Part::FaceMakerBullseye")
        parent = placement.multiply(sketch.Placement.inverse())
        profile.transformShape(anchor.inverse().multiply(parent).toMatrix(), True)
        for face in profile.Faces:
            oriented = Part.Face(plane, face.OuterWire)
            for wire in face.Wires:
                if not wire.isSame(face.OuterWire):
                    oriented = oriented.cut(Part.Face(plane, wire))
            faces.extend(oriented.Faces)
    result = faces[0].multiFuse(faces[1:]).removeSplitter() if len(faces) > 1 else faces[0]
    if (result.isNull() or not result.isValid() or not result.Faces
            or len(result.extrude(App.Vector(0, 0, 1)).Solids) != 1):
        raise ValueError("The profiles must overlap or share an edge to form one solid.")
    return result


class RegionProfile:
    """Keep a selected planar region linked to its editable source sketch."""

    def onDocumentRestored(self, obj):
        if not obj.ViewObject or obj.ViewObject.Proxy is not None:
            return
        # Older files had no view proxy: their internal face was shown on load,
        # hiding the solid tip in a Body's Through display mode.
        obj.ViewObject.Proxy = 0
        body = obj.getParentGeoFeatureGroup()
        if body and body.Tip != obj:
            obj.ViewObject.Visibility = False
            if body.ViewObject.Visibility and body.Tip and body.Tip.Shape.Solids:
                body.Tip.ViewObject.Visibility = True

    def execute(self, obj):
        sketch = obj.SourceSketch
        edges = list(obj.ProfileEdges) if "ProfileEdges" in obj.PropertiesList else []
        if edges:
            wires = Part.makeCompound([sketch.Shape.getElement(name) for name in edges]).makeWires("").Wires
            faces = Part.makeFace(wires, "Part::FaceMakerBullseye").Faces
        else:
            faces = [region_at(sketch, obj.RegionPoint)]
        plane = Part.Plane(App.Vector(), App.Vector(0, 0, 1))
        normalized = []
        # Explicit local planes retain the sketch normal through any rotation.
        for face in faces:
            local = face.copy()
            local.transformShape(sketch.Placement.inverse().toMatrix(), True)
            oriented = Part.Face(plane, local.OuterWire)
            for wire in local.Wires:
                if not wire.isSame(local.OuterWire):
                    oriented = oriented.cut(Part.Face(plane, wire))
            normalized.append(oriented)
        shape = normalized[0] if len(normalized) == 1 else Part.makeCompound(normalized)
        body = obj.getParentGeoFeatureGroup()
        obj.Placement = App.Placement()
        obj.Shape = shape
        obj.Placement = body.getGlobalPlacement().inverse().multiply(sketch.getGlobalPlacement())
        if "ExtrusionNormal" in obj.PropertiesList:
            obj.ExtrusionNormal = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))

    def dumps(self):
        return None

    def loads(self, state):
        pass


class CombinedProfile(RegionProfile):
    def execute(self, obj):
        sketches = list(obj.SourceSketches)
        shape = combined_profile(sketches)
        body = obj.getParentGeoFeatureGroup()
        obj.Placement = App.Placement()
        obj.Shape = shape
        obj.Placement = body.getGlobalPlacement().inverse().multiply(sketches[0].getGlobalPlacement())
        obj.ExtrusionNormal = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))


def create_combined_profile(body, sketches):
    obj = body.newObject("PartDesign::FeaturePython", "CombinedProfile")
    obj.addProperty("App::PropertyLinkListGlobal", "SourceSketches", "456D Design")
    obj.addProperty("App::PropertyLinkListGlobal", "CoordinateParents", "456D Design")
    obj.addProperty("App::PropertyVector", "ExtrusionNormal", "456D Design")
    obj.SourceSketches = list(sketches)
    parents = []
    for sketch in sketches:
        parent = sketch.getParentGeoFeatureGroup()
        while parent:
            if parent != body and parent not in parents:
                parents.append(parent)
            parent = parent.getParentGeoFeatureGroup()
    obj.CoordinateParents = parents
    obj.Proxy = CombinedProfile()
    if obj.ViewObject:
        obj.ViewObject.Proxy = 0
    obj.Document.recompute()
    if obj.ViewObject:
        obj.ViewObject.Visibility = False
    return obj


def create_profile(body, sketch, point=None, edges=None):
    obj = body.newObject("PartDesign::FeaturePython", "SelectedRegion")
    obj.addProperty("App::PropertyLinkGlobal", "SourceSketch", "456D Design")
    obj.addProperty("App::PropertyVector", "RegionPoint", "456D Design")
    obj.addProperty("App::PropertyStringList", "ProfileEdges", "456D Design")
    obj.addProperty("App::PropertyVector", "ExtrusionNormal", "456D Design")
    obj.SourceSketch = sketch
    obj.RegionPoint = App.Vector(point) if point is not None else App.Vector()
    obj.ProfileEdges = list(edges or [])
    obj.Proxy = RegionProfile()
    if obj.ViewObject:
        obj.ViewObject.Proxy = 0
    obj.Document.recompute()
    if obj.ViewObject:
        obj.ViewObject.Visibility = False
    return obj
