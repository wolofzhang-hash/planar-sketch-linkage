# -*- coding: utf-8 -*-
"""UI translations loaded from external locale JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

try:
    from PyQt6.QtWidgets import QApplication
except Exception:  # pragma: no cover - makes locale loading testable without Qt
    QApplication = None  # type: ignore[assignment]


_LOCALES_DIR = Path(__file__).with_name("locales")
_SUPPORTED_LANGS = ("en", "zh")


def _read_locale(path: Path) -> Dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def load_languages() -> Dict[str, Dict[str, str]]:
    languages: Dict[str, Dict[str, str]] = {}
    for lang in _SUPPORTED_LANGS:
        languages[lang] = _read_locale(_LOCALES_DIR / f"{lang}.json")
    languages.setdefault("en", {})
    languages.setdefault("zh", {})
    return languages


LANGUAGES: Dict[str, Dict[str, str]] = load_languages()


# NOTE:
# keep helper names and signatures stable because the rest of the UI imports them directly.

def norm_lang(value: str | None, fallback: str = "zh") -> str:
    vv = (str(value).strip().lower().replace("-", "_") if value is not None else "")
    if vv in {"zh", "cn", "zh_cn", "zh_hans", "zh_hans_cn", "zh_tw", "zh_hk"} or vv.startswith("zh"):
        return "zh"
    if vv == "en" or vv.startswith("en"):
        return "en"
    fb = str(fallback).strip().lower()
    return "zh" if fb.startswith("zh") else "en"


def tr(lang: str, key: str, default: str | None = None, **kwargs) -> str:
    """Translate a UI key (zh/en) with optional string interpolation."""
    lang = norm_lang(lang)
    table = LANGUAGES.get(lang, LANGUAGES.get("en", {}))
    if key in table:
        out = table[key]
    elif key in LANGUAGES.get("en", {}):
        out = LANGUAGES["en"][key]
    else:
        out = key if default is None else default
    if kwargs:
        try:
            return str(out).format(**kwargs)
        except Exception:
            return str(out)
    return str(out)


def ui_language(lang: str | None = None, fallback: str = "zh") -> str:
    """Resolve current UI language using software settings only (zh/en)."""
    if lang is not None:
        return norm_lang(lang, fallback)
    app = QApplication.instance() if QApplication is not None else None
    if app is not None:
        v = app.property("ui_language")
        if isinstance(v, str) and v:
            return norm_lang(v, fallback)
    return norm_lang(None, fallback)


def set_ui_language(lang: str | None, app: QApplication | None = None, fallback: str = "zh") -> str:
    """Set application UI language property. Only zh/en are allowed after normalization."""
    resolved = norm_lang(lang, fallback)
    if QApplication is None:
        return resolved
    if app is None:
        app = QApplication.instance()
    if app is not None:
        app.setProperty("ui_language", resolved)
    return resolved


def get_ui_language(ctrl=None, fallback: str = "zh") -> str:
    """Resolve UI language. Priority: controller setting > QApplication property > fallback."""
    try:
        if ctrl is not None and hasattr(ctrl, "ui_language"):
            return norm_lang(getattr(ctrl, "ui_language"), fallback)
    except Exception:
        pass
    return ui_language(None, fallback)


def tr_ui(key: str, default: str | None = None, fallback_lang: str = "zh", **kwargs) -> str:
    return tr(ui_language(None, fallback_lang), key, default, **kwargs)


__all__ = [
    "LANGUAGES",
    "load_languages",
    "tr",
    "tr_ui",
    "ui_language",
    "set_ui_language",
    "get_ui_language",
    "norm_lang",
]
