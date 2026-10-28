"""Uncapped, branch-preserving project history for one application session."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    value: dict[str, Any]
    parent: int | None = None
    children: list[int] = field(default_factory=list)
    preferred: int | None = None


class History:
    def __init__(self, value: dict[str, Any]):
        self.nodes = [Node(deepcopy(value))]
        self.current = 0

    def record(self, value: dict[str, Any]) -> None:
        if value == self.nodes[self.current].value:
            return
        parent = self.current
        self.current = len(self.nodes)
        self.nodes.append(Node(deepcopy(value), parent))
        self.nodes[parent].children.append(self.current)
        self.nodes[parent].preferred = self.current

    def select(self, index: int) -> dict[str, Any]:
        if not 0 <= index < len(self.nodes):
            raise ValueError("unknown history node")
        child = index
        parent = self.nodes[child].parent
        while parent is not None:
            self.nodes[parent].preferred = child
            child, parent = parent, self.nodes[parent].parent
        self.current = index
        return deepcopy(self.nodes[index].value)

    def undo(self) -> dict[str, Any] | None:
        parent = self.nodes[self.current].parent
        return self.select(parent) if parent is not None else None

    def redo(self) -> dict[str, Any] | None:
        child = self.nodes[self.current].preferred
        return self.select(child) if child is not None else None

    def tips(self) -> list[int]:
        return [i for i, node in enumerate(self.nodes) if not node.children]
