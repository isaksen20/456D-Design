# SPDX-License-Identifier: LGPL-2.1-or-later

import math
import FreeCADGui as Gui
import FreeCAD as App
import Part


OPERATIONS = ("Auto", "New Solid", "Merge", "Subtract / Cut")


def closed_profile_edges(sketch, selected=None):
    if selected:
        edges = [sketch.Shape.getElement(name) for name in selected]
        wires = Part.makeCompound(edges).makeWires("").Wires
        if not wires or not all(wire.isClosed() for wire in wires):
            raise ValueError("Select a closed outline, not an open line.")
        return list(selected)
    wires = [wire for wire in sketch.Shape.Wires if wire.isClosed()]
    if not wires:
        raise ValueError("Select a closed profile before pulling or cutting.")
    return ["Edge%d" % (index + 1) for index, edge in enumerate(sketch.Shape.Edges)
            if any(edge.isSame(candidate) for wire in wires for candidate in wire.Edges)]


def _valid_feature(feature):
    return ("Invalid" not in feature.State and not feature.Shape.isNull()
            and len(feature.Shape.Solids) == 1 and feature.Shape.isValid())


def _previous_solid(body, sketch):
    tip = getattr(body, "Tip", None)
    if tip is not None and tip != sketch and tip.isDerivedFrom("PartDesign::Feature"):
        if not _valid_feature(tip):
            raise ValueError("The body's final solid is invalid. Repair it before extruding.")
        return tip
    for obj in reversed(body.Group):
        if obj == sketch or not obj.isDerivedFrom("PartDesign::Feature"):
            continue
        try:
            if len(obj.Shape.Solids) == 1 and not obj.Shape.isNull():
                return obj
        except (AttributeError, ValueError):
            continue
    return None


def run_pull(sketch, cut=False):
    body = sketch.getParentGeoFeatureGroup()
    if not body or not body.isDerivedFrom("PartDesign::Body"):
        raise ValueError("The sketch must be inside a Part Design body.")
    if cut and _previous_solid(body, sketch) is None:
        raise ValueError("Cut needs an existing solid. Use Finish & Pull first.")
    if Gui.Control.activeDialog():
        raise ValueError("Close the current task before pulling the sketch.")

    Gui.activeView().setActiveObject("pdbody", body)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sketch.Document.Name, sketch.Name)
    Gui.runCommand("PartDesign_Pocket" if cut else "PartDesign_Pad")


class PullPreview:
    """A reversible native Pad/Pocket, updated while its depth is being chosen."""

    def __init__(self, sketch, cut=False, length=10.0, new_solid=False, taper=0.0, profile_edges=None, region_point=None, operation=None):
        self.source_sketches = list(sketch) if isinstance(sketch, (list, tuple)) else [sketch]
        if not self.source_sketches:
            raise ValueError("Select sketches to extrude.")
        sketch = self.source_sketches[0]
        multiple = len(self.source_sketches) > 1
        if multiple:
            from EasyDesignRegions import combined_profile
            combined_profile(self.source_sketches)
        body = sketch.getParentGeoFeatureGroup()
        if multiple and (not body or not body.isDerivedFrom("PartDesign::Body")):
            body = next((obj.getParentGeoFeatureGroup() for obj in self.source_sketches
                         if obj.getParentGeoFeatureGroup()
                         and obj.getParentGeoFeatureGroup().isDerivedFrom("PartDesign::Body")), None)
        if not multiple and (not body or not body.isDerivedFrom("PartDesign::Body")):
            raise ValueError("The sketch must be inside a Part Design body.")
        self.previous_solid = _previous_solid(body, sketch) if body else None
        self.standalone_body = body is None
        if cut and not new_solid and self.previous_solid is None:
            raise ValueError("Cut needs an existing solid. Pull a profile first.")
        if Gui.Control.activeDialog():
            raise ValueError("Close the current task before pulling the sketch.")
        self.region_point = None if multiple else region_point
        self.profile_edges = closed_profile_edges(sketch, profile_edges) if not multiple and region_point is None else []
        self.sketch = sketch
        self.source_sketch = sketch
        self.source_body = body
        self.original_tip = body.Tip if body else None
        self.operation = operation or ("New Solid" if new_solid else "Auto")
        if self.operation not in OPERATIONS:
            raise ValueError("Unknown extrusion operation.")
        self.new_solid = False
        self.taper = float(taper)
        if not -85 <= self.taper <= 85:
            raise ValueError("Taper must be between -85 and 85 degrees.")
        self.reversed = False
        self._distance = -abs(float(length)) if cut else float(length)
        if not math.isfinite(self._distance):
            raise ValueError("Enter a finite extrusion distance.")
        self.doc = sketch.Document
        if self.doc.HasPendingTransaction:
            raise ValueError("Finish the current operation before extruding.")
        self.document_name = self.doc.Name
        self.body = body
        self.cut = cut
        self.feature = None
        self.view_provider = sketch.ViewObject
        self.original_visibility = self.view_provider.Visibility if self.view_provider else None
        self.active = False
        self.original_views = [(obj.ViewObject, obj.ViewObject.Visibility)
                               for obj in [body, self.previous_solid] + self.source_sketches
                               if obj and obj.ViewObject]
        self.doc.openTransaction("Cut profile" if cut else "Pull profile")
        try:
            if self.body is None:
                self.body = self.source_body = self.doc.addObject("PartDesign::Body", "ExtrudedBody")
            self._build(self._distance)
            Gui.Selection.clearSelection()
            self.active = True
        except Exception:
            self.doc.abortTransaction()
            self._restore_visibility()
            raise

    def _restore_visibility(self):
        for provider, visible in self.original_views:
            provider.Visibility = visible

    def _clear_preview(self):
        if self.feature and self.doc.getObject(self.feature.Name):
            self.doc.removeObject(self.feature.Name)
        self.feature = None
        if self.sketch != self.source_sketch and self.doc.getObject(self.sketch.Name):
            self.doc.removeObject(self.sketch.Name)
        self.sketch = self.source_sketch
        if self.body != self.source_body and self.doc.getObject(self.body.Name):
            self.doc.removeObject(self.body.Name)
        self.body = self.source_body
        self.body.Tip = self.original_tip
        self._restore_visibility()

    def _tool(self, distance):
        if len(self.source_sketches) > 1:
            from EasyDesignRegions import combined_profile
            profile = combined_profile(self.source_sketches)
            relative = self.source_body.getGlobalPlacement().inverse().multiply(self.source_sketch.getGlobalPlacement())
            profile.transformShape(relative.toMatrix(), True)
            return profile.extrude(relative.Rotation.multVec(App.Vector(0, 0, distance)))
        if self.region_point is not None:
            from EasyDesignRegions import region_at
            profile = region_at(self.source_sketch, self.region_point)
        else:
            edges = [self.source_sketch.Shape.getElement(name) for name in self.profile_edges]
            wires = Part.makeCompound(edges).makeWires("").Wires
            profile = Part.makeFace(wires, "Part::FaceMakerBullseye")
        direction = self.source_sketch.Placement.Rotation.multVec(App.Vector(0, 0, distance))
        return profile.extrude(direction)

    def _build(self, distance, force_new=False):
        new_solid = self.operation == "New Solid" or force_new
        if self.operation == "Merge" and self.previous_solid is None:
            raise ValueError("Merge needs an existing solid. Choose Auto or New Solid.")
        if self.previous_solid and not new_solid and self.taper == 0:
            tool = self._tool(distance)
            contact = tool.distToShape(self.previous_solid.Shape)[0] < 1e-7
            overlap = tool.common(self.previous_solid.Shape).Volume > 1e-7
            if self.operation == "Auto":
                new_solid = not (overlap if distance < 0 else contact)
            elif self.operation == "Merge" and not contact:
                raise ValueError("Merge requires contact with the existing solid. Choose New Solid for this gap.")
            elif self.operation == "Subtract / Cut" and not overlap:
                raise ValueError("Subtract / Cut requires an extrusion that enters the existing solid.")
        cut = (self.operation == "Subtract / Cut" or
               (self.operation == "Auto" and distance < 0 and self.previous_solid is not None and not new_solid))
        if cut and not self.previous_solid:
            raise ValueError("Subtract / Cut needs an existing solid.")
        if self.feature and new_solid == self.new_solid and cut == self.cut:
            self.feature.Length = abs(distance)
            self.feature.Reversed = distance > 0 if cut else distance < 0
            self.doc.recompute()
            try:
                self._validate_result(cut)
            except ValueError:
                if self.operation == "Auto" and self.previous_solid and not force_new:
                    return self._build(distance, force_new=True)
                raise
            self.reversed = not cut and distance < 0
            self._distance = distance
            return
        source_visible = self.view_provider.Visibility if self.view_provider else None
        self._clear_preview()
        self.new_solid = new_solid
        if self.new_solid and not self.standalone_body:
            self.body = self.doc.addObject("PartDesign::Body", "ExtrudedBody")
        if len(self.source_sketches) > 1:
            from EasyDesignRegions import create_combined_profile
            self.sketch = create_combined_profile(self.body, self.source_sketches)
        elif self.region_point is not None:
            from EasyDesignRegions import create_profile
            self.sketch = create_profile(self.body, self.source_sketch, self.region_point)
        else:
            from EasyDesignRegions import create_profile
            self.sketch = create_profile(self.body, self.source_sketch, edges=self.profile_edges)
        try:
            self._create_feature(cut, distance)
        except ValueError:
            if self.operation == "Auto" and self.previous_solid and not force_new:
                return self._build(distance, force_new=True)
            raise
        self._distance = distance
        Gui.activeView().setActiveObject("pdbody", self.body)
        if self.view_provider:
            self.view_provider.Visibility = source_visible
        if not self.new_solid and self.previous_solid and self.previous_solid.ViewObject:
            self.previous_solid.ViewObject.Visibility = False

    def _create_feature(self, cut, distance):
        self.feature = self.body.newObject(
            "PartDesign::Pocket" if cut else "PartDesign::Pad",
            "Pocket" if cut else "Pad",
        )
        self.feature.Profile = self.sketch
        if "ExtrusionNormal" in self.sketch.PropertiesList:
            self.feature.UseCustomVector = True
            self.feature.setExpression("Direction", ("-" if cut else "") + self.sketch.Name + ".ExtrusionNormal")
        if not self.new_solid and self.previous_solid:
            self.feature.BaseFeature = self.previous_solid
        self.feature.Length = abs(distance)
        self.feature.TaperAngle = self.taper
        self.feature.Reversed = distance > 0 if cut else distance < 0
        self.reversed = not cut and distance < 0
        self.doc.recompute()
        self._validate_result(cut)
        if not self.new_solid and self.previous_solid:
            self._inherit_appearance()
        self.cut = cut

    def _validate_result(self, cut):
        if not _valid_feature(self.feature):
            raise ValueError("Merge requires a connected solid. Choose New Solid for a separate extrusion.")
        if not self.new_solid and self.previous_solid:
            change = self.feature.Shape.Volume - self.previous_solid.Shape.Volume
            if (cut and change >= -1e-7) or (not cut and abs(change) < 1e-7 and self.operation == "Auto"):
                raise ValueError("The extrusion does not change the existing solid. Choose New Solid or another depth.")

    def _inherit_appearance(self):
        source, target = self.previous_solid.ViewObject, self.feature.ViewObject
        if not source or not target:
            return
        for name in ("ShapeMaterial", "ShapeColor", "LineColor", "Transparency", "DisplayMode"):
            if hasattr(source, name) and hasattr(target, name):
                setattr(target, name, getattr(source, name))
        target.DiffuseColor = [tuple(source.ShapeColor[:3])] * len(self.feature.Shape.Faces)
        target.Transparency = source.Transparency

    def set_operation(self, operation):
        if operation not in OPERATIONS:
            raise ValueError("Unknown extrusion operation.")
        previous = self.operation
        self.operation = operation
        try:
            self._build(self._distance)
        except Exception:
            self.operation = previous
            self._build(self._distance)
            raise

    @property
    def length(self):
        return float(self.feature.Length.Value)

    @property
    def signed_length(self):
        return self._distance

    @property
    def base_direction(self):
        if len(self.source_sketches) > 1:
            body = self.sketch.getParentGeoFeatureGroup()
            return (body.getGlobalPlacement().multVec(self.sketch.Shape.BoundBox.Center),
                    self.source_sketch.getGlobalPlacement().Rotation.multVec(App.Vector(0, 0, 1)))
        sketch = self.source_sketch
        parent = sketch.getGlobalPlacement().multiply(sketch.Placement.inverse())
        direction = sketch.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        return parent.multVec(sketch.Shape.BoundBox.Center), parent.Rotation.multVec(direction)

    def set_taper(self, angle):
        angle = float(angle)
        if not -85 <= angle <= 85:
            raise ValueError("Taper must be between -85 and 85 degrees.")
        previous = self.taper
        self.feature.TaperAngle = angle
        self.doc.recompute()
        if not _valid_feature(self.feature):
            self.feature.TaperAngle = previous
            self.doc.recompute()
            raise ValueError("That taper angle would not make a valid solid.")
        self.taper = angle

    def set_length(self, length):
        if not self.active:
            return
        length = float(length)
        if not math.isfinite(length):
            raise ValueError("Enter a finite extrusion distance.")
        if abs(length) < 0.01:
            return
        length = max(-100000.0, min(length, 100000.0))
        previous = self._distance
        try:
            self._build(length)
        except Exception:
            self._build(previous)
            raise

    def finish(self, accept):
        if not self.active:
            return
        if self.document_name not in App.listDocuments():
            self.active = False
            return
        if accept:
            self.doc.recompute()
            if not _valid_feature(self.feature):
                raise ValueError("The extrusion is no longer valid. Adjust the distance or cancel.")
            self.doc.commitTransaction()
        else:
            self.doc.abortTransaction()
            self._restore_visibility()
        self.active = False
        if App.ActiveDocument == self.doc:
            Gui.Selection.clearSelection()
            selected = [self.feature] if accept else self.source_sketches
            for obj in selected:
                Gui.Selection.addSelection(self.document_name, obj.Name)
            if not accept:
                Gui.activeView().setActiveObject("pdbody", self.source_sketch.getParentGeoFeatureGroup())
        self.doc.recompute()
