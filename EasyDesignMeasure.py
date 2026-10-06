# SPDX-License-Identifier: LGPL-2.1-or-later

"""Compact measurements backed by FreeCAD's geometry kernel."""

import math

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets

import EasyDesignCommands as commands
from EasyDesignRegions import profile_regions, region_at


MODES = ("Distance", "Angle", "Area", "Volume")
UNITS = {"Distance": "mm", "Angle": "deg", "Area": "mm^2", "Volume": "mm^3"}


def _world_shape(obj, shape):
    result = shape.copy()
    parent = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
    result.Placement = parent.multiply(result.Placement)
    return result


def selected_shapes(selection, whole_objects=False):
    records = []
    seen = set()
    for item in selection:
        obj = item.Object
        if whole_objects:
            obj = commands._body_of(obj) or obj
            if obj.Name in seen:
                continue
            seen.add(obj.Name)
            shapes = [("", obj.Shape)]
        else:
            shapes = list(zip(item.SubElementNames, item.SubObjects)) if item.SubObjects else [("", obj.Shape)]
        for name, shape in shapes:
            if not shape.isNull():
                records.append((obj, name, _world_shape(obj, shape)))
    return records


def _axis(shape):
    if shape.ShapeType == "Face" and isinstance(shape.Surface, Part.Plane):
        u0, u1, v0, v1 = shape.ParameterRange
        return shape.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
    if shape.ShapeType == "Edge" and isinstance(shape.Curve, Part.Line):
        return shape.tangentAt((shape.FirstParameter + shape.LastParameter) / 2)
    return None


def measure(mode, records, selected_region=None):
    if not records:
        return None
    shapes = [shape for _, _, shape in records]
    if mode == "Distance":
        if len(shapes) == 2:
            return shapes[0].distToShape(shapes[1])[0]
        if len(shapes) == 1 and shapes[0].ShapeType == "Edge":
            return shapes[0].Length
        return None
    if mode == "Angle":
        if len(shapes) != 2:
            return None
        first, second = _axis(shapes[0]), _axis(shapes[1])
        return math.degrees(first.getAngle(second)) if first is not None and second is not None else None
    if mode == "Area":
        total = 0.0
        for (obj, name, shape) in records:
            if not name and obj.isDerivedFrom("Sketcher::SketchObject"):
                if selected_region and selected_region[0] == obj:
                    total += region_at(obj, selected_region[1]).Area
                else:
                    total += sum(face.Area for face in profile_regions(obj))
            else:
                total += shape.Area
        return total if total > 1e-9 else None
    if mode == "Volume":
        total = sum(shape.Volume for shape in shapes)
        return total if total > 1e-9 else None
    raise ValueError("Unknown measurement mode: %s" % mode)


class MeasureTool:
    def __init__(self, owner):
        self.owner = owner
        self.closed = False
        self.dock = QtWidgets.QDockWidget("Measure", owner.main)
        self.dock.setObjectName("EasyDesignMeasureDock")
        self.dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        self.dock.setFeatures(QtWidgets.QDockWidget.DockWidgetClosable |
                              QtWidgets.QDockWidget.DockWidgetMovable)
        contents = QtWidgets.QWidget(self.dock)
        layout = QtWidgets.QVBoxLayout(contents)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        modes = QtWidgets.QHBoxLayout()
        modes.setSpacing(1)
        self.mode_group = QtWidgets.QButtonGroup(contents)
        self.mode_group.setExclusive(True)
        for index, name in enumerate(MODES):
            button = QtWidgets.QToolButton(contents)
            button.setText(name)
            button.setCheckable(True)
            button.setFixedHeight(30)
            button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            button.setObjectName("EasyDesignMeasure" + name)
            button.setToolTip("Measure " + name.lower())
            self.mode_group.addButton(button, index)
            modes.addWidget(button)
        layout.addLayout(modes)
        self.mode_group.button(0).setChecked(True)
        self.mode_group.buttonClicked.connect(self._mode_changed)

        selection = QtWidgets.QHBoxLayout()
        selection.setSpacing(1)
        self.scope_group = QtWidgets.QButtonGroup(contents)
        self.scope_group.setExclusive(True)
        for index, name in enumerate(("Element", "Object")):
            button = QtWidgets.QToolButton(contents)
            button.setText(name)
            button.setCheckable(True)
            button.setFixedHeight(28)
            button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            button.setToolTip("Use selected " + ("face, edge or vertex" if index == 0 else "whole objects"))
            self.scope_group.addButton(button, index)
            selection.addWidget(button)
        self.scope_group.button(0).setChecked(True)
        self.scope_group.buttonClicked.connect(self.refresh)
        layout.addLayout(selection)

        self.selection_label = QtWidgets.QLabel(contents)
        self.selection_label.setObjectName("EasyDesignMeasureSelection")
        layout.addWidget(self.selection_label)
        result_row = QtWidgets.QHBoxLayout()
        self.result = QtWidgets.QLabel("--", contents)
        self.result.setObjectName("EasyDesignMeasureResult")
        self.result.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        font = self.result.font()
        font.setPointSize(max(13, font.pointSize() + 3))
        self.result.setFont(font)
        result_row.addWidget(self.result, 1)
        clear = QtWidgets.QToolButton(contents)
        clear.setObjectName("EasyDesignMeasureClear")
        clear.setIcon(QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        clear.setToolTip("Clear selection")
        clear.setFixedSize(30, 30)
        clear.clicked.connect(Gui.Selection.clearSelection)
        result_row.addWidget(clear)
        layout.addLayout(result_row)
        layout.addStretch(1)
        self.dock.setWidget(contents)
        self.dock.setMinimumWidth(300)
        owner.main.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.dock)
        self.dock.visibilityChanged.connect(self._visibility_changed)
        Gui.Selection.addObserver(self)
        self.dock.show()
        self.refresh()

    def _visibility_changed(self, visible):
        if not visible and not self.closed:
            self.close()

    def _mode_changed(self, *unused):
        volume = MODES[self.mode_group.checkedId()] == "Volume"
        self.scope_group.button(0).setEnabled(not volume)
        if volume:
            self.scope_group.button(1).setChecked(True)
        self.refresh()

    def addSelection(self, *unused):
        QtCore.QTimer.singleShot(0, self.refresh)

    def removeSelection(self, *unused):
        QtCore.QTimer.singleShot(0, self.refresh)

    def clearSelection(self, *unused):
        QtCore.QTimer.singleShot(0, self.refresh)

    def refresh(self, *unused):
        if self.closed:
            return
        mode = MODES[self.mode_group.checkedId()]
        whole = self.scope_group.checkedId() == 1
        records = selected_shapes(Gui.Selection.getSelectionEx(), whole)
        self.selection_label.setText("%d selected" % len(records))
        try:
            value = measure(mode, records, self.owner.selected_region if not whole else None)
        except (Part.OCCError, ValueError, RuntimeError):
            value = None
        self.result.setText("%g %s" % (value, UNITS[mode]) if value is not None else "--")

    def close(self):
        if self.closed:
            return
        self.closed = True
        Gui.Selection.removeObserver(self)
        if self.owner.measure_tool is self:
            self.owner.measure_tool = None
        self.dock.close()
        self.dock.deleteLater()
        if not self.owner.closed:
            self.owner.update_gear()
