# SPDX-License-Identifier: LGPL-2.1-or-later

"""The temporary drawing surface and viewport controls for 456D Design."""

import math

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets
from pivy import coin

import EasyDesignCommands as commands
import EasyDesignOrbit as orbit
import EasyDesignSketch as sketch_tools


_controller = None


def _icon(name):
    from EasyDesignIcons import icon as modelling_icon
    icon = modelling_icon(name)
    if icon is not None:
        return icon
    if name in ("EasyDesignLocked", "EasyDesignUnlocked"):
        icon = QtGui.QIcon.fromTheme("object-locked" if name == "EasyDesignLocked" else "object-unlocked")
        return icon if not icon.isNull() else Gui.getIcon("Constraint_Block")
    replacements = {
        "Std_Transform": "PartDesign_MultiTransform",
        "Std_Group": "PartDesign_MultiTransform",
    }
    themed = {
        "Std_Undo": ("edit-undo", QtWidgets.QStyle.SP_ArrowBack),
        "Std_Redo": ("edit-redo", QtWidgets.QStyle.SP_ArrowForward),
        "Std_Copy": ("edit-copy", QtWidgets.QStyle.SP_FileIcon),
        "Std_Paste": ("edit-paste", QtWidgets.QStyle.SP_DialogOpenButton),
        "Std_Measure": ("tool-measure", QtWidgets.QStyle.SP_FileDialogDetailedView),
        "Std_ViewAxonometric": ("view-refresh", QtWidgets.QStyle.SP_BrowserReload),
        "Std_ViewTop": ("view-grid", QtWidgets.QStyle.SP_DirIcon),
        "Std_ViewFitAll": ("zoom-fit-best", QtWidgets.QStyle.SP_ComputerIcon),
        "Std_ToggleVisibility": ("view-grid", QtWidgets.QStyle.SP_DirIcon),
    }
    if name in themed:
        theme_name, fallback = themed[name]
        icon = QtGui.QIcon.fromTheme(theme_name)
        return icon if not icon.isNull() else QtWidgets.QApplication.style().standardIcon(fallback)
    return Gui.getIcon(replacements.get(name, name))


def _lines(points, lengths, color, width=1, opacity=1):
    node = coin.SoSeparator()
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    node.addChild(pick)
    base = coin.SoMaterial()
    base.diffuseColor.setValue(*color)
    base.emissiveColor.setValue(0, 0, 0)
    base.transparency.setValue(1 - opacity)
    node.addChild(base)
    draw = coin.SoDrawStyle()
    draw.lineWidth = width
    node.addChild(draw)
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(points), points)
    node.addChild(coords)
    shape = coin.SoLineSet()
    shape.numVertices.setValues(0, len(lengths), lengths)
    node.addChild(shape)
    return node


def _grid(placement=None, faint=False, bounds=None):
    local = bounds is not None
    xmin, xmax, ymin, ymax = bounds if local else (-175, 175, -175, 175)
    def map_point(x, y, z):
        point = App.Vector(x, y, z)
        if placement:
            point = placement.multVec(point)
        return (point.x, point.y, point.z)

    root = coin.SoSeparator()
    surface_z = 0.03 if placement else -0.1
    line_z = 0.04 if placement else -0.08
    surface = coin.SoSeparator()
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    surface.addChild(pick)
    material = coin.SoMaterial()
    material.diffuseColor.setValue(0.75, 0.94, 0.97)
    material.transparency.setValue(0.99 if faint else (0.88 if local else 0.65))
    surface.addChild(material)
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, 4, [map_point(xmin, ymin, surface_z),
                                   map_point(xmax, ymin, surface_z),
                                   map_point(xmax, ymax, surface_z),
                                   map_point(xmin, ymax, surface_z)])
    surface.addChild(coords)
    face = coin.SoFaceSet()
    face.numVertices.setValue(4)
    surface.addChild(face)
    root.addChild(surface)
    minor, major = [], []
    for value in range(math.ceil(xmin / 5) * 5, math.floor(xmax / 5) * 5 + 1, 5):
        target = major if value % 25 == 0 else minor
        target.extend((map_point(value, ymin, line_z), map_point(value, ymax, line_z)))
    for value in range(math.ceil(ymin / 5) * 5, math.floor(ymax / 5) * 5 + 1, 5):
        target = major if value % 25 == 0 else minor
        target.extend((map_point(xmin, value, line_z), map_point(xmax, value, line_z)))
    root.addChild(_lines(minor, [2] * (len(minor) // 2), (0.64, 0.87, 0.95), opacity=.035 if faint else 1))
    root.addChild(_lines(major, [2] * (len(major) // 2), (0.24, 0.72, 0.90), 1.5, opacity=.07 if faint else 1))
    if faint:
        return root

    if local:
        border = [map_point(x, y, line_z) for x, y in
                  ((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin))]
        root.addChild(_lines(border, [5], (0.24, 0.72, 0.90)))
        ring = [map_point(.8 * math.cos(i * math.tau / 32), .8 * math.sin(i * math.tau / 32), line_z + .02)
                for i in range(33)]
        root.addChild(_lines(ring, [33], (0.12, 0.63, 0.77), 2))

    labels = coin.SoSeparator()
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    labels.addChild(pick)
    color = coin.SoBaseColor()
    color.rgb.setValue(0.10, 0.63, 0.83)
    labels.addChild(color)
    positions = [(value, (value, ymin - 5, 0))
                 for value in range(math.ceil(xmin / 25) * 25, math.floor(xmax / 25) * 25 + 1, 25) if value]
    positions += [(value, (xmin - 6, value, 0))
                  for value in range(math.ceil(ymin / 25) * 25, math.floor(ymax / 25) * 25 + 1, 25) if value]
    for value, position in positions:
        label = coin.SoSeparator()
        transform = coin.SoTranslation()
        transform.translation.setValue(*map_point(*position))
        label.addChild(transform)
        text = coin.SoText2()
        text.string.setValue(str(value))
        label.addChild(text)
        labels.addChild(label)
    root.addChild(labels)
    return root


def _local_grid_bounds(points):
    bounds = []
    for axis in ("x", "y"):
        lower, upper = min(getattr(p, axis) for p in points), max(getattr(p, axis) for p in points)
        margin = max(15, (upper - lower) * .6)
        bounds.extend((math.floor((lower - margin) / 5) * 5, math.ceil((upper + margin) / 5) * 5))
    return tuple(bounds)


def _face_grid(view, obj, name, pixel):
    face = obj.Shape.getElement(name)
    if not isinstance(face.Surface, Part.Plane):
        raise ValueError("This sketch tool needs a flat face.")
    parent = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
    points = [parent.multVec(vertex.Point) for vertex in face.Vertexes]
    if not points:
        raise ValueError("This face has no corner to anchor a grid.")
    corner = min(points, key=lambda point: math.hypot(
        view.getPointOnViewport(point)[0] - pixel[0], view.getPointOnViewport(point)[1] - pixel[1]))
    normal = parent.Rotation.multVec(face.normalAt(0, 0))
    # The face fixes the orientation; changing corners only translates the grid.
    direction = parent.Rotation.multVec(face.Surface.Rotation.multVec(App.Vector(1, 0, 0)))
    rotation = App.Rotation(direction, normal.cross(direction), normal, "ZXY")
    plane = App.Placement(corner, rotation)
    return plane, _local_grid_bounds([plane.inverse().multVec(point) for point in points])


def _rectangle_points(a, b):
    return [(a.x, a.y), (b.x, a.y), (b.x, b.y), (a.x, b.y)]


def _set_camera_projection(view, projection, angle=30.0):
    """Change projection around the current target without jumping in scale."""
    camera = view.getCameraOrientation()
    forward = camera.multVec(App.Vector(0, 0, -1))
    node = view.getCameraNode()
    distance = float(node.focalDistance.getValue())
    position = App.Vector(*node.position.getValue().getValue())
    target = position + forward * distance
    height = (float(node.height.getValue()) if view.getCameraType() == "Orthographic"
              else 2 * distance * math.tan(float(node.heightAngle.getValue()) / 2))
    if view.getCameraType() != projection:
        view.setCameraType(projection)
    node = view.getCameraNode()
    if projection == "Perspective":
        radians = math.radians(angle)
        distance = height / (2 * math.tan(radians / 2))
        node.heightAngle.setValue(radians)
    else:
        node.height.setValue(height)
    position = target - forward * distance
    node.position.setValue(position.x, position.y, position.z)
    node.focalDistance.setValue(distance)


def _sketch_geometry(sketch, kind, a, b):
    plane = sketch.getGlobalPlacement()
    return sketch_tools.geometry(kind, [plane.inverse().multVec(a), plane.inverse().multVec(b)])


def _add_geometry(sketch, kind, a, b):
    geometry = _sketch_geometry(sketch, kind, a, b)
    sketch.addGeometry(geometry, False)
    sketch.Document.recompute()


def _resize_sketch(sketch, values):
    if sketch.Constraints:
        raise ValueError("This sketch has constraints. Edit it in Sketcher instead.")
    kind = sketch.EasyDesignShape
    if kind == "rectangle":
        corner = sketch.Geometry[0].StartPoint
        opposite = sketch.Geometry[1].EndPoint
        x_sign = 1 if opposite.x >= corner.x else -1
        y_sign = 1 if opposite.y >= corner.y else -1
        other = App.Vector(corner.x + x_sign * values[0], corner.y + y_sign * values[1], 0)
    elif kind == "circle":
        corner = sketch.Geometry[0].Center
        other = App.Vector(corner.x + values[0], corner.y, 0)
    else:
        raise ValueError("This sketch does not have a simple size control.")
    doc = sketch.Document
    doc.openTransaction("Set profile size")
    try:
        for index in reversed(range(len(sketch.Geometry))):
            sketch.delGeometry(index)
        _add_geometry(sketch, kind, sketch.getGlobalPlacement().multVec(corner), sketch.getGlobalPlacement().multVec(other))
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise


class _SelectionObserver:
    def __init__(self, owner):
        self.owner = owner

    def addSelection(self, *unused):
        QtCore.QTimer.singleShot(0, self.owner.update_gear)

    def removeSelection(self, *unused):
        QtCore.QTimer.singleShot(0, self.owner.update_gear)

    def clearSelection(self, *unused):
        QtCore.QTimer.singleShot(0, self.owner.update_gear)


class _OrbitFilter(QtCore.QObject):
    def __init__(self, owner, viewport):
        super().__init__(viewport)
        self.owner = owner
        self.viewport = viewport
        self.tracker = None
        self.last = None
        self.pending = (0, 0)
        self.pivot = None
        self.normal = None
        self.replaying = False
        self.press = None
        self.selection_press = None
        viewport.installEventFilter(self)
        QtWidgets.QApplication.instance().installEventFilter(self)

    def cancel(self):
        self.tracker = None
        if QtWidgets.QWidget.mouseGrabber() is self.viewport:
            self.viewport.releaseMouse()

    @staticmethod
    def _copy_mouse_event(event):
        return QtGui.QMouseEvent(event.type(), event.localPos(), QtCore.QPointF(event.globalPos()),
                                 event.button(), event.buttons(), event.modifiers())

    def eventFilter(self, watched, event):
        if self.replaying or self.owner.closed or not self.owner.view:
            return False
        kind = event.type()
        if kind in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
            focus = QtWidgets.QApplication.focusWidget()
            in_view = (focus is self.viewport or (focus and
                       (self.viewport.isAncestorOf(focus) or focus.isAncestorOf(self.viewport))))
            if (in_view and not isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox))
                    and event.modifiers() == QtCore.Qt.ControlModifier
                    and event.key() in (QtCore.Qt.Key_C, QtCore.Qt.Key_V)):
                if kind == QtCore.QEvent.KeyPress:
                    if event.key() == QtCore.Qt.Key_C:
                        self.owner.copy_selection()
                    else:
                        self.owner.paste_selection()
                event.accept()
                return True
        if watched is not self.viewport:
            return False
        if kind == QtCore.QEvent.Leave:
            self.owner.motion_pixel = None
        if kind == QtCore.QEvent.Leave and self.owner.mini_grid_preview:
            self.owner._set_grid_plane(None)
            self.owner.cursor_point = None
            if self.owner.draw_guide:
                self.owner.draw_guide.update()
        if (kind == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton
                and self.owner.drawing_press and not self.owner.kind):
            self.owner.drawing_press = False
            event.accept()
            return True
        if kind == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
            if not (self.owner.kind or self.owner.pull_session or self.owner.transform_tool or self.owner.loft_tool
                    or Gui.Control.activeDialog()):
                pixel = (event.pos().x(), self.viewport.height() - event.pos().y())
                alt = bool(event.modifiers() & QtCore.Qt.AltModifier)
                ctrl = bool(event.modifiers() & QtCore.Qt.ControlModifier)
                shift = bool(event.modifiers() & QtCore.Qt.ShiftModifier or
                             (not alt and ctrl))
                measuring_multi = self.owner.measure_tool and (alt or shift)
                if not measuring_multi and self.owner._intercept_selection(pixel, alt, shift):
                    self.selection_press = (pixel, alt, shift, ctrl)
                    event.accept()
                    return True
        if self.selection_press and kind == QtCore.QEvent.MouseMove:
            event.accept()
            return True
        if self.selection_press and kind == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton:
            pixel, alt, shift, ctrl = self.selection_press
            self.selection_press = None
            if math.hypot(pixel[0] - event.pos().x(), pixel[1] - (self.viewport.height() - event.pos().y())) <= 5:
                self.owner._select_at(pixel, alt, shift, ctrl)
            event.accept()
            return True
        if kind == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.RightButton:
            if event.modifiers() != QtCore.Qt.NoModifier or Gui.Control.activeDialog():
                return False
            self.tracker = orbit.DirectionTracker()
            self.last = (event.pos().x(), event.pos().y())
            self.pending = (0, 0)
            self.pivot, self.normal = orbit.orbit_pivot(self.owner.view, self.owner.grid_placement)
            self.press = self._copy_mouse_event(event)
            self.viewport.grabMouse()
            event.accept()
            return True
        if self.tracker and kind == QtCore.QEvent.MouseMove:
            x, y = event.pos().x(), event.pos().y()
            dx, dy = x - self.last[0], y - self.last[1]
            self.last = (x, y)
            previous = self.tracker.mode
            mode = self.tracker.feed(dx, dy)
            if previous is None:
                self.pending = (self.pending[0] + dx, self.pending[1] + dy)
                dx, dy = self.pending
            if mode:
                orbit.rotate_camera(self.owner.view, self.pivot, self.normal, mode, dx, dy)
                if self.owner.pull_widget:
                    self.owner._position_pull()
                if self.owner.draw_widget:
                    self.owner._position_draw()
            event.accept()
            return True
        if self.tracker and kind == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.RightButton:
            clicked = self.tracker.mode is None
            self.cancel()
            # Preserve FreeCAD's ordinary right-click menu when no orbit began.
            if clicked:
                self.replaying = True
                try:
                    QtWidgets.QApplication.sendEvent(self.viewport, self.press)
                    QtWidgets.QApplication.sendEvent(self.viewport, self._copy_mouse_event(event))
                finally:
                    self.replaying = False
            event.accept()
            return True
        if kind in (QtCore.QEvent.WindowDeactivate, QtCore.QEvent.UngrabMouse):
            self.cancel()
            self.selection_press = None
        return False


class _ActionStrip(QtWidgets.QFrame):
    def __init__(self, parent):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
                         | QtCore.Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setObjectName("EasyDesignActionStrip")
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setContentsMargins(3, 3, 3, 3)
        self.layout.setSpacing(1)
        self.anchor = None
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(1550)
        self.timer.timeout.connect(self.hide)
        QtWidgets.QApplication.instance().installEventFilter(self)
        self.hide()

    def show_entries(self, anchor, entries, beside=False):
        self.timer.stop()
        if self.anchor is not anchor:
            self.hide()
            while self.layout.count():
                child = self.layout.takeAt(0).widget()
                child.hide()
                child.deleteLater()
            for entry in entries:
                if entry is None:
                    separator = QtWidgets.QFrame(self)
                    separator.setFrameShape(QtWidgets.QFrame.VLine)
                    separator.setFixedWidth(7)
                    self.layout.addWidget(separator)
                    separator.show()
                    continue
                label, icon, callback = entry
                button = QtWidgets.QToolButton(self)
                button.setIcon(_icon(icon))
                button.setIconSize(QtCore.QSize(22, 22))
                button.setToolTip(label)
                button.setAccessibleName(label)
                button.setFixedSize(32, 32)
                button.setFocusPolicy(QtCore.Qt.NoFocus)
                button.clicked.connect(lambda checked=False, action=callback: self._trigger(action))
                self.layout.addWidget(button)
                button.show()
            self.anchor = anchor
            # Newly added children of a visible tool window can be pending-show;
            # include them in the layout before locking the flyout's dimensions.
            self.layout.invalidate()
            self.layout.activate()
            self.setFixedSize(self.layout.sizeHint())
        position = anchor.mapToGlobal(QtCore.QPoint(
            anchor.width() if beside else 0, 0 if beside else anchor.height(),
        ))
        screen = QtWidgets.QApplication.desktop().availableGeometry(anchor)
        self.move(max(screen.left(), min(position.x(), screen.right() - self.width() + 1)),
                  max(screen.top(), min(position.y(), screen.bottom() - self.height() + 1)))
        self.show()
        self.raise_()

    def _trigger(self, action):
        self.hide()
        action()

    def enterEvent(self, event):
        self.timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.timer.start()
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if self.isVisible():
            if event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
                self.hide()
                return True
            if event.type() == QtCore.QEvent.MouseButtonPress and isinstance(watched, QtWidgets.QWidget):
                inside = watched is self or self.isAncestorOf(watched)
                on_anchor = watched is self.anchor or (self.anchor and self.anchor.isAncestorOf(watched))
                if not inside and not on_anchor:
                    self.hide()
        return False


class _FlyoutButton(QtWidgets.QToolButton):
    def __init__(self, strip, entries, parent, beside=False, hover=True):
        super().__init__(parent)
        self.strip = strip
        self.entries = entries
        self.beside = beside
        self.hover = hover
        self.setFixedSize(40, 40)
        self.setIconSize(QtCore.QSize(24, 24))
        self.clicked.connect(self._open)

    def _open(self):
        self.strip.show_entries(self, self.entries, self.beside)

    def enterEvent(self, event):
        if self.hover:
            self._open()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.strip.anchor is self:
            self.strip.timer.start()
        super().leaveEvent(event)


class _DrawInput(QtWidgets.QDoubleSpinBox):
    def __init__(self, owner, index, parent):
        super().__init__(parent)
        self.owner = owner
        self.index = index
        self.setRange(0.01, 100000.0)
        self.setDecimals(3)
        self.setSuffix(" mm")
        self.setKeyboardTracking(False)
        self.setFixedSize(104, 28)

    def event(self, event):
        if (event.type() == QtCore.QEvent.KeyPress
                and event.key() in (QtCore.Qt.Key_Tab, QtCore.Qt.Key_Backtab)):
            self.owner.lock_draw_field(self.index, finish=False)
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.owner.lock_draw_field(self.index, finish=True)
            event.accept()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.owner.cancel()
            event.accept()
        else:
            if (self.owner.draw_typing != self.index and not self.owner.draw_locked[self.index]
                    and event.text() and all(char.isdigit() or char in ".,+-" for char in event.text())):
                self.selectAll()
            self.owner.draw_typing = self.index
            super().keyPressEvent(event)


class _DepthInput(QtWidgets.QDoubleSpinBox):
    def __init__(self, owner, parent):
        super().__init__(parent)
        self.owner = owner
        self.setRange(-100000.0, 100000.0)
        self.setDecimals(2)
        self.setSingleStep(1.0)
        self.setSuffix(" mm")
        self.setFixedWidth(104)
        self.setKeyboardTracking(False)
        self.typing = False

    def setValue(self, value):
        self.typing = False
        super().setValue(value)

    def mousePressEvent(self, event):
        self.typing = False
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.owner.finish_pull(True)
            event.accept()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.owner.finish_pull(False)
            event.accept()
        else:
            if not self.typing and event.text() and all(char.isdigit() or char in ".,+-" for char in event.text()):
                self.selectAll()
            self.typing = True
            super().keyPressEvent(event)


class _DrawGuide(QtWidgets.QWidget):
    def __init__(self, owner, viewport):
        super().__init__(viewport)
        self.owner = owner
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor("#008d9f"), 1.5))
        painter.setBrush(QtGui.QColor("#ffffff"))
        for point in self.owner.snap_points:
            x, y = self.owner.view.getPointOnViewport(point)
            painter.drawEllipse(QtCore.QPointF(x, self.height() - y), 3.5, 3.5)
        for point in self.owner.draw_points:
            x, y = self.owner.view.getPointOnViewport(point)
            painter.drawEllipse(QtCore.QPointF(x, self.height() - y), 4, 4)
        if self.owner.cursor_point is not None:
            x, y = self.owner.view.getPointOnViewport(self.owner.cursor_point)
            painter.setPen(QtGui.QPen(QtGui.QColor("#23bb70" if self.owner.snap_kind else "#008d9f"), 2))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(QtCore.QPointF(x, self.height() - y), 6, 6)
        painter.end()


class _DepthHandle(QtWidgets.QToolButton):
    def __init__(self, owner, cut, parent):
        super().__init__(parent)
        self.owner = owner
        self.setArrowType(QtCore.Qt.DownArrow if cut else QtCore.Qt.UpArrow)
        self.setToolTip("Drag to change cut depth" if cut else "Drag to change pull height")
        self.setFixedSize(32, 32)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setStyleSheet(
            "QToolButton { background: #ffd84c; border: 1px solid #a27800; border-radius: 4px; }"
            "QToolButton:hover { background: #ffe787; }"
        )
        self.start_position = None
        self.start_length = None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.start_position = event.globalPos()
            self.start_length = self.owner.pull_session.signed_length
            event.accept()

    def mouseMoveEvent(self, event):
        if self.start_position is not None and event.buttons() & QtCore.Qt.LeftButton:
            self.owner.drag_pull(self.start_position, event.globalPos(), self.start_length)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.start_position = None
        self.start_length = None
        event.accept()


class _SketchList(QtWidgets.QDockWidget):
    def __init__(self, owner):
        super().__init__("Skisser", owner.main)
        self.owner = owner
        self.signature = None
        self.setObjectName("EasyDesignSketches")
        self.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        self.setMinimumWidth(180)
        content = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)
        controls = QtWidgets.QHBoxLayout()
        self.visibility_buttons = []
        for visible, name, title in ((True, "EasyDesignShowSketches", "Vis alle skisser"),
                                     (False, "EasyDesignHideSketches", "Skjul alle skisser")):
            button = QtWidgets.QToolButton(content)
            button.setIcon(_icon(name))
            button.setIconSize(QtCore.QSize(20, 20))
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.clicked.connect(lambda checked=False, value=visible: self.set_visibility(value))
            controls.addWidget(button)
            self.visibility_buttons.append(button)
        controls.addStretch()
        layout.addLayout(controls)
        self.tree = QtWidgets.QTreeWidget(content)
        self.tree.setHeaderLabels(["Skisse", "Vis"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.tree.itemChanged.connect(self._visibility_changed)
        self.tree.itemClicked.connect(self._select)
        layout.addWidget(self.tree)
        self.setWidget(content)
        owner.main.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self)
        owner.main.resizeDocks([self], [220], QtCore.Qt.Horizontal)

    def sketches(self):
        doc = App.ActiveDocument
        return [obj for obj in doc.Objects if commands.is_profile(obj)] if doc else []

    def refresh(self):
        sketches = self.sketches()
        selected = {obj.Name for obj in Gui.Selection.getSelection()}
        doc_name = App.ActiveDocument.Name if App.ActiveDocument else None
        signature = (doc_name, tuple((obj.Name, obj.Label, obj.ViewObject.Visibility,
                                     obj.Name in selected) for obj in sketches))
        if signature == self.signature:
            return
        self.signature = signature
        scroll = self.tree.verticalScrollBar().value()
        blocked = self.tree.blockSignals(True)
        try:
            names = [self.tree.topLevelItem(i).data(0, QtCore.Qt.UserRole)
                     for i in range(self.tree.topLevelItemCount())]
            if names != [obj.Name for obj in sketches] or doc_name != getattr(self, "document_name", None):
                self.tree.clear()
                for obj in sketches:
                    item = QtWidgets.QTreeWidgetItem(self.tree, [obj.Label, ""])
                    item.setData(0, QtCore.Qt.UserRole, obj.Name)
                    item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            self.document_name = doc_name
            for i, obj in enumerate(sketches):
                item = self.tree.topLevelItem(i)
                item.setText(0, obj.Label)
                item.setCheckState(1, QtCore.Qt.Checked if obj.ViewObject.Visibility else QtCore.Qt.Unchecked)
                item.setSelected(obj.Name in selected)
            self.tree.verticalScrollBar().setValue(scroll)
        finally:
            self.tree.blockSignals(blocked)
        for button in self.visibility_buttons:
            button.setEnabled(bool(sketches))

    def _visibility_changed(self, item, column):
        if column != 1 or not App.ActiveDocument:
            return
        obj = App.ActiveDocument.getObject(item.data(0, QtCore.Qt.UserRole))
        if obj:
            self.set_visibility(item.checkState(1) == QtCore.Qt.Checked, [obj])

    def set_visibility(self, visible, sketches=None):
        sketches = self.sketches() if sketches is None else sketches
        if not visible and self.owner.sketch in sketches:
            names = [obj.Name for obj in sketches]
            self.owner.cancel()
            sketches = [App.ActiveDocument.getObject(name) for name in names]
            sketches = [obj for obj in sketches if obj]
        changed = [obj for obj in sketches if obj.ViewObject.Visibility != visible]
        if not changed:
            return
        doc = App.ActiveDocument
        # Drawing and extrusion already own the active undo transaction.
        own_transaction = not doc.HasPendingTransaction
        if own_transaction:
            doc.openTransaction("Sketch visibility")
        try:
            for obj in changed:
                obj.ViewObject.Visibility = visible
                if not visible:
                    Gui.Selection.removeSelection(obj)
            if own_transaction:
                doc.commitTransaction()
        except Exception:
            if own_transaction:
                doc.abortTransaction()
            raise
        if not visible and self.owner.selected_region and self.owner.selected_region[0] in changed:
            self.owner.selected_region = None
        self.owner.profile_signature = None
        self.owner._refresh_profiles()
        self.owner.update_gear()
        self.refresh()

    def _select(self, item, column):
        if column != 0 or not App.ActiveDocument:
            return
        obj = App.ActiveDocument.getObject(item.data(0, QtCore.Qt.UserRole))
        if not obj:
            return
        if self.owner.kind and not self.owner.sketch:
            self.set_visibility(True, [obj])
            self.owner._resume_sketch(obj)
        else:
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            if modifiers & QtCore.Qt.ControlModifier:
                if obj in Gui.Selection.getSelection():
                    Gui.Selection.removeSelection(obj)
                else:
                    Gui.Selection.addSelection(obj)
            elif modifiers & QtCore.Qt.ShiftModifier:
                for row in self.tree.selectedItems():
                    target = App.ActiveDocument.getObject(row.data(0, QtCore.Qt.UserRole))
                    if target and target not in Gui.Selection.getSelection():
                        Gui.Selection.addSelection(target)
            else:
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(obj)


class ViewController:
    def __init__(self):
        self.main = Gui.getMainWindow()
        self.closed = False
        self.view = None
        self.document = None
        self.document_name = None
        self.grid = None
        self.mini_grid = None
        self.mini_grid_bounds = None
        self.mini_grid_placement = None
        self.mini_grid_preview = False
        self.native_grid_sketch = None
        self.grid_visible = True
        self.display_states = {}
        self.grid_placement = App.Placement()
        self.orbit_filter = None
        self.callback = None
        self.previous_navigation = None
        self.previous_projection = None
        self.previous_camera_angle = 30.0
        self.profile_root = None
        self.profile_signature = None
        self.profile_faces = []
        self.selected_region = None
        self.clipboard_objects = []
        self.kind = None
        self.draw_points = []
        self.drawing_press = False
        self.edit_target = None
        self.draw_sides = 6
        self.text_source = None
        self.sketch = None
        self.first = None
        self.first_pixel = None
        self.draw_point = None
        self.draw_widget = None
        self.draw_fields = []
        self.draw_locked = []
        self.draw_lock_buttons = []
        self.draw_signs = [1, 1]
        self.draw_typing = None
        self.draw_guide = None
        self.cursor_point = None
        self.motion_pixel = None
        self.motion_scheduled = False
        self.snap_points = []
        self.snap_kind = None
        self.preview = None
        self.pull_session = None
        self.pull_highlight = None
        self.transform_tool = None
        self.loft_tool = None
        self.gear_tool = None
        self.measure_tool = None
        self.pull_widget = None
        self.pull_input = None
        self.pull_handle = None
        self.pull_taper = None
        self.pull_mode = None
        self.pull_error = None
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/EasyDesign")
        self.projection = self.preferences.GetString("Projection", "Perspective")
        if self.projection not in ("Perspective", "Orthographic"):
            self.projection = "Perspective"
        self.snap_step = self.preferences.GetFloat("LinearSnap", 0.0)
        if self.snap_step not in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 5.0, 10.0):
            self.snap_step = 0.0
        self.flyout = _ActionStrip(self.main)
        self.observer = _SelectionObserver(self)
        Gui.Selection.addObserver(self.observer)
        self.toolbar = self._toolbar()
        self.gear = None
        self.sketch_dock = _SketchList(self)
        self.timer = QtCore.QTimer(self.main)
        self.timer.timeout.connect(self.sync_view)
        self.timer.start(300)
        self.sync_view()

    def _toolbar(self):
        bar = QtWidgets.QToolBar("456D Design tools", self.main)
        bar.setObjectName("EasyDesignTopTools")
        bar.setMovable(False)
        bar.setIconSize(QtCore.QSize(24, 24))
        self.main.addToolBar(QtCore.Qt.TopToolBarArea, bar)

        def command(menu, label, icon, callback):
            action = menu.addAction(_icon(icon), label)
            action.triggered.connect(callback)
            return action

        command(bar, "Undo", "Std_Undo", lambda: Gui.runCommand("Std_Undo"))
        command(bar, "Redo", "Std_Redo", lambda: Gui.runCommand("Std_Redo"))
        command(bar, "Copy", "Std_Copy", self.copy_selection)
        command(bar, "Paste", "Std_Paste", self.paste_selection)
        bar.addSeparator()

        def group(title, icon, entries, preserve_tool=False):
            if not preserve_tool:
                entries = [None if entry is None else (
                    entry[0], entry[1], lambda action=entry[2]: self._run_tool(action),
                ) for entry in entries]
            button = _FlyoutButton(self.flyout, entries, bar)
            button.setObjectName("EasyDesign" + title.replace(" ", ""))
            button.setIcon(_icon(icon))
            button.setToolTip(title)
            button.setAccessibleName(title)
            bar.addWidget(button)

        def native(name):
            return lambda: Gui.runCommand(name)

        group("Transform", "Std_Transform", [
            ("Move / rotate", "Std_Transform", self.begin_transform),
            ("Placement", "Std_Placement", native("Std_Placement")),
        ])
        bar.addSeparator()
        group("Primitives", "PartDesign_AdditiveBox", [
            (name, "PartDesign_Additive" + name,
             lambda index=index: Gui.runCommand("PartDesign_CompPrimitiveAdditive", index))
            for index, name in ((0, "Box"), (2, "Sphere"), (1, "Cylinder"),
                                (3, "Cone"), (5, "Torus"), (7, "Wedge"), (6, "Prism"))
        ])
        group("Sketch", "Sketcher_NewSketch", [
            ("Rectangle", "Sketcher_CreateRectangle", lambda: self.begin("rectangle")),
            ("Circle", "Sketcher_CreateCircle", lambda: self.begin("circle")),
            ("Text", "EasyDesignText", lambda: self.begin("text")),
            ("Ellipse", "Sketcher_CreateEllipseByCenter", lambda: self.begin("ellipse")),
            ("Polygon", "Sketcher_CreateRegularPolygon", lambda: self.begin("polygon")),
            None,
            ("Line / polyline", "Sketcher_CreatePolyline", lambda: self.begin("line")),
            ("Spline", "Sketcher_CreateBSpline", lambda: self.begin("spline")),
            ("Center arc", "Sketcher_CreateArc", lambda: self.begin("center_arc")),
            ("Three-point arc", "Sketcher_Create3PointArc", lambda: self.begin("arc3")),
            None,
            ("Sketch fillet", "Sketcher_CreateFillet", lambda: self.begin("sketch_fillet")),
            ("Trim", "Sketcher_Trimming", lambda: self.begin("trim")),
            ("Extend", "Sketcher_Extend", lambda: self.begin("extend")),
            ("Offset", "Sketcher_Offset", lambda: self.begin("offset")),
            None,
            ("Edit sketch", "Sketcher_NewSketch", lambda: commands.start_draw()),
        ])
        group("Construct", "PartDesign_Pad", [
            ("Extrude (U)", "PartDesign_Pad", lambda: commands.pull_sketch()),
            ("Sweep", "PartDesign_AdditivePipe", native("PartDesign_AdditivePipe")),
            ("Revolve", "PartDesign_Revolution", native("PartDesign_Revolution")),
            ("Loft", "PartDesign_AdditiveLoft", self.begin_loft),
            None,
            ("Cut", "PartDesign_Pocket", lambda: commands.pull_sketch(cut=True)),
        ])
        group("Modify", "PartDesign_Fillet", [
            ("Press/Pull (P)", "PartDesign_Pad", self.pull_selected_face),
            None,
            ("Fillet", "PartDesign_Fillet", self.begin_edge),
            ("Chamfer", "PartDesign_Chamfer", lambda: self.begin_edge(chamfer=True)),
            ("Shell", "PartDesign_Thickness", self.begin_shell),
        ])
        group("Pattern", "PartDesign_LinearPattern", [
            ("Gear", "EasyDesignGear", self.begin_gear),
            ("Linear", "PartDesign_LinearPattern", native("PartDesign_LinearPattern")),
            ("Circular", "PartDesign_PolarPattern", native("PartDesign_PolarPattern")),
            ("Mirror", "PartDesign_Mirrored", native("PartDesign_Mirrored")),
        ])
        group("Group", "Std_Group", [("Group", "Std_Group", native("Std_Group"))])
        group("Combine", "Part_Fuse", [
            ("Union", "Part_Fuse", native("Part_Fuse")),
            ("Subtract", "Part_Cut", native("Part_Cut")),
            ("Intersect", "Part_Common", native("Part_Common")),
        ])
        command(bar, "Measure", "Std_Measure", self.toggle_measure)
        self._snap_button(bar)
        self.grid_button = QtWidgets.QToolButton(bar)
        self.grid_button.setObjectName("EasyDesignGrid")
        self.grid_button.setIcon(_icon("EasyDesignGrid"))
        self.grid_button.setToolTip("Grid: visible / faint")
        self.grid_button.setAccessibleName("Grid: visible / faint")
        self.grid_button.setCheckable(True)
        self.grid_button.setChecked(self.grid_visible)
        self.grid_button.clicked.connect(self.toggle_grid)
        bar.addWidget(self.grid_button)
        self.display_buttons = {}
        for option, icon, label, checked in (
                ("outlines", "EasyDesignOutlines", "Show/hide solid outlines", True),
                ("solids", "EasyDesignSolids", "Show/hide solid surfaces", True),
                ("transparent", "EasyDesignTransparent", "Transparent solids", False)):
            button = QtWidgets.QToolButton(bar)
            button.setObjectName(icon)
            button.setIcon(_icon(icon))
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setCheckable(True)
            button.setChecked(checked)
            button.setFocusPolicy(QtCore.Qt.NoFocus)
            button.clicked.connect(lambda checked=False, option=option, button=button:
                                   self.set_solid_display(option, button.isChecked()))
            self.display_buttons[option] = button
            bar.addWidget(button)
        group("View", "Std_ViewAxonometric", [
            ("Natural perspective", "Std_PerspectiveCamera", lambda: self.set_projection("Perspective")),
            ("Orthographic", "Std_OrthographicCamera", lambda: self.set_projection("Orthographic")),
            None,
            ("Axonometric", "Std_ViewAxonometric", lambda: Gui.activeView().viewAxonometric() if Gui.ActiveDocument else None),
            ("Top", "Std_ViewTop", lambda: Gui.activeView().viewTop() if Gui.ActiveDocument else None),
            ("Fit all", "Std_ViewFitAll", self.fit_view),
            ("Toggle grid", "Std_ToggleVisibility", self.toggle_grid),
        ], preserve_tool=True)
        bar.show()
        return bar

    def _run_tool(self, action):
        if self.gear_tool:
            self.gear_tool.finish(False)
        if self.loft_tool:
            self.loft_tool.finish(False)
        if self.measure_tool:
            self.measure_tool.close()
        if self.transform_tool:
            self.transform_tool.finish(False)
        if self.kind:
            self.cancel()
        if self.pull_session:
            self.finish_pull(False)
        action()

    def toggle_measure(self):
        if self.measure_tool:
            self.measure_tool.close()
            return
        if not App.ActiveDocument:
            self.main.statusBar().showMessage("Open a document to measure.", 4000)
            return
        self._run_tool(lambda: None)
        import EasyDesignMeasure
        self.measure_tool = EasyDesignMeasure.MeasureTool(self)
        self.update_gear()

    def _snap_button(self, bar):
        self.snap_button = QtWidgets.QToolButton(bar)
        self.snap_button.setObjectName("EasyDesignLinearSnap")
        self.snap_button.setIcon(_icon("Constraint_Coincident"))
        self.snap_button.setFixedSize(40, 40)
        self.snap_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(self.snap_button)
        actions = QtWidgets.QActionGroup(menu)
        actions.setExclusive(True)
        for value in (0.1, 0.25, 0.5, 0.75, 1.0, 5.0, 10.0, 0.0):
            action = menu.addAction("%g mm" % value if value else "Off")
            action.setCheckable(True)
            action.setChecked(value == self.snap_step)
            actions.addAction(action)
            action.triggered.connect(lambda checked=False, step=value: self._set_snap(step))
        self.snap_button.setMenu(menu)
        bar.addWidget(self.snap_button)
        self._set_snap(self.snap_step)

    def _set_snap(self, step):
        self.snap_step = step
        self.preferences.SetFloat("LinearSnap", step)
        self.snap_button.setToolTip("Linear snap: " + ("%g mm" % step if step else "Off"))
        self.snap_button.setAccessibleName(self.snap_button.toolTip())

    def _snap_value(self, value):
        return round(value / self.snap_step) * self.snap_step if self.snap_step else value

    def set_projection(self, projection):
        self.projection = projection
        self.preferences.SetString("Projection", projection)
        if self.view:
            _set_camera_projection(self.view, projection)
            if self.pull_widget:
                self._position_pull()
            if self.draw_widget:
                self._position_draw()

    def fit_view(self):
        if self.view:
            self.view.fitAll()
            if self.view.getCameraType() == "Perspective":
                _set_camera_projection(self.view, "Perspective")

    def sync_view(self):
        self._sync_solid_display()
        view = Gui.activeView() if Gui.ActiveDocument else None
        name = App.ActiveDocument.Name if App.ActiveDocument else None
        self.sketch_dock.refresh()
        if App.ActiveDocument == self.document and (view is None) == (self.view is None):
            if not self.kind:
                editing = commands._editing_sketch()
                if editing and "EasyDesignGridBounds" in editing.PropertiesList:
                    plane = editing.getGlobalPlacement()
                    bounds = tuple(editing.EasyDesignGridBounds)
                    if (not self.mini_grid or self.mini_grid_preview or self.mini_grid_bounds != bounds
                            or not self.mini_grid_placement.isSame(plane, 1e-7)):
                        self._set_grid_plane(plane, bounds)
                    self.native_grid_sketch = editing
                elif self.native_grid_sketch:
                    self.native_grid_sketch = None
                    self._set_grid_plane(None)
            if view and view.getCameraType() == "Perspective":
                angle = math.degrees(float(view.getCameraNode().heightAngle.getValue()))
                if abs(angle - 30.0) > 0.01:
                    _set_camera_projection(view, "Perspective")
            self._refresh_profiles()
            if self.pull_session:
                self._position_pull()
            if self.draw_widget:
                self._position_draw()
            if self.transform_tool:
                self.transform_tool.refresh()
            if self.gear_tool:
                self.gear_tool.position()
            return
        if self.gear_tool:
            self.gear_tool.finish(False)
        if self.transform_tool:
            self.transform_tool.finish(False)
        if self.pull_session:
            self.finish_pull(False)
        if self.loft_tool:
            self.loft_tool.finish(False)
        if self.kind:
            self.cancel()
        self._detach_view()
        self.view = view
        self.document = App.ActiveDocument
        self.document_name = name
        if not view:
            return
        import EasyDesignLoft
        try:
            recovered = EasyDesignLoft.recover_missing_sections(App.ActiveDocument)
            if recovered:
                self.main.statusBar().showMessage("Loft: %d missing sketch(es) recovered from saved outlines." % len(recovered), 8000)
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            App.Console.PrintWarning("Loft recovery: %s\n" % exc)
        import EasyDesignMM
        try:
            upgraded = EasyDesignMM.upgrade_legacy_cuts(App.ActiveDocument)
            if upgraded:
                self.main.statusBar().showMessage("Cut MM: %d older cut(s) upgraded." % len(upgraded), 6000)
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            App.Console.PrintWarning("Cut MM upgrade: %s\n" % exc)
        self.previous_navigation = view.getNavigationType()
        self.previous_projection = view.getCameraType()
        if self.previous_projection == "Perspective":
            self.previous_camera_angle = math.degrees(float(view.getCameraNode().heightAngle.getValue()))
        view.setNavigationType("Gui::TinkerCADNavigationStyle")
        self.grid_placement = App.Placement()
        self.grid = _grid(faint=not self.grid_visible)
        view.getSceneGraph().addChild(self.grid)
        if not App.ActiveDocument.Objects:
            view.viewAxonometric()
            view.fitAll()
        _set_camera_projection(view, self.projection)
        viewport = self._viewport_widget()
        if viewport:
            self.orbit_filter = _OrbitFilter(self, viewport)
        self.callback = view.addEventCallbackPivy(coin.SoMouseButtonEvent.getClassTypeId(), self._mouse_button)
        self.motion_callback = view.addEventCallbackPivy(coin.SoLocation2Event.getClassTypeId(), self._mouse_move)
        self.key_callback = view.addEventCallbackPivy(coin.SoKeyboardEvent.getClassTypeId(), self._key)
        self._refresh_profiles()
        self.update_gear()

    def _detach_view(self):
        self.selected_region = None
        if self.measure_tool:
            self.measure_tool.close()
        if self.orbit_filter:
            try:
                self.orbit_filter.cancel()
                self.orbit_filter.viewport.removeEventFilter(self.orbit_filter)
                QtWidgets.QApplication.instance().removeEventFilter(self.orbit_filter)
                self.orbit_filter.deleteLater()
            except RuntimeError:
                pass
            self.orbit_filter = None
        self.flyout.hide()
        if self.gear:
            try:
                self.gear.hide()
            except RuntimeError:
                self.gear = None
        self._clear_preview()
        if not self.view:
            return
        if App.ActiveDocument and App.ActiveDocument == self.document:
            try:
                self.view.removeEventCallbackPivy(coin.SoMouseButtonEvent.getClassTypeId(), self.callback)
                self.view.removeEventCallbackPivy(coin.SoLocation2Event.getClassTypeId(), self.motion_callback)
                self.view.removeEventCallbackPivy(coin.SoKeyboardEvent.getClassTypeId(), self.key_callback)
                if self.profile_root:
                    self.view.getSceneGraph().removeChild(self.profile_root)
                if self.grid:
                    self.view.getSceneGraph().removeChild(self.grid)
                if self.mini_grid:
                    self.view.getSceneGraph().removeChild(self.mini_grid)
                if self.previous_navigation:
                    self.view.setNavigationType(self.previous_navigation)
                if self.previous_projection:
                    _set_camera_projection(self.view, self.previous_projection, self.previous_camera_angle)
            except RuntimeError:
                pass
        self.view = None
        self.document = None
        self.document_name = None
        self.grid = None
        self.mini_grid = None
        self.mini_grid_bounds = None
        self.mini_grid_placement = None
        self.mini_grid_preview = False
        self.native_grid_sketch = None
        self.previous_projection = None
        self.profile_root = None
        self.profile_signature = None
        self.profile_faces = []

    def _solid_display(self):
        doc = App.ActiveDocument
        if not doc:
            return None
        entry = self.display_states.get(doc.Name)
        if entry is None or entry[0] != doc:
            from EasyDesignDisplay import SolidDisplay
            entry = self.display_states[doc.Name] = (doc, SolidDisplay())
        return entry[1]

    def _sync_solid_display(self):
        documents = App.listDocuments()
        self.display_states = {name: entry for name, entry in self.display_states.items()
                               if documents.get(name) == entry[0]}
        state = self._solid_display()
        if state:
            state.apply(App.ActiveDocument)
        for option, button in self.display_buttons.items():
            button.setEnabled(state is not None)
            button.setChecked(getattr(state, option) if state else option != "transparent")

    def set_solid_display(self, option, enabled):
        state = self._solid_display()
        if not state:
            return
        state.apply(App.ActiveDocument)
        setattr(state, option, bool(enabled))
        self._sync_solid_display()

    def toggle_grid(self):
        self.grid_visible = not self.grid_visible
        self.grid_button.setChecked(self.grid_visible)
        self._set_grid_plane(self.mini_grid_placement if self.mini_grid else self.grid_placement,
                             self.mini_grid_bounds, preview=self.mini_grid_preview)

    def _set_grid_plane(self, placement, bounds=None, preview=False):
        if not self.view or not App.ActiveDocument or App.ActiveDocument.Name != self.document_name:
            return
        if not preview:
            self.grid_placement = App.Placement(placement) if placement else App.Placement()
        if self.grid:
            self.view.getSceneGraph().removeChild(self.grid)
            self.grid = None
        if self.mini_grid:
            self.view.getSceneGraph().removeChild(self.mini_grid)
        self.mini_grid = None
        self.mini_grid_bounds = tuple(bounds) if bounds is not None else None
        self.mini_grid_placement = App.Placement(placement) if bounds is not None else None
        self.mini_grid_preview = preview
        self.grid = _grid(None if bounds is not None else placement,
                          faint=bounds is not None or not self.grid_visible)
        self.view.getSceneGraph().addChild(self.grid)
        if bounds is not None:
            self.mini_grid = _grid(placement, bounds=bounds)
            self.view.getSceneGraph().addChild(self.mini_grid)

    def _hover_grid(self, pixel):
        if self._sketch_at(pixel):
            target = None
        else:
            try:
                _, face = commands.drawing_target_at(self.view, pixel, App.ActiveDocument)
                target = _face_grid(self.view, *face, pixel) if face else None
            except (AttributeError, ValueError, Part.OCCError):
                target = None
        if target:
            plane, bounds = target
            if (not self.mini_grid or not self.mini_grid_preview or self.mini_grid_bounds != bounds
                    or not self.mini_grid_placement.isSame(plane, 1e-7)):
                self._set_grid_plane(plane, bounds, preview=True)
            return plane, bounds
        if self.mini_grid_preview:
            self._set_grid_plane(None)
        return None

    def _place_text(self, pixel):
        from EasyDesignText import is_text, create_text, text_dialog
        if self.kind != "text":
            return
        try:
            hits = self._selection_hits(pixel)
            if hits and is_text(hits[0][1]):
                self.edit_text(hits[0][1])
                return
            existing = self._sketch_at(pixel)
            support = None
            if existing:
                plane = existing.getGlobalPlacement()
            else:
                _, face = commands.drawing_target_at(self.view, pixel, App.ActiveDocument)
                if face:
                    plane, _ = _face_grid(self.view, *face, pixel)
                    support = face[0]
                else:
                    plane = App.Placement()
            point = self._point_on_plane(pixel, plane, snap=True)
            if point is None:
                raise ValueError("This plane is edge-on. Rotate the view before placing text.")
            plane.Base = point
            self.cancel(abort=False)
            values = text_dialog(self.main)
            if not values:
                return
            doc = App.ActiveDocument
            doc.openTransaction("Create text sketch")
            try:
                obj = create_text(doc, values["Text"], values["FontFile"], values["FontSize"],
                                  plane, values["FontFamily"], support)
                doc.commitTransaction()
            except Exception:
                doc.abortTransaction()
                raise
            commands._remember(obj)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(obj)
            self.sketch_dock.refresh()
            self.update_gear()
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            commands._warn(str(exc))

    def edit_text(self, obj):
        from EasyDesignText import text_dialog
        self._run_tool(lambda: None)
        values = text_dialog(self.main, obj, wrapped=bool(obj.WrapTarget))
        if values:
            self._change_text(obj, values)

    def _change_text(self, obj, values):
        doc = obj.Document
        doc.openTransaction("Edit text")
        try:
            for name, value in values.items():
                setattr(obj, name, value)
            obj.Proxy.execute(obj)
            doc.recompute()
            # Reject an edit that breaks an already extruded/engraved text result.
            for dependent in obj.InList:
                if hasattr(dependent, "Profile") and dependent.Profile == obj and "Invalid" in dependent.State:
                    raise ValueError("This edit cannot rebuild the text extrusion. Reduce size, span or depth.")
            doc.commitTransaction()
        except Exception as exc:
            doc.abortTransaction()
            doc.recompute()
            commands._warn(str(exc))
        self.sketch_dock.refresh()
        self.update_gear()

    def begin_text_wrap(self, obj):
        self.begin("text_wrap")
        self.text_source = obj
        self.main.statusBar().showMessage("Choose the cylindrical side to wrap the text around.")

    def _wrap_text_at(self, pixel):
        from EasyDesignText import wrap_text, text_dialog, cylinder_frame
        if self.kind != "text_wrap" or not self.text_source:
            return
        info = self.view.getObjectInfo(tuple(map(int, pixel)))
        try:
            if not info:
                raise ValueError("Choose the curved side of a cylinder.")
            target = App.ActiveDocument.getObject(info.get("Object", ""))
            name = info.get("Component", "")
            if target is None:
                raise ValueError("Choose the curved side of a cylinder.")
            cylinder_frame(target, name)
            obj = self.text_source
            if target == obj or target in obj.InListRecursive:
                raise ValueError("Choose the cylinder before the text extrusion, not its result.")
            point = App.Vector(info["x"], info["y"], info["z"])
            self.cancel(abort=False)
            doc = obj.Document
            doc.openTransaction("Wrap text")
            try:
                wrap_text(obj, target, name, point)
                values = text_dialog(self.main, obj, wrapped=True)
                if not values:
                    doc.abortTransaction()
                else:
                    for field, value in values.items():
                        setattr(obj, field, value)
                    obj.Proxy.execute(obj)
                    doc.recompute()
                    for dependent in obj.InList:
                        if hasattr(dependent, "Profile") and dependent.Profile == obj and "Invalid" in dependent.State:
                            raise ValueError("The existing extrusion cannot follow this wrap. Reduce span or depth.")
                    doc.commitTransaction()
            except Exception:
                doc.abortTransaction()
                doc.recompute()
                raise
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(obj)
            self.update_gear()
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            commands._warn(str(exc))

    def unwrap_text(self, obj):
        self._run_tool(lambda: None)
        self._change_text(obj, dict(WrapTarget=None, WrapFace="", MapMode="Deactivated",
                                   Placement=obj.FlatPlacement, AttachmentOffset=App.Placement()))

    def begin(self, kind):
        self.flyout.hide()
        if self.gear_tool:
            self.gear_tool.finish(False)
        if self.loft_tool:
            self.loft_tool.finish(False)
        if self.kind:
            self.cancel()
        if self.pull_session:
            self.finish_pull(False)
        if self.transform_tool:
            self.transform_tool.finish(False)
        if Gui.Control.activeDialog():
            commands._warn("Close the current task before drawing.")
            return
        App.ActiveDocument or App.newDocument("Design")
        self.sync_view()
        self.kind = kind
        self.draw_points = []
        self.edit_target = None
        self.sketch = None
        self.first = None
        self.first_pixel = None
        self.draw_guide = _DrawGuide(self, self._viewport_widget())
        self.draw_guide.setGeometry(self._viewport_widget().rect())
        self.draw_guide.show()
        self._set_grid_plane(None)
        Gui.Selection.clearSelection()
        self.main.statusBar().showMessage("Choose a sketch, the grid or a flat face.")
        self.update_gear()

    def _resume_sketch(self, sketch):
        sketch.Document.openTransaction("Draw " + self.kind)
        self.sketch = sketch
        if "EasyDesignShape" in sketch.PropertiesList and sketch.GeometryCount:
            sketch.EasyDesignShape = "line" if self.kind == "line" else "mixed"
        self.view.setActiveObject("pdbody", commands._body_of(sketch))
        plane = sketch.getGlobalPlacement()
        bounds = tuple(sketch.EasyDesignGridBounds) if "EasyDesignGridBounds" in sketch.PropertiesList else None
        if bounds is None and any(name.startswith("Face") for _, names in sketch.AttachmentSupport for name in names):
            points = [plane.inverse().multVec(sketch.getGlobalPlacement().multiply(sketch.Placement.inverse()).multVec(v.Point))
                      for v in sketch.Shape.Vertexes]
            if points:
                bounds = _local_grid_bounds(points)
        self._set_grid_plane(plane, bounds)
        Gui.Selection.clearSelection()

    def _start_sketch(self, body, face, pixel=None):
        doc = App.ActiveDocument
        doc.openTransaction("Draw " + self.kind)
        try:
            local_grid = None
            if face:
                if pixel is None:
                    obj, name = face
                    parent = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
                    pixel = self.view.getPointOnViewport(parent.multVec(obj.Shape.getElement(name).CenterOfMass))
                local_grid = _face_grid(self.view, *face, pixel)
            if body is None:
                body = doc.addObject("PartDesign::Body", "Body")
            sketch = body.newObject("Sketcher::SketchObject", "Sketch")
            sketch.addProperty("App::PropertyString", "EasyDesignShape", "456D Design")
            sketch.EasyDesignShape = self.kind
            sketch.AttachmentSupport = commands.sketch_support(body, face)
            sketch.MapMode = "FlatFace"
            doc.recompute()
            if local_grid:
                plane, bounds = local_grid
                sketch.AttachmentOffset = sketch.getGlobalPlacement().inverse().multiply(plane)
                sketch.addProperty("App::PropertyFloatList", "EasyDesignGridBounds", "456D Design")
                sketch.EasyDesignGridBounds = bounds
                doc.recompute()
        except Exception as exc:
            doc.abortTransaction()
            commands._warn("Could not start drawing: " + str(exc))
            self.cancel(abort=False)
            return
        Gui.Selection.clearSelection()
        self.sketch = sketch
        self.first = None
        self.first_pixel = None
        self.view.setActiveObject("pdbody", body)
        self._set_grid_plane(sketch.getGlobalPlacement(), local_grid[1] if local_grid else None)
        self.main.statusBar().showMessage("Click the first corner or center. Esc cancels.")

    def _point_on_plane(self, pixel, sketch, snap=False):
        p, q = self.view.projectPointToLine(int(pixel[0]), int(pixel[1]))
        plane = (sketch if isinstance(sketch, App.Placement) else
                 sketch.getGlobalPlacement() if hasattr(sketch, "getGlobalPlacement") else sketch.Placement)
        normal = plane.Rotation.multVec(App.Vector(0, 0, 1))
        direction = q - p
        denominator = direction.dot(normal)
        if abs(denominator) < 1e-8:
            return None
        point = p + direction * ((plane.Base - p).dot(normal) / denominator)
        if snap:
            point = self._soft_snap(point, pixel, plane)
        return point

    def _soft_snap(self, point, pixel, plane, bounds=None):
        normal = plane.Rotation.multVec(App.Vector(0, 0, 1))
        candidates = []
        self.snap_points = []
        for obj in App.ActiveDocument.Objects:
            if not obj.isDerivedFrom("Sketcher::SketchObject") or not obj.ViewObject.Visibility:
                continue
            parent = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
            for vertex in obj.Shape.Vertexes:
                candidate = parent.multVec(vertex.Point)
                if abs((candidate - plane.Base).dot(normal)) > .001:
                    continue
                self.snap_points.append(candidate)
                x, y = self.view.getPointOnViewport(candidate)
                candidates.append((math.hypot(x - pixel[0], y - pixel[1]), candidate))
        for candidate in self.draw_points:
            if abs((candidate - plane.Base).dot(normal)) <= .001:
                self.snap_points.append(candidate)
                x, y = self.view.getPointOnViewport(candidate)
                candidates.append((math.hypot(x - pixel[0], y - pixel[1]), candidate))
        distance, target = min(candidates, key=lambda item: item[0], default=(100, point))
        self.snap_kind = None
        if distance <= 9:
            self.snap_kind = "endpoint"
            return target
        local = plane.inverse().multVec(point)
        if bounds is None and self.mini_grid and not self.mini_grid_preview and plane.isSame(self.grid_placement, 1e-7):
            bounds = self.mini_grid_bounds
        xmin, xmax, ymin, ymax = bounds if bounds is not None else (-175, 175, -175, 175)
        # Grid lines are five millimetres apart; capture is measured on screen.
        candidates = []
        for i in range(round(local.x / 5) - 1, round(local.x / 5) + 2):
            for j in range(round(local.y / 5) - 1, round(local.y / 5) + 2):
                if not (xmin <= i * 5 <= xmax and ymin <= j * 5 <= ymax):
                    continue
                candidate = plane.multVec(App.Vector(i * 5, j * 5, 0))
                x, y = self.view.getPointOnViewport(candidate)
                candidates.append((math.hypot(x - pixel[0], y - pixel[1]), candidate))
        distance, target = min(candidates, key=lambda item: item[0], default=(100, point))
        if distance <= 5:
            self.snap_kind = "grid"
            return target
        return point

    def _mouse_button(self, callback):
        event = callback.getEvent()
        if event.getButton() != coin.SoMouseButtonEvent.BUTTON1:
            return
        if event.getState() == coin.SoMouseButtonEvent.UP and self.drawing_press:
            self.drawing_press = False
            # The last DOWN may have completed the sketch; its UP still belongs to drawing.
            callback.setHandled()
            if not self.kind or self.first is None:
                return
        if not self.kind:
            return
        pixel = event.getPosition().getValue()
        if event.getState() == coin.SoMouseButtonEvent.DOWN:
            self.drawing_press = True
            self.motion_pixel = None
            if self.kind in ("text", "text_wrap"):
                action = self._place_text if self.kind == "text" else self._wrap_text_at
                QtCore.QTimer.singleShot(0, lambda: action(tuple(pixel)))
                callback.setHandled()
                return
            if not self.sketch:
                if self.kind not in ("text", "text_wrap"):
                    existing = self._sketch_at(pixel)
                    if existing:
                        self._resume_sketch(existing)
                        point = self._point_on_plane(pixel, existing, snap=True)
                        if point is not None:
                            self._draw_click(point, pixel)
                        callback.setHandled()
                        return
                if self.kind in sketch_tools.EDIT_TOOLS:
                    self.main.statusBar().showMessage("Choose a sketch edge or corner.", 4000)
                    callback.setHandled()
                    return
                try:
                    body, face = commands.drawing_target_at(self.view, pixel, App.ActiveDocument)
                except (AttributeError, ValueError) as exc:
                    self.main.statusBar().showMessage(str(exc), 4000)
                    callback.setHandled()
                    return
                self._start_sketch(body, face, pixel)
                callback.setHandled()
                return
            point = self._point_on_plane(pixel, self.sketch, snap=True)
            if point is None:
                return
            self._draw_click(point, pixel)
            callback.setHandled()
        elif event.getState() == coin.SoMouseButtonEvent.UP and self.first is not None:
            if (self.kind in ("line", "rectangle", "circle", "polygon") and self.first_pixel
                    and math.hypot(pixel[0] - self.first_pixel[0], pixel[1] - self.first_pixel[1]) > 4):
                point = self._point_on_plane(pixel, self.sketch, snap=True)
                if point is not None:
                    self._finish(point)
            callback.setHandled()

    def _key(self, callback):
        event = callback.getEvent()
        if (self.kind == "spline" and event.getState() == coin.SoKeyboardEvent.DOWN
                and event.getKey() in (coin.SoKeyboardEvent.RETURN, coin.SoKeyboardEvent.PAD_ENTER)):
            self.finish_spline()
            callback.setHandled()
        elif self.kind and event.getState() == coin.SoKeyboardEvent.DOWN and event.getKey() == coin.SoKeyboardEvent.ESCAPE:
            self.cancel()
            callback.setHandled()
        elif self.pull_session and event.getState() == coin.SoKeyboardEvent.DOWN and event.getKey() == coin.SoKeyboardEvent.ESCAPE:
            self.finish_pull(False)
            callback.setHandled()
        elif self.loft_tool and event.getState() == coin.SoKeyboardEvent.DOWN and event.getKey() == coin.SoKeyboardEvent.ESCAPE:
            QtCore.QTimer.singleShot(0, self.loft_tool.reject)
            callback.setHandled()
        elif self.gear_tool and event.getState() == coin.SoKeyboardEvent.DOWN and event.getKey() == coin.SoKeyboardEvent.ESCAPE:
            QtCore.QTimer.singleShot(0, self.gear_tool.reject)
            callback.setHandled()
        elif (not self.kind and not self.pull_session and not self.transform_tool and not self.loft_tool and not self.gear_tool and not Gui.Control.activeDialog()
              and event.getState() == coin.SoKeyboardEvent.DOWN
              and not event.wasCtrlDown() and not event.wasAltDown() and not event.wasShiftDown()):
            actions = {
                coin.SoKeyboardEvent.U: commands.pull_sketch,
                coin.SoKeyboardEvent.P: self.pull_selected_face,
                coin.SoKeyboardEvent.W: lambda: Gui.runCommand("PartDesign_AdditivePipe"),
                coin.SoKeyboardEvent.V: lambda: Gui.runCommand("PartDesign_Revolution"),
                coin.SoKeyboardEvent.L: self.begin_loft,
                coin.SoKeyboardEvent.E: self.begin_edge,
                coin.SoKeyboardEvent.C: lambda: self.begin_edge(chamfer=True),
                coin.SoKeyboardEvent.J: self.begin_shell,
            }
            action = actions.get(event.getKey())
            if action:
                QtCore.QTimer.singleShot(0, action)
                callback.setHandled()

    def _sketch_at(self, pixel):
        self._refresh_profiles()
        hits = self._selection_hits(pixel)
        if hits and hits[0][1].isDerivedFrom("Sketcher::SketchObject"):
            return hits[0][1]
        return None

    def _select_profile(self, pixel):
        return self._select_at(pixel, False, False)

    def _selection_hits(self, pixel):
        if not self.view or not App.ActiveDocument:
            return []
        ray_start, ray_end = self.view.projectPointToLine(int(pixel[0]), int(pixel[1]))
        direction = ray_end - ray_start
        if direction.Length < 1e-8:
            return []
        direction.normalize()
        hits = []
        for sketch, face in self.profile_faces:
            point = self._point_on_plane(pixel, sketch)
            if point is None:
                continue
            parent = sketch.getGlobalPlacement().multiply(sketch.Placement.inverse())
            if face.isInside(parent.inverse().multVec(point), 0.01, True):
                depth = (point - ray_start).dot(direction)
                if depth >= -0.1:
                    hits.append((depth, sketch, sketch.getGlobalPlacement().inverse().multVec(point)))
        infos = self.view.getObjectsInfo(tuple(map(int, pixel))) or []
        seen = {sketch.Name for _, sketch, _ in hits}
        for info in infos:
            obj = App.ActiveDocument.getObject(info.get("Object", ""))
            if not obj or obj.Name in seen:
                continue
            seen.add(obj.Name)
            try:
                point = App.Vector(float(info["x"]), float(info["y"]), float(info["z"]))
                depth = (point - ray_start).dot(direction)
            except (KeyError, TypeError, ValueError):
                depth = max((hit[0] for hit in hits), default=0) + 1
            hits.append((depth, obj, None))
        # At coplanar depth, the drawn sketch should win over the solid face.
        if self.gear_tool and self.gear_tool.session is None:
            hits = [hit for hit in hits if hit[1] != self.gear_tool.circle
                    and hit[1].isDerivedFrom("Sketcher::SketchObject")]
        hits.sort(key=lambda hit: (round(hit[0], 1), not commands.is_profile(hit[1]), hit[0]))
        return hits

    def _intercept_selection(self, pixel, alt, shift):
        hits = self._selection_hits(pixel)
        if not hits:
            return False
        return hits[0][2] is not None or "EasyDesignText" in hits[0][1].PropertiesList or alt or shift or bool(self.gear_tool and self.gear_tool.session is None)

    def _select_at(self, pixel, alt=False, shift=False, ctrl=False):
        hits = self._selection_hits(pixel)
        if not hits:
            return False
        index = 0
        if alt and len(hits) > 1:
            selected = Gui.Selection.getSelection()
            if len(selected) == 1:
                for i, (_, obj, _) in enumerate(hits):
                    if obj == selected[0]:
                        index = (i + 1) % len(hits)
                        break
            else:
                index = 1
        _, obj, region = hits[index]
        if region is None and "EasyDesignText" not in obj.PropertiesList and not shift and not alt and not (self.gear_tool and self.gear_tool.session is None):
            return False
        subelement = ""
        if ctrl and not alt and region is None and not commands.is_profile(obj):
            infos = self.view.getObjectsInfo(tuple(map(int, pixel))) or []
            info = next((info for info in infos if info.get("Object") == obj.Name), {})
            component = info.get("Component", "")
            if component.startswith(("Edge", "Face", "Vertex")):
                subelement = component
        selected = Gui.Selection.getSelection()
        if not shift:
            Gui.Selection.clearSelection()
        elif subelement:
            item = next((item for item in Gui.Selection.getSelectionEx() if item.Object == obj), None)
            if item and subelement in item.SubElementNames:
                Gui.Selection.removeSelection(obj.Document.Name, obj.Name, subelement)
                self.selected_region = None
                self.update_gear()
                return True
            if item and not item.SubElementNames:
                # Replace a whole-object selection with the requested edge/face.
                Gui.Selection.removeSelection(obj.Document.Name, obj.Name)
        elif obj in selected:
            Gui.Selection.removeSelection(obj.Document.Name, obj.Name)
            self.selected_region = None
            self.update_gear()
            return True
        self.selected_region = (obj, region) if region is not None else None
        if subelement:
            Gui.Selection.addSelection(obj.Document.Name, obj.Name, subelement)
        else:
            Gui.Selection.addSelection(obj.Document.Name, obj.Name)
        self.profile_signature = None
        self._refresh_profiles()
        self.update_gear()
        return True

    def copy_selection(self):
        selected = Gui.Selection.getSelection()
        objects = []
        for obj in selected:
            target = obj if commands.is_profile(obj) else commands._body_of(obj) or obj
            if target not in objects:
                objects.append(target)
        if not objects:
            self.main.statusBar().showMessage("Select a sketch or object to copy.", 4000)
            return
        self.clipboard_objects = [(obj.Document.Name, obj.Name) for obj in objects]
        self.main.statusBar().showMessage("Copied %d item(s)." % len(objects), 3000)

    def paste_selection(self):
        if self.gear_tool:
            self.gear_tool.finish(False)
        if self.loft_tool:
            self.loft_tool.finish(False)
        if not self.clipboard_objects or not App.ActiveDocument:
            self.main.statusBar().showMessage("Nothing to paste.", 4000)
            return
        if self.transform_tool:
            self.transform_tool.finish(True)
        if self.pull_session:
            self.finish_pull(False)
        if self.kind:
            self.cancel()
        sources = []
        for document_name, object_name in self.clipboard_objects:
            doc = App.listDocuments().get(document_name)
            obj = doc.getObject(object_name) if doc else None
            if not obj:
                self.main.statusBar().showMessage("The copied source is no longer available.", 4000)
                return
            sources.append(obj)
        doc = App.ActiveDocument
        doc.openTransaction("Paste")
        try:
            copies = [doc.copyObject(obj, not commands.is_profile(obj)) for obj in sources]
            doc.recompute()
            for source, copy in zip(sources, copies):
                if hasattr(source.ViewObject, "ShapeColor") and hasattr(copy.ViewObject, "ShapeColor"):
                    copy.ViewObject.ShapeColor = source.ViewObject.ShapeColor
                    copy.ViewObject.LineColor = source.ViewObject.LineColor
                copy.ViewObject.Visibility = True
            doc.commitTransaction()
        except Exception as exc:
            doc.abortTransaction()
            commands._warn("Paste failed: %s" % exc)
            return
        Gui.Selection.clearSelection()
        self.selected_region = None
        for copy in copies:
            Gui.Selection.addSelection(doc.Name, copy.Name)
        self.profile_signature = None
        self._refresh_profiles()
        self.begin_transform(copies if len(copies) > 1 else copies[0])

    def _refresh_profiles(self):
        if not self.view or not App.ActiveDocument:
            return
        sketches = [obj for obj in App.ActiveDocument.Objects
                    if obj.isDerivedFrom("Sketcher::SketchObject") and obj.ViewObject.Visibility
                    and obj.GeometryCount]
        signature = tuple((obj.Name, len(obj.Geometry), obj.Shape.hashCode(), obj.Shape.BoundBox.XMin,
                           obj.Shape.BoundBox.YMin, obj.Shape.BoundBox.ZMin,
                           obj.Shape.BoundBox.XMax, obj.Shape.BoundBox.YMax,
                           obj.Shape.BoundBox.ZMax) for obj in sketches)
        signature += (tuple(obj.Name for obj in Gui.Selection.getSelection()),)
        if signature == self.profile_signature:
            return
        if self.profile_root:
            self.view.getSceneGraph().removeChild(self.profile_root)
        self.profile_root = coin.SoSeparator()
        self.profile_faces = []
        from EasyDesignRegions import profile_regions, region_at
        selected_objects = Gui.Selection.getSelection()
        for sketch in sketches:
            try:
                faces = profile_regions(sketch)
            except (Part.OCCError, ValueError):
                faces = []
            chosen = None
            if self.selected_region and self.selected_region[0] == sketch and sketch in Gui.Selection.getSelection():
                try:
                    chosen = region_at(sketch, self.selected_region[1])
                except (Part.OCCError, ValueError):
                    pass
            for face in faces:
                try:
                    if face.Area <= 0:
                        continue
                    points, triangles = face.tessellate(0.2)
                    selected = (sketch in selected_objects and chosen is None or
                                chosen is not None and abs(face.Area - chosen.Area) < 1e-7
                                and (face.CenterOfMass - chosen.CenterOfMass).Length < 1e-7)
                    node = coin.SoSeparator()
                    pick = coin.SoPickStyle()
                    pick.style = coin.SoPickStyle.UNPICKABLE
                    node.addChild(pick)
                    material = coin.SoMaterial()
                    material.diffuseColor.setValue(0.10, 0.76, 0.79)
                    material.transparency.setValue(0.18 if selected else 0.7)
                    node.addChild(material)
                    coords = coin.SoCoordinate3()
                    parent = sketch.getGlobalPlacement().multiply(sketch.Placement.inverse())
                    points = [parent.multVec(point) for point in points]
                    normal = sketch.getGlobalPlacement().Rotation.multVec(App.Vector(0, 0, 1)) * 0.02
                    coords.point.setValues(0, len(points), [
                        (p.x + normal.x, p.y + normal.y, p.z + normal.z) for p in points
                    ])
                    node.addChild(coords)
                    polygon = coin.SoIndexedFaceSet()
                    indices = [index for triangle in triangles for index in (*triangle, -1)]
                    polygon.coordIndex.setValues(0, len(indices), indices)
                    node.addChild(polygon)
                    if selected:
                        border = coin.SoSeparator()
                        color = coin.SoBaseColor()
                        color.rgb.setValue(0.02, 0.12, 0.13)
                        border.addChild(color)
                        style = coin.SoDrawStyle()
                        style.lineWidth = 3
                        border.addChild(style)
                        lines = coin.SoCoordinate3()
                        edge_points = []
                        counts = []
                        for edge in face.Edges:
                            samples = edge.discretize(Deflection=.2)
                            counts.append(len(samples))
                            edge_points.extend(parent.multVec(p) + normal * 2 for p in samples)
                        lines.point.setValues(0, len(edge_points), [tuple(p) for p in edge_points])
                        border.addChild(lines)
                        line_set = coin.SoLineSet()
                        line_set.numVertices.setValues(0, len(counts), counts)
                        border.addChild(line_set)
                        node.addChild(border)
                    self.profile_root.addChild(node)
                    self.profile_faces.append((sketch, face))
                except (Part.OCCError, ValueError):
                    continue
            parent = sketch.getGlobalPlacement().multiply(sketch.Placement.inverse())
            points = [tuple(parent.multVec(vertex.Point)) for vertex in sketch.Shape.Vertexes]
            if points:
                node = coin.SoSeparator()
                pick = coin.SoPickStyle()
                pick.style = coin.SoPickStyle.UNPICKABLE
                node.addChild(pick)
                color = coin.SoBaseColor()
                color.rgb.setValue(1, 1, 1)
                node.addChild(color)
                style = coin.SoDrawStyle()
                style.pointSize = 6
                node.addChild(style)
                coords = coin.SoCoordinate3()
                coords.point.setValues(0, len(points), points)
                node.addChild(coords)
                node.addChild(coin.SoPointSet())
                self.profile_root.addChild(node)
        self.view.getSceneGraph().addChild(self.profile_root)
        self.profile_signature = signature

    def _show_draw_controls(self):
        viewport = self._viewport_widget()
        if not viewport:
            return
        panel = QtWidgets.QWidget(viewport)
        panel.setObjectName("EasyDesignDrawingDimensions")
        layout = QtWidgets.QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        second_stage = len(self.draw_points) == 2
        names = (("Width", "Height") if self.kind == "rectangle" else
                 ("Length", "Angle") if self.kind in ("line", "spline") or self.kind == "arc3" and not second_stage else
                 ("Bulge",) if self.kind == "arc3" else
                 ("Minor radius",) if self.kind == "ellipse" and second_stage else
                 ("Sweep",) if self.kind == "center_arc" and second_stage else
                 ("Radius", "Angle") if self.kind in ("ellipse", "center_arc") else
                 ("Radius", "Sides") if self.kind == "polygon" else
                 ("Distance",) if self.kind in ("offset", "extend") else ("Radius",))
        self.draw_fields = []
        self.draw_locked = [False] * len(names)
        self.draw_lock_buttons = []
        self.draw_signs = [1, 1]
        self.draw_typing = None
        for index, name in enumerate(names):
            field = _DrawInput(self, index, panel)
            field.setObjectName("EasyDesign" + name)
            field.setToolTip(name + " in millimetres")
            if name in ("Angle", "Sweep"):
                field.setRange(-360, 360)
                field.setSuffix(" deg")
                field.setToolTip("Angle in degrees")
            if name == "Sweep":
                field.setRange(.01, 359.99)
            elif name in ("Bulge", "Distance"):
                field.setRange(-100000, 100000)
            elif name == "Sides":
                field.setDecimals(0)
                field.setRange(3, 128)
                field.setSuffix("")
                field.setToolTip("Polygon sides")
            field.setValue(0 if name == "Angle" else .01)
            if name == "Sides":
                field.setValue(self.draw_sides)
                self.draw_locked[index] = True
                field.valueChanged.connect(lambda value: self._polygon_sides(value))
            layout.addWidget(field)
            self.draw_fields.append(field)
            lock = QtWidgets.QToolButton(panel)
            lock.setObjectName("EasyDesignLock" + name)
            lock.setIcon(_icon("EasyDesignUnlocked"))
            lock.setToolTip("Lock " + name.lower())
            lock.setCheckable(True)
            lock.setFocusPolicy(QtCore.Qt.NoFocus)
            lock.setFixedSize(24, 28)
            lock.toggled.connect(lambda checked, index=index: self._toggle_draw_lock(index, checked))
            layout.addWidget(lock)
            self.draw_lock_buttons.append(lock)
            if name == "Sides":
                lock.hide()
        if self.kind != "trim":
            apply = QtWidgets.QToolButton(panel)
            apply.setObjectName("EasyDesignDrawingApply")
            apply.setIcon(self._contrast_icon(panel.style().standardIcon(QtWidgets.QStyle.SP_DialogApplyButton)))
            apply.setStyleSheet("QToolButton { background: #176b3b; border-radius: 3px; }")
            apply.setToolTip("Finish spline" if self.kind == "spline" else "Apply")
            apply.setFixedSize(28, 28)
            apply.clicked.connect(self.apply_drawing)
            layout.addWidget(apply)
        cancel = QtWidgets.QToolButton(panel)
        cancel.setObjectName("EasyDesignDrawingCancel")
        cancel.setIcon(self._contrast_icon(panel.style().standardIcon(QtWidgets.QStyle.SP_DialogCancelButton)))
        cancel.setStyleSheet("QToolButton { background: #a12d35; border-radius: 3px; }")
        cancel.setToolTip("Cancel")
        cancel.setFixedSize(28, 28)
        cancel.clicked.connect(lambda: self.cancel())
        layout.addWidget(cancel)
        self.draw_widget = panel
        panel.adjustSize()
        self._position_draw()
        panel.show()
        panel.raise_()
        QtCore.QTimer.singleShot(0, self._focus_draw_input)

    def _polygon_sides(self, value):
        self.draw_sides = int(value)
        if self.draw_point:
            self._show_preview(self.draw_point)

    def apply_drawing(self):
        if self.kind == "spline":
            self.finish_spline()
            return
        for index, field in enumerate(self.draw_fields):
            field.interpretText()
            self.draw_locked[index] = True
        self.draw_typing = None
        self._finish(self.draw_point or self.first)

    def _draw_click(self, point, pixel):
        if self.kind in sketch_tools.EDIT_TOOLS:
            if self.edit_target:
                self._finish(point)
                return
            plane = self.sketch.getGlobalPlacement()
            local = plane.inverse().multVec(point)
            candidates = []
            for index, curve in enumerate(self.sketch.Geometry):
                if self.sketch.getConstruction(index):
                    continue
                if self.kind == "extend" and not isinstance(curve, Part.LineSegment):
                    continue
                if self.kind == "sketch_fillet":
                    if not isinstance(curve, Part.LineSegment):
                        continue
                    targets = [(curve.StartPoint, 1), (curve.EndPoint, 2)]
                else:
                    _, pairs, _ = Part.Vertex(local).distToShape(curve.toShape())
                    near = pairs[0][1]
                    endpoint = (1 if (near - curve.StartPoint).Length < (near - curve.EndPoint).Length else 2
                                ) if isinstance(curve, Part.LineSegment) else 0
                    targets = [(near, endpoint)]
                for near, endpoint in targets:
                    x, y = self.view.getPointOnViewport(plane.multVec(near))
                    candidates.append((math.hypot(x - pixel[0], y - pixel[1]), index, near, endpoint))
            target = min(candidates, default=None, key=lambda item: item[0])
            if target is None or target[0] > 10:
                self.main.statusBar().showMessage("Choose a sketch edge or corner.", 4000)
                return
            self.edit_target = target[1:]
            self.first = self.draw_point = plane.multVec(target[2])
            if self.kind == "trim":
                self._finish(point)
            else:
                self._show_draw_controls()
                self.draw_fields[0].setValue(1)
                self.main.statusBar().showMessage("Choose the size, then apply.")
            return
        if self.first is None:
            self.first, self.first_pixel = point, pixel
            self.draw_point = point
            self.draw_points = [point]
            self._show_draw_controls()
        else:
            self._finish(point)

    def finish_spline(self):
        if self.kind != "spline" or not self.sketch:
            return
        try:
            if len(self.draw_points) < 2:
                raise ValueError("Place at least two spline points.")
            plane = self.sketch.getGlobalPlacement()
            curves = sketch_tools.geometry("spline", [plane.inverse().multVec(p) for p in self.draw_points])
            self.sketch.addGeometry(curves, False)
            self.sketch.Document.recompute()
            self.sketch.Document.commitTransaction()
            self._complete_sketch(self.sketch)
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            self.main.statusBar().showMessage(str(exc), 4000)

    def _focus_draw_input(self):
        if self.draw_fields:
            try:
                self.draw_fields[0].setFocus()
                self.draw_fields[0].selectAll()
            except RuntimeError:
                pass

    def _position_draw(self):
        if not self.draw_widget or not self.draw_point or not self.view:
            return
        viewport = self._viewport_widget()
        if not viewport:
            return
        x, y = self.view.getPointOnViewport(self.draw_point)
        left = max(6, min(int(x) + 14, viewport.width() - self.draw_widget.width() - 6))
        top = max(6, min(viewport.height() - int(y) + 12,
                         viewport.height() - self.draw_widget.height() - 6))
        self.draw_widget.move(left, top)

    def _clear_draw_controls(self):
        if self.draw_widget:
            try:
                self.draw_widget.hide()
                self.draw_widget.deleteLater()
            except RuntimeError:
                pass
        self.draw_widget = None
        self.draw_fields = []
        self.draw_locked = []
        self.draw_lock_buttons = []
        self.draw_typing = None
        self.draw_point = None

    def lock_draw_field(self, index, finish):
        if not self.kind or not self.first or index >= len(self.draw_fields):
            return
        was_locked = self.draw_locked[index]
        field = self.draw_fields[index]
        field.interpretText()
        self.draw_locked[index] = True
        lock = self.draw_lock_buttons[index]
        lock.blockSignals(True)
        lock.setChecked(True)
        lock.setIcon(_icon("EasyDesignLocked"))
        lock.setToolTip("Unlock dimension")
        lock.blockSignals(False)
        self.draw_typing = None
        point = self.draw_point or self.first
        self._show_preview(point)
        if finish and (len(self.draw_fields) == 1 or (was_locked and all(self.draw_locked))
                       or (self.kind in ("line", "spline", "arc3", "ellipse", "center_arc", "polygon")
                           and all(self.draw_locked))):
            self._finish(point)
            return
        next_index = next((i for i, locked in enumerate(self.draw_locked) if not locked), 0)
        self.draw_fields[next_index].setFocus()
        self.draw_fields[next_index].selectAll()

    def _toggle_draw_lock(self, index, locked):
        if locked:
            self.lock_draw_field(index, finish=False)
        else:
            self.draw_locked[index] = False
            self.draw_typing = None
            self.draw_lock_buttons[index].setToolTip("Lock dimension")
            self.draw_lock_buttons[index].setIcon(_icon("EasyDesignUnlocked"))
            if self.draw_point:
                self._show_preview(self.draw_point)
            self.draw_fields[index].setFocus()
            self.draw_fields[index].selectAll()

    def _draw_endpoint(self, point):
        if not self.draw_fields:
            return point
        plane = self.sketch.getGlobalPlacement()
        a = plane.inverse().multVec(self.first)
        b = plane.inverse().multVec(point)
        dx, dy = b.x - a.x, b.y - a.y
        second_stage = len(self.draw_points) == 2
        if self.kind in sketch_tools.EDIT_TOOLS:
            if self.kind == "extend":
                raw = [sketch_tools.extend_delta(self.sketch, self.edit_target[0], b, self.edit_target[2])]
            elif self.kind == "offset":
                curve = self.sketch.Geometry[self.edit_target[0]]
                edge = curve.toShape()
                parameter = edge.Curve.parameter(a)
                tangent = edge.tangentAt(parameter)
                raw = [(b - a).dot(App.Vector(tangent.y, -tangent.x, 0))]
            else:
                raw = [math.hypot(dx, dy)]
        elif self.kind in ("line", "spline") or self.kind == "arc3" and not second_stage:
            raw = [math.hypot(dx, dy), math.degrees(math.atan2(dy, dx))]
        elif self.kind == "rectangle":
            raw = [abs(dx), abs(dy)]
            for index, delta in enumerate((dx, dy)):
                if not self.draw_locked[index] and abs(delta) > 0.001:
                    self.draw_signs[index] = 1 if delta >= 0 else -1
        elif self.kind == "arc3":
            end = plane.inverse().multVec(self.draw_points[1])
            chord = (end - a).normalize()
            raw = [(b - (a + end) * .5).dot(App.Vector(-chord.y, chord.x, 0))]
        elif self.kind == "ellipse" and second_stage:
            axis = (plane.inverse().multVec(self.draw_points[1]) - a).normalize()
            signed = (b - a).dot(App.Vector(-axis.y, axis.x, 0))
            raw = [abs(signed)]
            if abs(signed) > .001:
                self.draw_signs[0] = 1 if signed >= 0 else -1
        elif self.kind == "center_arc" and second_stage:
            start = plane.inverse().multVec(self.draw_points[1]) - a
            raw = [math.degrees((math.atan2(dy, dx) - math.atan2(start.y, start.x)) % math.tau)]
        elif self.kind in ("ellipse", "center_arc"):
            raw = [math.hypot(dx, dy), math.degrees(math.atan2(dy, dx))]
        elif self.kind == "polygon":
            raw = [math.hypot(dx, dy), self.draw_sides]
        else:
            raw = [max(0.01, math.hypot(dx, dy))]
        sizes = []
        for index, size in enumerate(raw):
            field = self.draw_fields[index]
            if not self.draw_locked[index] and self.draw_typing != index:
                field.blockSignals(True)
                field.setValue(size)
                field.blockSignals(False)
                if field.hasFocus():
                    field.selectAll()
            sizes.append(field.value() if self.draw_locked[index] or self.draw_typing == index else size)
        if self.kind == "rectangle":
            return plane.multVec(App.Vector(
                a.x + self.draw_signs[0] * sizes[0],
                a.y + self.draw_signs[1] * sizes[1], 0,
            ))
        if self.kind in sketch_tools.EDIT_TOOLS:
            return point
        if (self.kind in ("line", "spline") or
                self.kind in ("ellipse", "center_arc", "arc3") and not second_stage):
            angle = math.radians(sizes[1])
            return plane.multVec(App.Vector(a.x + math.cos(angle) * sizes[0],
                                           a.y + math.sin(angle) * sizes[0], 0))
        if self.kind == "arc3":
            if not self.draw_locked[0] and self.draw_typing != 0:
                return point
            end = plane.inverse().multVec(self.draw_points[1])
            axis = (end - a).normalize()
            return plane.multVec((a + end) * .5 + App.Vector(-axis.y, axis.x, 0) * sizes[0])
        if self.kind == "ellipse":
            axis = (plane.inverse().multVec(self.draw_points[1]) - a).normalize()
            return plane.multVec(a + App.Vector(-axis.y, axis.x, 0) * sizes[0] * self.draw_signs[0])
        if self.kind == "center_arc":
            start = plane.inverse().multVec(self.draw_points[1]) - a
            angle = math.atan2(start.y, start.x) + math.radians(sizes[0])
            return plane.multVec(a + App.Vector(math.cos(angle), math.sin(angle), 0) * start.Length)
        length = math.hypot(dx, dy)
        ux, uy = (dx / length, dy / length) if length > 0.001 else (1, 0)
        return plane.multVec(App.Vector(a.x + ux * sizes[0], a.y + uy * sizes[0], 0))

    def _mouse_move(self, callback):
        if not self.kind:
            return
        self.motion_pixel = tuple(callback.getEvent().getPosition().getValue())
        if not self.motion_scheduled:
            self.motion_scheduled = True
            # Coin is traversing the scene here; replace grid nodes after it returns.
            QtCore.QTimer.singleShot(0, self._process_mouse_move)

    def _process_mouse_move(self):
        self.motion_scheduled = False
        pixel, self.motion_pixel = self.motion_pixel, None
        if (pixel is None or self.closed or not self.kind or not self.view
                or App.ActiveDocument != self.document):
            return
        if self.sketch:
            point = self._point_on_plane(pixel, self.sketch, snap=True)
        else:
            local_grid = self._hover_grid(pixel)
            existing = self._sketch_at(pixel)
            if existing:
                point = self._point_on_plane(pixel, existing, snap=True)
            elif local_grid:
                plane, bounds = local_grid
                point = self._point_on_plane(pixel, plane)
                if point is not None:
                    point = self._soft_snap(point, pixel, plane, bounds)
            else:
                p, q = self.view.projectPointToLine(int(pixel[0]), int(pixel[1]))
                direction = q - p
                point = p - direction * (p.z / direction.z) if abs(direction.z) > 1e-8 else None
                if point is not None:
                    point = self._soft_snap(point, pixel, App.Placement())
        if point is None:
            return
        self.cursor_point = point
        if self.draw_guide:
            self.draw_guide.setGeometry(self._viewport_widget().rect())
            self.draw_guide.update()
            self.draw_guide.raise_()
            if self.draw_widget:
                self.draw_widget.raise_()
        if self.first is None or not self.sketch:
            return
        self._show_preview(point)
        self._position_draw()
        local_a = self.sketch.getGlobalPlacement().inverse().multVec(self.first)
        local_b = self.sketch.getGlobalPlacement().inverse().multVec(self._draw_endpoint(point))
        if self.kind in ("line", "spline"):
            size = "Length %.1f mm, angle %.1f deg" % (
                (local_b - local_a).Length, math.degrees(math.atan2(local_b.y - local_a.y, local_b.x - local_a.x)))
        elif self.kind == "rectangle":
            size = "%.1f x %.1f mm" % (abs(local_b.x - local_a.x), abs(local_b.y - local_a.y))
        else:
            size = "Radius %.1f mm" % math.hypot(local_b.x - local_a.x, local_b.y - local_a.y)
        self.main.statusBar().showMessage(size)

    def _show_preview(self, point):
        self._clear_preview()
        self.draw_point = point
        point = self._draw_endpoint(point)
        plane = self.sketch.getGlobalPlacement()
        a, b = plane.inverse().multVec(self.first), plane.inverse().multVec(point)
        if self.kind in sketch_tools.EDIT_TOOLS:
            curves = []
            try:
                index, anchor, endpoint = self.edit_target
                size = self.draw_fields[0].value()
                if self.kind == "offset":
                    curves = sketch_tools.offset_geometry(self.sketch, index, size)
                elif self.kind == "extend":
                    curve = self.sketch.Geometry[index]
                    direction = (curve.EndPoint - curve.StartPoint).normalize()
                    curves = [Part.LineSegment(curve.StartPoint if endpoint == 2 else curve.StartPoint - direction * size,
                                               curve.EndPoint + direction * size if endpoint == 2 else curve.EndPoint)]
                else:
                    curves = sketch_tools.fillet_preview(self.sketch, index, endpoint, size)
                paths = [curve.toShape().discretize(Deflection=.05) for curve in curves]
            except (ValueError, RuntimeError, Part.OCCError):
                paths = [[a, b]]
        else:
            kind = self.kind
            points = (self.draw_points + [point] if self.kind in ("arc3", "ellipse", "center_arc", "spline") else
                      [self.first, point])
            if kind in ("ellipse", "center_arc", "arc3") and len(points) < 3:
                kind = "line"
            paths = sketch_tools.preview(kind, [plane.inverse().multVec(p) for p in points], self.draw_sides)
        normal = plane.Rotation.multVec(App.Vector(0, 0, 1)) * 0.1
        paths = [[plane.multVec(p) + normal for p in path] for path in paths]
        self.preview = _lines([
            (p.x, p.y, p.z) for path in paths for p in path
        ], [len(path) for path in paths], (0.0, 0.55, 0.7), 2)
        self.view.getSceneGraph().addChild(self.preview)

    def _clear_preview(self):
        if (self.preview and self.view and App.ActiveDocument
                and App.ActiveDocument.Name == self.document_name):
            self.view.getSceneGraph().removeChild(self.preview)
        self.preview = None

    def _finish(self, point):
        sketch = self.sketch
        try:
            if self.draw_typing is not None:
                self.draw_fields[self.draw_typing].interpretText()
                self.draw_locked[self.draw_typing] = True
                self.draw_typing = None
            point = self._draw_endpoint(point)
            if self.kind in ("arc3", "ellipse", "center_arc") and len(self.draw_points) < 2:
                if (point - self.first).Length < .01:
                    raise ValueError("The points must be at least 0.01 mm apart.")
                self.draw_points = [self.first, point]
                self._clear_preview()
                self._clear_draw_controls()
                self.draw_point = point
                self.first_pixel = None
                self._show_draw_controls()
                return
            if self.kind == "spline":
                if (point - self.first).Length < .01:
                    raise ValueError("Place a different spline point.")
                self.draw_points.append(point)
                if len(self.draw_points) > 3 and (point - self.draw_points[0]).Length < 1e-7:
                    self.finish_spline()
                    return
                self._clear_preview()
                self._clear_draw_controls()
                self.first = self.draw_point = point
                self.first_pixel = None
                self._show_draw_controls()
                return
            if self.kind in sketch_tools.EDIT_TOOLS:
                sketch_tools.edit(sketch, self.kind, self.edit_target,
                                  self.draw_fields[0].value() if self.draw_fields else 1)
            elif self.kind in ("arc3", "ellipse", "center_arc", "polygon"):
                plane = sketch.getGlobalPlacement()
                points = self.draw_points + [point] if self.kind != "polygon" else [self.first, point]
                sketch.addGeometry(sketch_tools.geometry(self.kind, [plane.inverse().multVec(p) for p in points],
                                                        self.draw_sides), False)
                sketch.Document.recompute()
            else:
                _add_geometry(sketch, self.kind, self.first, point)
            if self.kind == "line":
                self._clear_preview()
                self._clear_draw_controls()
                self.first = self.draw_point = point
                self.first_pixel = None
                self._show_draw_controls()
                return
            sketch.Document.commitTransaction()
        except ValueError as exc:
            self.main.statusBar().showMessage(str(exc))
            return
        except Exception as exc:
            sketch.Document.abortTransaction()
            commands._warn("Could not finish drawing: " + str(exc))
            self.cancel(abort=False)
            return
        self._complete_sketch(sketch)

    def _complete_sketch(self, sketch):
        self._clear_preview()
        self._clear_draw_controls()
        self._clear_draw_guide()
        self.kind = self.sketch = self.first = self.first_pixel = None
        self.draw_points = []
        self.edit_target = None
        self.text_source = None
        self._set_grid_plane(None)
        commands._remember(sketch)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sketch.Document.Name, sketch.Name)
        self._refresh_profiles()
        self.main.statusBar().showMessage("Profile ready. Choose a tool from the gear or toolbar.", 5000)
        self.update_gear()

    def cancel(self, abort=True):
        if self.transform_tool:
            self.transform_tool.finish(False)
        if abort and self.sketch and self.document_name in App.listDocuments():
            if self.kind == "line" and self.sketch.GeometryCount:
                self.sketch.Document.commitTransaction()
                commands._remember(self.sketch)
            else:
                self.sketch.Document.abortTransaction()
        self._clear_preview()
        self._clear_draw_controls()
        self._clear_draw_guide()
        self.kind = self.sketch = self.first = self.first_pixel = None
        self.draw_points = []
        self.edit_target = None
        self._set_grid_plane(None)
        self.main.statusBar().clearMessage()

    def _clear_draw_guide(self):
        self.motion_pixel = None
        if self.draw_guide:
            try:
                self.draw_guide.hide()
                self.draw_guide.deleteLater()
            except RuntimeError:
                pass
        self.draw_guide = None
        self.cursor_point = None
        self.snap_points = []
        self.snap_kind = None

    def _viewport_widget(self):
        mdi = self.main.findChild(QtWidgets.QMdiArea)
        sub = mdi.activeSubWindow() if mdi else None
        return sub.findChild(QtWidgets.QOpenGLWidget) if sub else None

    def _size_dialog(self, sketch):
        kind = sketch.EasyDesignShape
        if kind == "rectangle":
            first = sketch.Geometry[0].StartPoint
            last = sketch.Geometry[1].EndPoint
            fields = (("Width", abs(last.x - first.x)), ("Height", abs(last.y - first.y)))
        elif kind == "circle":
            fields = (("Radius", sketch.Geometry[0].Radius),)
        else:
            return
        dialog = QtWidgets.QDialog(self.main)
        dialog.setWindowTitle("Profile size")
        layout = QtWidgets.QFormLayout(dialog)
        controls = []
        for name, value in fields:
            control = QtWidgets.QDoubleSpinBox(dialog)
            control.setRange(0.01, 1000000)
            control.setDecimals(3)
            control.setSuffix(" mm")
            control.setValue(value)
            layout.addRow(name, control)
            controls.append(control)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, dialog
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            try:
                _resize_sketch(sketch, [control.value() for control in controls])
                self._refresh_profiles()
            except Exception as exc:
                commands._warn("Could not change size: " + str(exc))

    def begin_pull(self, sketch, cut=False):
        import EasyDesignPull

        self.flyout.hide()
        self._run_tool(lambda: None)
        self.sync_view()
        multiple = isinstance(sketch, (list, tuple)) and len(sketch) > 1
        selected = Gui.Selection.getSelectionEx()
        edges = ([name for name in selected[0].SubElementNames if name.startswith("Edge")]
                 if not multiple and len(selected) == 1 and selected[0].Object == sketch else None)
        region = self.selected_region[1] if not multiple and self.selected_region and self.selected_region[0] == sketch and sketch in Gui.Selection.getSelection() else None
        from EasyDesignText import is_text, TextPullPreview
        session = (TextPullPreview(sketch, cut) if not multiple and is_text(sketch) else
                   EasyDesignPull.PullPreview(sketch, cut, profile_edges=edges, region_point=region))
        self._show_pull(session)

    def make_face_sketch(self, obj, face_name):
        import EasyDesignFace

        self._run_tool(lambda: None)
        try:
            sketch = EasyDesignFace.make_face_sketch(obj, face_name)
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            commands._warn(str(exc))
            return
        commands._remember(sketch)
        self.view.setActiveObject("pdbody", commands._body_of(sketch))
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sketch)
        self.profile_signature = None
        self._refresh_profiles()
        self.sketch_dock.refresh()
        self.update_gear()

    def begin_face_pull(self, obj, face_name, mesh=False):
        import EasyDesignFace

        self.flyout.hide()
        self._run_tool(lambda: None)
        try:
            EasyDesignFace.face_frame(obj.Shape.getElement(face_name))
            options = {}
            if mesh:
                dialog = QtWidgets.QDialog(self.main)
                dialog.setWindowTitle("Mesh")
                layout = QtWidgets.QFormLayout(dialog)
                pattern = QtWidgets.QComboBox(dialog)
                pattern.addItems(EasyDesignFace.PATTERNS)
                layout.addRow("Pattern", pattern)
                fields = []
                for label, value in (("Spacing", 8.0), ("Opening", 5.0), ("Border", 2.0)):
                    field = QtWidgets.QDoubleSpinBox(dialog)
                    field.setRange(0.0 if label == "Border" else 0.1, 10000.0)
                    field.setDecimals(2)
                    field.setSuffix(" mm")
                    field.setValue(value)
                    layout.addRow(label, field)
                    fields.append(field)
                buttons = QtWidgets.QDialogButtonBox(
                    QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, dialog)
                buttons.accepted.connect(dialog.accept)
                buttons.rejected.connect(dialog.reject)
                layout.addRow(buttons)
                if dialog.exec_() != QtWidgets.QDialog.Accepted:
                    return
                options = dict(pattern=pattern.currentText(), pitch=fields[0].value(),
                               opening=fields[1].value(), border=fields[2].value())
            self.sync_view()
            session = EasyDesignFace.FacePreview(obj, face_name, distance=-1.0 if mesh else 1.0, **options)
            self._show_pull(session)
        except (ValueError, RuntimeError) as exc:
            commands._warn(str(exc))

    def pull_selected_face(self):
        selected = Gui.Selection.getSelectionEx()
        if len(selected) != 1 or len(selected[0].SubElementNames) != 1 or not selected[0].SubElementNames[0].startswith("Face"):
            self.main.statusBar().showMessage("Select a planar solid face first.", 4000)
            return
        self.begin_face_pull(selected[0].Object, selected[0].SubElementNames[0])

    def begin_shell(self):
        if Gui.Control.activeDialog():
            self.main.statusBar().showMessage("Close the current task before using Shell.", 4000)
            return
        self._run_tool(lambda: None)
        selected = Gui.Selection.getSelectionEx()
        if len(selected) != 1 or not selected[0].SubElementNames:
            self.main.statusBar().showMessage("Select the face to remove from one solid for Shell.", 4000)
            return
        obj = selected[0].Object
        names = list(selected[0].SubElementNames)
        body = commands._body_of(obj)
        if obj == body:
            obj = body.Tip
        if (obj is None or obj.Document != App.ActiveDocument or not hasattr(obj, "Shape")
                or len(obj.Shape.Solids) != 1 or any(not name.startswith("Face") for name in names)):
            self.main.statusBar().showMessage("Select faces on a single solid for Shell.", 4000)
            return
        if body and obj != body.Tip:
            self.main.statusBar().showMessage("Select a face on the body's current final solid.", 4000)
            return
        active = App.getActiveTransaction()
        if (active and active[0] == "Shell" and self.pull_session is None
                and not Gui.activeDocument().getInEdit()):
            # Older failed Shell attempts could leave a global transaction open.
            # Commit that orphan rather than discarding any subsequent user edits.
            App.closeActiveTransaction(False, active[1])
        self.flyout.hide()
        self.sync_view()
        self.view.setActiveObject("pdbody", body)
        try:
            from EasyDesignShell import ShellPreview
            self._show_pull(ShellPreview(obj, names))
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            commands._warn(str(exc))

    def begin_edge(self, chamfer=False):
        import EasyDesignEdge

        if self.gear_tool:
            self.gear_tool.finish(False)
        if self.loft_tool:
            self.loft_tool.finish(False)
        selected = Gui.Selection.getSelectionEx()
        if len(selected) != 1:
            self.main.statusBar().showMessage("Select edges on one solid first.", 4000)
            return
        obj, names = selected[0].Object, list(selected[0].SubElementNames)
        self.flyout.hide()
        if self.transform_tool:
            self.transform_tool.finish(False)
        if self.pull_session:
            self.finish_pull(False)
        if self.kind:
            self.cancel()
        self.sync_view()
        try:
            session = EasyDesignEdge.EdgePreview(obj, names, chamfer)
            self._show_pull(session)
        except (ValueError, RuntimeError) as exc:
            commands._warn(str(exc))

    def _show_pull(self, session):
        self.pull_session = session
        self._refresh_profiles()
        widget = self._viewport_widget()
        if not widget:
            self.finish_pull(False)
            raise ValueError("The 3D view is not available.")

        panel = QtWidgets.QWidget(widget)
        panel.setObjectName("EasyDesignDepthControl")
        panel.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        panel.setStyleSheet(
            "QWidget#EasyDesignDepthControl { background: #f5f7f8;"
            "border: 1px solid #a9b7bf; border-radius: 4px; }"
        )
        outer = QtWidgets.QVBoxLayout(panel)
        outer.setContentsMargins(5, 4, 5, 4)
        outer.setSpacing(4)
        layout = QtWidgets.QHBoxLayout()
        outer.addLayout(layout)
        layout.setSpacing(4)
        self.pull_handle = _DepthHandle(self, session.signed_length < 0, panel)
        if hasattr(session, "measure_name"):
            label = QtWidgets.QLabel(session.measure_name, panel)
            label.setStyleSheet("color: #22323d; background: transparent;")
            self.pull_handle.setToolTip("Drag to change " + session.measure_name.lower())
            points = [point for line in session.highlight_lines for point in line]
            self.pull_highlight = _lines(points, [len(line) for line in session.highlight_lines],
                                         (0.12, 0.95, 0.45), 3)
            self.view.getSceneGraph().addChild(self.pull_highlight)
        if getattr(session, "new_solid", False):
            self.pull_handle.setToolTip("Drag to change extrusion distance")
        layout.addWidget(self.pull_handle)
        if hasattr(session, "measure_name"):
            layout.addWidget(label)
        depth = _DepthInput(self, panel)
        if hasattr(session, "measure_name"):
            depth.setMinimum(.01)
            depth.setObjectName("EasyDesignEdge" + session.measure_name)
            depth.setToolTip(session.measure_name + " in millimetres")
        depth.setValue(session.signed_length)
        depth.valueChanged.connect(self._set_pull_depth)
        layout.addWidget(depth)
        if hasattr(session, "source_sketch") and hasattr(session, "set_taper"):
            reverse = QtWidgets.QToolButton(panel)
            reverse.setObjectName("EasyDesignReverseExtrusion")
            reverse.setIcon(self._contrast_icon(_icon("EasyDesignReverse"), "#22323d"))
            reverse.setToolTip("Reverse extrusion direction (+ / -)")
            reverse.setAccessibleName("Reverse extrusion direction")
            reverse.setFixedSize(30, 30)
            reverse.clicked.connect(lambda: depth.setValue(-depth.value()))
            layout.addWidget(reverse)
        style = QtWidgets.QApplication.style()
        accept = QtWidgets.QToolButton(panel)
        accept.setObjectName("EasyDesignApply")
        accept.setIcon(self._contrast_icon(style.standardIcon(QtWidgets.QStyle.SP_DialogApplyButton)))
        accept.setStyleSheet("QToolButton { background: #176b3b; border: 1px solid #0c4224; border-radius: 3px; }"
                            "QToolButton:hover { background: #218b50; }")
        accept.setToolTip("Apply")
        accept.setAccessibleName("Apply")
        accept.setIconSize(QtCore.QSize(22, 22))
        accept.setFixedSize(32, 32)
        accept.clicked.connect(lambda: self.finish_pull(True))
        layout.addWidget(accept)
        reject = QtWidgets.QToolButton(panel)
        reject.setObjectName("EasyDesignCancel")
        reject.setIcon(self._contrast_icon(style.standardIcon(QtWidgets.QStyle.SP_DialogCloseButton)))
        reject.setStyleSheet("QToolButton { background: #a52d35; border: 1px solid #6e1c23; border-radius: 3px; }"
                            "QToolButton:hover { background: #c43c46; }")
        reject.setToolTip("Cancel")
        reject.setAccessibleName("Cancel")
        reject.setIconSize(QtCore.QSize(22, 22))
        reject.setFixedSize(32, 32)
        reject.clicked.connect(lambda: self.finish_pull(False))
        layout.addWidget(reject)
        if hasattr(session, "set_taper"):
            options = QtWidgets.QHBoxLayout()
            mode = QtWidgets.QComboBox(panel)
            mode.setObjectName("EasyDesignExtrudeOperation")
            from EasyDesignPull import OPERATIONS
            mode.addItems(list(OPERATIONS))
            mode.setMinimumContentsLength(17)
            mode.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            mode.setToolTip("Extrusion operation")
            mode.setCurrentIndex(OPERATIONS.index(session.operation))
            mode.activated.connect(self._change_pull_mode)
            options.addWidget(mode)
            label = QtWidgets.QLabel("Taper", panel)
            label.setStyleSheet("color: #22323d; background: transparent;")
            options.addWidget(label)
            taper = _DepthInput(self, panel)
            taper.setObjectName("EasyDesignExtrudeTaper")
            taper.setRange(-85, 85)
            taper.setSuffix(" deg")
            taper.setFixedWidth(86)
            taper.setValue(session.taper)
            taper.setToolTip("Taper angle")
            taper.valueChanged.connect(self._set_pull_taper)
            if "EasyDesignText" in getattr(getattr(session, "sketch", None), "PropertiesList", []):
                taper.setEnabled(False)
            options.addWidget(taper)
            outer.addLayout(options)
            self.pull_taper = taper
            self.pull_mode = mode
        self.pull_widget = panel
        self.pull_input = depth
        self._update_pull_operation()
        panel.adjustSize()
        self._position_pull()
        panel.show()
        panel.raise_()
        self.update_gear()
        QtCore.QTimer.singleShot(0, self._focus_pull_input)

    @staticmethod
    def _contrast_icon(icon, color="#ffffff"):
        pixmap = icon.pixmap(22, 22)
        painter = QtGui.QPainter(pixmap)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QtGui.QColor(color))
        painter.end()
        return QtGui.QIcon(pixmap)

    def _focus_pull_input(self):
        if self.pull_input:
            try:
                self.pull_input.setFocus()
                self.pull_input.selectAll()
            except RuntimeError:
                pass

    def _change_pull_mode(self, index):
        import EasyDesignPull

        session = self.pull_session
        if not session or not hasattr(session, "operation") or session.operation == EasyDesignPull.OPERATIONS[index]:
            return
        self.pull_error = None
        self.pull_input.interpretText()
        if self.pull_taper:
            self.pull_taper.interpretText()
        if self.pull_error:
            self.pull_mode.blockSignals(True)
            self.pull_mode.setCurrentIndex(EasyDesignPull.OPERATIONS.index(session.operation))
            self.pull_mode.blockSignals(False)
            return
        try:
            session.set_operation(EasyDesignPull.OPERATIONS[index])
        except (ValueError, RuntimeError) as exc:
            self.main.statusBar().showMessage(str(exc), 5000)
        self._update_pull_operation()
        self._position_pull()

    def _update_pull_operation(self):
        if not self.pull_mode or not self.pull_session or not hasattr(self.pull_session, "operation"):
            return
        from EasyDesignPull import OPERATIONS
        session = self.pull_session
        result = "New Solid" if session.new_solid or session.previous_solid is None else ("Cut" if session.cut else "Merge")
        self.pull_mode.blockSignals(True)
        self.pull_mode.setItemText(0, "Auto (" + result + ")")
        self.pull_mode.setCurrentIndex(OPERATIONS.index(session.operation))
        self.pull_mode.blockSignals(False)

    def _set_pull_taper(self, value):
        if not self.pull_session or not self.pull_taper:
            return
        self.pull_error = None
        try:
            self.pull_session.set_taper(value)
        except ValueError as exc:
            self.pull_error = str(exc)
            self.pull_taper.blockSignals(True)
            self.pull_taper.setValue(self.pull_session.taper)
            self.pull_taper.blockSignals(False)
            self.main.statusBar().showMessage(str(exc), 5000)

    def _pull_base_direction(self):
        if hasattr(self.pull_session, "base_direction"):
            return self.pull_session.base_direction
        sketch = self.pull_session.sketch
        base = sketch.Shape.BoundBox.Center
        direction = sketch.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        return base, direction

    def _position_pull(self):
        if not self.pull_session or not self.pull_widget or not self.view:
            return
        viewport = self._viewport_widget()
        if not viewport:
            return
        base, direction = self._pull_base_direction()
        if hasattr(self.pull_session, "measure_name"):
            start = self.view.getPointOnViewport(base)
            end = self.view.getPointOnViewport(base + direction)
            angle = math.degrees(math.atan2(start[1] - end[1], end[0] - start[0])) + 90
            icon = QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_ArrowUp)
            pixmap = icon.pixmap(18, 18)
            painter = QtGui.QPainter(pixmap)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), QtGui.QColor("#22323d"))
            painter.end()
            self.pull_handle.setArrowType(QtCore.Qt.NoArrow)
            self.pull_handle.setIcon(QtGui.QIcon(pixmap.transformed(QtGui.QTransform().rotate(angle))))
            self.pull_handle.setIconSize(QtCore.QSize(22, 22))
        x, y = self.view.getPointOnViewport(base + direction * self.pull_session.signed_length)
        left = max(6, min(int(x) - 18, viewport.width() - self.pull_widget.width() - 6))
        top = max(6, min(viewport.height() - int(y) - 18,
                         viewport.height() - self.pull_widget.height() - 6))
        self.pull_widget.move(left, top)

    def _set_pull_depth(self, value):
        if not self.pull_session:
            return
        self.pull_error = None
        if abs(value) < 0.01:
            self.pull_error = "Enter a nonzero extrusion distance."
            self.main.statusBar().showMessage("Enter a nonzero extrusion distance.", 4000)
            return
        try:
            self.pull_session.set_length(value)
        except ValueError as exc:
            self.pull_error = str(exc)
            self.pull_input.blockSignals(True)
            self.pull_input.setValue(self.pull_session.signed_length)
            self.pull_input.blockSignals(False)
            self.main.statusBar().showMessage(str(exc), 4000)
        self._update_pull_operation()
        if self.pull_handle:
            cut = self.pull_session.cut
            self.pull_handle.setArrowType(QtCore.Qt.DownArrow if self.pull_session.signed_length < 0 else QtCore.Qt.UpArrow)
            self.pull_handle.setToolTip("Drag to change cut depth" if cut else "Drag to change height")
            if hasattr(self.pull_session, "measure_name"):
                self.pull_handle.setToolTip("Drag to change " + self.pull_session.measure_name.lower())
        self._position_pull()

    def drag_pull(self, start_position, current_position, start_length):
        if not self.pull_session or not self.pull_input:
            return
        base, direction = self._pull_base_direction()
        origin = self.view.getPointOnViewport(base)
        end = self.view.getPointOnViewport(base + direction * 10)
        dx = (end[0] - origin[0]) / 10.0
        dy = (origin[1] - end[1]) / 10.0
        pixels_per_mm = math.hypot(dx, dy)
        if pixels_per_mm < 0.2:
            dx, dy = 0.0, -1.0
            pixels_per_mm = max(1.0, self._viewport_widget().height() / 150.0)
        else:
            dx, dy = dx / pixels_per_mm, dy / pixels_per_mm
        movement = current_position - start_position
        length = start_length + (movement.x() * dx + movement.y() * dy) / pixels_per_mm
        self.pull_input.setValue(self._snap_value(length))

    def finish_pull(self, accept):
        session = self.pull_session
        if not session:
            return
        if accept and self.pull_input:
            self.pull_error = None
            self.pull_input.interpretText()
            if self.pull_taper and not self.pull_error:
                self.pull_taper.interpretText()
            if self.pull_error:
                return
            if abs(self.pull_input.value()) < 0.01:
                self.main.statusBar().showMessage("Enter a nonzero extrusion distance.", 4000)
                return
        try:
            session.finish(accept)
        except (ValueError, RuntimeError, Part.OCCError) as exc:
            self.main.statusBar().showMessage(str(exc), 6000)
            App.Console.PrintWarning("456D Design: %s\n" % exc)
            return
        self.pull_session = None
        if self.pull_highlight is not None:
            try:
                self.view.getSceneGraph().removeChild(self.pull_highlight)
            except RuntimeError:
                pass
            self.pull_highlight = None
        if self.pull_widget:
            try:
                self.pull_widget.hide()
                self.pull_widget.deleteLater()
            except RuntimeError:
                pass
        self.pull_widget = None
        self.pull_input = None
        self.pull_handle = None
        self.pull_taper = None
        self.pull_mode = None
        self._refresh_profiles()
        self.update_gear()

    def update_gear(self):
        if self.closed:
            return
        self.sketch_dock.refresh()
        if self.gear_tool:
            self.gear_tool.pick_selection()
        if self.gear and self.flyout.anchor is self.gear:
            self.flyout.hide()
            self.flyout.anchor = None
        if self.gear:
            try:
                self.gear.objectName()
            except RuntimeError:
                self.gear = None
        if self.kind or self.pull_session or self.transform_tool or self.loft_tool or self.gear_tool or self.measure_tool or not Gui.ActiveDocument:
            if self.gear:
                self.gear.hide()
            return
        selected = Gui.Selection.getSelectionEx()
        multi_sketch = len(selected) >= 2 and all(item.Object.isDerivedFrom("Sketcher::SketchObject")
                                                for item in selected)
        if len(selected) != 1 and not multi_sketch:
            if self.gear:
                self.gear.hide()
            return
        item = selected[0]
        obj = item.Object
        sketch = commands.is_profile(obj)
        subelement = item.SubElementNames[0] if item.SubElementNames else ""
        face = subelement.startswith("Face")
        edge = subelement.startswith("Edge")
        solid = not subelement and hasattr(obj, "Shape") and bool(obj.Shape.Solids)
        if not sketch and not face and not edge and not solid:
            if self.gear:
                self.gear.hide()
            return
        widget = self._viewport_widget()
        if not widget:
            return
        if self.gear:
            self.gear.deleteLater()
        entries = []
        native = lambda name: lambda: Gui.runCommand(name)
        if multi_sketch:
            sketches = [item.Object for item in selected]
            entries.extend([
                ("Extrude (U)", "PartDesign_Pad", lambda: commands.pull_sketch()),
                ("Loft", "PartDesign_AdditiveLoft", self.begin_loft),
                ("Move / rotate", "Std_Transform", lambda: self.begin_transform(sketches)),
                ("Hide", "Std_ToggleVisibility", lambda: self.sketch_dock.set_visibility(False, sketches)),
            ])
        elif "EasyDesignText" in obj.PropertiesList:
            entries.extend([
                ("Move / rotate", "Std_Transform", lambda: self.begin_transform(obj)),
                ("Edit text", "EasyDesignText", lambda: self.edit_text(obj)),
                ("Wrap text", "PartDesign_AdditiveCylinder", lambda: self.begin_text_wrap(obj)),
                ("Extrude (U)", "PartDesign_Pad", lambda: self.begin_pull(obj)),
                ("Cut", "PartDesign_Pocket", lambda: self.begin_pull(obj, cut=True)),
                ("Hide", "Std_ToggleVisibility", lambda: self._hide_object(obj)),
            ])
            if obj.WrapTarget:
                entries.insert(3, ("Unwrap text", "EasyDesignText", lambda: self.unwrap_text(obj)))
        elif sketch:
            entries.append(("Move / rotate", "Std_Transform", lambda: self.begin_transform(obj)))
            from EasyDesignGear import circle_frame
            try:
                circle_frame(obj)
                entries.append(("Gear", "EasyDesignGear", lambda: self.begin_gear(obj)))
            except ValueError:
                pass
            simple = ("EasyDesignShape" in obj.PropertiesList and obj.Geometry
                      and obj.EasyDesignShape in ("rectangle", "circle"))
            if simple:
                entries.append(("Scale", "PartDesign_AdditiveBox", lambda: self._scale_profile_dialog(obj)))
            if any(wire.isClosed() for wire in obj.Shape.Wires):
                entries.extend([
                    ("Extrude (U)", "PartDesign_Pad", lambda: commands.pull_sketch()),
                    ("Sweep", "PartDesign_AdditivePipe", native("PartDesign_AdditivePipe")),
                    ("Revolve", "PartDesign_Revolution", native("PartDesign_Revolution")),
                ])
            entries.append(("Edit dimension", "Sketcher_NewSketch",
                            (lambda: self._size_dialog(obj)) if simple else (lambda: commands.start_draw())))
            entries.append(("Hide", "Std_ToggleVisibility", lambda: self._hide_object(obj)))
            if commands._body_of(obj):
                entries.append(("Cut", "PartDesign_Pocket", lambda: commands.pull_sketch(cut=True)))
        elif face:
            entries.extend([
                ("Make sketch", "Sketcher_NewSketch", lambda: self.make_face_sketch(obj, subelement)),
                ("Press/Pull", "PartDesign_Pad", lambda: self.begin_face_pull(obj, subelement)),
                ("Mesh", "PartDesign_LinearPattern", lambda: self.begin_face_pull(obj, subelement, mesh=True)),
                None,
                ("Draw rectangle on face", "Sketcher_CreateRectangle", lambda: self.begin("rectangle")),
                ("Draw circle on face", "Sketcher_CreateCircle", lambda: self.begin("circle")),
                None,
                ("Fillet", "PartDesign_Fillet", self.begin_edge),
                ("Chamfer", "PartDesign_Chamfer", lambda: self.begin_edge(chamfer=True)),
                ("Shell", "PartDesign_Thickness", self.begin_shell),
            ])
        elif edge:
            entries.extend([
                ("Fillet", "PartDesign_Fillet", self.begin_edge),
                ("Chamfer", "PartDesign_Chamfer", lambda: self.begin_edge(chamfer=True)),
            ])
        else:
            entries.extend([
                ("Move / rotate", "Std_Transform", lambda: self.begin_transform(obj)),
                ("Placement", "Std_Placement", native("Std_Placement")),
                ("Hide", "Std_ToggleVisibility", lambda: self._hide_object(obj)),
            ])
        if not sketch and not obj.isDerivedFrom("App::Part") and hasattr(obj, "Shape") and obj.Shape.Solids:
            entries.extend([None,
                ("Export selected", "Std_Export", lambda: self._export_selected(obj)),
                ("Cut MM", "Part_Cut", lambda: self._run_tool(lambda: commands.cut_mm(obj))),
            ])
        if not sketch and obj.ViewObject and hasattr(obj.ViewObject, "ShapeColor"):
            entries.extend([None, ("Fargevelger", "EasyDesignColor", lambda: self._color_dialog(obj))])
        self.gear = _FlyoutButton(self.flyout, entries, widget, beside=True, hover=False)
        self.gear.setObjectName("EasyDesignGear")
        self.gear.setIcon(_icon("EasyDesignGear"))
        self.gear.setToolTip("Shape actions")
        self.gear.setFixedSize(34, 34)
        position = widget.mapFromGlobal(QtGui.QCursor.pos())
        x = max(8, min(position.x() + 12, widget.width() - 42))
        y = max(8, min(position.y() + 12, widget.height() - 42))
        self.gear.move(x, y)
        self.gear.show()
        self.gear.raise_()

    def _export_selected(self, obj):
        from pathlib import Path
        import EasyDesignExport

        self.flyout.hide()
        try:
            EasyDesignExport.solid_shape(obj)
            initial = str(Path(obj.Document.FileName).parent) if obj.Document.FileName else str(Path.home())
            dialog = QtWidgets.QFileDialog(self.main, "Export selected")
            dialog.setObjectName("EasyDesignExportDialog")
            dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
            dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
            dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
            dialog.setNameFilters([EasyDesignExport.STL_FILTER, EasyDesignExport.STEP_FILTER])
            dialog.selectNameFilter(EasyDesignExport.STL_FILTER)
            dialog.setDefaultSuffix("stl")

            dialog.filterSelected.connect(lambda name: dialog.setDefaultSuffix(
                "step" if name == EasyDesignExport.STEP_FILTER else "stl"))
            dialog.setDirectory(self.preferences.GetString("ExportDirectory", initial))
            dialog.selectFile(EasyDesignExport.file_label(obj) + ".stl")
            try:
                if dialog.exec_() != QtWidgets.QDialog.Accepted:
                    return
                path = EasyDesignExport.export_selected(obj, dialog.selectedFiles()[0])
            finally:
                dialog.deleteLater()
            self.preferences.SetString("ExportDirectory", str(path.parent))
            self.main.statusBar().showMessage("Exported %s to %s" % (obj.Label, path), 6000)
        except (ValueError, RuntimeError, OSError, Part.OCCError) as exc:
            commands._warn("Export: " + str(exc))

    def _hide_object(self, obj):
        obj.ViewObject.Visibility = False
        Gui.Selection.clearSelection()
        self._refresh_profiles()

    def _color_dialog(self, obj):
        self.flyout.hide()
        body = commands._body_of(obj)
        targets = [obj]
        for target in (body, getattr(body, "Tip", None)):
            if target and target not in targets:
                targets.append(target)
        targets = [target for target in targets if target.ViewObject
                   and hasattr(target.ViewObject, "ShapeColor")]
        originals = [(target.ViewObject, tuple(target.ViewObject.ShapeColor),
                      list(target.ViewObject.DiffuseColor) if hasattr(target.ViewObject, "DiffuseColor") else None)
                     for target in targets]
        if not originals:
            return
        selected = [(item.Object, list(item.SubElementNames)) for item in Gui.Selection.getSelectionEx()]
        initial = QtGui.QColor.fromRgbF(*originals[0][1][:3])
        dialog = QtWidgets.QColorDialog(initial, self.main)
        dialog.setObjectName("EasyDesignColorDialog")
        dialog.setWindowTitle("Fargevelger")
        dialog.setOption(QtWidgets.QColorDialog.DontUseNativeDialog, True)

        def preview(color):
            if not color.isValid():
                return
            rgb = (color.redF(), color.greenF(), color.blueF())
            for target in targets:
                target.ViewObject.ShapeColor = rgb
                if hasattr(target.ViewObject, "DiffuseColor"):
                    target.ViewObject.DiffuseColor = [rgb] * max(1, len(target.Shape.Faces))

        dialog.currentColorChanged.connect(preview)
        doc = obj.Document
        doc.openTransaction("Object color")
        Gui.Selection.clearSelection()
        try:
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                preview(dialog.currentColor())
                doc.commitTransaction()
            else:
                doc.abortTransaction()
                for provider, color, diffuse in originals:
                    provider.ShapeColor = color
                    if diffuse is not None:
                        provider.DiffuseColor = diffuse
        except Exception:
            doc.abortTransaction()
            for provider, color, diffuse in originals:
                provider.ShapeColor = color
                if diffuse is not None:
                    provider.DiffuseColor = diffuse
            raise
        finally:
            dialog.deleteLater()
            for target, names in selected:
                for name in names or [""]:
                    Gui.Selection.addSelection(doc.Name, target.Name, name)
            self.update_gear()

    def _scale_profile_dialog(self, sketch):
        factor, accepted = QtWidgets.QInputDialog.getDouble(
            self.main, "Scale profile", "Scale factor", 1.0, 0.001, 1000.0, 3,
        )
        if not accepted:
            return
        if sketch.EasyDesignShape == "rectangle":
            a, b = sketch.Geometry[0].StartPoint, sketch.Geometry[1].EndPoint
            sizes = [abs(b.x - a.x) * factor, abs(b.y - a.y) * factor]
        else:
            sizes = [sketch.Geometry[0].Radius * factor]
        try:
            _resize_sketch(sketch, sizes)
            self._refresh_profiles()
        except ValueError as exc:
            commands._warn(str(exc))

    def begin_gear(self, circle=None):
        import EasyDesignGear

        if Gui.Control.activeDialog():
            self.main.statusBar().showMessage("Finish the current task before creating a Gear pattern.", 4000)
            return
        if circle is None:
            selected = Gui.Selection.getSelection()
            if len(selected) != 1:
                self.main.statusBar().showMessage("Select a circle sketch first.", 4000)
                return
            circle = selected[0]
        self.flyout.hide()
        self._run_tool(lambda: None)
        try:
            self.gear_tool = EasyDesignGear.GearTool(self, circle)
            Gui.Selection.clearSelection()
            self.selected_region = None
            self.main.statusBar().showMessage("Select the sketch to repeat around the circle. Esc to cancel.")
            self.update_gear()
        except (ValueError, RuntimeError) as exc:
            self.main.statusBar().showMessage(str(exc), 5000)

    def begin_loft(self):
        import EasyDesignLoft

        self.flyout.hide()
        if self.loft_tool:
            self.loft_tool.raise_()
            return
        if Gui.Control.activeDialog():
            self.main.statusBar().showMessage("Finish the current task before lofting.", 4000)
            return
        sketches = Gui.Selection.getSelection()
        self._run_tool(lambda: None)
        try:
            self.loft_tool = EasyDesignLoft.LoftTool(self, sketches)
            self.loft_tool.show()
            viewport = self._viewport_widget()
            if viewport:
                self.loft_tool.move(viewport.mapToGlobal(QtCore.QPoint(
                    12, max(12, viewport.height() - self.loft_tool.height() - 40))))
            self.update_gear()
        except (ValueError, RuntimeError) as exc:
            self.main.statusBar().showMessage(str(exc), 6000)

    def begin_transform(self, obj=None):
        import EasyDesignTransform

        self.flyout.hide()
        if self.gear_tool:
            self.gear_tool.finish(False)
        if self.loft_tool:
            self.loft_tool.finish(False)
        if self.measure_tool:
            self.measure_tool.close()
        if self.transform_tool:
            self.transform_tool.finish(False)
        if self.pull_session:
            self.finish_pull(False)
        if self.kind:
            self.cancel()
        if obj is None:
            selected = Gui.Selection.getSelection()
            if not selected:
                self.main.statusBar().showMessage("Select an object or sketch to move or rotate.", 4000)
                return
            obj = selected if len(selected) > 1 else selected[0]
        if isinstance(obj, (list, tuple)):
            targets = [item if commands.is_profile(item) else commands._body_of(item) or item
                       for item in obj]
            obj = [item for item in dict.fromkeys(targets)
                   if item.getParentGeoFeatureGroup() not in targets]
            if len(obj) == 1:
                obj = obj[0]
        elif not commands.is_profile(obj):
            obj = commands._body_of(obj) or obj
        self.sync_view()
        try:
            self.transform_tool = EasyDesignTransform.TransformTool(self, obj)
            self.update_gear()
        except (ValueError, RuntimeError) as exc:
            commands._warn(str(exc))

    def close(self):
        self.closed = True
        self.flyout.hide()
        if self.gear_tool:
            self.gear_tool.finish(False)
        if self.loft_tool:
            self.loft_tool.finish(False)
        if self.pull_session:
            self.finish_pull(False)
        self.cancel()
        self.timer.stop()
        Gui.Selection.removeObserver(self.observer)
        documents = App.listDocuments()
        for name, (doc, state) in self.display_states.items():
            if documents.get(name) == doc:
                state.restore(doc)
        self.display_states.clear()
        self._detach_view()
        if self.gear:
            try:
                self.gear.deleteLater()
            except RuntimeError:
                pass
        self.toolbar.hide()
        self.toolbar.deleteLater()
        self.sketch_dock.hide()
        self.main.removeDockWidget(self.sketch_dock)
        self.sketch_dock.deleteLater()
        self.flyout.deleteLater()


def activate():
    global _controller
    if _controller is None:
        _controller = ViewController()


def deactivate():
    global _controller
    if _controller:
        _controller.close()
        _controller = None


def begin(kind):
    if _controller is None:
        activate()
    _controller.begin(kind)


def begin_loft():
    if _controller is None:
        activate()
    _controller.begin_loft()


def begin_pull(sketch, cut=False):
    if _controller is None:
        activate()
    _controller.begin_pull(sketch, cut)
