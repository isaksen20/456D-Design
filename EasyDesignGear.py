# SPDX-License-Identifier: LGPL-2.1-or-later

"""Editable sketch copies distributed around a user-drawn circle."""

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets


def circle_frame(sketch):
    if not sketch.isDerivedFrom("Sketcher::SketchObject"):
        raise ValueError("Select a circle sketch first.")
    circles = [geometry for index, geometry in enumerate(sketch.Geometry)
               if isinstance(geometry, Part.Circle) and not sketch.getConstruction(index)]
    if len(circles) != 1:
        raise ValueError("The reference sketch must contain one circle.")
    placement = sketch.getGlobalPlacement()
    return (placement.multVec(circles[0].Center),
            placement.Rotation.multVec(circles[0].Axis))


def rotated_placement(placement, center, axis, angle):
    rotation = App.Rotation(axis, angle)
    around = App.Placement(center - rotation.multVec(center), rotation)
    return around.multiply(placement)


class GearPreview:
    def __init__(self, circle, source, count=12):
        self.center, self.axis = circle_frame(circle)
        if source == circle or not source.isDerivedFrom("Sketcher::SketchObject") or not source.GeometryCount:
            raise ValueError("Choose a different, non-empty sketch to repeat.")
        self.doc = circle.Document
        if source.Document != self.doc:
            raise ValueError("Both sketches must be in the same document.")
        if self.doc.HasPendingTransaction:
            raise ValueError("Finish the current operation before creating a Gear pattern.")
        self.document_name = self.doc.Name
        self.source = source
        self.source_placement = App.Placement(source.getGlobalPlacement())
        self.finished = False
        self.copies = []
        self.doc.openTransaction("Gear sketch pattern")
        try:
            self.group = self.doc.addObject("PartDesign::Body", "GearPattern")
            self.group.addProperty("App::PropertyInteger", "Count", "Gear")
            self.group.addProperty("App::PropertyAngle", "Spacing", "Gear")
            self.group.setEditorMode("Count", 1)
            self.group.setEditorMode("Spacing", 1)
            self.set_count(count)
        except Exception:
            self.doc.abortTransaction()
            self.finished = True
            raise

    def _copy(self):
        # Snapshot the solved geometry, without face attachments or external
        # constraints that would pull a rotated copy back to its old support.
        copy = self.group.newObject("Sketcher::SketchObject", "GearSketch")
        for index, geometry in enumerate(self.source.Geometry):
            copy.addGeometry(geometry.copy(), self.source.getConstruction(index))
        if "EasyDesignShape" in self.source.PropertiesList:
            copy.addProperty("App::PropertyString", "EasyDesignShape", "456D Design")
            copy.EasyDesignShape = self.source.EasyDesignShape
        if copy.ViewObject:
            for name in ("LineColor", "PointColor", "ShapeColor", "LineWidth", "PointSize"):
                if hasattr(self.source.ViewObject, name) and hasattr(copy.ViewObject, name):
                    setattr(copy.ViewObject, name, getattr(self.source.ViewObject, name))
            copy.ViewObject.Visibility = True
        return copy

    def set_count(self, count):
        if self.finished or self.document_name not in App.listDocuments():
            raise ValueError("The Gear document is no longer open.")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 360:
            raise ValueError("Count must be a whole number from 1 to 360.")
        while len(self.copies) > count - 1:
            self.doc.removeObject(self.copies.pop().Name)
        while len(self.copies) < count - 1:
            self.copies.append(self._copy())
        for index, copy in enumerate(self.copies, 1):
            copy.Placement = rotated_placement(self.source_placement, self.center, self.axis,
                                               index * 360.0 / count)
            copy.Label = "%s (Gear %d/%d)" % (self.source.Label, index + 1, count)
        self.group.Count = count
        self.group.Spacing = 360.0 / count
        self.group.Label = "Gear (%d)" % count
        self.doc.recompute()
        if any("Invalid" in obj.State or obj.Shape.isNull() or not obj.Shape.isValid()
               for obj in self.copies):
            raise ValueError("Cannot repeat this sketch. Check its geometry.")

    def finish(self, accept):
        if self.finished:
            return
        if self.document_name in App.listDocuments():
            if accept:
                self.doc.commitTransaction()
            else:
                self.doc.abortTransaction()
            self.doc.recompute()
        self.finished = True


class _CountInput(QtWidgets.QSpinBox):
    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.parent().accept()
            event.accept()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.parent().reject()
            event.accept()
        else:
            super().keyPressEvent(event)


class GearTool(QtWidgets.QDialog):
    def __init__(self, owner, circle):
        self.center, unused = circle_frame(circle)
        super().__init__(owner.main, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.owner, self.circle = owner, circle
        self.document_name = circle.Document.Name
        self.session = None
        self.finished = False
        self.setObjectName("EasyDesignGearControl")
        self.setWindowTitle("Gear")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Gear", self))
        self.count = _CountInput(self)
        self.count.setObjectName("EasyDesignGearCount")
        self.count.setRange(1, 360)
        self.count.setValue(12)
        self.count.setKeyboardTracking(False)
        self.count.setToolTip("Total occurrences, including the original sketch")
        self.count.setAccessibleName("Gear count")
        self.count.setMinimumWidth(80)
        self.count.valueChanged.connect(self.refresh)
        row.addWidget(self.count)
        for accept, name, color, symbol in (
                (True, "Apply", "#176b3b", QtWidgets.QStyle.SP_DialogApplyButton),
                (False, "Cancel", "#a52d35", QtWidgets.QStyle.SP_DialogCloseButton)):
            button = QtWidgets.QToolButton(self)
            button.setObjectName("EasyDesignGear" + name)
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setIcon(owner._contrast_icon(self.style().standardIcon(symbol)))
            button.setIconSize(QtCore.QSize(22, 22))
            button.setFixedSize(32, 32)
            button.setStyleSheet("QToolButton { background: %s; border-radius: 3px; }" % color)
            button.clicked.connect(self.accept if accept else self.reject)
            row.addWidget(button)
            if accept:
                self.apply = button
        layout.addLayout(row)
        self.error = QtWidgets.QLabel(self)
        self.error.setWordWrap(True)
        self.error.setMaximumWidth(320)
        self.error.hide()
        layout.addWidget(self.error)

    def pick_selection(self):
        if self.finished or self.session:
            return
        selected = Gui.Selection.getSelection()
        if len(selected) != 1 or selected[0] == self.circle:
            return
        try:
            self.session = GearPreview(self.circle, selected[0], self.count.value())
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            self.owner.main.statusBar().showMessage(str(exc), 5000)
            return
        self.owner.main.statusBar().clearMessage()
        self.owner.selected_region = None
        self.owner.profile_signature = None
        self.owner._refresh_profiles()
        self.show()
        self.position()
        self.count.setFocus()
        self.count.selectAll()

    def position(self):
        viewport = self.owner._viewport_widget()
        if not viewport or not self.owner.view or not self.isVisible():
            return
        self.adjustSize()
        x, y = self.owner.view.getPointOnViewport(self.center)
        point = QtCore.QPoint(max(6, min(round(x) + 30, viewport.width() - self.width() - 6)),
                             max(6, min(viewport.height() - round(y) + 30,
                                        viewport.height() - self.height() - 6)))
        self.move(viewport.mapToGlobal(point))

    def refresh(self, *unused):
        if not self.session or self.finished:
            return
        try:
            self.session.set_count(self.count.value())
            self.error.hide()
            self.apply.setEnabled(True)
            self.owner.profile_signature = None
            self.owner._refresh_profiles()
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            self.error.setText(str(exc))
            self.error.show()
            self.apply.setEnabled(False)
        self.position()

    def accept(self):
        self.count.interpretText()
        self.refresh()
        if self.session and self.apply.isEnabled():
            self.finish(True)

    def reject(self):
        self.finish(False)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.finish(False)
        event.accept()

    def finish(self, accept):
        if self.finished:
            return
        self.finished = True
        self.owner.gear_tool = None
        active = App.ActiveDocument and App.ActiveDocument.Name == self.document_name
        if self.session:
            copies = list(self.session.copies) if accept and active else []
            self.session.finish(accept)
            if copies:
                Gui.Selection.clearSelection()
                for copy in copies:
                    Gui.Selection.addSelection(copy)
        self.hide()
        self.deleteLater()
        if active:
            self.owner.profile_signature = None
            self.owner._refresh_profiles()
            self.owner.update_gear()
        self.owner.main.statusBar().clearMessage()
