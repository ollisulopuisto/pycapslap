import json
from pathlib import Path

from app.models.captions import CaptionStyle


class PresetManager:
    """
    Manages saving and loading custom user style presets (font, color, karaoke, etc.)
    allowing preferences to be stored permanently across shows and sessions.
    """

    def __init__(self, storage_path: Path | str | None = None) -> None:
        if storage_path is not None:
            self.storage_path = Path(storage_path)
        else:
            config_dir = Path.home() / ".config" / "pycapslap"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.storage_path = config_dir / "presets.json"

        self._presets: dict[str, CaptionStyle] = {}
        self._default_style: CaptionStyle | None = None
        # Entries whose field types did not parse on load, kept verbatim and
        # written back on save so a hand-edit typo is not silently deleted.
        self._skipped_presets: dict[str, dict] = {}
        self._skipped_default_style: dict | None = None
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                custom_dict = data.get("presets", {})
                for name, s_dict in custom_dict.items():
                    if not isinstance(s_dict, dict):
                        continue
                    try:
                        self._presets[name] = CaptionStyle.from_dict(s_dict)
                    except (TypeError, ValueError):
                        # A malformed typed field must not crash startup.
                        self._skipped_presets[name] = s_dict
                def_dict = data.get("default_style")
                if isinstance(def_dict, dict):
                    try:
                        self._default_style = CaptionStyle.from_dict(def_dict)
                    except (TypeError, ValueError):
                        self._skipped_default_style = def_dict
        except (OSError, json.JSONDecodeError):
            pass

    def _save(self) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "presets": {
                    # Valid entries win on name collision; skipped entries pass
                    # through byte-identical so no data is lost on save.
                    **self._skipped_presets,
                    **{name: style.to_dict() for name, style in self._presets.items()},
                },
                "default_style": (
                    self._default_style.to_dict()
                    if self._default_style
                    else self._skipped_default_style
                ),
            }
            self.storage_path.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def list_presets(self) -> list[str]:
        return sorted(self._presets.keys())

    def get_preset(self, name: str) -> CaptionStyle | None:
        style = self._presets.get(name)
        if style:
            # Return a copy to avoid mutation
            return CaptionStyle.from_dict(style.to_dict())
        return None

    def save_preset(self, name: str, style: CaptionStyle) -> None:
        # Clone style
        clone = CaptionStyle.from_dict(style.to_dict())
        clone.template_id = name
        self._presets[name] = clone
        self._skipped_presets.pop(name, None)
        self._save()

    def delete_preset(self, name: str) -> bool:
        removed = name in self._skipped_presets
        self._skipped_presets.pop(name, None)
        if name in self._presets:
            del self._presets[name]
            removed = True
        if removed:
            self._save()
        return removed

    def save_default_style(self, style: CaptionStyle) -> None:
        self._default_style = CaptionStyle.from_dict(style.to_dict())
        self._skipped_default_style = None
        self._save()

    def get_default_style(self) -> CaptionStyle | None:
        if self._default_style:
            return CaptionStyle.from_dict(self._default_style.to_dict())
        return None
