from __future__ import annotations

from typing import Callable, Optional, Sequence

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QDialog, QInputDialog, QMenu, QMessageBox

from .i18n import tr, get_ui_language, ui_language

Action = Optional[Callable[[], None]]

__all__ = [
    'build_table_context_menu',
    'exec_table_context_menu',
    'install_sketch_table_context_menus',
    'install_optimization_table_context_menus',
    'install_sim_table_context_menus',
    'bind_optimization_table_context_menus',
    'bind_sim_table_context_menus',
]


def _lang_from_owner(owner) -> str:
    ctrl = getattr(owner, 'ctrl', None)
    if ctrl is None and hasattr(owner, 'parent'):
        try:
            p = owner.parent()
        except Exception:
            p = None
        while p is not None and ctrl is None:
            ctrl = getattr(p, 'ctrl', None)
            try:
                p = p.parent()
            except Exception:
                p = None
    return get_ui_language(ctrl, fallback='zh')


# --- common menu builder ---
def build_table_context_menu(
    parent,
    *,
    on_add_row: Action = None,
    on_delete_row: Action = None,
    on_remove_row: Action = None,  # alias
    on_expr_builder: Action = None,
    on_new_param: Action = None,
    on_use_existing_param: Action = None,
    on_use_numeric: Action = None,
    extra_actions: Sequence[tuple[str, Callable[[], None], bool]] | None = None,
    lang: Optional[str] = None,
) -> QMenu:
    lang = _lang_from_owner(parent) if lang is None else ui_language(lang)
    menu = QMenu(parent)
    delete_cb = on_delete_row if callable(on_delete_row) else (on_remove_row if callable(on_remove_row) else None)

    row_actions = []
    if callable(on_add_row):
        row_actions.append((tr(lang, 'menu.add_row'), on_add_row, True))
    if callable(delete_cb):
        row_actions.append((tr(lang, 'menu.delete_row'), delete_cb, True))
    for text, cb, enabled in row_actions:
        a = menu.addAction(text)
        a.setEnabled(enabled)
        a.triggered.connect(cb)

    expr_actions = []
    if callable(on_expr_builder):
        expr_actions.append((tr(lang, 'analysis.expression_builder'), on_expr_builder, True))
    if callable(on_new_param):
        expr_actions.append((tr(lang, 'menu.new_parameter'), on_new_param, True))
    if callable(on_use_existing_param):
        expr_actions.append((tr(lang, 'menu.use_existing_parameter'), on_use_existing_param, True))
    if callable(on_use_numeric):
        expr_actions.append((tr(lang, 'menu.use_numeric'), on_use_numeric, True))
    if extra_actions:
        expr_actions.extend(list(extra_actions))

    if row_actions and expr_actions:
        menu.addSeparator()
    for text, cb, enabled in expr_actions:
        a = menu.addAction(text)
        a.setEnabled(bool(enabled))
        if callable(cb):
            a.triggered.connect(cb)
    return menu


def exec_table_context_menu(table, pos: QPoint, **kwargs) -> None:
    menu = build_table_context_menu(table, **kwargs)
    if menu.isEmpty():
        return
    menu.exec(table.viewport().mapToGlobal(pos))


def _remove_widgets(owner, *names: str) -> None:
    for name in names:
        w = getattr(owner, name, None)
        if w is None:
            continue
        try:
            if w.parentWidget() and w.parentWidget().layout():
                w.parentWidget().layout().removeWidget(w)
        except Exception:
            pass
        try:
            w.setParent(None)
        except Exception:
            pass
        try:
            w.deleteLater()
        except Exception:
            pass
        setattr(owner, name, None)


def _bind_table_menu(table, handler) -> None:
    if table is None:
        return
    try:
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    except Exception:
        return
    try:
        table.customContextMenuRequested.disconnect()
    except Exception:
        pass
    table.customContextMenuRequested.connect(handler)


# --- installers (single entry framework over existing classes) ---
def install_sketch_table_context_menus() -> None:
    from . import tabs as _tabs
    if getattr(_tabs, '_PS_SKETCH_CTX_INSTALLED', False):
        return
    _tabs._PS_SKETCH_CTX_INSTALLED = True

    def _wrap(cls, fn):
        if getattr(cls, '_ps_ctx_wrapped', False):
            return
        orig = cls.__init__
        def _init(self, *a, **k):
            orig(self, *a, **k)
            fn(self)
        cls.__init__ = _init
        cls._ps_ctx_wrapped = True

    def _expr_dispatch_points(self, idx, act):
        pid = int(self.table.item(idx.row(), 0).text())
        axis = 'x' if idx.column() == 1 else 'y'
        if act == 'expr': self._open_expression_builder(idx.row(), pid, axis)
        elif act == 'new': self._create_new_parameter(idx.row(), pid, axis)
        elif act == 'use': self._use_existing_parameter(idx.row(), pid, axis)
        elif act == 'num': self._clear_parameterization(idx.row(), pid, axis)

    def _expr_dispatch_links(self, idx, act):
        lid = int(self.table.item(idx.row(), 0).text())
        if act == 'expr': self._open_expression_builder(idx.row(), lid)
        elif act == 'new': self._create_new_parameter(idx.row(), lid)
        elif act == 'use': self._use_existing_parameter(idx.row(), lid)
        elif act == 'num': self._clear_parameterization(idx.row(), lid)

    def _expr_dispatch_angles(self, idx, act):
        aid = int(self.table.item(idx.row(), 0).text())
        if act == 'expr': self._open_expression_builder(idx.row(), aid)
        elif act == 'new': self._create_new_parameter(idx.row(), aid)
        elif act == 'use': self._use_existing_parameter(idx.row(), aid)
        elif act == 'num': self._clear_parameterization(idx.row(), aid)

    def _menu_with_exec(self, table, pos, *, can_add, on_add, on_del, expr_ok, expr_dispatch=None, extras=None):
        idx = table.indexAt(pos)
        lang = _lang_from_owner(self)
        selected = {'which': None}
        kwargs = {}
        if can_add:
            kwargs['on_add_row'] = lambda: on_add()
        kwargs['on_delete_row'] = (lambda: on_del()) if idx.isValid() else None
        if expr_ok:
            kwargs.update(
                on_expr_builder=lambda: selected.__setitem__('which','expr'),
                on_new_param=lambda: selected.__setitem__('which','new'),
                on_use_existing_param=lambda: selected.__setitem__('which','use'),
                on_use_numeric=lambda: selected.__setitem__('which','num'),
            )
        if extras:
            kwargs['extra_actions'] = extras(lang, idx)
        menu = build_table_context_menu(table, lang=lang, **kwargs)
        # disable delete when invalid row but keep action visible if wanted
        if not idx.isValid():
            for a in menu.actions():
                if a.text() == tr(lang,'menu.delete_row'):
                    a.setEnabled(False)
        act = menu.exec(table.viewport().mapToGlobal(pos))
        if act is None:
            return
        if selected['which'] and expr_dispatch and idx.isValid():
            expr_dispatch(idx, selected['which'])

    # ParametersTab
    def _cfg_params(self):
        _remove_widgets(self, 'btn_add', 'btn_del')
        def _menu(pos):
            idx = self.table.indexAt(pos)
            lang = _lang_from_owner(self)
            menu = build_table_context_menu(
                self.table,
                lang=lang,
                on_add_row=self._add_param,
                on_delete_row=self._delete_selected if idx.isValid() else None,
            )
            for a in menu.actions():
                if a.text() == tr(lang,'menu.delete_row') and not idx.isValid():
                    a.setEnabled(False)
            menu.exec(self.table.viewport().mapToGlobal(pos))
        _bind_table_menu(self.table, _menu)
    _wrap(_tabs.ParametersTab, _cfg_params)

    # PointsTab
    def _cfg_points(self):
        _remove_widgets(self, 'btn_add', 'btn_del')
        def _menu(pos):
            idx = self.table.indexAt(pos)
            expr_ok = bool(idx.isValid() and idx.column() in (1,2))
            return _menu_with_exec(self, self.table, pos, can_add=True,
                                   on_add=lambda: self.ctrl.cmd_add_point(0.0,0.0),
                                   on_del=self._delete_selected,
                                   expr_ok=expr_ok,
                                   expr_dispatch=lambda i,w: _expr_dispatch_points(self,i,w))
        _bind_table_menu(self.table, _menu)
    _wrap(_tabs.PointsTab, _cfg_points)

    # LinksTab
    def _cfg_links(self):
        _remove_widgets(self, 'btn_add', 'btn_del')
        def _menu(pos):
            idx = self.table.indexAt(pos)
            expr_ok = bool(idx.isValid() and idx.column() == 3)
            return _menu_with_exec(self, self.table, pos, can_add=True,
                                   on_add=self._add_link_from_points,
                                   on_del=self._delete_selected,
                                   expr_ok=expr_ok,
                                   expr_dispatch=lambda i,w: _expr_dispatch_links(self,i,w))
        _bind_table_menu(self.table, _menu)
    _wrap(_tabs.LinksTab, _cfg_links)

    # AnglesTab
    def _cfg_angles(self):
        _remove_widgets(self, 'btn_add', 'btn_del')
        def _menu(pos):
            idx = self.table.indexAt(pos)
            expr_ok = bool(idx.isValid() and idx.column() == 4)
            return _menu_with_exec(self, self.table, pos, can_add=False,
                                   on_add=None,
                                   on_del=self._delete_selected,
                                   expr_ok=expr_ok,
                                   expr_dispatch=lambda i,w: _expr_dispatch_angles(self,i,w))
        _bind_table_menu(self.table, _menu)
    _wrap(_tabs.AnglesTab, _cfg_angles)

    # SplinesTab
    def _cfg_splines(self):
        _remove_widgets(self, 'btn_add', 'btn_del')
        def _menu(pos):
            idx = self.table.indexAt(pos)
            lang = _lang_from_owner(self)
            menu = build_table_context_menu(
                self.table, lang=lang,
                on_add_row=self._add_spline_from_points,
                on_delete_row=self._delete_selected if idx.isValid() else None,
            )
            for a in menu.actions():
                if a.text() == tr(lang,'menu.delete_row') and not idx.isValid():
                    a.setEnabled(False)
            menu.exec(self.table.viewport().mapToGlobal(pos))
        _bind_table_menu(self.table, _menu)
    _wrap(_tabs.SplinesTab, _cfg_splines)

    # ConstraintsTab: toggle + delete (no add)
    def _cfg_constraints(self):
        _remove_widgets(self, 'btn_toggle', 'btn_delete')
        def _menu(pos):
            idx = self.table.indexAt(pos)
            lang = _lang_from_owner(self)
            extra = [
                (tr(lang, 'context.toggle'), self._toggle_selected, bool(idx.isValid())),
            ]
            menu = build_table_context_menu(
                self.table, lang=lang,
                on_delete_row=self._delete_selected if idx.isValid() else None,
                extra_actions=extra,
            )
            for a in menu.actions():
                if a.text() == tr(lang,'menu.delete_row') and not idx.isValid():
                    a.setEnabled(False)
            menu.exec(self.table.viewport().mapToGlobal(pos))
        _bind_table_menu(self.table, _menu)
    _wrap(_tabs.ConstraintsTab, _cfg_constraints)


def bind_optimization_table_context_menus(owner) -> None:
    if owner is None:
        return
    if getattr(owner, '_ps_opt_ctx_bound', False):
        return
    owner._ps_opt_ctx_bound = True

    _remove_widgets(owner, 'btn_add_var', 'btn_del_var', 'btn_add_obj', 'btn_del_obj', 'btn_add_con', 'btn_del_con')

    def _bind(tbl, addf, delf, allow_add=True):
        if tbl is None:
            return
        def handler(pos):
            idx = tbl.indexAt(pos)
            lang = _lang_from_owner(owner)
            menu = build_table_context_menu(
                tbl, lang=lang,
                on_add_row=(addf if allow_add else None),
                on_delete_row=(delf if idx.isValid() else None),
            )
            for a in menu.actions():
                if a.text() == tr(lang,'menu.delete_row') and not idx.isValid():
                    a.setEnabled(False)
            menu.exec(tbl.viewport().mapToGlobal(pos))
        _bind_table_menu(tbl, handler)

    _bind(getattr(owner, 'table_vars', None), getattr(owner,'add_variable_row',None), getattr(owner,'remove_variable_row',None), True)
    # Keep OptimizationTab native objective/constraint context menus so expression columns
    # can use the local Expression Builder entry without inheriting sim/friction-style
    # parameterization actions from the generic wrapper.
    try:
        tbl_obj = getattr(owner, 'table_obj', None)
        if tbl_obj is not None and hasattr(owner, '_open_objective_context_menu'):
            _bind_table_menu(tbl_obj, lambda pos: owner._open_objective_context_menu(pos))
        tbl_con = getattr(owner, 'table_con', None)
        if tbl_con is not None and hasattr(owner, '_open_constraint_context_menu'):
            _bind_table_menu(tbl_con, lambda pos: owner._open_constraint_context_menu(pos))
    except Exception:
        pass


def install_optimization_table_context_menus() -> None:
    """Deprecated: explicit registration is now used by OptimizationTab.__init__."""
    return

def bind_sim_table_context_menus(owner) -> None:
    if owner is None:
        return
    if getattr(owner, "_ps_sim_ctx_bound", False):
        return
    owner._ps_sim_ctx_bound = True
    _remove_widgets(owner, 'btn_add_load_row','btn_delete_load_row','btn_add_friction_row','btn_delete_friction_row','btn_add_meas_row','btn_delete_meas_row')

    from .expression_builder import ExpressionBuilderDialog
    from .expression_builder import PARAMETER_FUNCTIONS

    def _open_expr_dialog(initial: str):
        d = ExpressionBuilderDialog(owner, initial=initial, tokens=list(owner.ctrl.parameters.params.keys()), functions=PARAMETER_FUNCTIONS)
        if d.exec() == QDialog.DialogCode.Accepted:
            return d.expression().strip()
        return None

    def _new_param_from_value(val: float):
        lang = _lang_from_owner(owner)
        name, ok = QInputDialog.getText(owner, tr(lang, 'menu.new_parameter_title'), tr(lang, 'menu.parameter_name'))
        if ok and str(name).strip():
            owner.ctrl.cmd_set_param(str(name).strip(), float(val))
            return str(name).strip()
        return None

    def _pick_existing_param():
        lang = _lang_from_owner(owner)
        params = sorted(owner.ctrl.parameters.params.keys())
        if not params:
            QMessageBox.information(owner, tr(lang, 'menu.parameters'), tr(lang, 'menu.no_parameters'))
            return None
        name, ok = QInputDialog.getItem(owner, tr(lang, 'menu.use_parameter_title'), tr(lang, 'menu.parameter'), params, 0, False)
        return str(name) if (ok and name) else None

    def _load_menu(pos):
        tbl = owner.table_loads; idx = tbl.indexAt(pos); lang = _lang_from_owner(owner)
        expr_ok = False
        if idx.isValid():
            item = tbl.item(idx.row(), idx.column())
            expr_ok = bool(item is not None and (item.flags() & Qt.ItemFlag.ItemIsEditable))
        chosen = {'v': None}
        menu = build_table_context_menu(
            tbl, lang=lang,
            on_delete_row=owner._remove_selected_load if idx.isValid() else None,
            on_expr_builder=(lambda: chosen.__setitem__('v','expr')) if expr_ok else None,
            on_new_param=(lambda: chosen.__setitem__('v','new')) if expr_ok else None,
            on_use_existing_param=(lambda: chosen.__setitem__('v','use')) if expr_ok else None,
            on_use_numeric=(lambda: chosen.__setitem__('v','num')) if expr_ok else None,
        )
        for a in menu.actions():
            if a.text()==tr(lang,'menu.delete_row') and not idx.isValid(): a.setEnabled(False)
        act = menu.exec(tbl.viewport().mapToGlobal(pos))
        if act is None or chosen['v'] is None or not idx.isValid():
            return
        row,col=idx.row(),idx.column()
        if row<0 or row>=len(owner.ctrl.loads): return
        ld=owner.ctrl.loads[row]; ltype=str(ld.get('type','force')).lower(); fx,fy,mz=owner.ctrl._resolve_load_components(ld)
        mapping={2:('fx','fx_expr',float(fx)),3:('fy','fy_expr',float(fy)),4:('mz','mz_expr',float(mz)),5:('k','k_expr',float(ld.get('k',0.0) or 0.0)),6:('load','load_expr',float(ld.get('load',0.0) or 0.0))}
        if col not in mapping: return
        if ltype in ('force','torque') and col not in (2,3,4): return
        if ltype not in ('force','torque') and col not in (5,6): return
        num_key,expr_key,num_val = mapping[col]
        cur_expr = str(ld.get(expr_key,'') or '').strip()
        initial = cur_expr or owner.ctrl.format_number(num_val)
        def apply_expr(txt:str):
            txt=(txt or '').strip()
            try:
                v=float(txt)
            except Exception:
                if not txt: return
                ld[expr_key]=txt; owner.ctrl.recompute_from_parameters()
            else:
                ld[num_key]=float(v); ld[expr_key]=''
            owner.refresh_labels()
        choice=chosen['v']
        if choice=='expr':
            txt=_open_expr_dialog(initial)
            if txt is not None: apply_expr(txt)
        elif choice=='new':
            name=_new_param_from_value(num_val)
            if name: apply_expr(name)
        elif choice=='use':
            name=_pick_existing_param()
            if name: apply_expr(name)
        elif choice=='num':
            apply_expr(owner.ctrl.format_number(num_val))
    _bind_table_menu(owner.table_loads, _load_menu)

    def _fric_menu(pos):
        tbl = owner.table_friction; idx = tbl.indexAt(pos); lang = _lang_from_owner(owner)
        expr_ok = bool(idx.isValid() and idx.column() in (1,2) and tbl.item(idx.row(), idx.column()) is not None and (tbl.item(idx.row(), idx.column()).flags() & Qt.ItemFlag.ItemIsEditable))
        chosen={'v':None}
        menu = build_table_context_menu(
            tbl, lang=lang,
            on_delete_row=owner._remove_selected_friction if idx.isValid() else None,
            on_expr_builder=(lambda: chosen.__setitem__('v','expr')) if expr_ok else None,
            on_new_param=(lambda: chosen.__setitem__('v','new')) if expr_ok else None,
            on_use_existing_param=(lambda: chosen.__setitem__('v','use')) if expr_ok else None,
            on_use_numeric=(lambda: chosen.__setitem__('v','num')) if expr_ok else None,
        )
        for a in menu.actions():
            if a.text()==tr(lang,'menu.delete_row') and not idx.isValid(): a.setEnabled(False)
        act = menu.exec(tbl.viewport().mapToGlobal(pos))
        if act is None or chosen['v'] is None or not idx.isValid(): return
        row,col=idx.row(),idx.column()
        if row<0 or row>=len(owner.ctrl.friction_joints): return
        fj=owner.ctrl.friction_joints[row]
        key_map={1:('mu','mu_expr',float(fj.get('mu',0.0) or 0.0)),2:('diameter','diameter_expr',float(fj.get('diameter',0.0) or 0.0))}
        if col not in key_map: return
        num_key,expr_key,num_val=key_map[col]
        cur_expr=str(fj.get(expr_key,'') or '').strip(); initial=cur_expr or owner.ctrl.format_number(num_val)
        def apply_expr(txt:str):
            txt=(txt or '').strip()
            try: v=float(txt)
            except Exception:
                if not txt: return
                fj[expr_key]=txt; owner.ctrl.recompute_from_parameters()
            else:
                fj[num_key]=float(v); fj[expr_key]=''
            owner.refresh_labels()
        c=chosen['v']
        if c=='expr':
            txt=_open_expr_dialog(initial)
            if txt is not None: apply_expr(txt)
        elif c=='new':
            name=_new_param_from_value(num_val)
            if name: apply_expr(name)
        elif c=='use':
            name=_pick_existing_param()
            if name: apply_expr(name)
        elif c=='num':
            apply_expr(owner.ctrl.format_number(num_val))
    _bind_table_menu(owner.table_friction, _fric_menu)

    def _meas_menu(pos):
        tbl=owner.table_meas; idx=tbl.indexAt(pos); lang=_lang_from_owner(owner)
        menu = build_table_context_menu(
            tbl, lang=lang,
            on_delete_row=owner._delete_selected_measure if idx.isValid() else None,
            on_expr_builder=None,
            on_new_param=None,
            on_use_existing_param=None,
            on_use_numeric=None,
        )
        for a in menu.actions():
            if a.text()==tr(lang,'menu.delete_row') and not idx.isValid():
                a.setEnabled(False)
        menu.exec(tbl.viewport().mapToGlobal(pos))
    _bind_table_menu(owner.table_meas, _meas_menu)


def install_sim_table_context_menus() -> None:
    """Deprecated: explicit registration is now used by SimulationPanel.__init__."""
    return
