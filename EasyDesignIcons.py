# SPDX-License-Identifier: LGPL-2.1-or-later

"""Original, neutral modelling symbols for the compact 456D Design toolbar."""

import math

from PySide import QtCore, QtGui, QtWidgets


KINDS = {
    "Std_Transform": "move", "Std_Group": "group",
    "PartDesign_AdditiveBox": "primitives", "Sketcher_NewSketch": "sketch",
    "PartDesign_Pad": "extrude", "PartDesign_Pocket": "cut",
    "PartDesign_Fillet": "fillet", "PartDesign_Chamfer": "chamfer",
    "PartDesign_LinearPattern": "pattern", "Part_Fuse": "combine",
    "EasyDesignGrid": "grid", "Std_ToggleVisibility": "grid",
    "Std_ViewAxonometric": "view", "EasyDesignReverse": "reverse",
    "Constraint_Coincident": "snap",
    "EasyDesignColor": "color",
    "EasyDesignGear": "gear",
    "EasyDesignShowSketches": "eye",
    "EasyDesignHideSketches": "eye-off",
    "EasyDesignText": "text",
    "EasyDesignOutlines": "outlines",
    "EasyDesignSolids": "solid",
    "EasyDesignTransparent": "transparent",
}


def icon(name):
    kind = KINDS.get(name)
    if kind is None:
        return None
    pixmap = QtGui.QPixmap(64, 64)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.scale(2, 2)
    palette = QtWidgets.QApplication.palette()
    dark = palette.color(QtGui.QPalette.Window).lightness() < 128
    ink = QtGui.QColor("#eff3f4" if dark else "#303436")
    painter.setPen(QtGui.QPen(ink, 1.2, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))

    def polygon(points, fill):
        painter.setBrush(QtGui.QColor(fill))
        painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))

    def cube(x=7, y=7, size=18):
        half, depth = size / 2, size / 4
        polygon([(x, y + depth), (x + half, y), (x + size, y + depth), (x + half, y + depth * 2)], "#eef1f2")
        polygon([(x, y + depth), (x + half, y + depth * 2), (x + half, y + size), (x, y + size - depth)], "#767d80")
        polygon([(x + half, y + depth * 2), (x + size, y + depth), (x + size, y + size - depth), (x + half, y + size)], "#484f52")

    def line(x1, y1, x2, y2):
        painter.drawLine(QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2))

    def arrow(x1, y1, x2, y2):
        line(x1, y1, x2, y2)
        direction = QtCore.QPointF(x1 - x2, y1 - y2)
        length = (direction.x() ** 2 + direction.y() ** 2) ** .5
        dx, dy = direction.x() / length * 3, direction.y() / length * 3
        line(x2, y2, x2 + dx - dy, y2 + dy + dx)
        line(x2, y2, x2 + dx + dy, y2 + dy - dx)

    if kind == "outlines":
        painter.setBrush(QtCore.Qt.NoBrush)
        points = [(5, 10), (16, 5), (27, 10), (27, 23), (16, 28), (5, 23)]
        painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))
        line(5, 10, 16, 15)
        line(27, 10, 16, 15)
        line(16, 15, 16, 28)
    elif kind == "solid":
        cube(5, 5, 22)
    elif kind == "transparent":
        painter.save()
        painter.setOpacity(.5)
        cube(5, 5, 22)
        painter.restore()
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(QtGui.QPen(ink, 1, QtCore.Qt.DashLine))
        line(5, 22, 16, 17)
        line(27, 22, 16, 17)
        line(16, 17, 16, 5)
    elif kind == "text":
        painter.setFont(QtGui.QFont("DejaVu Sans", 22, QtGui.QFont.Bold))
        painter.drawText(QtCore.QRectF(0, 0, 32, 32), QtCore.Qt.AlignCenter, "T")
    elif kind == "gear":
        path = QtGui.QPainterPath()
        for tooth in range(8):
            for fraction, radius in ((0, 10), (.2, 10), (.3, 13), (.7, 13), (.8, 10)):
                angle = (tooth + fraction) * math.tau / 8
                point = QtCore.QPointF(16 + radius * math.cos(angle), 16 + radius * math.sin(angle))
                if tooth == 0 and fraction == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
        path.closeSubpath()
        path.addEllipse(QtCore.QRectF(11, 11, 10, 10))
        path.setFillRule(QtCore.Qt.OddEvenFill)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(ink)
        painter.drawPath(path)
    elif kind in ("eye", "eye-off"):
        painter.setBrush(QtCore.Qt.NoBrush)
        path = QtGui.QPainterPath()
        path.moveTo(3, 16)
        path.cubicTo(10, 5, 22, 5, 29, 16)
        path.cubicTo(22, 27, 10, 27, 3, 16)
        painter.drawPath(path)
        painter.drawEllipse(QtCore.QRectF(12, 12, 8, 8))
        if kind == "eye-off":
            line(5, 28, 27, 4)
    elif kind == "color":
        for x, y, fill in ((4, 4, "#df665f"), (18, 4, "#64b879"),
                           (4, 18, "#60a8d5"), (18, 18, "#edcb62")):
            polygon([(x, y), (x + 10, y), (x + 10, y + 10), (x, y + 10)], fill)
    elif kind == "primitives":
        painter.setBrush(QtGui.QColor("#bbc1c3"))
        painter.drawEllipse(QtCore.QRectF(17, 3, 11, 11))
        cube(4, 12, 17)
    elif kind == "sketch":
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawEllipse(QtCore.QRectF(3, 8, 13, 13))
        polygon([(11, 25), (14, 18), (24, 5), (28, 8), (18, 21)], "#767d80")
        polygon([(11, 25), (14, 18), (18, 21)], "#eef1f2")
    elif kind == "move":
        cube(4, 13, 13)
        arrow(20, 13, 20, 3)
        arrow(20, 13, 29, 13)
        arrow(20, 13, 26, 20)
    elif kind in ("extrude", "cut"):
        cube(5, 12, 21)
        arrow(16, 15 if kind == "extrude" else 2, 16, 2 if kind == "extrude" else 15)
    elif kind in ("fillet", "chamfer"):
        cube(5, 6, 22)
        painter.setBrush(QtGui.QColor("#bbc1c3"))
        if kind == "fillet":
            painter.drawEllipse(QtCore.QRectF(14, 14, 15, 15))
        else:
            polygon([(17, 18), (27, 13), (27, 22), (17, 28)], "#bbc1c3")
    elif kind in ("pattern", "group"):
        for x, y in ((4, 3), (18, 3), (4, 18), (18, 18)):
            cube(x, y, 10)
        if kind == "group":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(ink, 1, QtCore.Qt.DashLine))
            painter.drawRect(QtCore.QRectF(1, 1, 30, 29))
    elif kind == "combine":
        cube(3, 4, 16)
        cube(13, 12, 16)
    elif kind == "grid":
        painter.setBrush(QtCore.Qt.NoBrush)
        for position in (4, 12, 20, 28):
            line(4, position, 28, position)
            line(position, 4, position, 28)
    elif kind == "reverse":
        arrow(5, 10, 27, 10)
        arrow(27, 22, 5, 22)
    elif kind == "snap":
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(QtGui.QPen(ink, 3, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        path = QtGui.QPainterPath()
        path.moveTo(8, 5)
        path.lineTo(8, 18)
        path.cubicTo(8, 29, 24, 29, 24, 18)
        path.lineTo(24, 5)
        painter.drawPath(path)
        painter.setPen(QtGui.QPen(QtGui.QColor("#767d80"), 3))
        line(8, 8, 8, 12)
        line(24, 8, 24, 12)
    elif kind == "view":
        for y in (18, 12, 6):
            polygon([(4, y + 5), (16, y), (28, y + 5), (16, y + 10)], "#767d80")
    painter.end()
    return QtGui.QIcon(pixmap)
