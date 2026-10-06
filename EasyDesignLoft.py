# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets
import EasyDesignMM as mm


OPERATIONS = ("Auto", "New Solid", "Subtract / Cut")


def section_wire(sketch):
    if sketch is None or not sketch.isDerivedFrom("Sketcher::SketchObject"):
        raise ValueError("The loft's source sketch is missing. Restore or replace that sketch.")
    wires = [wire for wire in sketch.Shape.Wires if wire.isClosed()]
    if len(wires) != 1 or not wires[0].isValid() or Part.Face(wires[0]).Area <= 1e-7:
        raise ValueError("Each loft sketch must contain one closed profile.")
    wire = wires[0].copy()
    parent = sketch.getGlobalPlacement().multiply(sketch.Placement.inverse())
    wire.transformShape(parent.toMatrix(), True)
    return wire


class LoftSection:
    def onDocumentRestored(self, obj):
        if obj.SourceSketch is None:
            obj.touch()

    def _status(self, obj, value):
        if "SourceStatus" not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", "SourceStatus", "456D Design")
            obj.setEditorMode("SourceStatus", 1)
        changed = obj.SourceStatus != value
        if changed:
            obj.SourceStatus = value
        return changed

    def execute(self, obj):
        if obj.SourceSketch is None:
            wires = obj.Shape.Wires
            if (len(wires) != 1 or not wires[0].isClosed() or not wires[0].isValid()
                    or Part.Face(wires[0]).Area <= 1e-7):
                raise ValueError("The loft's source sketch is missing and no saved outline is available.")
            if self._status(obj, "Frozen - source sketch removed"):
                App.Console.PrintWarning("456D Design: %s uses its saved outline because its source sketch was removed.\n" % obj.Label)
            return
        wire = section_wire(obj.SourceSketch)
        key = (obj.SourceSketch.Shape.hashCode(), tuple(obj.SourceSketch.getGlobalPlacement().toMatrix().A))
        if key == getattr(self, "_key", None):
            self._status(obj, "Linked")
            return
        if getattr(self, "_key", None) is None and len(obj.Shape.Wires) == 1:
            saved = obj.Shape.Wires[0]
            if saved.isClosed() and len(saved.Edges) == len(wire.Edges):
                try:
                    before, after = Part.Face(saved), Part.Face(wire)
                    if before.cut(after).Area + after.cut(before).Area <= max(1e-7, before.Area * 1e-7):
                        # Keep saved edge identities when merely restoring an identical
                        # outline, so downstream face references are not renumbered.
                        self._key = key
                        self._status(obj, "Linked")
                        return
                except (ValueError, RuntimeError, Part.OCCError):
                    pass
        placement = App.Placement(wire.Placement)
        wire.Placement = App.Placement()
        # FreeCAD keeps a Feature's Placement when assigning its Shape.
        obj.Shape = wire
        obj.Placement = placement
        self._key = key
        self._status(obj, "Linked")

    def dumps(self):
        return None

    def loads(self, state):
        pass


def recover_missing_sections(doc):
    """Restore editable sketches from cached wires left by deleted loft inputs."""
    sections = [obj for obj in doc.Objects if isinstance(getattr(obj, "Proxy", None), LoftSection)
                and obj.SourceSketch is None and len(obj.Shape.Wires) == 1
                and obj.Shape.Wires[0].isClosed() and obj.Shape.Wires[0].isValid()]
    if not sections or doc.HasPendingTransaction:
        return []
    from draftmake.make_sketch import make_sketch

    restored = []
    doc.openTransaction("Recover loft sketches")
    try:
        for section in sections:
            cached = section.Shape
            saved = cached.Wires[0].copy()
            body = doc.addObject("PartDesign::Body", "RecoveredSketchBody")
            body.Label = "Recovered loft profile"
            sketch = body.newObject("Sketcher::SketchObject", "RecoveredLoftSketch")
            sketch.Label = "Recovered - " + section.Label.split(": ", 1)[-1]
            if make_sketch(saved, addTo=sketch, autoconstraints=False, delete=False) is None:
                raise ValueError("Could not recover the saved outline for '%s'." % section.Label)
            sketch.MapMode = "Deactivated"
            doc.recompute()
            recovered = section_wire(sketch)
            before, after = Part.Face(saved), Part.Face(recovered)
            if before.cut(after).Area + after.cut(before).Area > max(1e-7, before.Area * 1e-7):
                raise ValueError("The recovered sketch does not match the saved loft outline.")
            section.SourceSketch = sketch
            section.CoordinateParents = [body]
            section.Shape = cached
            section.Proxy._key = (sketch.Shape.hashCode(), tuple(sketch.getGlobalPlacement().toMatrix().A))
            if section.ViewObject:
                section.ViewObject.Visibility = False
            if sketch.ViewObject:
                sketch.ViewObject.Visibility = True
            restored.append(sketch)
        doc.recompute()
        if any("Invalid" in section.State for section in sections):
            raise ValueError("A recovered loft section is still invalid.")
        doc.commitTransaction()
        return restored
    except Exception:
        doc.abortTransaction()
        raise


class LoftPreview:
    def __init__(self, sketches):
        self.sketches = list(sketches)
        if len(self.sketches) < 2 or len(set(self.sketches)) != len(self.sketches):
            raise ValueError("Select at least two different sketches to loft.")
        if any(not obj.isDerivedFrom("Sketcher::SketchObject") for obj in self.sketches):
            raise ValueError("Select sketches only for a loft.")
        self.doc = self.sketches[0].Document
        self.document_name = self.doc.Name
        if any(obj.Document != self.doc for obj in self.sketches):
            raise ValueError("The loft sketches must be in the same document.")
        for sketch in self.sketches:
            section_wire(sketch)
        if self.doc.HasPendingTransaction:
            raise ValueError("Finish the current operation before lofting.")
        self.finished = False
        self.candidates = [obj for obj in self.doc.Objects
                           if mm.solid_object(obj) == obj and not obj.isDerivedFrom("App::Part")
                           and mm._visible(obj) and hasattr(obj, "Shape") and obj.Shape.Solids
                           and not obj.isDerivedFrom("PartDesign::SubShapeBinder")
                           and not obj.isDerivedFrom("PartDesign::ShapeBinder")]
        self.visibility = [(obj, obj.ViewObject.Visibility) for obj in self.candidates]
        self.cuts = []
        self.references = {}
        self.operation = "New Solid"
        self.doc.openTransaction("Loft sketches")
        try:
            self.sections = []
            for sketch in self.sketches:
                section = self.doc.addObject("Part::FeaturePython", "LoftSection")
                section.Label = "Loft section: " + sketch.Label
                section.addProperty("App::PropertyLinkGlobal", "SourceSketch", "456D Design")
                section.addProperty("App::PropertyLinkList", "CoordinateParents", "456D Design")
                section.SourceSketch = sketch
                parents = []
                parent = sketch.getParentGeoFeatureGroup()
                while parent:
                    parents.append(parent)
                    parent = parent.getParentGeoFeatureGroup()
                section.CoordinateParents = parents
                section.Proxy = LoftSection()
                section.ViewObject.Proxy = 0
                section.ViewObject.Visibility = False
                self.sections.append(section)
            self.feature = self.doc.addObject("Part::Loft", "EasyDesignLoft")
            self.feature.Label = "Loft"
            self.feature.Solid = True
            self.feature.Closed = False
            self.feature.Sections = self.sections
            self.feature.Ruled = len(sketches) == 2
            self.feature.ViewObject.ShapeColor = (0.32, 0.65, 0.78)
            self.doc.recompute()
            self.validate()
        except Exception:
            self.doc.abortTransaction()
            self.finished = True
            raise

    def validate(self):
        objects = self.sections + [self.feature]
        shape = self.feature.Shape
        if (any("Invalid" in obj.State for obj in objects) or shape.isNull()
                or not shape.isValid() or len(shape.Solids) != 1 or shape.Volume <= 1e-7):
            raise ValueError("Cannot loft these profiles in this order. Check their positions and order.")

    @property
    def result_objects(self):
        return self.cuts or [self.feature]

    def _clear_cuts(self):
        for cut in self.cuts:
            self.doc.removeObject(cut.Name)
        self.cuts = []
        for reference in self.references.values():
            self.doc.removeObject(reference.Name)
        self.references = {}
        for target, visible in self.visibility:
            target.ViewObject.Visibility = visible

    def set_operation(self, operation):
        if operation not in OPERATIONS:
            raise ValueError("Unknown loft operation.")
        tool = self.feature.Shape
        planned = []
        if operation != "New Solid":
            for target in self.candidates:
                base = mm._shape(target)
                if not base.BoundBox.intersect(tool.BoundBox) or base.common(tool).Volume <= 1e-7:
                    continue
                shape = base.cut(tool).removeSplitter()
                if shape.isNull() or not shape.Solids or shape.Volume <= 1e-7 or not shape.isValid():
                    raise ValueError("Loft would remove all or invalidate '%s'. Choose New Solid or change the profiles." % target.Label)
                planned.append((target, shape.Volume))
            if operation == "Subtract / Cut" and not planned:
                raise ValueError("Subtract / Cut requires the loft to enter an existing visible solid.")
        self._clear_cuts()
        for target, expected_volume in planned:
            cut = self.doc.addObject("Part::Cut", "LoftCut")
            cut.Label = target.Label + " (Loft cut)"
            cut.Base = mm._input(self.doc, target, self.references)
            cut.Tool = self.feature
            cut.Refine = True
            self.cuts.append(cut)
        self.doc.recompute()
        for (target, expected_volume), cut in zip(planned, self.cuts):
            if ("Invalid" in cut.State or not cut.Shape.isValid() or not cut.Shape.Solids
                    or abs(cut.Shape.Volume - expected_volume) > max(1e-7, expected_volume * 1e-7)):
                raise ValueError("Could not cut '%s' with this loft." % target.Label)
            mm._appearance(target, cut)
            target.ViewObject.Visibility = False
        for reference in self.references.values():
            reference.ViewObject.Visibility = False
        self.feature.ViewObject.Visibility = not self.cuts
        self.operation = operation

    def update(self, order, ruled, operation=None):
        if sorted(order) != list(range(len(self.sections))):
            raise ValueError("Invalid section order.")
        self.feature.Sections = [self.sections[index] for index in order]
        self.feature.Ruled = len(order) == 2 or ruled
        self.doc.recompute()
        self.validate()
        self.set_operation(operation or self.operation)

    def finish(self, accept):
        if self.finished:
            return
        if self.document_name in App.listDocuments():
            if accept:
                self.validate()
                if any("Invalid" in cut.State or not cut.Shape.isValid() or not cut.Shape.Solids
                       for cut in self.cuts):
                    raise ValueError("The loft cut is not valid.")
                self.doc.commitTransaction()
            else:
                self.doc.abortTransaction()
            self.doc.recompute()
        self.finished = True


class LoftTool(QtWidgets.QDialog):
    def __init__(self, owner, sketches):
        self.session = LoftPreview(sketches)
        super().__init__(owner.main, QtCore.Qt.Tool)
        self.owner = owner
        self.setObjectName("EasyDesignLoftControl")
        self.setWindowTitle("Loft")
        self.setMinimumWidth(280)
        layout = QtWidgets.QVBoxLayout(self)
        self.list = QtWidgets.QListWidget(self)
        self.list.setMaximumHeight(160)
        for index, sketch in enumerate(sketches):
            item = QtWidgets.QListWidgetItem(sketch.Label, self.list)
            item.setData(QtCore.Qt.UserRole, index)
        self.list.setCurrentRow(0)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.list)
        arrows = QtWidgets.QVBoxLayout()
        for offset, icon, label in ((-1, QtWidgets.QStyle.SP_ArrowUp, "Move section up"),
                                     (1, QtWidgets.QStyle.SP_ArrowDown, "Move section down")):
            button = QtWidgets.QToolButton(self)
            button.setIcon(self.style().standardIcon(icon))
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.clicked.connect(lambda checked=False, delta=offset: self.reorder(delta))
            arrows.addWidget(button)
        arrows.addStretch()
        row.addLayout(arrows)
        layout.addLayout(row)
        self.mode = QtWidgets.QComboBox(self)
        self.mode.addItems(["Smooth", "Straight"])
        self.mode.setCurrentIndex(1 if len(sketches) == 2 else 0)
        self.mode.setEnabled(len(sketches) > 2)
        self.mode.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.mode)
        self.operation = QtWidgets.QComboBox(self)
        self.operation.addItems(OPERATIONS)
        self.operation.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.operation)
        self.error = QtWidgets.QLabel(self)
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QtWidgets.QDialogButtonBox(self)
        self.apply = buttons.addButton("Apply", QtWidgets.QDialogButtonBox.AcceptRole)
        self.apply.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogApplyButton))
        cancel = buttons.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
        cancel.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCancelButton))
        self.apply.setStyleSheet("background: #176b40; color: white; min-height: 28px;")
        cancel.setStyleSheet("background: #a52c35; color: white; min-height: 28px;")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def reorder(self, offset):
        index = self.list.currentRow()
        target = index + offset
        if index < 0 or not 0 <= target < self.list.count():
            return
        item = self.list.takeItem(index)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)
        self.refresh()

    def refresh(self, *args):
        try:
            self.session.update([self.list.item(i).data(QtCore.Qt.UserRole)
                                 for i in range(self.list.count())], self.mode.currentIndex() == 1,
                                OPERATIONS[self.operation.currentIndex()])
            self.operation.setItemText(0, "Auto (Cut)" if self.session.cuts else "Auto (New Solid)")
            self.error.hide()
            self.apply.setEnabled(True)
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            self.error.setText(str(exc))
            self.error.show()
            self.apply.setEnabled(False)

    def accept(self):
        self.refresh()
        if self.apply.isEnabled():
            self.finish(True)

    def reject(self):
        self.finish(False)

    def closeEvent(self, event):
        self.finish(False)
        event.accept()

    def finish(self, accept):
        if self.session.finished:
            return
        features = self.session.result_objects if accept else []
        self.session.finish(accept)
        self.owner.loft_tool = None
        self.hide()
        self.deleteLater()
        if App.ActiveDocument == self.session.doc:
            if features:
                Gui.Selection.clearSelection()
                for feature in features:
                    Gui.Selection.addSelection(feature)
            self.owner.profile_signature = None
            self.owner._refresh_profiles()
            self.owner.update_gear()
