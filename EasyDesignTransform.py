# SPDX-License-Identifier: LGPL-2.1-or-later

import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets


AXES = (App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1))
COLORS = ("#eb665d", "#66c77b", "#68bfff")
MODES = ("Move X", "Move Y", "Move Z", "Rotate X", "Rotate Y", "Rotate Z")


def soft_snap_angle(value):
    nearest = round(value / 5.0) * 5.0
    return nearest if abs(value - nearest) <= 0.75 else value


class TransformPreview:
    def __init__(self, obj):
        self.obj = obj
        self.doc = obj.Document
        self.document_name = self.doc.Name
        self.property = "AttachmentOffset" if getattr(obj, "MapMode", "Deactivated") != "Deactivated" else "Placement"
        if self.property not in obj.PropertiesList or obj.getEditorMode(self.property) == 1:
            raise ValueError("This object cannot be moved directly.")
        self.original = App.Placement(getattr(obj, self.property))
        self.global_original = obj.getGlobalPlacement()
        self.parent = self.global_original.multiply(self.original.inverse())
        self.center = (obj.Shape.BoundBox.Center if hasattr(obj, "Shape") and not obj.Shape.isNull()
                       else obj.Placement.Base)
        # Shapes are in their parent's coordinates, unlike global placements.
        if self.property == "Placement":
            self.center = self.parent.multVec(self.center)
        else:
            parent = self.global_original.multiply(obj.Placement.inverse())
            self.center = parent.multVec(self.center)
        self.values = [0.0] * 6
        self.finished = False
        self.doc.openTransaction("Move / rotate")

    @property
    def current_center(self):
        return self.center + App.Vector(*self.values[:3])

    def set_value(self, index, value):
        values = list(self.values)
        values[index] = value
        rotation = App.Rotation()
        for axis, angle in zip(AXES, values[3:]):
            rotation = App.Rotation(axis, angle).multiply(rotation)
        delta = App.Placement(self.center + App.Vector(*values[:3]), rotation).multiply(
            App.Placement(-self.center, App.Rotation()))
        placement = self.parent.inverse().multiply(delta.multiply(self.global_original))
        setattr(self.obj, self.property, placement)
        self.doc.recompute()
        self.values = values

    def finish(self, accept):
        if self.finished:
            return
        if self.document_name not in App.listDocuments():
            self.finished = True
            return
        if accept:
            self.doc.commitTransaction()
        else:
            self.doc.abortTransaction()
        self.doc.recompute()
        self.finished = True


class MultiTransformPreview:
    def __init__(self, objects):
        self.objects = list(objects)
        self.obj = self.objects[0]
        self.doc = self.obj.Document
        self.document_name = self.doc.Name
        self.states = []
        centers = []
        for obj in self.objects:
            if obj.Document != self.doc:
                raise ValueError("Move objects from one document at a time.")
            prop = "AttachmentOffset" if getattr(obj, "MapMode", "Deactivated") != "Deactivated" else "Placement"
            if prop not in obj.PropertiesList or obj.getEditorMode(prop) == 1:
                raise ValueError("One of the selected objects cannot be moved directly.")
            original = App.Placement(getattr(obj, prop))
            global_original = obj.getGlobalPlacement()
            parent = global_original.multiply(original.inverse())
            bounds = obj.Shape.BoundBox if hasattr(obj, "Shape") and not obj.Shape.isNull() else None
            local_center = bounds.Center if bounds else obj.Placement.Base
            if prop == "Placement":
                centers.append(parent.multVec(local_center))
            else:
                centers.append(global_original.multiply(obj.Placement.inverse()).multVec(local_center))
            self.states.append((obj, prop, global_original, parent))
        self.center = sum(centers[1:], centers[0]) / len(centers)
        self.values = [0.0] * 6
        self.finished = False
        self.doc.openTransaction("Move / rotate")

    @property
    def current_center(self):
        return self.center + App.Vector(*self.values[:3])

    def set_value(self, index, value):
        values = list(self.values)
        values[index] = value
        rotation = App.Rotation()
        for axis, angle in zip(AXES, values[3:]):
            rotation = App.Rotation(axis, angle).multiply(rotation)
        delta = App.Placement(self.center + App.Vector(*values[:3]), rotation).multiply(
            App.Placement(-self.center, App.Rotation()))
        for obj, prop, original, parent in self.states:
            setattr(obj, prop, parent.inverse().multiply(delta.multiply(original)))
        self.doc.recompute()
        self.values = values

    def finish(self, accept):
        if self.finished:
            return
        if self.document_name not in App.listDocuments():
            self.finished = True
            return
        if accept:
            self.doc.commitTransaction()
        else:
            self.doc.abortTransaction()
        self.doc.recompute()
        self.finished = True


class _ValueInput(QtWidgets.QDoubleSpinBox):
    def __init__(self, tool, parent):
        super().__init__(parent)
        self.tool = tool
        self.setRange(-100000, 100000)
        self.setDecimals(2)
        self.setKeyboardTracking(False)
        self.setFixedSize(116, 32)
        self.typing = False

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.tool.finish(True)
        elif event.key() == QtCore.Qt.Key_Escape:
            self.tool.finish(False)
        else:
            if not self.typing and event.text() and all(c.isdigit() or c in ".,+-" for c in event.text()):
                self.selectAll()
            self.typing = True
            super().keyPressEvent(event)


class _Gizmo(QtWidgets.QWidget):
    def __init__(self, tool, parent):
        super().__init__(parent)
        self.tool = tool
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.setObjectName("EasyDesignTransformGizmo")

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        for index, points in self.tool.paths.items():
            painter.setBrush(QtCore.Qt.NoBrush)
            active = index == self.tool.mode.currentIndex()
            color = QtGui.QColor("#ffd84c" if active else COLORS[index % 3])
            painter.setPen(QtGui.QPen(QtGui.QColor("#26333c"), 5 if active else 4))
            path = QtGui.QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.drawPath(path)
            painter.setPen(QtGui.QPen(color, 3 if active else 2))
            painter.drawPath(path)
            if index < 3:
                tip, base = points[-1], points[-2]
                direction = tip - base
                length = math.hypot(direction.x(), direction.y())
                if length > 1:
                    direction /= length
                    side = QtCore.QPointF(-direction.y(), direction.x())
                    painter.setBrush(color)
                    painter.drawPolygon(QtGui.QPolygonF([
                        tip, tip - direction * 14 + side * 6, tip - direction * 14 - side * 6]))
                painter.drawText(tip + QtCore.QPointF(8, -8), "XYZ"[index])
            else:
                painter.setBrush(color)
                painter.drawEllipse(points[len(points) // 2], 5, 5)
        painter.end()


class TransformTool(QtCore.QObject):
    def __init__(self, owner, obj):
        viewport = owner._viewport_widget()
        if not viewport:
            raise ValueError("The 3D view is not available.")
        super().__init__(viewport)
        self.owner = owner
        self.viewport = viewport
        self.session = MultiTransformPreview(obj) if isinstance(obj, (list, tuple)) else TransformPreview(obj)
        self.paths = {}
        self.drag = None
        self.closed = False
        self.overlay = _Gizmo(self, viewport)
        self.panel = QtWidgets.QWidget(viewport)
        self.panel.setObjectName("EasyDesignTransformControl")
        self.panel.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.panel.setStyleSheet("QWidget#EasyDesignTransformControl { background: #f5f7f8;"
                                 "border: 1px solid #a9b7bf; border-radius: 4px; }")
        layout = QtWidgets.QHBoxLayout(self.panel)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(4)
        self.mode = QtWidgets.QComboBox(self.panel)
        self.mode.setObjectName("EasyDesignTransformAxis")
        self.mode.addItems(MODES)
        self.mode.setFixedSize(108, 32)
        self.mode.setToolTip("Translation or rotation axis")
        layout.addWidget(self.mode)
        self.input = _ValueInput(self, self.panel)
        self.input.setObjectName("EasyDesignTransformValue")
        self.input.valueChanged.connect(self.set_value)
        layout.addWidget(self.input)
        style = QtWidgets.QApplication.style()
        for accept, icon, color in ((True, QtWidgets.QStyle.SP_DialogApplyButton, "#176b3b"),
                                    (False, QtWidgets.QStyle.SP_DialogCloseButton, "#a52d35")):
            button = QtWidgets.QToolButton(self.panel)
            button.setObjectName("EasyDesignTransformApply" if accept else "EasyDesignTransformCancel")
            button.setIcon(owner._contrast_icon(style.standardIcon(icon)))
            button.setIconSize(QtCore.QSize(22, 22))
            button.setFixedSize(32, 32)
            button.setToolTip("Apply" if accept else "Cancel")
            button.setStyleSheet("QToolButton { background: %s; border-radius: 3px; }" % color)
            button.clicked.connect(lambda checked=False, accept=accept: self.finish(accept))
            layout.addWidget(button)
        self.mode.currentIndexChanged.connect(self.select_mode)
        self.panel.adjustSize()
        viewport.installEventFilter(self)
        self.select_mode(0)
        self.overlay.show()
        self.panel.show()
        self.refresh()
        self.input.setFocus()
        self.input.selectAll()

    def project(self, point):
        x, y = self.owner.view.getPointOnViewport(point)
        return QtCore.QPointF(x, self.viewport.height() - y)

    def refresh(self):
        if self.closed:
            return
        self.overlay.setGeometry(self.viewport.rect())
        center = self.session.current_center
        origin = self.project(center)
        scales = [(self.project(center + axis * 10) - origin).manhattanLength() / 10 for axis in AXES]
        radius = 85 / max(max(scales), 0.1)
        self.paths = {}
        for index, axis in enumerate(AXES):
            self.paths[index] = [self.project(center + axis * radius * .22),
                                 self.project(center + axis * radius)]
            a, b = AXES[(index + 1) % 3], AXES[(index + 2) % 3]
            self.paths[index + 3] = [self.project(center + (a * math.cos(t) + b * math.sin(t)) * radius * 1.2)
                                      for t in [math.radians(15 + step * 7.5) for step in range(43)]]
        self.overlay.update()
        left = max(6, min(int(origin.x()) - self.panel.width() // 2,
                          self.viewport.width() - self.panel.width() - 6))
        top = max(6, min(int(origin.y()) + 120, self.viewport.height() - self.panel.height() - 6))
        self.panel.move(left, top)
        self.overlay.raise_()
        self.panel.raise_()

    def select_mode(self, index):
        self.input.blockSignals(True)
        self.input.setSuffix(" mm" if index < 3 else " deg")
        self.input.setValue(self.session.values[index])
        self.input.typing = False
        self.input.blockSignals(False)
        self.refresh()

    def set_value(self, value):
        try:
            self.session.set_value(self.mode.currentIndex(), value)
            if any(obj.isDerivedFrom("Sketcher::SketchObject")
                   for obj in getattr(self.session, "objects", [self.session.obj])):
                self.owner._refresh_profiles()
            self.refresh()
        except (ValueError, RuntimeError) as exc:
            self.owner.main.statusBar().showMessage(str(exc), 4000)
            self.select_mode(self.mode.currentIndex())

    def hit(self, point):
        candidates = []
        for index, points in self.paths.items():
            for a, b in zip(points, points[1:]):
                segment = b - a
                length2 = segment.x() ** 2 + segment.y() ** 2
                if length2 < 1e-6:
                    continue
                relative = point - a
                t = max(0, min(1, (relative.x() * segment.x() + relative.y() * segment.y()) / length2))
                distance = point - (a + segment * t)
                candidates.append((math.hypot(distance.x(), distance.y()), index))
        arrow_distance, arrow = min((item for item in candidates if item[1] < 3), default=(100, 0))
        if arrow_distance <= 3:
            return arrow
        distance, index = min(candidates, default=(100, 0))
        return index if distance <= 10 else None

    def rotation_angle(self, point, index):
        axis = AXES[index - 3]
        center = self.session.current_center
        ray_start = self.owner.view.getPoint(int(point.x()), self.viewport.height() - int(point.y()))
        node = self.owner.view.getCameraNode()
        if self.owner.view.getCameraType() == "Perspective":
            camera = App.Vector(*node.position.getValue().getValue())
            ray = ray_start - camera
            ray_start = camera
        else:
            ray = self.owner.view.getCameraOrientation().multVec(App.Vector(0, 0, -1))
        denominator = ray.dot(axis)
        if abs(denominator) < ray.Length * 0.03:
            return None
        hit = ray_start + ray * ((center - ray_start).dot(axis) / denominator)
        relative = hit - center
        a, b = AXES[(index - 2) % 3], AXES[(index - 1) % 3]
        return math.atan2(relative.dot(b), relative.dot(a))

    def eventFilter(self, watched, event):
        if self.closed:
            return False
        kind = event.type()
        if kind == QtCore.QEvent.ToolTip:
            index = self.hit(QtCore.QPointF(event.pos()))
            if index is not None:
                QtWidgets.QToolTip.showText(event.globalPos(), MODES[index], self.viewport)
                return True
        if kind == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
            index = self.hit(QtCore.QPointF(event.pos()))
            if index is None:
                return False
            self.input.interpretText()
            self.mode.setCurrentIndex(index)
            center = self.session.current_center
            origin = self.project(center)
            self.drag = dict(index=index, start=QtCore.QPointF(event.pos()),
                             value=self.session.values[index], origin=origin,
                             direction=(self.project(center + AXES[index % 3] * 10) - origin) / 10,
                             angle=self.rotation_angle(QtCore.QPointF(event.pos()), index) if index >= 3 else None,
                             total=0.0)
            self.viewport.grabMouse()
            return True
        if kind == QtCore.QEvent.MouseMove and self.drag:
            drag = self.drag
            point = QtCore.QPointF(event.pos())
            if drag["index"] < 3:
                direction = drag["direction"]
                length2 = direction.x() ** 2 + direction.y() ** 2
                movement = point - drag["start"]
                delta = ((movement.x() * direction.x() + movement.y() * direction.y()) / length2
                         if length2 >= .04 else -movement.y() / max(1, self.viewport.height() / 150))
                value = self.owner._snap_value(drag["value"] + delta)
            else:
                # Intersect the cursor ray with the rotation plane, avoiding
                # screen-angle reversal when an axis points away from the eye.
                angle = self.rotation_angle(point, drag["index"])
                if angle is None:
                    value = drag["value"] + (point.x() - drag["start"].x()) * .5
                else:
                    if drag["angle"] is not None:
                        drag["total"] += math.degrees(math.atan2(math.sin(angle - drag["angle"]),
                                                                 math.cos(angle - drag["angle"])))
                    drag["angle"] = angle
                    value = drag["value"] + drag["total"]
                value = soft_snap_angle(value)
            self.input.setValue(round(value, 2))
            return True
        if kind == QtCore.QEvent.MouseButtonRelease and self.drag and event.button() == QtCore.Qt.LeftButton:
            self.drag = None
            self.viewport.releaseMouse()
            self.input.setFocus()
            self.input.selectAll()
            self.input.typing = False
            return True
        if kind == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
            self.finish(False)
            return True
        if kind in (QtCore.QEvent.UngrabMouse, QtCore.QEvent.WindowDeactivate):
            self.drag = None
        return False

    def finish(self, accept):
        if self.closed:
            return
        if accept:
            self.input.interpretText()
        self.session.finish(accept)
        self.closed = True
        self.owner.transform_tool = None
        # Closing a document can destroy the viewport before the controller runs.
        try:
            if QtWidgets.QWidget.mouseGrabber() is self.viewport:
                self.viewport.releaseMouse()
            self.viewport.removeEventFilter(self)
        except RuntimeError:
            pass
        for widget in (self.panel, self.overlay):
            try:
                widget.hide()
                widget.deleteLater()
            except RuntimeError:
                pass
        self.owner._refresh_profiles()
        self.owner.update_gear()
        try:
            self.deleteLater()
        except RuntimeError:
            pass
