import hashlib
from pathlib import Path

from app.services.broll import net, sources
from app.services.broll.assets import Asset


def fetch(a: Asset, folder: Path, *, cancel=None, progress=None) -> Path:
    """Fetch an asset into `folder`, once; the name comes from its URL."""
    # Resolve metadata with the same cancellation/timeout budget as media.
    if cancel is not None and a.resolver:
        import json

        a = sources.RESOLVERS[a.resolver](
            a,
            fetch=lambda url, params=None: json.loads(
                net.get(url, params, cancel=cancel)
            ),
        )
    else:
        a = sources.resolve(a)
    folder.mkdir(parents=True, exist_ok=True)
    ext = Path(a.url.split("?")[0]).suffix or ".bin"
    dest = folder / f"{hashlib.sha1(a.url.encode()).hexdigest()[:16]}{ext}"
    if not dest.exists():
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            net.download(a.url, tmp, cancel=cancel, progress=progress)
            tmp.replace(dest)
        finally:
            tmp.unlink(missing_ok=True)
    return dest
