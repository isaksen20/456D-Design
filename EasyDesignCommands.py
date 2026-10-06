# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets


_last_sketch = None


def is_profile(obj):
    return obj is not None and (obj.isDerivedFrom("Sketcher::SketchObject")
                               or "EasyDesignText" in obj.PropertiesList)


def _warn(message):
    App.Console.PrintWarning("456D Design: " + message + "\n")
    QtWidgets.QMessageBox.warning(Gui.getMainWindow(), "456D Design", message)


def _editing_sketch():
    if not Gui.ActiveDocument:
        return None
    edit = Gui.ActiveDocument.getInEdit()
    if edit and edit.isDerivedFrom("SketcherGui::ViewProviderSketch"):
        return edit.Object
    return None


def _selected_sketch():
    selected = Gui.Selection.getSelection()
    if len(selected) == 1 and is_profile(selected[0]):
        return selected[0]
    return None


def _remember(sketch):
    global _last_sketch
    _last_sketch = (sketch.Document.Name, sketch.Name)


def _recent_sketch():
    if not _last_sketch or not App.ActiveDocument:
        return None
    if _last_sketch[0] != App.ActiveDocument.Name:
        return None
    sketch = App.ActiveDocument.getObject(_last_sketch[1])
    if is_profile(sketch):
        return sketch
    return None


def _body_of(obj):
    if obj.isDerivedFrom("PartDesign::Body"):
        return obj
    parent = obj.getParentGeoFeatureGroup()
    if parent and parent.isDerivedFrom("PartDesign::Body"):
        return parent
    return None


def _drawing_target():
    selected = Gui.Selection.getSelectionEx()
    if len(selected) > 1:
        raise ValueError("Select one face or body before drawing.")
    if not selected:
        return None, None

    item = selected[0]
    if item.SubObjects:
        if len(item.SubObjects) != 1 or not item.SubElementNames[0].startswith("Face"):
            raise ValueError("Select one flat face to draw on.")
        face = item.SubObjects[0]
        if not isinstance(face.Surface, Part.Plane):
            raise ValueError("This sketch tool needs a flat face.")
        body = _body_of(item.Object)
        return body, (item.Object, item.SubElementNames[0])

    body = _body_of(item.Object)
    if body is None:
        raise ValueError("Select a Part Design body, or clear the selection.")
    return body, None


def drawing_target_at(view, pixel, doc):
    info = view.getObjectInfo((int(pixel[0]), int(pixel[1])))
    if not info or "Object" not in info:
        return None, None
    obj = doc.getObject(info["Object"])
    component = info.get("Component", "")
    if not obj or not component.startswith("Face"):
        raise ValueError("Choose the grid or a flat face to draw on.")
    face = obj.Shape.getElement(component)
    if not isinstance(face.Surface, Part.Plane):
        raise ValueError("This sketch tool needs a flat face.")
    body = _body_of(obj)
    return body, (obj, component)


def sketch_support(body, face):
    if not face:
        return body.Origin.OriginFeatures[3], [""]
    obj, name = face
    if _body_of(obj) == body:
        return obj, [name]
    # External Part faces need a native reference inside the sketch's body.
    binder = body.newObject("PartDesign::SubShapeBinder", "SketchSupport")
    binder.Support = [(obj, [name])]
    body.Document.recompute()
    if binder.ViewObject:
        binder.ViewObject.Visibility = False
    return binder, ["Face1"]


def start_draw(tool=None):
    import EasyDesignView
    from EasyDesignSketch import TOOLS

    sketch = _editing_sketch()
    if sketch:
        Gui.ActiveDocument.resetEdit()
        sketch.Document.recompute()

    if Gui.Control.activeDialog():
        _warn("Close the current task before starting a sketch.")
        return

    selected = _selected_sketch()
    if selected and "EasyDesignText" in getattr(selected, "PropertiesList", []):
        EasyDesignView._controller.edit_text(selected)
        return
    kind = TOOLS.get(tool) if tool else "line"
    if not kind:
        _warn("This sketch tool is not available in 456D Design.")
        return
    EasyDesignView.begin(kind)
    if not tool and (sketch or selected):
        EasyDesignView._controller._resume_sketch(sketch or selected)


def pull_sketch(cut=False):
    sketch = _editing_sketch()
    if sketch:
        Gui.ActiveDocument.resetEdit()
        sketch.Document.recompute()
    else:
        selected = Gui.Selection.getSelection()
        if len(selected) > 1:
            if not all(obj.isDerivedFrom("Sketcher::SketchObject") for obj in selected):
                _warn("Select sketches only for a combined extrusion.")
                return
            import EasyDesignView
            try:
                EasyDesignView.begin_pull(selected, cut)
            except (ValueError, RuntimeError, Part.OCCError) as exc:
                _warn(str(exc))
            return
        sketch = _selected_sketch() or _recent_sketch()

    if sketch is None:
        _warn("Draw or select a sketch first.")
        return
    if not (sketch.Shape.Faces if "EasyDesignText" in getattr(sketch, "PropertiesList", []) else sketch.Geometry):
        _warn("Draw a closed shape before pulling the sketch.")
        return

    _remember(sketch)
    import EasyDesignView

    try:
        EasyDesignView.begin_pull(sketch, cut)
    except ValueError as exc:
        _warn(str(exc))


def cut_mm(obj):
    import EasyDesignMM

    try:
        results = EasyDesignMM.cut_mm(obj)
    except (ValueError, RuntimeError, Part.OCCError) as exc:
        _warn(str(exc))
        return
    message = ("Cut MM: %d object(s) cut; both material parts retained." % len(results)
               if results else "Cut MM: no other visible solids overlap the selected part.")
    Gui.getMainWindow().statusBar().showMessage(message, 6000)


class _Command:
    def __init__(self, name, icon, tooltip, action, cmd_type="ForEdit"):
        self.name = name
        self.icon = icon
        self.tooltip = tooltip
        self.action = action
        self.cmd_type = cmd_type

    def GetResources(self):
        return {
            "Pixmap": self.icon,
            "MenuText": self.name,
            "ToolTip": self.tooltip,
            "CmdType": self.cmd_type,
        }

    def IsActive(self):
        return True

    def Activated(self):
        self.action()


def register_commands():
    commands = {
        "EasyDesign_Draw": _Command(
            "Draw", "Sketcher_NewSketch", "Draw on the XY plane or a selected flat face",
            lambda: start_draw(),
        ),
        "EasyDesign_Rectangle": _Command(
            "Rectangle", "Sketcher_CreateRectangle", "Draw a rectangle on a sketch",
            lambda: __import__("EasyDesignView").begin("rectangle"),
        ),
        "EasyDesign_Circle": _Command(
            "Circle", "Sketcher_CreateCircle", "Draw a circle on a sketch",
            lambda: __import__("EasyDesignView").begin("circle"),
        ),
        "EasyDesign_Polyline": _Command(
            "Polyline", "Sketcher_CreatePolyline", "Draw a connected outline",
            lambda: start_draw("Sketcher_CreatePolyline"),
        ),
        "EasyDesign_Text": _Command(
            "Text", "Draft_ShapeString", "Place an editable text sketch",
            lambda: QtCore.QTimer.singleShot(0, lambda: __import__("EasyDesignView").begin("text")),
            cmd_type="ForEdit,NoTransaction",
        ),
        "EasyDesign_FinishPull": _Command(
            "Extrude", "PartDesign_Pad", "Extrude a profile; negative distance cuts into a solid",
            lambda: QtCore.QTimer.singleShot(0, pull_sketch),
            cmd_type="ForEdit,NoTransaction",
        ),
        "EasyDesign_FinishCut": _Command(
            "Cut", "PartDesign_Pocket", "Cut a profile into an existing solid",
            lambda: QtCore.QTimer.singleShot(0, lambda: pull_sketch(cut=True)),
            cmd_type="ForEdit,NoTransaction",
        ),
        "EasyDesign_Loft": _Command(
            "Loft", "PartDesign_AdditiveLoft", "Loft through selected sketch profiles",
            lambda: QtCore.QTimer.singleShot(0, __import__("EasyDesignView").begin_loft),
            cmd_type="ForEdit,NoTransaction",
        ),
    }
    for name, command in commands.items():
        Gui.addCommand(name, command)
