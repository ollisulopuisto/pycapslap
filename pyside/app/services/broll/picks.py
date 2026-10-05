"""A person's decisions over the proposals: accept one candidate, or reject."""

from typing import Any

from app.services.broll.assets import Asset


class Picks:
    def __init__(self, proposals: list[dict[str, Any]]):
        self._p = proposals
        self.status: list[str] = [
            w.get("status") or ("pending" if w.get("chosen") is None else "accepted")
            for w in proposals
        ]

    def accept(self, window: int, candidate: int) -> None:
        cands = self._p[window]["candidates"]
        if not 0 <= candidate < len(cands):
            raise IndexError(f"window {window} has no candidate {candidate}")
        self._p[window]["chosen"] = candidate
        self.status[window] = "accepted"

    def reject(self, window: int) -> None:
        self._p[window]["chosen"] = None
        self.status[window] = "rejected"

    def pending(self) -> list[int]:
        return [i for i, s in enumerate(self.status) if s == "pending"]

    def accepted(self) -> list[tuple[dict[str, Any], Asset]]:
        return [
            (w, Asset.from_dict(w["candidates"][w["chosen"]]))
            for w, s in zip(self._p, self.status, strict=True)
            if s == "accepted"
        ]

    def data(self) -> list[dict[str, Any]]:
        return [{**w, "status": s} for w, s in zip(self._p, self.status, strict=True)]
