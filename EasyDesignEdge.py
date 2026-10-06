# SPDX-License-Identifier: LGPL-2.1-or-later

import math

import FreeCAD as App
import FreeCADGui as Gui

from EasyDesignPull import _valid_feature


def edge_names(obj, subelements):
    names = []
    for name in subelements:
        if name.startswith("Edge"):
            obj.Shape.getElement(name)
            names.append(name)
        elif name.startswith("Face"):
            face = obj.Shape.getElement(name)
            names.extend("Edge%d" % (index + 1) for index, edge in enumerate(obj.Shape.Edges)
                         if any(edge.isSame(candidate) for candidate in face.Edges))
        else:
            raise ValueError("Select solid edges or faces for this operation.")
    names = list(dict.fromkeys(names))
    if not names:
        raise ValueError("Select one or more edges, or a face, first.")
    return names


class EdgePreview:
    """Reversible native edge dress-up with a shared viewport distance control."""

    def __init__(self, obj, subelements, chamfer=False):
        if Gui.Control.activeDialog():
            raise ValueError("Close the current task before changing edges.")
        self.body = obj if obj.isDerivedFrom("PartDesign::Body") else obj.getParentGeoFeatureGroup()
        if not self.body or not self.body.isDerivedFrom("PartDesign::Body"):
            self.body = None
        if obj == self.body:
            obj = self.body.Tip
        if not obj or not hasattr(obj, "Shape") or len(obj.Shape.Solids) != 1:
            raise ValueError("Select edges on one solid.")
        if self.body and obj != self.body.Tip:
            raise ValueError("Select edges on the current solid, not an earlier feature.")
        self.names = edge_names(obj, subelements)
        self.source = obj
        self.doc = obj.Document
        self.document_name = self.doc.Name
        self.chamfer = chamfer
        self.measure_name = "Size" if chamfer else "Radius"
        self.cut = False
        self.active = False
        self.original_visibility = obj.ViewObject.Visibility
        self.original_tip = self.body.Tip if self.body else None
        parent = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
        edge = obj.Shape.getElement(self.names[0])
        parameter = (edge.FirstParameter + edge.LastParameter) / 2
        base = edge.valueAt(parameter)
        tangent = edge.tangentAt(parameter)
        direction = obj.Shape.CenterOfMass - base
        direction -= tangent * direction.dot(tangent)
        if direction.Length < 1e-6:
            direction = tangent.cross(App.Vector(0, 0, 1))
            if direction.Length < 1e-6:
                direction = tangent.cross(App.Vector(0, 1, 0))
        direction.normalize()
        self.base_direction = parent.multVec(base), parent.Rotation.multVec(direction)
        self.highlight_lines = []
        for name in self.names:
            points = obj.Shape.getElement(name).discretize(Number=40)
            self.highlight_lines.append([tuple(parent.multVec(point)) for point in points])
        self._length = 0.0
        title = "Chamfer" if chamfer else "Fillet"
        self.doc.openTransaction(title + " edges")
        try:
            if self.body:
                self.feature = self.body.newObject("PartDesign::" + title, title)
                self.feature.Base = (obj, self.names)
            else:
                self.feature = self.doc.addObject("Part::" + title, title)
                self.feature.Base = obj
                group = obj.getParentGeoFeatureGroup()
                if group and group.isDerivedFrom("App::Part"):
                    group.addObject(self.feature)
            smallest = min(value for value in (obj.Shape.BoundBox.XLength, obj.Shape.BoundBox.YLength,
                                               obj.Shape.BoundBox.ZLength) if value > 1e-6)
            initial = max(.01, min(1.0, smallest * .05))
            for attempt in range(7):
                candidate = max(.01, initial / 2 ** attempt)
                self._assign(candidate)
                self.doc.recompute()
                if _valid_feature(self.feature):
                    self._length = candidate
                    break
            if not self._length:
                raise ValueError("These edges cannot make a valid %s. Try another edge selection." % title.lower())
            obj.ViewObject.Visibility = False
            self.feature.ViewObject.Visibility = True
            Gui.Selection.clearSelection()
            self.active = True
        except Exception:
            self.doc.abortTransaction()
            obj.ViewObject.Visibility = self.original_visibility
            raise

    @property
    def signed_length(self):
        return self._length

    def _assign(self, value):
        if self.body:
            setattr(self.feature, "Size" if self.chamfer else "Radius", value)
        else:
            self.feature.Edges = [(int(name[4:]), value, value) for name in self.names]

    def set_length(self, value):
        value = float(value)
        if not math.isfinite(value) or value < .01 or value > 100000:
            raise ValueError("Enter a positive %s of at least 0.01 mm." % self.measure_name.lower())
        if not self.active:
            return
        previous = self._length
        try:
            self._assign(value)
            self.doc.recompute()
            if not _valid_feature(self.feature):
                raise ValueError("That %s is too large or cannot make a valid solid." % self.measure_name.lower())
        except Exception as exc:
            self._assign(previous)
            self.doc.recompute()
            raise ValueError(str(exc)) from exc
        self._length = value

    def finish(self, accept):
        if not self.active:
            return
        self.active = False
        if self.document_name not in App.listDocuments():
            return
        if accept:
            self.doc.commitTransaction()
        else:
            self.doc.abortTransaction()
            self.source.ViewObject.Visibility = self.original_visibility
            if self.body:
                self.body.Tip = self.original_tip
        self.doc.recompute()
        if App.ActiveDocument != self.doc:
            return
        Gui.Selection.clearSelection()
        target = self.feature if accept else self.source
        if accept:
            Gui.Selection.addSelection(self.document_name, target.Name)
        else:
            for name in self.names:
                Gui.Selection.addSelection(self.document_name, target.Name, name)
