"""Square tile buttons: an icon over a short label, coloured by state.

The colours follow what the button can do: a plain tile is quiet, a checked
one is lit, the primary action is solid, and a button that cannot act now
fades back into the panel.
"""

import tempfile
from functools import lru_cache, partial
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QSizePolicy, QToolButton

NORMAL = "#e4e4e7"
ACTIVE = "#ffffff"
DISABLED = "#52525b"

# 24×24 outline icons, stroked in the colour given to _svg().
_ICONS = {
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "save": '<path d="M5 3h11l3 3v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M7 3v5h8V3"/><path d="M7 21v-7h10v7"/>',
    "people": '<circle cx="9" cy="7" r="4"/><path d="M2 21v-2a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v2"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/>',
    "film": '<rect x="2" y="3" width="20" height="18" rx="2"/><path d="M7 3v18M17 3v18M2 8h5M2 16h5M17 8h5M17 16h5"/>',
    "layers": '<path d="M12 3 2 8l10 5 10-5-10-5z"/><path d="M2 13l10 5 10-5"/><path d="M2 18l10 5 10-5"/>',
    "tag": '<path d="M3 3h8l10 10-8 8L3 11z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/>',
    "play": '<path d="M6 4l14 8-14 8z"/>',
    "share": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "mic": '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5"/>',
    "wand": '<path d="M15 4l5 5L9 20H4v-5z"/><path d="M13 6l5 5"/>',
    "text": '<path d="M4 6V4h16v2M9 20h6M12 4v16"/>',
    "grid": '<rect x="4" y="4" width="7" height="7"/><rect x="13" y="4" width="7" height="7"/><rect x="4" y="13" width="7" height="7"/><rect x="13" y="13" width="7" height="7"/>',
    "align": '<path d="M4 6h16M4 12h10M4 18h14"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "chevron": '<path d="M6 9l6 6 6-6"/>',
    "dots": '<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>',
    "zoom_in": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5M11 8v6M8 11h6"/>',
    "zoom_out": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5M8 11h6"/>',
    "fit": '<path d="M3 9V3h6M21 9V3h-6M3 15v6h6M21 15v6h-6"/>',
}


def _svg(markup: str, color: str) -> bytes:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{markup}</svg>'
    ).encode()


def _render(markup: str, color: str, size: int = 24) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_svg(markup, color)))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


@lru_cache(maxsize=None)
def icon(name: str) -> QIcon:
    """The named icon in its normal, active and disabled colours."""
    markup = _ICONS[name]
    out = QIcon()
    out.addPixmap(_render(markup, NORMAL), QIcon.Mode.Normal)
    out.addPixmap(_render(markup, ACTIVE), QIcon.Mode.Active)
    out.addPixmap(_render(markup, ACTIVE), QIcon.Mode.Selected)
    out.addPixmap(_render(markup, DISABLED), QIcon.Mode.Disabled)
    return out


@lru_cache(maxsize=None)
def chevron_url() -> str:
    """A drop-down arrow file for style sheets, which can only point at files."""
    path = Path(tempfile.gettempdir()) / "pycapslap_chevron.png"
    _render(_ICONS["chevron"], "#a1a1aa", 16).save(str(path))
    return path.as_posix()


TILE_QSS = """
QToolButton#tile {
    background-color: #27272a; border: 1px solid #3f3f46; border-radius: 8px;
    color: #e4e4e7; font-size: 11px; font-weight: 500; padding: 3px 4px;
}
QToolButton#tile:hover { background-color: #3f3f46; border-color: #52525b; color: #ffffff; }
QToolButton#tile:pressed { background-color: #18181b; border-color: #3f3f46; }
QToolButton#tile:checked { background-color: #312e81; border-color: #6366f1; color: #ffffff; }
QToolButton#tile:checked:hover { background-color: #3730a3; }
QToolButton#tile:disabled { background-color: #1c1c1f; border-color: #27272a; color: #52525b; }
QToolButton#tile:focus { border-color: #6366f1; }
QToolButton[popupMode="2"] { padding-right: 14px; }
QToolButton::menu-indicator { subcontrol-origin: padding; subcontrol-position: right center; right: 4px; width: 8px; }
QToolButton#primary {
    background-color: #4f46e5; border: 1px solid #818cf8; border-radius: 8px;
    color: #ffffff; font-size: 12px; font-weight: 700; padding: 3px 4px;
}
QToolButton#primary:hover { background-color: #6366f1; border-color: #a5b4fc; }
QToolButton#primary:pressed { background-color: #4338ca; border-color: #6366f1; }
QToolButton#primary:disabled { background-color: #1c1c1f; border-color: #27272a; color: #52525b; }
"""

# Plain QPushButtons in the panels: the same quiet look as a tile, one size down.
SMALL_QSS = """
QPushButton { background-color: #27272a; border: 1px solid #3f3f46; border-radius: 6px;
    color: #e4e4e7; font-size: 11px; padding: 2px 8px; }
QPushButton:hover { background-color: #3f3f46; border-color: #52525b; color: #ffffff; }
QPushButton:pressed { background-color: #18181b; }
QPushButton:checked { background-color: #312e81; border-color: #6366f1; color: #ffffff; }
QPushButton:disabled { background-color: #1c1c1f; border-color: #27272a; color: #52525b; }
"""

# One height for every control in a row: tiles, combo boxes, small buttons.
ROW_HEIGHT = 28


def tile(
    text: str,
    icon_name: str,
    tooltip: str = "",
    *,
    primary: bool = False,
    compact: bool = False,
    dense: bool = False,
) -> QToolButton:
    """An icon beside a short label, in a grid it stretches to fill.

    `compact` and `dense` are the short, one-row-high form; without either the
    tile is the tall form with the icon above the label.
    """
    button = QToolButton()
    button.setObjectName("primary" if primary else "tile")
    button.setStyleSheet(TILE_QSS)
    button.setText(text)
    button.setIcon(icon(icon_name))
    button.setToolTip(tooltip)
    if compact or dense:
        button.setIconSize(QSize(16, 16))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        height = ROW_HEIGHT + 6 if primary else ROW_HEIGHT
        button.setMinimumSize(72 if compact else 96, height)
    else:
        button.setStyleSheet(
            TILE_QSS + "QToolButton#tile { padding: 6px 4px 4px 4px; }"
        )
        button.setIconSize(QSize(22, 22))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setMinimumSize(96, 66)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return button


def chip(text: str, tooltip: str = "") -> QToolButton:
    """A checkable text-only toggle, lit while it is the active mode."""
    button = QToolButton()
    button.setObjectName("tile")
    button.setStyleSheet(TILE_QSS)
    button.setText(text)
    button.setCheckable(True)
    button.setToolTip(tooltip)
    button.setMinimumHeight(ROW_HEIGHT)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return button


# The top bar's tiles: same look as tile(), at the short height.
dense_tile = partial(tile, dense=True)
