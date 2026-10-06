# SPDX-License-Identifier: LGPL-2.1-or-later

"""Validated hollow solids, including a section-offset fallback for lofts."""

import math
import FreeCAD as App
import Part


def valid_hollow(base, result):
    if result.isNull() or not result.isValid() or len(result.Solids) != 1:
        return False
    removed = base.Volume - result.Volume
    return result.Volume > 1e-7 and removed > max(1e-6, base.Volume * 1e-7)


def _validate_outer_skin(base, opening, cavity):
    # A valid cavity can still overshoot between loft samples and puncture a
    # curved outer wall. Closed solids and volume checks do not detect that.
    for face in base.Faces:
        if face.isSame(opening):
            continue
        leaked = face.common(cavity).Area
        if leaked > max(1e-6, face.Area * 1e-7):
            raise ValueError("The Shell fallback would break through an outer wall. Change the thickness or opening.")


def _inset_outline(outer, thickness):
    try:
        offset = outer.makeOffset2D(-thickness, join=0)
        offset.check(True)
    except (ValueError, RuntimeError, Part.OCCError):
        if not any(isinstance(edge.Curve, Part.BSplineCurve) for edge in outer.Edges):
            raise
        # Some OCC spline offsets have inconsistent 2D/3D curves. Only the
        # already approximate inner wall uses a bounded chord approximation.
        points = outer.OuterWire.discretize(Deflection=min(.01, thickness / 20))
        if len(points) > 1000:
            raise ValueError("The inner outline is too complex for a validated Shell fallback.")
        if (points[0] - points[-1]).Length > 1e-7:
            points.append(points[0])
        offset = Part.Face(Part.makePolygon(points)).makeOffset2D(-thickness, join=0)
        offset.check(True)
    if (len(offset.Wires) != 1 or not offset.isValid() or not offset.Wires[0].isClosed()
            or offset.Area >= outer.Area):
        raise ValueError("This thickness splits or removes the inner outline.")
    return offset


def section_cavity(base, face, thickness):
    if face.findPlane(1e-7) is None:
        raise ValueError("The CAD kernel cannot open this curved face. Select a flat side or end face for Shell.")
    from EasyDesignFace import face_frame
    frame = face_frame(face)
    opening_index = next(index for index, candidate in enumerate(base.Faces) if candidate.isSame(face))
    local = base.copy()
    local.transformShape(frame.inverse().toMatrix(), True)
    if local.BoundBox.ZMax > .001:
        raise ValueError("The opening must be an end cap for the section fallback.")
    floor = local.BoundBox.ZMin + thickness
    if floor >= -.02:
        raise ValueError("Shell thickness is greater than the solid's height.")
    cap = face.copy()
    cap.transformShape(frame.inverse().toMatrix(), True)
    end = _inset_outline(Part.Face(cap.OuterWire), thickness)
    prism = Part.Face(cap.OuterWire).extrude(App.Vector(0, 0, local.BoundBox.ZMin))
    tolerance = max(1e-6, local.Volume * 1e-7)
    prismatic = (abs(prism.Volume - local.Volume) <= tolerance
                 and prism.cut(local).Volume + local.cut(prism).Volume <= tolerance)
    if prismatic:
        # A planar spline side of a bent loft can bound a true extrusion.
        # Extruding its inner outline avoids a fragile loft through identical curves.
        inner = Part.Face(end.Wires[0])
        inner.translate(App.Vector(0, 0, floor))
        cavity = inner.extrude(App.Vector(0, 0, max(1, thickness) - floor))
    else:
        cavity = _sampled_cavity(local, end, floor, thickness)
    if not cavity.isValid() or len(cavity.Solids) != 1:
        raise ValueError("The section cavity could not be built as a valid solid.")
    if len(cap.Wires) == 1:
        _validate_outer_skin(local, local.Faces[opening_index], cavity)
    opened_pockets = False
    for wire in cap.Wires:
        if wire.isSame(cap.OuterWire):
            continue
        hole = Part.Face(wire)
        column = hole.extrude(App.Vector(0, 0, local.BoundBox.ZMin))
        void = column.cut(local)
        if not void.Solids:
            raise ValueError("The opening's holes could not be traced into the solid.")
        if void.BoundBox.ZMin > local.BoundBox.ZMin + .001:
            # Keeping a blind well under a removed cap would create a loose island.
            # Open it into the cavity instead; the Method records this explicitly.
            opened_pockets = True
            continue
        if column.cut(void).Volume > max(1e-7, column.Volume * 1e-7):
            raise ValueError("The fallback needs straight through holes; try a smaller thickness.")
        expanded = hole.makeOffset2D(thickness, join=0)
        if (len(expanded.Faces) != 1 or expanded.cut(end).Area > 1e-7
                or expanded.Area <= hole.Area):
            raise ValueError("Shell thickness leaves too little clearance around a hole.")
        collar = expanded.extrude(App.Vector(0, 0, local.BoundBox.ZMin))
        collar = collar.fuse(expanded.extrude(App.Vector(0, 0, max(1, thickness))))
        cavity = cavity.cut(collar)
    result = local.cut(cavity).removeSplitter()
    if not valid_hollow(local, result):
        raise ValueError("The section cavity did not leave a valid hollow solid.")
    result.transformShape(frame.toMatrix(), True)
    result.check(True)
    return result, opened_pockets


def _sampled_cavity(local, end, floor, thickness):
    profiles = []
    # Sample the unchanged outer solid. Only the cavity is approximated between
    # slices; this fallback is explicitly identified in the feature's Method.
    count = 25
    for index in range(count - 1):
        z = floor * (1 - index / (count - 1))
        slices = local.slice(App.Vector(0, 0, 1), z)
        if not slices or any(not wire.isClosed() for wire in slices):
            raise ValueError("The section fallback needs a single closed section at every height.")
        sections = Part.makeFace(slices, "Part::FaceMakerBullseye").Faces
        if len(sections) != 1:
            raise ValueError("The section fallback cannot bridge disconnected sections.")
        outer = Part.Face(sections[0].OuterWire)
        offset = _inset_outline(outer, thickness)
        profiles.append(offset.Wires[0])
    profiles.append(end.Wires[0])
    cavity = Part.makeLoft(profiles, True, False)
    # Continuing the spline beyond the cap, especially through a near-duplicate
    # section, makes it overshoot the outer walls. Extend the opening separately.
    extension = Part.Face(end.Wires[0]).extrude(App.Vector(0, 0, max(1, thickness)))
    return cavity.fuse(extension)


def hollow_shape(base, names, thickness, method="Auto"):
    if not math.isfinite(thickness) or thickness < .01:
        raise ValueError("Enter a shell thickness of at least 0.01 mm.")
    if base.isNull() or not base.isValid() or len(base.Solids) != 1:
        raise ValueError("Shell needs one valid solid.")
    faces = [base.getElement(name) for name in names]
    if not faces:
        raise ValueError("Select the face to remove.")
    if len(set(names)) != len(names) or any(face.ShapeType != "Face" for face in faces):
        raise ValueError("Select distinct faces to remove, not edges or vertices.")
    if not method.startswith("Section offset"):
        for join in (2, 0):
            try:
                result = base.makeThickness(faces, -thickness, .001, False, False, 0, join)
                if valid_hollow(base, result):
                    result.check(True)
                    return result, "Normal offset"
            except (ValueError, RuntimeError, Part.OCCError):
                pass
    if len(faces) != 1:
        raise ValueError("The CAD kernel cannot shell these faces. Try a smaller thickness or one planar opening.")
    result, opened = section_cavity(base, faces[0], thickness)
    method = "Section offset (approximate; blind pockets opened)" if opened else "Section offset (approximate)"
    return result, method


class ShellFeature:
    def seed(self, source, names, thickness, result, method):
        self._key = (source.Shape.hashCode(), tuple(names), float(thickness), method)
        self._source_shape = source.Shape
        self._result = result
        self._method = method

    def execute(self, obj):
        from EasyDesignFace import _shape_in_frame
        source, names = obj.SourceFace
        if source is None:
            raise ValueError("The source solid for Shell is missing.")
        if any(name.startswith("?") for name in names):
            normals = getattr(obj, "OpeningNormals", [])
            areas = getattr(obj, "OpeningAreas", [])
            if len(normals) != len(names) or len(areas) != len(names):
                raise ValueError("The Shell opening was lost. Select its face again.")
            resolved = []
            for normal, area in zip(normals, areas):
                matches = ["Face%d" % index for index, face in enumerate(source.Shape.Faces, 1)
                           if face.findPlane(1e-7) is not None
                           and face.normalAt(0, 0).dot(normal) > .999999
                           and abs(face.Area - area) <= max(1e-7, area * 1e-7)]
                if len(matches) != 1:
                    raise ValueError("The Shell opening is ambiguous after editing. Select its face again.")
                resolved.append(matches[0])
            if len(set(resolved)) != len(resolved):
                raise ValueError("The Shell openings could not be recovered independently.")
            names = resolved
            obj.SourceFace = (source, names)
        key = (source.Shape.hashCode(), tuple(names), obj.Thickness.Value, obj.Method)
        if key != getattr(self, "_key", None) or not source.Shape.isEqual(self._source_shape):
            result, method = hollow_shape(source.Shape, names, obj.Thickness.Value, obj.Method)
            self.seed(source, names, obj.Thickness.Value, result, method)
        result, method = self._result, self._method
        obj.Shape = _shape_in_frame(result, source, obj)
        obj.Method = method
        for name, kind in (("OpeningNormals", "App::PropertyVectorList"),
                           ("OpeningAreas", "App::PropertyFloatList")):
            if name not in obj.PropertiesList:
                obj.addProperty(kind, name, "Shell")
                obj.setEditorMode(name, 2)
        obj.OpeningNormals = [source.Shape.getElement(name).normalAt(0, 0) for name in names]
        obj.OpeningAreas = [source.Shape.getElement(name).Area for name in names]

    def dumps(self):
        return None

    def loads(self, state):
        pass


def create_shell(source, names, thickness, prepared=None):
    result, method = prepared if prepared is not None else hollow_shape(source.Shape, names, thickness)
    doc = source.Document
    body = source.getParentGeoFeatureGroup()
    if body is not None and body.isDerivedFrom("PartDesign::Body"):
        feature = body.newObject("PartDesign::FeaturePython", "Shell")
    else:
        feature = doc.addObject("Part::FeaturePython", "Shell")
    feature.addProperty("App::PropertyLinkSub", "SourceFace", "Shell")
    feature.addProperty("App::PropertyLength", "Thickness", "Shell")
    feature.addProperty("App::PropertyString", "Method", "Shell")
    feature.addProperty("App::PropertyVectorList", "OpeningNormals", "Shell")
    feature.addProperty("App::PropertyFloatList", "OpeningAreas", "Shell")
    feature.OpeningNormals = [source.Shape.getElement(name).normalAt(0, 0) for name in names]
    feature.OpeningAreas = [source.Shape.getElement(name).Area for name in names]
    feature.setEditorMode("OpeningNormals", 2)
    feature.setEditorMode("OpeningAreas", 2)
    if body is None or not body.isDerivedFrom("PartDesign::Body"):
        feature.addProperty("App::PropertyLinkList", "CoordinateParents", "Shell")
        parents = []
        parent = source.getParentGeoFeatureGroup()
        while parent:
            parents.append(parent)
            parent = parent.getParentGeoFeatureGroup()
        feature.CoordinateParents = parents
    feature.SourceFace = (source, names)
    feature.Thickness = thickness
    feature.Method = method
    feature.setEditorMode("Method", 1)
    feature.Proxy = ShellFeature()
    feature.Proxy.seed(source, names, thickness, result, method)
    if feature.ViewObject:
        feature.ViewObject.Proxy = 0
    from EasyDesignFace import _shape_in_frame
    feature.Shape = _shape_in_frame(result, source, feature)
    doc.recompute()
    if "Invalid" in feature.State or not valid_hollow(source.Shape, result):
        raise ValueError("Shell did not produce a valid hollow solid.")
    return feature


class ShellPreview:
    def __init__(self, source, names):
        import FreeCADGui as Gui
        from EasyDesignMM import _appearance
        self.doc = source.Document
        if self.doc.HasPendingTransaction:
            raise ValueError("Finish the current operation before Shell.")
        self.document_name = self.doc.Name
        self.source = source
        self.original_visibility = source.ViewObject.Visibility
        self.body = source.getParentGeoFeatureGroup()
        if self.body and not self.body.isDerivedFrom("PartDesign::Body"):
            self.body = None
        self.original_tip = self.body.Tip if self.body else None
        self.measure_name = "Thickness"
        self.cut = False
        self.active = False
        face = source.Shape.getElement(names[0])
        parent = source.getGlobalPlacement().multiply(source.Placement.inverse())
        self.base_direction = (parent.multVec(face.CenterOfMass),
                               parent.Rotation.multVec(-face.normalAt(0, 0)))
        self.highlight_lines = [[tuple(parent.multVec(p)) for p in edge.discretize(Number=30)]
                                for edge in face.Edges]
        bounds = source.Shape.BoundBox
        self._length = min(1., min(v for v in (bounds.XLength, bounds.YLength, bounds.ZLength) if v > .01) * .025)
        # Preflight before opening an undo transaction: aborting an unused
        # document transaction does not clear FreeCAD's global transaction.
        for attempt in range(7):
            try:
                result, method = hollow_shape(source.Shape, names, self._length)
                break
            except (ValueError, RuntimeError, Part.OCCError):
                if attempt == 6 or self._length <= .01:
                    raise
                self._length = max(.01, self._length / 2)
        self.doc.openTransaction("Shell")
        transaction = App.getActiveTransaction()
        try:
            self.feature = create_shell(source, names, self._length, (result, method))
            _appearance(source, self.feature)
            source.ViewObject.Visibility = False
            self.feature.ViewObject.Visibility = True
            Gui.Selection.clearSelection()
            self.active = True
        except Exception:
            self.doc.abortTransaction()
            if transaction and App.getActiveTransaction() == transaction:
                App.closeActiveTransaction(True, transaction[1])
            source.ViewObject.Visibility = self.original_visibility
            raise

    @property
    def signed_length(self):
        return self._length

    def set_length(self, value):
        previous = self._length
        try:
            if not math.isfinite(value) or value < .01:
                raise ValueError("Enter a shell thickness of at least 0.01 mm.")
            self.feature.Thickness = value
            self.feature.Proxy.execute(self.feature)
            self.doc.recompute()
            if "Invalid" in self.feature.State:
                raise ValueError("This thickness cannot make a valid shell.")
            self._length = value
        except Exception as exc:
            self.feature.Thickness = previous
            self.feature.Proxy.execute(self.feature)
            self.doc.recompute()
            raise ValueError(str(exc)) from exc

    def finish(self, accept):
        import FreeCADGui as Gui
        if not self.active:
            return
        if self.document_name not in App.listDocuments():
            self.active = False
            return
        if accept:
            self.feature.Proxy.execute(self.feature)
            self.doc.recompute()
            if ("Invalid" in self.feature.State
                    or not valid_hollow(self.source.Shape, self.feature.Shape)):
                raise ValueError("Shell is no longer valid. Adjust thickness or cancel.")
            self.doc.commitTransaction()
            if self.feature.Method != "Normal offset":
                App.Console.PrintWarning("456D Design: Shell uses an approximate section-offset cavity; outer geometry is unchanged.\n")
            if "blind pockets opened" in self.feature.Method:
                App.Console.PrintWarning("456D Design: Blind pockets on the removed face were opened into the Shell cavity.\n")
        else:
            self.doc.abortTransaction()
            self.source.ViewObject.Visibility = self.original_visibility
            if self.body:
                self.body.Tip = self.original_tip
        self.active = False
        self.doc.recompute()
        if App.ActiveDocument == self.doc:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(self.feature if accept else self.source)
