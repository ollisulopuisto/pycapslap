"""Local opt-in style profile, shared by the LibreOffice UI and adapter."""
import json
import os
from pathlib import Path
import tempfile


def settings_path():
    return Path(os.path.expanduser(os.environ.get('PUNAKYNA_CONFIG', '~/.config/punakyna'))) / 'style.json'


def load_profile():
    from punakyna.style import StyleProfile
    try:
        return StyleProfile.from_value(json.loads(settings_path().read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError):
        return StyleProfile()


def save_profile(profile):
    from dataclasses import asdict
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix='.style-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(asdict(profile), out, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
