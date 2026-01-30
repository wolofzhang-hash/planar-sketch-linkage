# -*- coding: utf-8 -*-
"""Graphics items used in the QGraphicsScene."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPen, QColor, QPainterPath, QBrush
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsSimpleTextItem,
    QGraphicsPathItem,
)

from ..utils.constants import PURPLE, DARK, YELLOW, GRAY, HILITE, BODY_COLORS
from ..utils.qt_safe import safe_event

if TYPE_CHECKING:
    from ..core.controller import SketchController


class TextMarker(QGraphicsSimpleTextItem):
    def __init__(self, text: str = ""):
        super().__init__(text)
        self.setZValue(30)
        self.setBrush(DARK)
        # Markers should not intercept mouse events (allow right-click on underlying items).
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)


class PointItem(QGraphicsEllipseItem):
    def __init__(self, pid: int, ctrl: "SketchController"):
        super().__init__(-5, -5, 10, 10)
        self.pid = pid
        self.ctrl = ctrl
        self._internal = False
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(10)
        self.sync_style()

    @safe_event
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.ctrl.mode == "CreateLine":
                self.ctrl.on_point_clicked_create_line(self.pid)
                e.accept(); return
            if self.ctrl.mode == "Coincide":
                self.ctrl.on_point_clicked_coincide(self.pid)
                e.accept(); return
            if self.ctrl.mode == "PointOnLine":
                self.ctrl.on_point_clicked_point_on_line(self.pid)
                e.accept(); return
            self.ctrl.on_point_clicked_idle(self.pid, e.modifiers())
            e.accept(); return
        super().mousePressEvent(e)

    def sync_style(self):
        p = self.ctrl.points[self.pid]
        hidden = self.ctrl.is_point_effectively_hidden(self.pid) or (not self.ctrl.show_points_geometry)
        self.setVisible(not hidden)

        fixed = bool(p.get("fixed", False))
        bid = self.ctrl.point_body(self.pid)
        body_color = None
        if (
            self.ctrl.show_body_coloring
            and bid is not None
            and bid in self.ctrl.bodies
            and not self.ctrl.bodies[bid].get("hidden", False)
        ):
            cname = self.ctrl.bodies[bid].get("color_name", "Blue")
            body_color = BODY_COLORS.get(cname, BODY_COLORS["Blue"])

        if body_color is not None:
            self.setRect(-7, -7, 14, 14)
            if fixed:
                self.setBrush(GRAY)
                self.setPen(QPen(body_color, 3))
            else:
                self.setBrush(body_color)
                self.setPen(QPen(Qt.GlobalColor.black, 1))
        else:
            self.setRect(-5, -5, 10, 10)
            self.setBrush(GRAY if fixed else YELLOW)
            self.setPen(QPen(Qt.GlobalColor.black, 1))

        sel = self.isSelected() or (self.pid in self.ctrl.selected_point_ids)
        if sel:
            self.setPen(QPen(HILITE, 3))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, (not fixed) and (not hidden))

    def itemChange(self, change, val):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and not self._internal:
            p = self.ctrl.points[self.pid]
            if p.get("fixed", False) or self.ctrl.is_point_effectively_hidden(self.pid) or (not self.ctrl.show_points_geometry):
                return QPointF(p["x"], p["y"])
            nx, ny = float(val.x()), float(val.y())
            self.ctrl.on_drag_update(self.pid, nx, ny)
            p2 = self.ctrl.points[self.pid]
            return QPointF(p2["x"], p2["y"])
        return super().itemChange(change, val)


class LinkItem(QGraphicsLineItem):
    def __init__(self, lid: int, ctrl: "SketchController"):
        super().__init__()
        self.lid = lid
        self.ctrl = ctrl
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(0)
        self.sync_style()
        self.update_position()

    @safe_event
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.ctrl.select_link_single(self.lid)
            e.accept(); return
        super().mousePressEvent(e)

    def sync_style(self):
        l = self.ctrl.links[self.lid]
        hidden = bool(l.get("hidden", False)) or (not self.ctrl.show_links_geometry)
        i, j = l["i"], l["j"]
        if self.ctrl.is_point_effectively_hidden(i) and self.ctrl.is_point_effectively_hidden(j):
            hidden = True
        self.setVisible(not hidden)
        # Visual hint: Reference length is not constrained.
        if l.get("ref", False):
            base = GRAY
        else:
            base = PURPLE if l.get("over", False) else QColor(0, 0, 0)
        sel = (self.ctrl.selected_link_id == self.lid) or self.isSelected()
        pen = QPen(HILITE if sel else base, 3 if sel else (2 if not l.get("ref", False) else 2))
        if l.get("ref", False) and not sel:
            pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)

    def update_position(self):
        l = self.ctrl.links[self.lid]
        p1 = self.ctrl.points[l["i"]]
        p2 = self.ctrl.points[l["j"]]
        self.setLine(p1["x"], p1["y"], p2["x"], p2["y"])


class SplineItem(QGraphicsPathItem):
    def __init__(self, sid: int, ctrl: "SketchController"):
        super().__init__()
        self.sid = sid
        self.ctrl = ctrl
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-1)
        self.sync_style()

    @safe_event
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.ctrl.mode == "PointOnSpline":
                self.ctrl.on_spline_clicked_point_on_spline(self.sid)
                e.accept(); return
            self.ctrl.select_spline_single(self.sid)
            e.accept(); return
        super().mousePressEvent(e)

    def sync_style(self):
        s = self.ctrl.splines[self.sid]
        hidden = bool(s.get("hidden", False)) or (not self.ctrl.show_splines_geometry)
        self.setVisible(not hidden)
        sel = (getattr(self.ctrl, "selected_spline_id", None) == self.sid) or self.isSelected()
        base = PURPLE if s.get("over", False) else QColor(30, 30, 180)
        pen = QPen(HILITE if sel else base, 2 if sel else 1.6)
        self.setPen(pen)


class PointSplineItem(QGraphicsSimpleTextItem):
    """Marker for point-on-spline constraint."""
    def __init__(self, psid: int, ctrl: "SketchController"):
        super().__init__("∈")
        self.psid = psid
        self.ctrl = ctrl
        self.setZValue(10)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(GRAY)
        self.sync()

    @safe_event
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.ctrl.select_point_spline_single(self.psid)
            e.accept(); return
        super().mousePressEvent(e)

    def sync(self):
        ps = self.ctrl.point_splines[self.psid]
        p = int(ps.get("p", -1))
        if p not in self.ctrl.points:
            self.setVisible(False)
            return
        pp = self.ctrl.points[p]
        self.setPos(pp["x"] + 8, pp["y"] + 8)
        hidden = bool(ps.get("hidden", False)) or (not self.ctrl.show_dim_markers)
        self.setVisible(not hidden)
        sel = (getattr(self.ctrl, "selected_point_spline_id", None) == self.psid) or self.isSelected()
        if not bool(ps.get("enabled", True)):
            col = GRAY
        else:
            col = PURPLE if ps.get("over", False) else GRAY
        self.setBrush(HILITE if sel else col)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)


class CoincideItem(QGraphicsSimpleTextItem):
    """A small marker indicating a coincidence (point-on-point) constraint."""
    def __init__(self, cid: int, ctrl: "SketchController"):
        super().__init__("⨉")  # simple symbol
        self.cid = cid
        self.ctrl = ctrl
        self.setZValue(10)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(GRAY)
        self.sync()

    @safe_event
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.ctrl.select_coincide_single(self.cid)
            e.accept(); return
        super().mousePressEvent(e)

    def sync(self):
        c = self.ctrl.coincides[self.cid]
        a, b = c["a"], c["b"]
        if a not in self.ctrl.points or b not in self.ctrl.points:
            self.setVisible(False); return
        pa, pb = self.ctrl.points[a], self.ctrl.points[b]
        mx, my = (pa["x"] + pb["x"]) * 0.5, (pa["y"] + pb["y"]) * 0.5
        self.setPos(mx + 4, my + 4)
        hidden = bool(c.get("hidden", False)) or (not self.ctrl.show_dim_markers)
        self.setVisible(not hidden)
        sel = (self.ctrl.selected_coincide_id == self.cid) or self.isSelected()
        self.setBrush(HILITE if sel else (PURPLE if c.get("over", False) else GRAY))
        # Don't intercept right-click menus; allow passing through.
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)


class PointLineItem(QGraphicsSimpleTextItem):
    """A small marker indicating a point-on-line (point belongs to line) constraint."""
    def __init__(self, plid: int, ctrl: "SketchController"):
        super().__init__("∈")
        self.plid = plid
        self.ctrl = ctrl
        self.setZValue(10)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(GRAY)
        self.sync()

    @safe_event
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.ctrl.select_point_line_single(self.plid)
            e.accept(); return
        super().mousePressEvent(e)

    def sync(self):
        pl = self.ctrl.point_lines[self.plid]
        p = int(pl.get("p", -1))
        i = int(pl.get("i", -1))
        j = int(pl.get("j", -1))
        if p not in self.ctrl.points or i not in self.ctrl.points or j not in self.ctrl.points:
            self.setVisible(False)
            return

        pp = self.ctrl.points[p]
        # Place marker near the constrained point
        self.setPos(pp["x"] + 8, pp["y"] - 8)

        hidden = bool(pl.get("hidden", False)) or (not self.ctrl.show_dim_markers)
        self.setVisible(not hidden)

        sel = (getattr(self.ctrl, "selected_point_line_id", None) == self.plid) or self.isSelected()
        if not bool(pl.get("enabled", True)):
            col = GRAY
        else:
            col = PURPLE if pl.get("over", False) else GRAY
        self.setBrush(HILITE if sel else col)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)


class AngleItem(QGraphicsSimpleTextItem):
    def __init__(self, aid: int, ctrl: "SketchController"):
        super().__init__("")
        self.aid = aid
        self.ctrl = ctrl
        self.setZValue(25)
        self.setBrush(DARK)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.sync()

    @safe_event
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.ctrl.select_angle_single(self.aid)
            e.accept(); return
        super().mousePressEvent(e)

    def sync(self):
        a = self.ctrl.angles[self.aid]
        i, j, k = a["i"], a["j"], a["k"]
        if i not in self.ctrl.points or j not in self.ctrl.points or k not in self.ctrl.points:
            self.setVisible(False); return
        pj = self.ctrl.points[j]
        self.setText(f"A={a['deg']:.6g}°")
        self.setPos(pj["x"] + 10, pj["y"] - 10)
        hidden = bool(a.get("hidden", False)) or (not self.ctrl.show_angles_geometry)
        if self.ctrl.is_point_effectively_hidden(i) and self.ctrl.is_point_effectively_hidden(j) and self.ctrl.is_point_effectively_hidden(k):
            hidden = True
        self.setVisible(self.ctrl.show_dim_markers and not hidden)
        sel = (self.ctrl.selected_angle_id == self.aid) or self.isSelected()
        self.setBrush(HILITE if sel else DARK)


class TrajectoryItem(QGraphicsPathItem):
    def __init__(self, pid: int, ctrl: "SketchController"):
        super().__init__()
        self.pid = pid
        self.ctrl = ctrl
        self._path = QPainterPath()
        self.setZValue(-5)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        pen = QPen(QColor(0, 120, 215, 140), 1.6)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setAcceptHoverEvents(False)
        self.setVisible(False)

    def reset_path(self, x: float, y: float):
        self._path = QPainterPath(QPointF(float(x), float(y)))
        self.setPath(self._path)

    def add_point(self, x: float, y: float):
        if self._path.isEmpty():
            self._path.moveTo(float(x), float(y))
        else:
            self._path.lineTo(float(x), float(y))
        self.setPath(self._path)
