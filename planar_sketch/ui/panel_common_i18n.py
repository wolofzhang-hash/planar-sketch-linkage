# -*- coding: utf-8 -*-
"""Shared panel i18n helpers.

These helpers are intentionally tiny and stateless. They expect the owner object
to expose ``ctrl`` (or any object accepted by ``get_ui_language``).
"""

from __future__ import annotations

from .i18n import tr, get_ui_language


def panel_lang(owner) -> str:
    ctrl = getattr(owner, "ctrl", None)
    return get_ui_language(ctrl, fallback="zh")


def panel_tr(owner, key: str, **kwargs):
    text = tr(panel_lang(owner), key)
    return text.format(**kwargs) if kwargs else text


def panel_is_zh(owner) -> bool:
    return panel_lang(owner) == "zh"


def panel_is_en(owner) -> bool:
    return panel_lang(owner) == "en"
