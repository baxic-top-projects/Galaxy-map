from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any


class GalaxyGraphService:
    """Hypercorridor adjacency graph from a galaxy index payload (DB/API or file)."""

    def __init__(self, payload: dict[str, Any] | Path):
        if isinstance(payload, Path):
            import json

            data = json.loads(payload.read_text(encoding="utf-8"))
        else:
            data = payload
        self.systems = {row["id"]: row for row in data.get("systems", []) if row.get("id")}
        self.edges = data.get("edgesDisplay") or data.get("edgesCanon") or []
        self.adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in self.edges:
            a = edge.get("a")
            b = edge.get("b")
            if not a or not b or a == b:
                continue
            if a not in self.systems or b not in self.systems:
                continue
            self.adjacency[a].add(b)
            self.adjacency[b].add(a)
        self.seed_ids = [
            system_id
            for system_id, system in self.systems.items()
            if system.get("kind") in {"star", "black_hole", "well"}
        ]
        if not self.seed_ids:
            self.seed_ids = list(self.systems)

    def neighbors(self, system_id: str) -> set[str]:
        return self.adjacency.get(system_id, set())

    def systems_within_hops(self, origin_id: str, max_hops: int) -> dict[str, int]:
        if origin_id not in self.systems:
            return {}
        hops = {origin_id: 0}
        queue = deque([origin_id])
        while queue:
            current = queue.popleft()
            current_hops = hops[current]
            if current_hops >= max_hops:
                continue
            for neighbor in self.neighbors(current):
                if neighbor in hops:
                    continue
                hops[neighbor] = current_hops + 1
                queue.append(neighbor)
        return hops
