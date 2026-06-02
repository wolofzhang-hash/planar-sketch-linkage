from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import os
from typing import List, Optional, Dict, Any

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QFont, QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QWidget,
    QRadioButton,
    QButtonGroup,
    QDialogButtonBox,
    QToolButton,
    QGridLayout,
)

from ..intel import Requirement, recommend, insert_template, save_current_model_as_template, list_user_templates, delete_user_template, _user_template_preview_path
from ..intel.synthesis_registry import can_continue_in_synthesis
from ..intel.recommender import _load_catalog
from .i18n import tr


# preview pixmap cache for template library thumbnails/previews
_PREVIEW_PIXMAP_CACHE: Dict[Any, QPixmap] = {}
# source signature cache for invalidating stale preview pixmaps when image files change
_PREVIEW_SOURCE_SIG_CACHE: Dict[str, Any] = {}


def _supports_synthesis(template_id: str) -> bool:
    """Compatibility wrapper.

    Keep a local helper for older call sites in this file, but use
    ``intel.synthesis_registry`` as the single source of truth.
    """
    return can_continue_in_synthesis(template_id)


def _collect_synthesis_profile(ctrl) -> Dict[str, Any]:
    """Collect current Intelligent Synthesis UI settings for persistence.

    This is used only when the user explicitly chooses to save synthesis settings
    into a template.
    """
    win = getattr(ctrl, 'win', None)
    sim_panel = getattr(win, 'sim_panel', None) if win else None
    tab = getattr(sim_panel, 'synthesis_tab', None) if sim_panel else None
    if tab is None:
        return {}
    # helper
    def _f(s, d):
        try:
            return float(str(s).strip())
        except Exception:
            return float(d)
    # mapping points
    pts = []
    try:
        n = int(tab.table_map.rowCount())
        for r in range(n):
            a = tab.table_map.item(r, 0)
            b = tab.table_map.item(r, 1)
            x = _f(a.text() if a else '', 0.0)
            y = _f(b.text() if b else '', 0.0)
            pts.append([float(x), float(y)])
    except Exception:
        pts = []
    return {
        'template_id': str(getattr(tab.combo_template, 'currentData', lambda: '')() or getattr(tab.combo_template, 'currentText', lambda: '')()).strip(),
        'axis_ad': _f(getattr(tab.ed_axis, 'text', lambda: '400')(), 400.0),
        'curve_target_points': pts,
        'tolerance_deg': _f(getattr(tab.ed_tol, 'text', lambda: '2.0')(), 2.0),
        'lower_factor': _f(getattr(tab.ed_lower, 'text', lambda: '0.7')(), 0.7),
        'upper_factor': _f(getattr(tab.ed_upper, 'text', lambda: '1.3')(), 1.3),
        'evals': int(_f(getattr(tab.ed_evals, 'text', lambda: '400')(), 400)),
        'steps': int(_f(getattr(tab.ed_steps, 'text', lambda: '61')(), 61)),
    }


def _family_label(fam: str) -> str:
    m = {"cam": "Cam", "4bar": "4-bar", "6bar": "6-bar", "slider_rail": "Slider/Rail", "any": "Any"}
    return m.get((fam or '').lower(), fam or '')


def _template_preview_pixmap(item: Dict[str, Any], size: QSize = QSize(240, 150)) -> QPixmap:
    w, h = size.width(), size.height()
    pm = QPixmap(w, h)
    pm.fill(QColor('#ffffff'))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # background border
    p.setPen(QPen(QColor('#d0d7de'), 1))
    p.drawRoundedRect(1, 1, w-2, h-2, 8, 8)
    fam = str(item.get('family','') or '').lower()
    name = str(item.get('name','') or '')
    # common styles
    blue = QColor('#2563eb'); green = QColor('#16a34a'); gray = QColor('#6b7280'); orange = QColor('#ea580c')
    p.setPen(QPen(QColor('#374151'), 1))
    # draw family-specific mini schematic
    if fam == 'cam':
        cx, cy, r = int(w*0.33), int(h*0.6), 34
        p.setPen(QPen(blue, 2))
        pts = []
        import math
        for k in range(16):
            a = 2*math.pi*k/16.0
            rr = r*(1.0 + (0.15 if k in (2,3,4) else 0.0))
            pts.append((cx + rr*math.cos(a), cy + rr*math.sin(a)))
        for i in range(len(pts)):
            x1,y1=pts[i]; x2,y2=pts[(i+1)%len(pts)]
            p.drawLine(int(x1),int(y1),int(x2),int(y2))
        p.setBrush(QBrush(green)); p.setPen(QPen(green,1)); p.drawEllipse(cx-4, cy-4, 8, 8)
        # follower
        if 'oscillat' in name.lower():
            ox, oy = int(w*0.68), int(h*0.72)
            tx, ty = int(w*0.56), int(h*0.45)
            p.setPen(QPen(QColor('#111827'), 3)); p.drawLine(ox, oy, tx, ty)
            p.setBrush(QBrush(QColor('#111827'))); p.drawEllipse(ox-4, oy-4, 8, 8)
            p.setBrush(QBrush(orange)); p.setPen(QPen(orange,2)); p.drawEllipse(tx-5, ty-5, 10, 10)
        else:
            x = int(w*0.72); y1 = int(h*0.25); y2 = int(h*0.82)
            p.setPen(QPen(gray, 2, Qt.PenStyle.DashLine)); p.drawLine(x, y1, x, y2)
            p.setPen(QPen(QColor('#111827'), 3)); p.drawRect(x-14, int(h*0.42), 28, 20)
            p.setBrush(QBrush(orange)); p.setPen(QPen(orange,2)); p.drawEllipse(x-5, int(h*0.55)-5, 10, 10)
    elif fam == '4bar':
        pts = [(50,95),(95,55),(170,70),(200,110)]
        p.setPen(QPen(QColor('#111827'), 3))
        for a,b in ((0,1),(1,2),(2,3),(3,0)):
            x1,y1=pts[a]; x2,y2=pts[b]; p.drawLine(x1,y1,x2,y2)
        p.setBrush(QBrush(green)); p.setPen(QPen(green,1))
        for x,y in (pts[0],pts[3]): p.drawEllipse(x-5,y-5,10,10)
    elif fam == '6bar':
        pts=[(36,100),(78,66),(126,78),(162,52),(200,82),(175,118)]
        p.setPen(QPen(QColor('#111827'), 3))
        for a,b in ((0,1),(1,2),(2,3),(3,4),(4,5),(5,0),(2,5)):
            x1,y1=pts[a]; x2,y2=pts[b]; p.drawLine(x1,y1,x2,y2)
        p.setBrush(QBrush(green)); p.setPen(QPen(green,1)); p.drawEllipse(pts[0][0]-5,pts[0][1]-5,10,10)
    else:  # slider rail
        p.setPen(QPen(gray, 2, Qt.PenStyle.DashLine)); p.drawLine(32,100,212,100)
        p.setPen(QPen(QColor('#111827'), 3)); p.drawRect(150,86,28,28); p.drawLine(70,55,164,100)
        p.setBrush(QBrush(green)); p.setPen(QPen(green,1)); p.drawEllipse(66,51,10,10); p.drawEllipse(145,95,10,10)
    # footer text
    p.setPen(QPen(QColor('#374151'), 1))
    f=QFont(); f.setPointSize(8)
    p.setFont(f)
    p.drawText(8, 18, f"{_family_label(fam)}")
    p.end()
    return pm


def _preview_pixmap_for_item(item: Dict[str, Any], size: QSize) -> QPixmap:
    fam = str(item.get("family", "") or "")
    key = str(item.get("template_id") or item.get("template") or item.get("id") or "")
    w = int(size.width())
    h = int(size.height())
    pth = str(item.get("preview_image_path", "") or "").strip()
    cache_key = None
    if pth:
        sig = None
        try:
            st = os.stat(pth)
            sig = (int(st.st_mtime_ns), int(st.st_size))
        except Exception:
            sig = None
        if sig is not None:
            src_key = f"file:{pth}"
            old_sig = _PREVIEW_SOURCE_SIG_CACHE.get(src_key)
            if old_sig != sig:
                # invalidate stale scaled pixmaps for this source
                stale = [k for k in _PREVIEW_PIXMAP_CACHE.keys() if isinstance(k, tuple) and len(k) >= 4 and k[0] == 'file' and k[1] == pth]
                for k2 in stale:
                    _PREVIEW_PIXMAP_CACHE.pop(k2, None)
                _PREVIEW_SOURCE_SIG_CACHE[src_key] = sig
            cache_key = ('file', pth, sig, w, h)
            pm = _PREVIEW_PIXMAP_CACHE.get(cache_key)
            if pm is not None and not pm.isNull():
                return pm
            base = QPixmap(pth)
            if not base.isNull():
                pm = base.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                if len(_PREVIEW_PIXMAP_CACHE) > 512:
                    _PREVIEW_PIXMAP_CACHE.clear()
                _PREVIEW_PIXMAP_CACHE[cache_key] = pm
                return pm
    cache_key = ('drawn', fam, key, w, h)
    pm = _PREVIEW_PIXMAP_CACHE.get(cache_key)
    if pm is not None and not pm.isNull():
        return pm
    pm = _template_preview_pixmap(item, size)
    if len(_PREVIEW_PIXMAP_CACHE) > 512:
        _PREVIEW_PIXMAP_CACHE.clear()
    _PREVIEW_PIXMAP_CACHE[cache_key] = pm
    return pm


def _capture_view_preview(ctrl, out_path: str) -> bool:
    try:
        win = getattr(ctrl, 'win', None)
        view = getattr(win, 'view', None) if win else None
        if view is None:
            return False
        pix = view.grab()
        if pix.isNull():
            return False
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        return bool(pix.save(out_path, 'PNG'))
    except Exception:
        return False


class SaveTemplateDialog(QDialog):
    def __init__(self, ctrl, rec=None, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.rec = rec
        lang = getattr(self.ctrl, 'ui_language', 'en')
        self.setWindowTitle(tr(lang, 'intel.save.dialog_title', 'Save Current Model as Template'))
        self.setMinimumWidth(620)

        self.rb_override = QRadioButton(tr(lang, 'intel.save.mode.override', 'Override existing template'), self)
        self.rb_new = QRadioButton(tr(lang, 'intel.save.mode.new', 'Create new template'), self)
        self.rb_override.setChecked(True)
        grp = QButtonGroup(self); grp.addButton(self.rb_override); grp.addButton(self.rb_new)

        self.cmb_target = QComboBox(self)
        # builtin from catalog
        cat = _load_catalog() or {}
        for c in list(cat.get('concepts', []) or []):
            tid = str(c.get('template') or '').strip()
            if tid:
                self.cmb_target.addItem(f"{c.get('name','')}  [{tid}]", {'template_id': tid, 'name': c.get('name',''), 'family': c.get('family',''), 'concept_id': c.get('id','')})
        # user entries
        for u in list_user_templates():
            tid = str(u.get('template_id') or '').strip()
            if tid and self.cmb_target.findData({'template_id': tid}) < 0:
                self.cmb_target.addItem(f"{tr(lang, 'intel.save.user_prefix', '(User)')} {u.get('name',tid)}  [{tid}]", u)

        self.edit_new_id = QLineEdit(self)
        self.edit_name = QLineEdit(self)
        self.cmb_family = QComboBox(self)
        for t,k in [('Cam','cam'),('4-bar','4bar'),('6-bar','6bar'),('Slider/Rail','slider_rail')]:
            self.cmb_family.addItem(t,k)
        self.edit_tags = QLineEdit(self)
        self.edit_desc = QPlainTextEdit(self); self.edit_desc.setFixedHeight(80)
        self.chk_save_preview = QCheckBox(tr(lang, 'intel.save.preview_checkbox', 'Save current canvas screenshot as template preview (PNG)'), self); self.chk_save_preview.setChecked(True)

        # Optional: persist Intelligent Synthesis profile into the template.
        # Disabled by default; enabled only when Optimization has a feasible result.
        self.chk_save_synthesis = QCheckBox(tr(lang, 'intel.save.synth_checkbox', 'Save Intelligent Synthesis profile into this template'), self)
        self.chk_save_synthesis.setChecked(False)
        self.chk_save_synthesis.setEnabled(False)
        self.chk_save_synthesis.setStyleSheet('QCheckBox:disabled{color:#8b949e;}')
        try:
            win = getattr(self.ctrl, 'win', None)
            sim_panel = getattr(win, 'sim_panel', None) if win else None
            opt_tab = getattr(sim_panel, 'optimization_tab', None) if sim_panel else None
            ok = bool(getattr(opt_tab, '_last_run_feasible', False))
            self.chk_save_synthesis.setEnabled(ok)
        except Exception:
            pass

        # defaults from rec
        if rec is not None:
            tid = str(getattr(rec, 'template', '') or '').strip()
            cname = str(getattr(rec, 'concept_name', '') or '')
            cid = str(getattr(rec, 'concept_id', '') or '')
            self.edit_name.setText(cname)
            if tid:
                self.edit_new_id.setText(f"{tid}_user_v1")
                for i in range(self.cmb_target.count()):
                    d = self.cmb_target.itemData(i) or {}
                    if isinstance(d, dict) and str(d.get('template_id','')).strip().lower() == tid.lower():
                        self.cmb_target.setCurrentIndex(i); break
            if cid.startswith('cam'): self.cmb_family.setCurrentIndex(0)
            elif cid.startswith('6bar'): self.cmb_family.setCurrentIndex(2)
            elif cid.startswith('slider'): self.cmb_family.setCurrentIndex(3)
            else: self.cmb_family.setCurrentIndex(1)

        form = QFormLayout()
        form.addRow(self.rb_override)
        form.addRow(tr(lang, 'intel.save.target_template', 'Target template'), self.cmb_target)
        form.addRow(self.rb_new)
        form.addRow(tr(lang, 'intel.save.new_template_id', 'New template ID'), self.edit_new_id)
        form.addRow(tr(lang, 'intel.save.display_name', 'Display name'), self.edit_name)
        form.addRow(tr(lang, 'intel.save.family', 'Mechanism family'), self.cmb_family)
        form.addRow(tr(lang, 'intel.save.tags', 'Tags (comma-separated)'), self.edit_tags)
        form.addRow(tr(lang, 'intel.save.description', 'Description'), self.edit_desc)
        form.addRow(self.chk_save_preview)
        form.addRow(self.chk_save_synthesis)

        self.btn_ok = QPushButton(tr(lang, 'intel.save.ok', 'Save'), self)
        self.btn_cancel = QPushButton(tr(lang, 'common.cancel', 'Cancel'), self)
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(self.btn_ok); row.addWidget(self.btn_cancel)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addLayout(row)

        self.rb_override.toggled.connect(self._sync_mode)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self._sync_mode()

    def _alloc_next_template_id(self) -> str:
        fam = str(self.cmb_family.currentData() or '4bar')
        prefix_map = {'cam': 'cam_user', '4bar': '4bar_user', '6bar': '6bar_user', 'slider_rail': 'slider_user'}
        prefix = prefix_map.get(fam, 'template_user')
        nums = []
        # scan builtin + user template ids
        cat = _load_catalog() or {}
        ids = []
        for c in list(cat.get('concepts', []) or []):
            tid = str(c.get('template') or '').strip().lower()
            if tid:
                ids.append(tid)
        for u in list_user_templates():
            tid = str(u.get('template_id') or '').strip().lower()
            if tid:
                ids.append(tid)
        import re
        pat = re.compile(rf'^{re.escape(prefix)}_(\d+)$')
        for tid in ids:
            m = pat.match(tid)
            if m:
                try: nums.append(int(m.group(1)))
                except Exception: pass
        n = (max(nums) + 1) if nums else 1
        return f"{prefix}_{n:03d}"

    def _sync_mode(self):
        over = self.rb_override.isChecked()
        self.cmb_target.setEnabled(over)
        for w in (self.edit_new_id, self.edit_name, self.cmb_family, self.edit_tags, self.edit_desc):
            w.setEnabled(not over)
        if (not over) and not str(self.edit_new_id.text() or '').strip():
            self.edit_new_id.setText(self._alloc_next_template_id())

    def values(self) -> Dict[str, Any]:
        mode = 'override' if self.rb_override.isChecked() else 'new'
        data = self.cmb_target.currentData() or {}
        template_id = str((data.get('template_id') if isinstance(data, dict) else '') or '').strip() if mode == 'override' else str(self.edit_new_id.text() or '').strip()
        if mode == 'new' and not template_id:
            template_id = self._alloc_next_template_id()
            self.edit_new_id.setText(template_id)
        if not template_id:
            raise ValueError(tr(getattr(self.ctrl, 'ui_language', 'en'), 'intel.save.template_id_required', 'Template ID cannot be empty'))
        name = str((data.get('name') if isinstance(data, dict) else '') or template_id) if mode == 'override' else str(self.edit_name.text() or template_id)
        family = str((data.get('family') if isinstance(data, dict) else '') or '') if mode == 'override' else str(self.cmb_family.currentData() or '')
        concept_id = str((data.get('concept_id') if isinstance(data, dict) else '') or '')
        tags = [] if mode == 'override' else [t.strip() for t in str(self.edit_tags.text() or '').split(',') if t.strip()]
        desc = '' if mode == 'override' else str(self.edit_desc.toPlainText() or '').strip()
        return {
            'mode': mode, 'template_id': template_id, 'name': name, 'family': family,
            'concept_id': concept_id, 'tags': tags, 'description': desc, 'save_preview': bool(self.chk_save_preview.isChecked())
            , 'save_synthesis': bool(self.chk_save_synthesis.isEnabled() and self.chk_save_synthesis.isChecked())
        }


class InsertTemplateOptionsDialog(QDialog):
    def __init__(self, req: Requirement, rec, parent=None):
        super().__init__(parent)
        lang = getattr(parent, 'ctrl', None).ui_language if getattr(parent, 'ctrl', None) is not None else 'en'
        self.setWindowTitle(tr(lang, 'intel.insert_options.title', 'Insert Template Options'))
        self.setMinimumWidth(520)
        self.chk_smart = QCheckBox(tr(lang, 'intel.insert_options.smart_check', 'Run intelligent synthesis (structural completion) check after insertion'), self)
        self.chk_smart.setChecked(True)
        self.chk_auto_setup = QCheckBox(tr(lang, 'intel.insert_options.auto_setup', 'Auto-configure driver/output and single case (when supported by template)'), self)
        self.chk_auto_setup.setChecked(True)
        self.chk_solve = QCheckBox(tr(lang, 'intel.insert_options.solve_now', 'Solve immediately after insertion (recommended off for further editing)'), self)
        self.chk_solve.setChecked(False)
        self.lbl = QLabel(self)
        self.lbl.setWordWrap(True)
        self.lbl.setText(tr(lang, 'intel.insert_options.summary', 'Template: {tpl}\nTask={task}, Open angle={angle:.1f}°, Preferences: fewer={fewer}, compact={compact}').format(tpl=getattr(rec,'template',''), task=req.task, angle=req.open_angle_deg, fewer=req.prefer_fewer_links, compact=req.prefer_compact))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.lbl)
        lay.addWidget(self.chk_smart)
        lay.addWidget(self.chk_auto_setup)
        lay.addWidget(self.chk_solve)
        lay.addWidget(bb)
    def values(self):
        return {
            'smart_synthesis': bool(self.chk_smart.isChecked()),
            'auto_setup': bool(self.chk_auto_setup.isChecked()),
            'solve_after_insert': bool(self.chk_solve.isChecked()),
        }


def _intel_pref_path() -> Path:
    d = Path.home()/'.planar_sketch'/ 'intel_templates'
    d.mkdir(parents=True, exist_ok=True)
    return d / 'library_prefs.json'


def _load_intel_prefs() -> Dict[str, Any]:
    p = _intel_pref_path()
    if not p.exists():
        return {'favorites': [], 'recent_used': []}
    try:
        d=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(d, dict):
            raise ValueError
        d.setdefault('favorites', [])
        d.setdefault('recent_used', [])
        return d
    except Exception:
        return {'favorites': [], 'recent_used': []}


def _save_intel_prefs(d: Dict[str, Any]) -> None:
    try:
        _intel_pref_path().write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass



class TemplateLibraryDialog(QDialog):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self._lang = getattr(self.ctrl, 'ui_language', 'en')
        _zh = str(self._lang).lower().startswith('zh')
        self.setWindowTitle(tr(self._lang, 'intel.gallery.title', 'Template Library'))
        self.setMinimumSize(1120, 700)
        cat = _load_catalog() or {}
        self._concepts = list(cat.get('concepts', []))
        self._filtered = []
        self._prefs = _load_intel_prefs()
        self._icon_load_timer = QTimer(self)
        self._icon_load_timer.setSingleShot(True)
        self._icon_load_timer.timeout.connect(self._load_icons_batch)
        self._icon_queue = []
        self._icon_batch_size = 24

        self.edit_search = QLineEdit(self); self.edit_search.setPlaceholderText(tr(self._lang, 'intel.gallery.search_ph', 'Search name / tag / ID ...'))
        self.combo_family_filter = QComboBox(self); self.combo_family_filter.addItem(tr(self._lang, 'common.all', 'All'), 'any')
        for txt, key in [('Cam', 'cam'), ('4-bar', '4bar'), ('6-bar', '6bar'), ('Slider/Rail', 'slider_rail')]:
            self.combo_family_filter.addItem(txt, key)
        self.combo_has_template = QComboBox(self)
        self.combo_has_template.addItems([tr(self._lang, 'common.all', 'All'), tr(self._lang, 'intel.gallery.filter.insertable', 'Insertable template'), tr(self._lang, 'intel.gallery.filter.concept_only', 'Concept only (no template)')])
        self.combo_sort = QComboBox(self)
        self.combo_sort.addItem(tr(self._lang, 'intel.gallery.sort.recent', 'Recent'), 'recent')
        self.combo_sort.addItem(tr(self._lang, 'intel.gallery.sort.favorite', 'Favorites first'), 'favorite')
        self.combo_sort.addItem(tr(self._lang, 'intel.gallery.sort.name', 'Name'), 'name')
        self.combo_sort.addItem(tr(self._lang, 'intel.gallery.sort.index', 'Index'), 'seq')
        self.chk_favorites_only = QCheckBox(tr(self._lang, 'intel.gallery.favorites_only', 'Favorites only'), self)
        self.edit_tag = QLineEdit(self); self.edit_tag.setPlaceholderText(tr(self._lang, 'intel.gallery.tag_ph', 'Filter by tag (optional)'))

        self.list_templates = QListWidget(self)
        self.list_templates.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_templates.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_templates.setMovement(QListWidget.Movement.Static)
        self.list_templates.setSpacing(10)
        self.list_templates.setIconSize(QSize(220, 132))
        self.list_templates.setGridSize(QSize(260, 210))
        self.list_templates.setWordWrap(True)

        self.lbl_preview = QLabel(self); self.lbl_preview.setMinimumSize(420, 260)
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet('QLabel{background:#fff;border:1px solid #d0d7de;border-radius:8px;}')
        self.txt_detail = QPlainTextEdit(self); self.txt_detail.setReadOnly(True)
        self.btn_fav = QPushButton(tr(self._lang, 'intel.gallery.favorite_toggle', 'Favorite / Unfavorite'), self)
        self.btn_delete = QPushButton(tr(self._lang, 'intel.gallery.delete', 'Delete template'), self)
        self.btn_continue_synth = QPushButton(tr(self._lang, 'intel.continue_synth', 'Continue in Intelligent Synthesis (Generate & Configure)'), self)
        self.btn_continue_synth.setEnabled(False)
        # Make disabled state visually obvious even if global styles keep text dark.
        self.btn_continue_synth.setStyleSheet('QPushButton:disabled{color:#8b949e;}')
        # Highlight only when supported.
        self.btn_continue_synth.setProperty("primary", False)
        self.btn_insert = QPushButton(tr(self._lang, 'intel.gallery.insert_selected', 'Insert selected template'), self)
        self.btn_close = QPushButton(tr(self._lang, 'intel.close', 'Close'), self)

        top = QGridLayout()
        top.addWidget(QLabel(tr(self._lang, 'intel.gallery.family', 'Family')),0,0); top.addWidget(self.combo_family_filter,0,1)
        top.addWidget(QLabel(tr(self._lang, 'intel.gallery.type', 'Type')),0,2); top.addWidget(self.combo_has_template,0,3)
        top.addWidget(QLabel(tr(self._lang, 'intel.gallery.sort', 'Sort')),0,4); top.addWidget(self.combo_sort,0,5)
        top.addWidget(self.chk_favorites_only,0,6)
        top.addWidget(self.edit_search,1,0,1,4)
        top.addWidget(self.edit_tag,1,4,1,3)

        left = QVBoxLayout(); left.addLayout(top); left.addWidget(self.list_templates, 1)
        leftw = QWidget(self); leftw.setLayout(left)
        right = QVBoxLayout(); right.addWidget(QLabel(tr(self._lang, 'intel.gallery.preview', 'Preview'))); right.addWidget(self.lbl_preview)
        fav_row = QHBoxLayout(); fav_row.addWidget(self.btn_fav); fav_row.addWidget(self.btn_delete); fav_row.addStretch(1); right.addLayout(fav_row)
        right.addWidget(QLabel(tr(self._lang, 'intel.gallery.details', 'Details'))); right.addWidget(self.txt_detail,1)
        btns = QHBoxLayout(); btns.addStretch(1); btns.addWidget(self.btn_continue_synth); btns.addWidget(self.btn_insert); btns.addWidget(self.btn_close); right.addLayout(btns)
        rightw = QWidget(self); rightw.setLayout(right)
        split = QSplitter(self); split.addWidget(leftw); split.addWidget(rightw); split.setSizes([700,420])
        lay = QVBoxLayout(self); lay.addWidget(split)

        for w in [self.edit_search, self.edit_tag]: w.textChanged.connect(self._refresh_list)
        for w in [self.combo_family_filter, self.combo_has_template, self.combo_sort]: w.currentIndexChanged.connect(self._refresh_list)
        self.chk_favorites_only.toggled.connect(self._refresh_list)
        self.list_templates.currentItemChanged.connect(self._update_preview)
        self.list_templates.itemDoubleClicked.connect(lambda _i: self._insert_selected())
        self.btn_continue_synth.clicked.connect(self._continue_in_synthesis_from_selected)
        self.btn_insert.clicked.connect(self._insert_selected)
        self.btn_fav.clicked.connect(self._toggle_favorite)
        self.btn_delete.clicked.connect(self._delete_selected_template)
        self.btn_close.clicked.connect(self.reject)
        self._refresh_list()

    def _make_rows(self):
        rows=[]
        for c in self._concepts:
            row=dict(c); row['_source_kind']='builtin' if c.get('template') else 'concept_only'; row['template_id']=c.get('template') or ''; rows.append(row)
        for u in list_user_templates():
            row=dict(u); row.setdefault('name', row.get('template_id','')); row.setdefault('family',''); row.setdefault('tags',[]); row['_source_kind']=str(u.get('source') or 'user'); row['id']=row.get('concept_id') or row.get('template_id'); rows.append(row)
        favs=set(self._prefs.get('favorites',[]) or [])
        recent=list(self._prefs.get('recent_used',[]) or [])
        recent_rank={k:i for i,k in enumerate(recent)}
        next_seq = 1
        for r in rows:
            tid=str(r.get('template_id') or r.get('template') or '')
            rid=str(r.get('id') or tid)
            key=tid or rid
            r['_key']=key; r['_is_favorite']= key in favs; r['_recent_rank']= recent_rank.get(key, 10**9)
            try:
                disp = int(r.get('display_order') or 0)
            except Exception:
                disp = 0
            if disp > 0:
                r['_seq'] = disp
            else:
                r['_seq'] = next_seq
                next_seq += 1
        return rows

    def _refresh_list(self):
        q=(self.edit_search.text() or '').strip().lower(); fam=str(self.combo_family_filter.currentData() or 'any')
        mode=self.combo_has_template.currentIndex(); tagq=(self.edit_tag.text() or '').strip().lower()
        rows=[]
        for c in self._make_rows():
            cfam=str(c.get('family','') or '').lower()
            if fam!='any' and cfam!=fam: continue
            has_tpl=bool(c.get('template_id') or c.get('template'))
            if mode==1 and not has_tpl: continue
            if mode==2 and has_tpl: continue
            tags=[str(t) for t in (c.get('tags',[]) or [])]
            if self.chk_favorites_only.isChecked() and not c.get('_is_favorite'): continue
            if tagq and not any(tagq in t.lower() for t in tags): continue
            seq = int(c.get('_seq', 0) or 0)
            seq_tokens = [str(seq), f"#{seq}", f"{seq:03d}", f"#{seq:03d}"] if seq > 0 else []
            blob=' '.join([str(c.get('name','')), str(c.get('id','')), str(c.get('template_id') or c.get('template') or ''), ' '.join(tags), ' '.join(seq_tokens)]).lower()
            if q and q not in blob: continue
            rows.append(c)
        sort_mode=str(self.combo_sort.currentData() or 'recent')
        if sort_mode=='recent': rows.sort(key=lambda r:(r.get('_recent_rank',10**9), str(r.get('name',''))))
        elif sort_mode=='favorite': rows.sort(key=lambda r:(0 if r.get('_is_favorite') else 1, str(r.get('name',''))))
        elif sort_mode=='name': rows.sort(key=lambda r:str(r.get('name','')).lower())
        else: rows.sort(key=lambda r:int(r.get('_seq',0)))
        self._filtered=rows
        self._icon_load_timer.stop()
        self._icon_queue = []
        self.list_templates.clear()
        placeholder = QIcon(_template_preview_pixmap({'family':'any'}, QSize(220,132)))
        for c in rows:
            item=QListWidgetItem()
            famtxt=_family_label(str(c.get('family','')))
            tpl=str(c.get('template_id') or c.get('template') or '')
            star='★' if c.get('_is_favorite') else '☆'
            item.setText(f"{star} #{int(c.get('_seq',0)):03d} {c.get('name','')}\n[{famtxt}] {tpl or tr(self._lang, 'intel.gallery.concept', 'Concept')}")
            item.setData(Qt.ItemDataRole.UserRole, c)
            item.setIcon(placeholder)
            self.list_templates.addItem(item)
            self._icon_queue.append(item)
        if self.list_templates.count():
            self.list_templates.setCurrentRow(0)
            self.btn_fav.setEnabled(True)
            self._icon_load_timer.start(0)
        else:
            self.lbl_preview.clear(); self.txt_detail.setPlainText(tr(self._lang, 'intel.gallery.no_match', 'No matching templates.')); self.btn_fav.setEnabled(False); self.btn_delete.setEnabled(False)

    def _load_icons_batch(self):
        if not self._icon_queue:
            return
        n = min(int(self._icon_batch_size), len(self._icon_queue))
        batch = [self._icon_queue.pop(0) for _ in range(n)]
        for item in batch:
            try:
                c = item.data(Qt.ItemDataRole.UserRole) or {}
                item.setIcon(QIcon(_preview_pixmap_for_item(c, QSize(220,132))))
            except Exception:
                continue
        if self._icon_queue:
            self._icon_load_timer.start(0)

    def _update_preview(self, cur, prev=None):
        if not cur: return
        c = cur.data(Qt.ItemDataRole.UserRole) or {}
        self.lbl_preview.setPixmap(_preview_pixmap_for_item(c, QSize(420, 260)))
        self.btn_fav.setText(tr(self._lang, 'intel.gallery.unfavorite', 'Unfavorite') if c.get('_is_favorite') else tr(self._lang, 'intel.gallery.add_favorite', 'Add favorite'))
        is_user = str(c.get('_source_kind','')) != 'builtin'
        try:
            tpl_id = str(c.get('template_id') or c.get('template') or '').strip()
            ok = _supports_synthesis(tpl_id)
            self.btn_continue_synth.setEnabled(bool(ok) and bool(tpl_id))
            self.btn_continue_synth.setProperty("primary", bool(ok) and bool(tpl_id))
            try:
                self.btn_continue_synth.style().unpolish(self.btn_continue_synth)
                self.btn_continue_synth.style().polish(self.btn_continue_synth)
            except Exception:
                pass
        except Exception:
            try:
                self.btn_continue_synth.setEnabled(False)
                self.btn_continue_synth.setProperty("primary", False)
            except Exception:
                pass

        self.btn_delete.setEnabled(is_user)
        self.btn_delete.setText(tr(self._lang, 'intel.gallery.delete', 'Delete template') if is_user else tr(self._lang, 'intel.gallery.delete_user_only', 'Delete template (user only)'))
        lines=[f"{tr(self._lang, 'intel.gallery.detail.seq', 'Index')}: #{int(c.get('_seq',0)):03d}", f"{tr(self._lang, 'intel.gallery.detail.name', 'Name')}: {c.get('name','')}", f"{tr(self._lang, 'intel.gallery.detail.family', 'Family')}: {_family_label(str(c.get('family','')))}",
               f"{tr(self._lang, 'intel.gallery.detail.template_id', 'Template ID')}: {c.get('template_id') or c.get('template') or tr(self._lang, 'intel.output.none', 'None (concept only)')}", f"{tr(self._lang, 'intel.gallery.detail.concept_id', 'Concept ID')}: {c.get('id','')}", f"{tr(self._lang, 'intel.gallery.detail.source', 'Source')}: {c.get('_source_kind','builtin')}"]
        if c.get('tags'): lines.append(tr(self._lang, 'intel.gallery.detail.tags', 'Tags') + ': ' + ', '.join(map(str,c.get('tags') or [])))
        if c.get('description'): lines += ['', tr(self._lang, 'intel.gallery.detail.description', 'Description') + ':', str(c.get('description'))]
        for ttl,key in [(tr(self._lang, 'intel.gallery.detail.pros', 'Pros'),'pros'),(tr(self._lang, 'intel.gallery.detail.cons', 'Notes'),'cons')]:
            arr=c.get(key,[]) or []
            if arr: lines += ['', ttl+':'] + [f'- {x}' for x in arr]
        self.txt_detail.setPlainText('\n'.join(lines))

    def _toggle_favorite(self):
        cur=self.list_templates.currentItem()
        if not cur: return
        c=cur.data(Qt.ItemDataRole.UserRole) or {}
        key=str(c.get('_key') or '')
        favs=set(self._prefs.get('favorites',[]) or [])
        if key in favs: favs.remove(key)
        else: favs.add(key)
        self._prefs['favorites']=sorted(favs)
        _save_intel_prefs(self._prefs)
        self._refresh_list()

    def _mark_recent(self, key:str):
        key=str(key or '').strip()
        if not key: return
        rec=[k for k in (self._prefs.get('recent_used',[]) or []) if str(k)!=key]
        rec.insert(0,key); self._prefs['recent_used']=rec[:50]; _save_intel_prefs(self._prefs)

    def _delete_selected_template(self):
        cur = self.list_templates.currentItem()
        if not cur:
            return
        c = cur.data(Qt.ItemDataRole.UserRole) or {}
        sk = str(c.get('_source_kind',''))
        if sk == 'builtin':
            QMessageBox.information(self, tr(self._lang, 'intel.gallery.title', 'Template Library'), tr(self._lang, 'intel.gallery.msg.builtin_not_deletable', 'Built-in templates cannot be deleted.'))
            return
        tid = str(c.get('template_id') or '').strip()
        if not tid:
            QMessageBox.warning(self, tr(self._lang, 'intel.gallery.title', 'Template Library'), tr(self._lang, 'intel.gallery.msg.missing_template_id', 'This entry has no template_id and cannot be deleted.'))
            return
        name = str(c.get('name') or tid)
        ret = QMessageBox.question(self, tr(self._lang, 'intel.gallery.delete_confirm_title', 'Delete Template'), tr(self._lang, 'intel.gallery.delete_confirm_body', 'Delete this user template?\n#{seq:03d} {name}\nID: {tid}\n(The template file and preview image will be deleted.)').format(seq=int(c.get('_seq',0)), name=name, tid=tid))
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_user_template(tid, remove_preview=True)
            # 清理收藏/最近使用与预览缓存
            key = str(c.get('_key') or tid)
            self._prefs['favorites'] = [x for x in (self._prefs.get('favorites',[]) or []) if str(x) != key]
            self._prefs['recent_used'] = [x for x in (self._prefs.get('recent_used',[]) or []) if str(x) != key]
            _save_intel_prefs(self._prefs)
            try:
                _PREVIEW_PIXMAP_CACHE.clear()
                _PREVIEW_SOURCE_SIG_CACHE.clear()
            except Exception:
                pass
            self._refresh_list()
            QMessageBox.information(self, tr(self._lang, 'intel.gallery.title', 'Template Library'), tr(self._lang, 'intel.gallery.msg.deleted', 'Template deleted: {tid}').format(tid=tid))
        except Exception as e:
            QMessageBox.critical(self, tr(self._lang, 'intel.gallery.title', 'Template Library'), tr(self._lang, 'intel.gallery.msg.delete_failed', 'Failed to delete template: {err}').format(err=e))

    def _insert_selected(self):
        cur=self.list_templates.currentItem()
        if not cur: return
        c=cur.data(Qt.ItemDataRole.UserRole) or {}
        tpl=str(c.get('template_id') or c.get('template') or '').strip()
        if not tpl:
            QMessageBox.information(self, tr(self._lang, 'intel.gallery.title', 'Template Library'), tr(self._lang, 'intel.gallery.msg.concept_no_template', 'This item is a concept entry and has no insertable template yet.')); return

        center_xy=(0.0,0.0)
        try:
            win=getattr(self.ctrl,'win',None); view=getattr(win,'view',None) if win else None
            if view is not None:
                center=view.mapToScene(view.viewport().rect().center()); center_xy=(float(center.x()), float(center.y()))
        except Exception: pass
        info = insert_template(self.ctrl, tpl, center_xy=center_xy, scale=1.0, auto_setup_io_cases=False, solve_after_insert=False, return_info=True) or {}
        self._mark_recent(c.get('_key') or tpl)
        QMessageBox.information(self, tr(self._lang, 'intel.gallery.title', 'Template Library'), tr(self._lang, 'intel.gallery.msg.inserted_light', 'Template inserted (light mode): {tpl}\n(No auto case setup, no immediate solve.)').format(tpl=tpl))

    def _continue_in_synthesis_from_selected(self):
        """Jump to Intelligent Synthesis without inserting.

        This is enabled only for templates supported by Synthesis.
        """
        cur = self.list_templates.currentItem()
        if not cur:
            return
        c = cur.data(Qt.ItemDataRole.UserRole) or {}
        tpl = str(c.get('template_id') or c.get('template') or '').strip()
        if not tpl or not _supports_synthesis(tpl):
            return
        self._handoff_to_synthesis(template_id=tpl)
        self._mark_recent(c.get('_key') or tpl)

    def _handoff_to_synthesis(self, template_id: str):
        """Switch to Intelligent Synthesis tab and pre-fill mapping points.

        This is a pure navigation handoff:
        - NO insertion
        - NO generate/configure
        Synthesis stays the single owner of optimization configuration.
        """
        tpl = str(template_id or '').strip()
        if not tpl:
            return
        win = getattr(self.ctrl, 'win', None)
        # This dialog is modal; close it first. Also close the owning Intelligent
        # Design dialog (if any) so it doesn't block interaction with the main UI.
        try:
            self.accept()
        except Exception:
            pass
        try:
            owner = self.parent()
            # Only close if it looks like the IntelligentDesignDialog itself.
            from PyQt6.QtWidgets import QDialog
            if isinstance(owner, QDialog):
                owner.accept()
        except Exception:
            pass

        def _do_switch() -> None:
            try:
                if win is None:
                    return
                # Ensure analysis dock is visible without forcing Simulation tab.
                try:
                    if hasattr(win, '_set_active_ribbon'):
                        win._set_active_ribbon('analysis')
                    if hasattr(win, '_set_dock_visibility'):
                        win._set_dock_visibility(active='analysis')
                except Exception:
                    pass
                sim_panel = getattr(win, 'sim_panel', None)
                tab = getattr(sim_panel, 'synthesis_tab', None) if sim_panel else None
                if sim_panel is None or tab is None:
                    return
                # Suggest default mapping based on the most common door workflow.
                pts = [(0.0, 0.0), (30.0, 30.0), (60.0, 60.0), (90.0, 90.0)]
                if hasattr(tab, '_set_mapping_points'):
                    tab._set_mapping_points(pts)
                # Select corresponding synthesis template (robustly)
                try:
                    if hasattr(tab, 'select_template_id'):
                        tab.select_template_id(tpl)
                    elif hasattr(tab, 'combo_template'):
                        i = tab.combo_template.findData(tpl)
                        if i >= 0:
                            tab.combo_template.setCurrentIndex(i)
                except Exception:
                    pass
                try:
                    sim_panel.tabs.setCurrentWidget(tab)
                except Exception:
                    pass
                # Bring the analysis dock to front for immediate visibility.
                try:
                    dock = getattr(win, 'sim_dock', None)
                    if dock is not None:
                        dock.show(); dock.raise_()
                except Exception:
                    pass
            except Exception:
                pass

        QTimer.singleShot(0, _do_switch)


class IntelligentDesignDialog(QDialog):
    """A minimal wizard: Requirement -> Recommend -> Insert template."""

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self._recs = []

        lang = getattr(self.ctrl, "ui_language", "en")
        self.setWindowTitle(tr(lang, "intel.title", "Intelligent Design"))
        self.setMinimumWidth(720)
        self.setMinimumHeight(520)

        self.combo_task = QComboBox(self)
        self.combo_task.addItem(tr(lang, "intel.task.door", "Door / Hatch opening"), "door")
        self.combo_task.addItem(tr(lang, "intel.task.path", "Path generation"), "path")
        self.combo_task.addItem(tr(lang, "intel.task.function", "Function generation"), "function")
        self.combo_task.addItem(tr(lang, "intel.task.guidance", "Rigid body guidance"), "rigid_guidance")

        self.combo_family = QComboBox(self)
        self.combo_family.addItem(tr(lang, "intel.family.any", "Any mechanism"), "any")
        self.combo_family.addItem(tr(lang, "intel.family.cam", "Cam mechanisms"), "cam")
        self.combo_family.addItem(tr(lang, "intel.family.4bar", "4-bar linkages"), "4bar")
        self.combo_family.addItem(tr(lang, "intel.family.6bar", "6-bar linkages"), "6bar")
        self.combo_family.addItem(tr(lang, "intel.family.slider", "Slider / rail linkages"), "slider_rail")

        self.spin_angle = QSpinBox(self)
        self.spin_angle.setRange(0, 180)
        self.spin_angle.setValue(90)
        self.spin_angle.setSuffix(" °")

        self.spin_scale = QDoubleSpinBox(self)
        self.spin_scale.setRange(0.1, 10.0)
        self.spin_scale.setSingleStep(0.1)
        self.spin_scale.setValue(1.0)

        self.chk_fewer = QCheckBox(tr(lang, "intel.prefer_fewer_links", "Prefer fewer links"), self)
        self.chk_fewer.setChecked(True)
        self.chk_compact = QCheckBox(tr(lang, "intel.prefer_compact", "Prefer compact packaging"), self)
        self.chk_compact.setChecked(True)

        self.combo_results = QComboBox(self)
        self.combo_results.setEnabled(False)

        self.txt = QPlainTextEdit(self)
        self.txt.setReadOnly(True)
        self.txt.setPlaceholderText(tr(lang, "intel.output.placeholder", "Recommendations and design notes will appear here."))

        form = QFormLayout()
        form.addRow(QLabel(tr(lang, "intel.task", "Task")), self.combo_task)
        form.addRow(QLabel(tr(lang, "intel.family", "Mechanism family")), self.combo_family)
        form.addRow(QLabel(tr(lang, "intel.open_angle", "Opening angle (deg)")), self.spin_angle)
        form.addRow(QLabel(tr(lang, "intel.scale", "Template scale")), self.spin_scale)
        form.addRow(self.chk_fewer)
        form.addRow(self.chk_compact)
        form.addRow(QLabel(tr(lang, "intel.results", "Recommended concepts")), self.combo_results)

        self.btn_recommend = QPushButton(tr(lang, "intel.recommend", "Recommend"), self)
        self.btn_insert = QPushButton(tr(lang, "intel.insert", "Insert to canvas"), self)
        self.btn_continue_synth = QPushButton(tr(lang, 'intel.continue_synth', 'Continue in Intelligent Synthesis (Generate & Configure)'), self)
        self.btn_continue_synth.setEnabled(False)
        # Make disabled state visually obvious even if global styles keep text dark.
        self.btn_continue_synth.setStyleSheet('QPushButton:disabled{color:#8b949e;}')
        self.btn_continue_synth.setProperty("primary", False)
        self.btn_save_template = QPushButton(tr(lang, "intel.save_template", "Save current model as template"), self)
        self.btn_gallery = QPushButton(tr(lang, "intel.gallery", "Template library"), self)
        self.btn_close = QPushButton(tr(lang, "intel.close", "Close"), self)
        self.btn_insert.setEnabled(False)
        self.btn_save_template.setEnabled(True)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_recommend)
        btn_row.addWidget(self.btn_insert)
        btn_row.addWidget(self.btn_continue_synth)
        btn_row.addWidget(self.btn_save_template)
        btn_row.addWidget(self.btn_gallery)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_close)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.txt, 1)
        layout.addLayout(btn_row)
        self.setLayout(layout)

        self.combo_results.currentIndexChanged.connect(self._on_selected_rec_changed)
        self.btn_recommend.clicked.connect(self._on_recommend)
        self.btn_insert.clicked.connect(self._on_insert)
        self.btn_continue_synth.clicked.connect(self._on_continue_synth)
        self.btn_save_template.clicked.connect(self._on_save_template)
        self.btn_gallery.clicked.connect(self._on_gallery)
        self.btn_close.clicked.connect(self.reject)

    def _current_requirement(self) -> Requirement:
        task = self.combo_task.currentData() or "door"
        fam = self.combo_family.currentData() or "any"
        angle = float(self.spin_angle.value())
        # For non-door tasks, angle is not essential. Keep it anyway.
        return Requirement(
            task=str(task),
            mechanism_family=str(fam),
            open_angle_deg=angle,
            prefer_fewer_links=bool(self.chk_fewer.isChecked()),
            prefer_compact=bool(self.chk_compact.isChecked()),
        )

    def _on_recommend(self) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        req = self._current_requirement()
        recs = recommend(req, top_k=3)
        self._recs = recs

        self.combo_results.blockSignals(True)
        self.combo_results.clear()
        for idx, r in enumerate(recs, start=1):
            self.combo_results.addItem(f"{idx}. {r.concept_name}  (score={r.score:.1f})", idx - 1)
        self.combo_results.blockSignals(False)
        self.combo_results.setEnabled(bool(recs))
        self.btn_insert.setEnabled(bool(recs))
        self._on_selected_rec_changed()
        self.btn_save_template.setEnabled(True)

        lines: List[str] = []
        lines.append(tr(lang, "intel.output.req", "Requirement"))
        for k, v in asdict(req).items():
            lines.append(f"- {k}: {v}")
        lines.append("")
        lines.append(tr(lang, "intel.output.recs", "Top recommendations"))
        for idx, r in enumerate(recs, start=1):
            lines.append(f"{idx}) {r.concept_name}  (score={r.score:.1f})")
            for w in r.why:
                lines.append(f"   - {w}")
            intro = _design_intro(r.concept_id)
            if intro:
                lines.append("   " + tr(lang, "intel.output.intro", "Design intro") + ":")
                for t in intro:
                    lines.append(f"     • {t}")
            if r.template:
                lines.append(f"   - {tr(lang, 'intel.output.template', 'Template')}: {r.template}")
            else:
                lines.append(f"   - {tr(lang, 'intel.output.template_missing', 'Template')}: {tr(lang, 'intel.output.none', 'None (concept only)')}")
            lines.append("")
        lines.append(tr(lang, "intel.output.next", "Next steps"))
        lines.append("- Insert template → run Analysis → set driver/constraints → tune dimensions")
        lines.append("- For door mechanisms: add keep-out envelopes + opening angle checks")

        self.txt.setPlainText("\n".join(lines))

    def _on_selected_rec_changed(self, *_a) -> None:
        """Enable/disable the 'continue synthesis' option based on template support."""
        try:
            tid = ''
            if self._recs:
                idx = int(self.combo_results.currentData() or 0)
                idx = max(0, min(idx, len(self._recs) - 1))
                tid = str(getattr(self._recs[idx], 'template', '') or '').strip()
            ok = _supports_synthesis(tid)
            enabled = bool(ok) and bool(tid)
            self.btn_continue_synth.setEnabled(enabled)
            self.btn_continue_synth.setProperty("primary", enabled)
            try:
                self.btn_continue_synth.style().unpolish(self.btn_continue_synth)
                self.btn_continue_synth.style().polish(self.btn_continue_synth)
            except Exception:
                pass
        except Exception:
            try:
                self.btn_continue_synth.setEnabled(False)
                self.btn_continue_synth.setProperty("primary", False)
            except Exception:
                pass

    def _inherit_req_to_synthesis(self, req: Requirement) -> None:
        try:
            setattr(self.ctrl, '_intel_last_requirement', asdict(req))
            win = getattr(self.ctrl, 'win', None)
            sim_panel = getattr(win, 'sim_panel', None) if win else None
            tab = getattr(sim_panel, 'synthesis_tab', None) if sim_panel else None
            if tab is not None:
                # 参数继承（尽量写入已有控件）
                if hasattr(tab, 'ed_axis'):
                    axis = 400.0 * max(0.1, float(self.spin_scale.value()))
                    tab.ed_axis.setText(f"{axis:.3g}")
                if hasattr(tab, 'combo_template') and (req.mechanism_family or '') in ('4bar','any'):
                    pass
        except Exception:
            pass

    def _on_continue_synth(self) -> None:
        """Jump to Intelligent Synthesis for supported templates (no insertion)."""
        if not self._recs:
            return
        idx = int(self.combo_results.currentData() or 0)
        idx = max(0, min(idx, len(self._recs) - 1))
        rec = self._recs[idx]
        tid = str(getattr(rec, 'template', '') or '').strip()
        if not tid or not _supports_synthesis(tid):
            return
        try:
            win = getattr(self.ctrl, 'win', None)
            sim_panel = getattr(win, 'sim_panel', None) if win else None
            tab = getattr(sim_panel, 'synthesis_tab', None) if sim_panel else None
            if sim_panel is None or tab is None:
                return
            ang = float(self.spin_angle.value())
            pts = [(0.0, 0.0), (ang / 3.0, ang / 3.0), (2.0 * ang / 3.0, 2.0 * ang / 3.0), (ang, ang)]
            if hasattr(tab, '_set_mapping_points'):
                tab._set_mapping_points(pts)
            # Select corresponding synthesis template (robustly)
            try:
                if hasattr(tab, 'select_template_id'):
                    tab.select_template_id(tid)
                elif hasattr(tab, 'combo_template'):
                    i = tab.combo_template.findData(tid)
                    if i >= 0:
                        tab.combo_template.setCurrentIndex(i)
            except Exception:
                pass
            try:
                sim_panel.tabs.setCurrentWidget(tab)
            except Exception:
                pass
            # This dialog is modal; user must be able to operate synthesis tab.
            try:
                self.accept()
            except Exception:
                pass
        except Exception:
            pass

    def _run_structural_completion_check(self) -> List[str]:
        msgs=[]
        try:
            if not getattr(self.ctrl, 'driver', None): msgs.append(tr(getattr(self.ctrl, 'ui_language', 'en'), 'intel.check.no_driver', 'Driver is not set'))
            if not getattr(self.ctrl, 'output', None): msgs.append(tr(getattr(self.ctrl, 'ui_language', 'en'), 'intel.check.no_output', 'Output is not set'))
            # 轻量约束检查
            bad=[]
            for lid, lk in (getattr(self.ctrl,'links',{}) or {}).items():
                try:
                    if float(lk.get('L',0) or 0) <= 1e-9: bad.append(str(lid))
                except Exception:
                    bad.append(str(lid))
            if bad: msgs.append(tr(getattr(self.ctrl, 'ui_language', 'en'), 'intel.check.zero_length_links', 'Zero-length links found: {ids}').format(ids=','.join(bad[:6])))
        except Exception:
            msgs.append(tr(getattr(self.ctrl, 'ui_language', 'en'), 'intel.check.failed_ignored', 'Structural check failed (ignored)'))
        return msgs

    def _on_insert(self) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        if not self._recs:
            QMessageBox.information(self, tr(lang, "intel.title", "Intelligent Design"), tr(lang, "intel.msg.no_recs", "Please click Recommend first."))
            return
        idx = int(self.combo_results.currentData() or 0)
        idx = max(0, min(idx, len(self._recs)-1))
        rec = self._recs[idx]
        req = self._current_requirement()
        # NOTE (Flow Simplification)
        # Intelligent Design is a *single UI* for picking a starting mechanism.
        # It should NOT create cases/presets/optimization configuration.
        # All optimization workflow must live in Intelligent Synthesis.
        self._inherit_req_to_synthesis(req)

        center_xy = (0.0, 0.0)
        try:
            win = getattr(self.ctrl, 'win', None)
            view = getattr(win, 'view', None) if win else None
            if view is not None:
                c = view.mapToScene(view.viewport().rect().center())
                center_xy = (float(c.x()), float(c.y()))
        except Exception:
            pass

        # Plain insert mode (no auto case setup, no synthesis generation).
        insert_template(
            self.ctrl,
            rec.template,
            center_xy=center_xy,
            scale=float(self.spin_scale.value()),
            open_angle_deg=float(self.spin_angle.value()),
            auto_setup_io_cases=False,
            solve_after_insert=False,
            return_info=False,
        )

        QMessageBox.information(self, tr(lang, "intel.title", "Intelligent Design"), tr(lang, "intel.msg.template_inserted_named", "Template inserted: {tpl}").format(tpl=rec.template))

    def _on_gallery(self) -> None:
        try:
            dlg = TemplateLibraryDialog(self.ctrl, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, tr(getattr(self.ctrl, "ui_language", "en"), "intel.gallery.title", "Template Library"), tr(getattr(self.ctrl, "ui_language", "en"), "intel.gallery.msg.open_failed", "Failed to open template library: {err}").format(err=e))

    def _on_save_template(self) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        rec = None
        if self._recs:
            idx = int(self.combo_results.currentData() or 0)
            idx = max(0, min(idx, len(self._recs) - 1))
            rec = self._recs[idx]
        dlg = SaveTemplateDialog(self.ctrl, rec=rec, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            vals = dlg.values()
        except Exception as exc:
            QMessageBox.warning(self, tr(lang, "intel.title"), tr(lang, "intel.save.invalid_params", "Invalid parameters: {err}").format(err=exc))
            return
        preview_path = ''
        if vals.get('save_preview'):
            preview_path = str(_user_template_preview_path(vals['template_id']))
            ok = _capture_view_preview(self.ctrl, preview_path)
            if not ok:
                preview_path = ''
        try:
            path = save_current_model_as_template(
                self.ctrl,
                vals['template_id'],
                mode=vals['mode'],
                name=vals.get('name'),
                family=vals.get('family'),
                tags=vals.get('tags') or [],
                description=vals.get('description') or '',
                concept_id=vals.get('concept_id') or '',
                base_template_id=(vals['template_id'] if vals['mode']=='override' else ''),
                preview_image_path=preview_path or None,
                synthesis_profile=(_collect_synthesis_profile(self.ctrl) if vals.get('save_synthesis') else None),
            )
        except Exception as exc:
            QMessageBox.critical(self, tr(lang, "intel.title"), tr(lang, "intel.save.failed", "Failed to save template: {err}").format(err=exc))
            return
        # refresh thumbnail caches so template library immediately shows latest real screenshot
        try:
            _PREVIEW_PIXMAP_CACHE.clear()
            _PREVIEW_SOURCE_SIG_CACHE.clear()
        except Exception:
            pass
        tip = tr(lang, 'intel.save.saved_new', 'Template saved') if vals['mode'] == 'new' else tr(lang, 'intel.save.saved_override', 'Template override saved')
        extra = ('\n' + tr(lang, 'intel.save.preview_path', 'Preview image') + f': {preview_path}') if preview_path else ('\n' + tr(lang, 'intel.save.preview_path', 'Preview image') + ': ' + tr(lang, 'intel.save.preview_not_saved', '(not saved)'))
        QMessageBox.information(self, tr(lang, "intel.title"), f"{tip}: {vals['template_id']}\n{path}{extra}")


def _design_intro(concept_id: str) -> List[str]:
    cid = (concept_id or "").lower().strip()
    cam = _cam_intro(cid)
    if cam:
        return cam
    if cid == "4bar":
        return [
            "Classic 1-DOF mechanism: ground + 3 moving links.",
            "Good for door/hatch opening and simple guidance.",
            "Sizing tips: check Grashof condition and avoid toggle positions.",
        ]
    if cid == "slider_crank":
        return [
            "Converts rotary motion to linear motion (or vice versa).",
            "Useful for actuator-driven mechanisms.",
            "Watch side loads on the slider guide; add stiffness if needed.",
        ]
    if cid.startswith("6bar"):
        return [
            "6-bar mechanisms offer richer motion and packaging than 4-bar.",
            "Good for compact hinges and complex door trajectories.",
            "Typically needs good initial layout + optimization for sizing.",
        ]
    return []


def _cam_intro(cid: str) -> List[str]:
    if cid in ("cam_translating", "cam_oscillating"):
        return [
            "Cam mechanisms directly encode motion program (s-θ or φ-θ).",
            "Key checks: pressure angle, undercut, minimum radius of curvature, and follower type.",
            "In Planar Sketch, cams are recommended as a concept; use linkages when you need pure pin-joint modeling.",
        ]
    return []
