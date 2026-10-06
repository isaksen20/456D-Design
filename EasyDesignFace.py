# SPDX-License-Identifier: LGPL-2.1-or-later

import math

import FreeCAD as App
import Part


PATTERNS = ("Circles", "Squares", "Hexagons")


def face_frame(face):
    if face.findPlane(1e-7) is None:
        raise ValueError("Select a planar face for Press/Pull or Mesh.")
    normal = face.normalAt(0, 0)
    return App.Placement(face.CenterOfMass, App.Rotation(App.Vector(0, 0, 1), normal))


def make_face_sketch(source, face_name):
    """Take an editable, independent snapshot of a planar solid face's wires."""
    if not hasattr(source, "Shape") or not source.Shape.Solids or not face_name.startswith("Face"):
        raise ValueError("Select a flat face on a solid to make a sketch.")
    body = source if source.isDerivedFrom("PartDesign::Body") else source.getParentGeoFeatureGroup()
    if body and not body.isDerivedFrom("PartDesign::Body"):
        body = None
    if source == body:
        source = body.Tip
    if source is None:
        raise ValueError("Select a flat face on a solid to make a sketch.")
    face = source.Shape.getElement(face_name)
    if not isinstance(face.Surface, Part.Plane):
        raise ValueError("Make sketch needs a flat face. Curved faces cannot form a planar sketch.")
    from draftmake.make_sketch import make_sketch

    frame = face_frame(face)
    local = face.copy()
    local.transformShape(frame.inverse().toMatrix(), True)
    parent = source.getGlobalPlacement().multiply(source.Placement.inverse())
    doc = source.Document
    if App.ActiveDocument != doc:
        raise ValueError("Select a face in the active document.")
    doc.openTransaction("Make sketch from face")
    try:
        if body is None:
            body = doc.addObject("PartDesign::Body", "FaceSketchBody")
        tip = body.Tip
        sketch = body.newObject("Sketcher::SketchObject", "FaceSketch")
        sketch.Label = "Sketch - " + source.Label + " " + face_name
        if make_sketch(local, addTo=sketch, autoconstraints=False, delete=False) is None:
            raise ValueError("This face's outline could not be converted to a sketch.")
        sketch.MapMode = "Deactivated"
        # Draft may choose either plane normal; retain its conversion placement.
        sketch.Placement = body.getGlobalPlacement().inverse().multiply(
            parent.multiply(frame).multiply(sketch.Placement))
        if tip:
            body.Tip = tip
        doc.recompute()
        if (sketch.GeometryCount != len(face.Edges) or not sketch.Shape.Wires
                or any(not wire.isClosed() for wire in sketch.Shape.Wires)):
            raise ValueError("The converted outline is not closed. No sketch was created.")
        if sketch.ViewObject:
            sketch.ViewObject.Visibility = True
        doc.commitTransaction()
        return sketch
    except Exception:
        doc.abortTransaction()
        raise


def pattern_faces(face, pattern, pitch, opening, border):
    if (not all(math.isfinite(value) for value in (pitch, opening, border))
            or pattern not in PATTERNS or pitch <= 0 or opening <= 0 or opening >= pitch or border < 0):
        raise ValueError("Opening must be smaller than spacing; border cannot be negative.")
    placement = face_frame(face)
    local = face.copy()
    local.Placement = placement.inverse().multiply(local.Placement)
    bounds = local.BoundBox
    step_y = pitch * math.sqrt(3) / 2 if pattern == "Hexagons" else pitch
    columns = max(1, int(math.ceil(bounds.XLength / pitch)))
    rows = max(1, int(math.ceil(bounds.YLength / step_y)))
    if columns * rows > 600:
        raise ValueError("Pattern is too dense. Increase spacing (maximum 600 cells).")
    boundary = Part.makeCompound(local.Wires)
    cells = []
    for row in range(rows):
        y = (bounds.YMin + bounds.YMax) / 2 + (row - (rows - 1) / 2.0) * step_y
        stagger = pitch / 2 if pattern == "Hexagons" and row % 2 else 0
        for column in range(columns):
            x = (bounds.XMin + bounds.XMax) / 2 + (column - (columns - 1) / 2.0) * pitch + stagger
            center = App.Vector(x, y, 0)
            if not local.isInside(center, 1e-7, True):
                continue
            if pattern == "Circles":
                cell = Part.Face(Part.Wire([Part.makeCircle(opening / 2, center)]))
            else:
                count = 4 if pattern == "Squares" else 6
                radius = opening / math.sqrt(2) if count == 4 else opening / 2
                angle = math.pi / 4 if count == 4 else 0
                points = [center + App.Vector(radius * math.cos(angle + i * 2 * math.pi / count),
                                             radius * math.sin(angle + i * 2 * math.pi / count), 0)
                          for i in range(count)]
                cell = Part.Face(Part.makePolygon(points + [points[0]]))
            # Checking the entire cell against every boundary also preserves existing holes.
            if cell.distToShape(boundary)[0] <= border + 1e-7:
                continue
            cell.Placement = placement.multiply(cell.Placement)
            cells.append(cell)
    if not cells:
        raise ValueError("No pattern cells fit. Reduce opening, spacing or border.")
    return cells


def make_result(base, face, distance, cells=None):
    if not math.isfinite(distance) or abs(distance) < 0.01:
        raise ValueError("Enter a nonzero distance.")
    direction = face_frame(face).Rotation.multVec(App.Vector(0, 0, 1)) * distance
    tools = [cell.extrude(direction) for cell in (cells if cells is not None else [face])]
    result = base.multiFuse(tools) if distance > 0 else base.cut(Part.makeCompound(tools))
    result = result.removeSplitter()
    if result.isNull() or len(result.Solids) != 1 or not result.isValid():
        raise ValueError("That distance would not leave one valid solid.")
    if abs(result.Volume - base.Volume) < 1e-7:
        raise ValueError("The extrusion does not intersect the solid.")
    return result


def _shape_in_frame(shape, source, target):
    source_frame = source.getGlobalPlacement().multiply(source.Placement.inverse())
    target_frame = target.getGlobalPlacement().multiply(target.Placement.inverse())
    relative = target_frame.inverse().multiply(source_frame)
    if not relative.isSame(App.Placement(), 1e-7):
        shape = shape.copy()
        shape.transformShape(relative.toMatrix(), True)
        # A compound retains the child transform when assigning Feature.Shape.
        shape = Part.makeCompound([shape])
    return shape


class FaceFeature:
    """Rebuild the face operation from its source and editable pattern properties."""

    def execute(self, obj):
        base, names = obj.SourceFace
        if base is None or not names:
            raise ValueError("The source face for this operation is missing.")
        face = base.Shape.getElement(names[0])
        cells = (pattern_faces(face, obj.Pattern, obj.Spacing.Value, obj.Opening.Value, obj.Border.Value)
                 if obj.Pattern != "None" else None)
        obj.Shape = _shape_in_frame(make_result(base.Shape, face, obj.Distance, cells), base, obj)

    def dumps(self):
        return None

    def loads(self, state):
        pass


class FacePreview:
    def __init__(self, source, face_name, distance=1.0, pattern=None, pitch=8.0, opening=5.0, border=2.0):
        import FreeCADGui as Gui

        if Gui.Control.activeDialog():
            raise ValueError("Close the current task first.")
        self.body = source if source.isDerivedFrom("PartDesign::Body") else source.getParentGeoFeatureGroup()
        if self.body and not self.body.isDerivedFrom("PartDesign::Body"):
            self.body = None
        # Use the tip's body-local geometry, never a Body link to its own new tip.
        if source == self.body:
            source = self.body.Tip
        if not source or (self.body and self.body.Tip != source):
            raise ValueError("Select a face on the body's current final solid.")
        if len(source.Shape.Solids) != 1:
            raise ValueError("Select a face on a single solid.")
        self.source = source
        self.doc = source.Document
        if self.doc.HasPendingTransaction:
            raise ValueError("Finish the current operation before Press/Pull or Mesh.")
        self.document_name = self.doc.Name
        self.face = source.Shape.getElement(face_name)
        self.placement = face_frame(self.face)
        self.cells = pattern_faces(self.face, pattern, pitch, opening, border) if pattern else None
        shape = make_result(source.Shape, self.face, distance, self.cells)
        self.view_provider = self.source.ViewObject
        self.original_visibility = self.view_provider.Visibility if self.view_provider else None
        self.active = False
        self.doc.openTransaction("Mesh face" if pattern else "Press/Pull face")
        try:
            kind = "PartDesign::FeaturePython" if self.body else "Part::FeaturePython"
            name = "MeshFace" if pattern else "PressPull"
            self.feature = self.body.newObject(kind, name) if self.body else self.doc.addObject(kind, name)
            self.feature.addProperty("App::PropertyLinkSub", "SourceFace", "Face operation")
            self.feature.SourceFace = (self.source, [face_name])
            if not self.body:
                self.feature.addProperty("App::PropertyLinkList", "CoordinateParents", "Face operation")
                parents = []
                parent = source.getParentGeoFeatureGroup()
                while parent:
                    parents.append(parent)
                    parent = parent.getParentGeoFeatureGroup()
                self.feature.CoordinateParents = parents
            self.feature.addProperty("App::PropertyFloat", "Distance", "Face operation")
            self.feature.Distance = distance
            self.feature.addProperty("App::PropertyEnumeration", "Pattern", "Mesh")
            self.feature.Pattern = ["None"] + list(PATTERNS)
            self.feature.Pattern = pattern or "None"
            for name, value in (("Spacing", pitch), ("Opening", opening), ("Border", border)):
                self.feature.addProperty("App::PropertyLength", name, "Mesh")
                setattr(self.feature, name, value)
            self.feature.Proxy = FaceFeature()
            if self.feature.ViewObject:
                self.feature.ViewObject.Proxy = 0
            self.feature.Shape = _shape_in_frame(shape, self.source, self.feature)
            self.doc.recompute()
            if self.view_provider:
                self.view_provider.Visibility = False
                self.feature.ViewObject.ShapeColor = self.view_provider.ShapeColor
            Gui.Selection.clearSelection()
            self.active = True
        except Exception:
            self.doc.abortTransaction()
            raise

    @property
    def signed_length(self):
        return float(self.feature.Distance)

    @property
    def cut(self):
        return self.signed_length < 0

    @property
    def base_direction(self):
        parent = self.source.getGlobalPlacement().multiply(self.source.Placement.inverse())
        normal = self.placement.Rotation.multVec(App.Vector(0, 0, 1))
        return parent.multVec(self.face.CenterOfMass), parent.Rotation.multVec(normal)

    def set_length(self, distance):
        shape = make_result(self.source.Shape, self.face, distance, self.cells)
        self.feature.Distance = distance
        self.feature.Shape = _shape_in_frame(shape, self.source, self.feature)

    def finish(self, accept):
        import FreeCADGui as Gui

        if not self.active:
            return
        if self.document_name not in App.listDocuments():
            self.active = False
            return
        if accept:
            self.doc.recompute()
            if ("Invalid" in self.feature.State or self.feature.Shape.isNull()
                    or len(self.feature.Shape.Solids) != 1 or not self.feature.Shape.isValid()):
                raise ValueError("The face operation is no longer valid. Adjust the distance or cancel.")
            self.doc.commitTransaction()
            selected = self.feature
        else:
            self.doc.abortTransaction()
            if self.view_provider:
                self.view_provider.Visibility = self.original_visibility
            selected = self.source
        self.active = False
        if App.ActiveDocument == self.doc:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(self.document_name, selected.Name)
        self.doc.recompute()
