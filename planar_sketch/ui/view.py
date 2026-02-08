# -*- coding: utf-8 -*-
"""Graphics view interaction (pan/zoom/box select)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt, QPointF, QRect, QRectF
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QRubberBand, QGraphicsPixmapItem

from ..utils.qt_safe import safe_event
from .items import (
    PointItem,
    LinkItem,
    CoincideItem,
    PointLineItem,
    SplineItem,
    PointSplineItem,
    ForceArrowItem,
    TorqueArrowItem,
    AngleItem,
    GridItem,
)

if TYPE_CHECKING:
    from ..core.controller import SketchController


class SketchView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, ctrl: "SketchController"):
        super().__init__(scene)
        self.ctrl = ctrl
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        self._rmb_down = False
        self._rmb_pan = False
        self._rmb_start = QPointF()
        self._rmb_threshold_px = 6.0

        self._rb = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
        self._rb_origin: Optional[QPointF] = None
        self._rb_active = False
        self._rb_ctrl_toggle = False
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8
        self.scale(f, f)

    def _is_load_arrow_item(self, item) -> bool:
        cur = item
        while cur is not None:
            if isinstance(cur, (ForceArrowItem, TorqueArrowItem)):
                return True
            cur = cur.parentItem()
        return False

    def _item_at_pos(self, pos):
        for item in self.items(pos):
            if isinstance(item, QGraphicsPixmapItem) and item is self.ctrl._background_item:
                continue
            if isinstance(item, GridItem):
                continue
            if self._is_load_arrow_item(item):
                continue
            return item
        return None

    @safe_event
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.ctrl.mode == "CreatePoint":
            sp = self.mapToScene(e.position().toPoint())
            self.ctrl.on_scene_clicked_create_point(sp)
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton and self.ctrl.mode == "BackgroundImagePick":
            sp = self.mapToScene(e.position().toPoint())
            if self.ctrl.on_background_pick(sp):
                e.accept(); return
        if e.button() == Qt.MouseButton.RightButton:
            self.ctrl.commit_drag_if_any()
            self._rmb_down = True
            self._rmb_pan = False
            self._rmb_start = e.position().toPoint()
            e.accept(); return

        if e.button() == Qt.MouseButton.LeftButton:
            item = self._item_at_pos(e.position().toPoint())
            if item is None:
                self.ctrl.commit_drag_if_any()
                self._rb_active = True
                self._rb_origin = e.position().toPoint()
                self._rb_ctrl_toggle = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
                self._rb.setGeometry(QRect(self._rb_origin, self._rb_origin))
                self._rb.show()
                e.accept(); return

        super().mousePressEvent(e)

    @safe_event
    def mouseMoveEvent(self, e):
        self.ctrl.update_last_scene_pos(self.mapToScene(e.position().toPoint()))
        if self._rmb_down:
            if not self._rmb_pan:
                dx = e.position().toPoint().x() - self._rmb_start.x()
                dy = e.position().toPoint().y() - self._rmb_start.y()
                if (dx * dx + dy * dy) ** 0.5 >= self._rmb_threshold_px:
                    self._rmb_pan = True
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self._rmb_pan:
                dx = e.position().toPoint().x() - self._rmb_start.x()
                dy = e.position().toPoint().y() - self._rmb_start.y()
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - dx)
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - dy)
                self._rmb_start = e.position().toPoint()
                e.accept(); return

        if self._rb_active and self._rb_origin is not None:
            rect = QRect(self._rb_origin, e.position().toPoint()).normalized()
            self._rb.setGeometry(rect)
            e.accept(); return

        super().mouseMoveEvent(e)

    def _finish_box_select(self):
        if not self._rb_active:
            return
        self._rb.hide()
        rect = self._rb.geometry()
        self._rb_active = False
        self._rb_origin = None
        p1 = self.mapToScene(rect.topLeft())
        p2 = self.mapToScene(rect.bottomRight())
        srect = QRectF(min(p1.x(), p2.x()), min(p1.y(), p2.y()),
                       abs(p2.x() - p1.x()), abs(p2.y() - p1.y()))
        items = self.scene().items(srect, Qt.ItemSelectionMode.IntersectsItemShape)
        pids = []
        for it in items:
            if isinstance(it, PointItem):
                pids.append(it.pid)
        self.ctrl.apply_box_selection(pids, toggle=self._rb_ctrl_toggle)

    @safe_event
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton and self._rmb_down:
            self._rmb_down = False
            if self._rmb_pan:
                self._rmb_pan = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.ctrl.update_status()
                e.accept(); return
            item = self._item_at_pos(e.position().toPoint())
            sp = self.mapToScene(e.position().toPoint())
            if item is None:
                self.ctrl.show_empty_context_menu(e.globalPosition().toPoint(), sp)
            else:
                if isinstance(item, PointItem):
                    self.ctrl.show_point_context_menu(item.pid, e.globalPosition().toPoint())
                elif isinstance(item, LinkItem):
                    self.ctrl.show_link_context_menu(item.lid, e.globalPosition().toPoint())
                elif isinstance(item, CoincideItem):
                    self.ctrl.show_coincide_context_menu(item.cid, e.globalPosition().toPoint())
                elif isinstance(item, PointLineItem):
                    self.ctrl.show_point_line_context_menu(item.plid, e.globalPosition().toPoint())
                elif isinstance(item, SplineItem):
                    self.ctrl.show_spline_context_menu(item.sid, e.globalPosition().toPoint())
                elif isinstance(item, PointSplineItem):
                    self.ctrl.show_point_spline_context_menu(item.psid, e.globalPosition().toPoint())
            e.accept(); return

        if e.button() == Qt.MouseButton.LeftButton and self._rb_active:
            self._finish_box_select()
            e.accept(); return

        if e.button() == Qt.MouseButton.LeftButton:
            self.ctrl.commit_drag_if_any()

        super().mouseReleaseEvent(e)

    @safe_event
    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            item = self._item_at_pos(e.position().toPoint())
            if isinstance(item, PointItem):
                self.ctrl.focus_point_in_panel(item.pid)
                e.accept()
                return
            if isinstance(item, LinkItem):
                self.ctrl.focus_link_in_panel(item.lid)
                e.accept()
                return
            if isinstance(item, AngleItem):
                self.ctrl.focus_angle_in_panel(item.aid)
                e.accept()
                return
            if isinstance(item, SplineItem):
                self.ctrl.focus_spline_in_panel(item.sid)
                e.accept()
                return
            if isinstance(item, CoincideItem):
                self.ctrl.focus_coincide_in_panel(item.cid)
                e.accept()
                return
            if isinstance(item, PointLineItem):
                self.ctrl.focus_point_line_in_panel(item.plid)
                e.accept()
                return
            if isinstance(item, PointSplineItem):
                self.ctrl.focus_point_spline_in_panel(item.psid)
                e.accept()
                return
        super().mouseDoubleClickEvent(e)

    @safe_event
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.ctrl.win:
                self.ctrl.win.delete_selected()
            e.accept()
            return
        if e.key() == Qt.Key.Key_Escape:
            self.ctrl.cancel_model_action()
            e.accept()
            return
        super().keyPressEvent(e)

    def reset_view(self):
        self.resetTransform()
        self.centerOn(0, 0)

    def fit_all(self):
        rect = self.scene().itemsBoundingRect()
        if rect.isNull():
            return
        pad = 40
        r = QRectF(rect.left() - pad, rect.top() - pad, rect.width() + 2 * pad, rect.height() + 2 * pad)
        self.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)
