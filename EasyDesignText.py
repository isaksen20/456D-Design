# SPDX-License-Identifier: LGPL-2.1-or-later

"""Editable font outlines and exact cylindrical text using OpenCascade curves."""

import math
from pathlib import Path
import subprocess

import FreeCAD as App
import Part


def is_text(obj):
    return obj is not None and "EasyDesignText" in obj.PropertiesList


def font_file(family):
    result = subprocess.run(["fc-match", "-f", "%{file}", family],
                            capture_output=True, text=True, check=True)
    path = result.stdout.strip()
    if not Path(path).is_file():
        raise ValueError("No outline font file was found for this typeface.")
    return path


def flat_faces(string, font, size):
    if not string.strip() or size <= 0 or not math.isfinite(size):
        raise ValueError("Enter text and a positive font size.")
    if len(string) > 256:
        raise ValueError("Use at most 256 characters per text sketch.")
    if not Path(font).is_file():
        raise ValueError("The saved font file is missing. Choose another typeface.")
    faces = []
    for row, line in enumerate(string.splitlines()):
        for char in Part.makeWireString(line, font, float(size), 0):
            if not char:
                continue
            letters = Part.makeFace(char, "Part::FaceMakerBullseye").Faces
            for face in letters:
                face.translate(App.Vector(0, -row * size * 1.4, 0))
                faces.append(face)
    if not faces or any(not face.isValid() for face in faces):
        raise ValueError("This text/font cannot produce closed letter outlines.")
    return faces


def cylinder_frame(target, name):
    if target.isDerivedFrom("PartDesign::Body"):
        target = target.Tip
    if target is None or not hasattr(target, "Shape") or not name.startswith("Face"):
        raise ValueError("Select the curved side of a cylinder.")
    face = target.Shape.getElement(name)
    if not isinstance(face.Surface, Part.Cylinder):
        raise ValueError("Wrap text needs a cylindrical side face, not a flat cap or cone.")
    surface = face.Surface
    parent = target.getGlobalPlacement().multiply(target.Placement.inverse())
    axis = App.Vector(surface.Axis)
    _, _, low, high = face.ParameterRange
    # OCC may represent the same cylinder with a reversed axis and negative V.
    # Anchor the frame at a real end of the trimmed side, rather than assuming V>0.
    reverse = axis.dot(target.Placement.Rotation.multVec(App.Vector(0, 0, 1))) < 0
    origin = surface.Center + axis * (high if reverse else low)
    if reverse:
        axis = -axis
    frame = App.Placement(origin, App.Rotation(App.Vector(0, 0, 1), axis))
    return parent.multiply(frame), surface.Radius


def wrapped_faces(faces, radius, spiral=0, span=0, start=0, height=0):
    if radius <= 0 or not -80 <= spiral <= 80 or not 0 <= span <= 3600:
        raise ValueError("Use a positive radius, spiral angle between -80 and 80, and span up to 3600 degrees.")
    bounds = Part.makeCompound(faces).BoundBox
    angle = math.radians(spiral)
    cosine, sine = math.cos(angle), math.sin(angle)
    scale = math.radians(span) * radius / (bounds.XLength * cosine) if span else 1.0
    surface = Part.Cylinder()
    surface.Radius = radius
    result = []
    # Affine mapping of the original rational font splines into cylinder UV space
    # preserves curved glyphs and holes; no polygon or mesh approximation is used.
    for face in faces:
        wires = []
        ordered = [face.OuterWire] + [wire for wire in face.Wires if not wire.isSame(face.OuterWire)]
        for wire in ordered:
            edges = []
            for edge in wire.Edges:
                nurbs = edge.toNurbs().Edges[0]
                curve = nurbs.Curve.copy()
                curve.segment(nurbs.FirstParameter, nurbs.LastParameter)
                poles = [App.Base.Vector2d(math.radians(start) +
                         ((p.x - bounds.XMin) * scale * cosine - p.y * sine) / radius,
                         height + (p.x - bounds.XMin) * scale * sine + p.y * cosine)
                         for p in curve.getPoles()]
                uv = Part.Geom2d.BSplineCurve2d()
                uv.buildFromPolesMultsKnots(poles, curve.getMultiplicities(), curve.getKnots(),
                                          curve.isPeriodic(), curve.Degree, curve.getWeights())
                mapped = uv.toShape(surface)
                if edge.Orientation == "Reversed":
                    mapped.reverse()
                edges.append(mapped)
            wires.append(Part.Wire(edges))
        curved = Part.Face(surface, wires[0])
        for hole in wires[1:]:
            curved = curved.cut(Part.Face(surface, hole))
        if not curved.isValid() or not curved.Faces:
            raise ValueError("This wrap overlaps itself. Reduce the span or increase the spiral angle/radius.")
        result.extend(curved.Faces)
    for index, face in enumerate(result):
        for other in result[:index]:
            if face.BoundBox.intersect(other.BoundBox) and face.common(other).Area > 1e-5:
                raise ValueError("Wrapped letters overlap. Increase the spiral angle/radius or reduce the span.")
    return result


class TextProfile:
    def execute(self, obj):
        placement = App.Placement(obj.Placement)
        faces = flat_faces(obj.Text, obj.FontFile, obj.FontSize.Value)
        if obj.WrapTarget:
            frame, radius = cylinder_frame(obj.WrapTarget, obj.WrapFace)
            faces = wrapped_faces(faces, radius, obj.SpiralAngle.Value, obj.WrapSpan,
                                  obj.StartAngle.Value, obj.WrapHeight.Value)
            placement = frame.multiply(obj.AttachmentOffset)
            obj.WrapRadius = radius
        obj.Shape = Part.makeCompound(faces)
        obj.Placement = placement

    def dumps(self):
        return None

    def loads(self, state):
        pass


class TextView:
    def attach(self, view):
        pass

    def doubleClicked(self, view):
        import EasyDesignView
        if EasyDesignView._controller:
            EasyDesignView._controller.edit_text(view.Object)
        return True

    def getIcon(self):
        return ":/icons/Draft_ShapeString.svg"

    def dumps(self):
        return None

    def loads(self, state):
        pass


def create_text(doc, string, font, size, placement, family="DejaVu Sans", support=None):
    flat_faces(string, font, size)
    obj = doc.addObject("Part::FeaturePython", "TextSketch")
    for kind, name, value in (
        ("App::PropertyBool", "EasyDesignText", True),
        ("App::PropertyString", "Text", string),
        ("App::PropertyString", "FontFamily", family),
        ("App::PropertyFile", "FontFile", font),
        ("App::PropertyLength", "FontSize", size),
        ("App::PropertyLinkGlobal", "WrapTarget", None),
        ("App::PropertyLinkGlobal", "SupportSolid", support),
        ("App::PropertyString", "WrapFace", ""),
        ("App::PropertyAngle", "SpiralAngle", 0),
        ("App::PropertyFloat", "WrapSpan", 0),
        ("App::PropertyAngle", "StartAngle", 0),
        ("App::PropertyDistance", "WrapHeight", 0),
        ("App::PropertyLength", "WrapRadius", 0),
        ("App::PropertyString", "MapMode", "Deactivated"),
        ("App::PropertyPlacement", "AttachmentOffset", App.Placement()),
        ("App::PropertyPlacement", "FlatPlacement", placement),
    ):
        description = "Circumferential span in degrees; 0 preserves natural width." if name == "WrapSpan" else ""
        # PropertyAngle clamps saved values to 360; the span must allow multiple turns.
        obj.addProperty(kind, name, "Text" if name in ("Text", "FontFamily", "FontFile", "FontSize") else "Wrap", description)
        setattr(obj, name, value)
    for name in ("EasyDesignText", "WrapRadius", "MapMode", "FlatPlacement"):
        obj.setEditorMode(name, 1)
    obj.Proxy = TextProfile()
    obj.Placement = placement
    obj.Label = "Text - " + string.splitlines()[0][:32]
    if obj.ViewObject:
        obj.ViewObject.Proxy = TextView()
        obj.ViewObject.ShapeColor = (0.12, 0.70, 0.74)
        obj.ViewObject.LineColor = (0.05, 0.20, 0.22)
    doc.recompute()
    return obj


def wrap_text(obj, target, name, point=None):
    frame, radius = cylinder_frame(target, name)
    if point is not None:
        local = frame.inverse().multVec(point)
        obj.StartAngle = math.degrees(math.atan2(local.y, local.x))
        obj.WrapHeight = local.z
    if not obj.WrapTarget:
        obj.FlatPlacement = obj.Placement
    obj.AttachmentOffset = App.Placement()
    obj.WrapTarget, obj.WrapFace = target, name
    obj.MapMode = "Cylinder"
    obj.WrapRadius = radius
    obj.Document.recompute()


def text_solid(profile, distance):
    if not math.isfinite(distance) or abs(distance) < .01:
        raise ValueError("Enter a nonzero extrusion distance.")
    if profile.WrapTarget and profile.WrapRadius.Value + distance <= .01:
        raise ValueError("Cut depth must be smaller than the cylinder radius.")
    solids = []
    for face in profile.Shape.Faces:
        if profile.WrapTarget:
            result = face.makeOffsetShape(distance, 1e-5, fill=True)
        else:
            result = face.extrude(profile.Placement.Rotation.multVec(App.Vector(0, 0, distance)))
        if not result.isValid() or not result.Solids or result.Volume <= 1e-7:
            raise ValueError("This text/depth cannot produce a valid solid.")
        solids.extend(result.Solids)
    return Part.makeCompound(solids)


class TextExtrusion:
    def onDocumentRestored(self, obj):
        if obj.Target and obj.Target.isDerivedFrom("PartDesign::Body") and obj.Target.Tip:
            obj.Target = obj.Target.Tip

    def execute(self, obj):
        import EasyDesignMM as mm
        if obj.Profile is None:
            raise ValueError("The text profile is missing.")
        key = (obj.Profile.Shape.hashCode(), tuple(obj.Profile.getGlobalPlacement().toMatrix().A), obj.Depth)
        cached = getattr(self, "_cached_tool", None)
        if cached is None or cached[0] != key:
            cached = self._cached_tool = (key, text_solid(obj.Profile, obj.Depth))
        tool = cached[1]
        if obj.Operation != "New Solid":
            if obj.Target is None:
                raise ValueError("Select an intersecting solid for Merge or Cut.")
            base = mm._shape(obj.Target)
            if obj.Operation == "Merge":
                result = base.multiFuse(tool.Solids).removeSplitter()
                if len(result.Solids) != len(base.Solids):
                    raise ValueError("All letters must touch the solid for Merge. Choose New Solid otherwise.")
            else:
                result = base.cut(tool).removeSplitter()
                if base.Volume - result.Volume <= 1e-7:
                    raise ValueError("The text does not cut into this solid.")
        else:
            result = tool
        if not result.isValid() or not result.Solids:
            raise ValueError("The text extrusion is not a valid solid.")
        placement = App.Placement(obj.Placement)
        obj.Shape = Part.makeCompound(result.Solids)
        obj.Placement = placement

    def dumps(self):
        return None

    def loads(self, state):
        pass


class TextPullPreview:
    def __init__(self, profile, cut=False, length=2):
        import FreeCADGui as Gui
        import EasyDesignMM as mm
        self.sketch = self.source_sketch = profile
        self.doc, self.document_name = profile.Document, profile.Document.Name
        self.operation = "Auto"
        self.taper = 0
        self._length = -abs(length) if cut else length
        self.active = False
        self.candidates = [obj for obj in self.doc.Objects if mm.solid_object(obj) == obj
                           and not obj.isDerivedFrom("App::Part") and mm._visible(obj)
                           and hasattr(obj, "Shape") and obj.Shape.Solids]
        self.visibility = [(obj, obj.ViewObject.Visibility) for obj in self.candidates]
        self.doc.openTransaction("Extrude text")
        try:
            self.feature = self.doc.addObject("Part::FeaturePython", "TextExtrusion")
            for kind, name in (("App::PropertyLinkGlobal", "Profile"), ("App::PropertyLinkGlobal", "Target"),
                               ("App::PropertyFloat", "Depth"), ("App::PropertyEnumeration", "Operation")):
                self.feature.addProperty(kind, name, "Text extrusion")
            self.feature.Operation = ["New Solid", "Merge", "Subtract / Cut"]
            self.feature.Profile = profile
            self.feature.Proxy = TextExtrusion()
            self.feature.ViewObject.Proxy = 0
            self.feature.ViewObject.ShapeColor = profile.ViewObject.ShapeColor
            self.set_length(self._length)
            self.active = True
            Gui.Selection.clearSelection()
        except Exception:
            self.doc.abortTransaction()
            raise

    @property
    def signed_length(self):
        return self._length

    @property
    def base_direction(self):
        center = self.sketch.Shape.CenterOfMass
        if self.sketch.WrapTarget:
            local = self.sketch.Placement.inverse().multVec(center)
            radial = App.Vector(local.x, local.y, 0)
            if radial.Length < 1e-7:
                radial = App.Vector(1, 0, 0)
            radial.normalize()
            return center, self.sketch.Placement.Rotation.multVec(radial)
        return center, self.sketch.Placement.Rotation.multVec(App.Vector(0, 0, 1))

    def _build(self, distance):
        import EasyDesignMM as mm
        tool = text_solid(self.sketch, distance)
        self.feature.Proxy._cached_tool = ((self.sketch.Shape.hashCode(), tuple(self.sketch.getGlobalPlacement().toMatrix().A), distance), tool)
        preferred = mm.solid_object(self.sketch.WrapTarget or self.sketch.SupportSolid) if (self.sketch.WrapTarget or self.sketch.SupportSolid) else None
        candidates = sorted(self.candidates, key=lambda obj: obj != preferred)
        target = None
        if self.operation != "New Solid":
            for candidate in candidates:
                base = mm._shape(candidate)
                if tool.distToShape(base)[0] < 1e-6:
                    if distance >= 0 or tool.common(base).Volume > 1e-7:
                        target = candidate
                        break
        actual = self.operation
        if actual == "Auto":
            actual = ("Subtract / Cut" if distance < 0 else "Merge") if target else "New Solid"
        if actual != "New Solid" and target is None:
            raise ValueError("The text must touch a solid for Merge or enter it for Cut.")
        # A Body's Tip can change later. Keep this operation linked to the
        # feature it actually used, not to the body's evolving final result.
        self.feature.Target = (target.Tip if target and target.isDerivedFrom("PartDesign::Body") else target) if actual != "New Solid" else None
        self.feature.Operation, self.feature.Depth = actual, distance
        try:
            self.feature.Proxy.execute(self.feature)
        except ValueError:
            if self.operation != "Auto" or actual != "Merge":
                raise
            # A partly contacting word must not hide its support or silently
            # discard disconnected letters. Auto leaves it as a new solid set.
            target, actual = None, "New Solid"
            self.feature.Target = None
            self.feature.Operation = actual
            self.feature.Proxy.execute(self.feature)
        self.doc.recompute()
        if "Invalid" in self.feature.State:
            raise ValueError("The text extrusion could not be rebuilt.")
        self.previous_solid = target
        self.new_solid = actual == "New Solid"
        self.cut = actual == "Subtract / Cut"
        for obj, visible in self.visibility:
            obj.ViewObject.Visibility = visible and (self.new_solid or obj != target)
        if target:
            mm._appearance(target, self.feature)
        self._length = distance

    def set_length(self, distance):
        previous = self._length
        try:
            self._build(float(distance))
        except Exception as exc:
            if self.active:
                self._build(previous)
            raise ValueError(str(exc)) from exc

    def set_operation(self, operation):
        from EasyDesignPull import OPERATIONS
        if operation not in OPERATIONS:
            raise ValueError("Unknown extrusion operation.")
        previous = self.operation
        self.operation = operation
        try:
            self._build(self._length)
        except Exception as exc:
            self.operation = previous
            self._build(self._length)
            raise ValueError(str(exc)) from exc

    def set_taper(self, value):
        if value != 0:
            raise ValueError("Text extrusion uses straight or radial walls; taper is unavailable.")

    def finish(self, accept):
        import FreeCADGui as Gui
        if not self.active:
            return
        if self.document_name not in App.listDocuments():
            self.active = False
            return
        if accept:
            self.feature.Proxy.execute(self.feature)
            self.doc.commitTransaction()
        else:
            self.doc.abortTransaction()
            for obj, visible in self.visibility:
                obj.ViewObject.Visibility = visible
        self.doc.recompute()
        self.active = False
        if App.ActiveDocument == self.doc:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(self.feature if accept else self.sketch)


def text_dialog(parent, obj=None, wrapped=False):
    from PySide import QtCore, QtGui, QtWidgets
    dialog = QtWidgets.QDialog(parent, QtCore.Qt.Tool)
    dialog.setWindowTitle("Text")
    dialog.setObjectName("EasyDesignTextDialog")
    layout = QtWidgets.QFormLayout(dialog)
    content = QtWidgets.QPlainTextEdit(dialog)
    content.setObjectName("EasyDesignTextContent")
    content.setFixedHeight(76)
    content.setPlainText(obj.Text if obj else "")
    layout.addRow("Text", content)
    size = QtWidgets.QDoubleSpinBox(dialog)
    size.setObjectName("EasyDesignTextSize")
    size.setRange(.1, 1000)
    size.setSuffix(" mm")
    size.setValue(obj.FontSize.Value if obj else 8)
    layout.addRow("Size", size)
    font = QtWidgets.QFontComboBox(dialog)
    font.setObjectName("EasyDesignTextFont")
    font.setCurrentFont(QtGui.QFont(obj.FontFamily if obj else "DejaVu Sans"))
    layout.addRow("Typeface", font)
    fields = {}
    if wrapped:
        for label, name, low, high, value in (
            ("Spiral angle", "SpiralAngle", -80, 80, obj.SpiralAngle.Value),
            ("Wrap span", "WrapSpan", 0, 3600, obj.WrapSpan),
            ("Start angle", "StartAngle", -3600, 3600, obj.StartAngle.Value),
            ("Height", "WrapHeight", -100000, 100000, obj.WrapHeight.Value),
        ):
            field = QtWidgets.QDoubleSpinBox(dialog)
            field.setObjectName("EasyDesignText" + name)
            field.setRange(low, high)
            field.setValue(value)
            field.setSuffix(" mm" if name == "WrapHeight" else " deg")
            if name == "WrapSpan":
                field.setSpecialValueText("Auto")
            layout.addRow(label, field)
            fields[name] = field
    error = QtWidgets.QLabel(dialog)
    error.setWordWrap(True)
    layout.addRow(error)
    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    layout.addRow(buttons)
    values = {}

    def accept():
        try:
            path = font_file(font.currentFont().family())
            faces = flat_faces(content.toPlainText(), path, size.value())
            options = {name: field.value() for name, field in fields.items()}
            if wrapped:
                wrapped_faces(faces, obj.WrapRadius.Value, options["SpiralAngle"], options["WrapSpan"],
                              options["StartAngle"], options["WrapHeight"])
            values.update(Text=content.toPlainText(), FontFile=path, FontFamily=font.currentFont().family(),
                          FontSize=size.value(), **options)
            dialog.accept()
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            error.setText(str(exc))
    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    content.setFocus()
    return values if dialog.exec_() == QtWidgets.QDialog.Accepted else None
