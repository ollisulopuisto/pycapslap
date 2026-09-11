from pathlib import Path

from PySide6.QtGui import QFontDatabase

_LOADED = False
_AVAILABLE_FONTS: list[str] = []


def init_app_fonts() -> list[str]:
    """
    Load bundled fonts from rust/src/fonts into QFontDatabase.
    Returns prioritized list of available font family names.
    """
    global _LOADED, _AVAILABLE_FONTS
    if _LOADED:
        return _AVAILABLE_FONTS

    fonts_dir = Path(__file__).resolve().parents[2] / "rust" / "src" / "fonts"
    found_families = set()
    if fonts_dir.exists():
        for font_path in sorted(fonts_dir.glob("*.ttf")):
            fid = QFontDatabase.addApplicationFont(str(font_path))
            if fid >= 0:
                for family in QFontDatabase.applicationFontFamilies(fid):
                    found_families.add(family)

    preferred_order = [
        "Montserrat",
        "Komika Axis",
        "Roboto",
        "Poppins",
        "Kanit",
        "THE BOLD FONT",
        "Bebas Neue",
        "Luckiest Guy",
        "Permanent Marker",
        "Bangers",
        "Fredoka",
        "Lilita One",
        "Lato",
        "Raleway",
        "Oswald",
        "Cinzel",
        "Caveat Brush",
        "Amatic SC",
        "Chewy",
        "Patrick Hand",
        "Playfair Display",
    ]
    ordered = [f for f in preferred_order if f in found_families]
    for f in sorted(found_families):
        if f not in ordered:
            ordered.append(f)

    _AVAILABLE_FONTS = ordered
    _LOADED = True
    return _AVAILABLE_FONTS
