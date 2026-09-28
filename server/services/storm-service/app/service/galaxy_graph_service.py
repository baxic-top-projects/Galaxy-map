from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path


class GalaxyGraphService:
    """Loads galaxy-index.json and exposes the hypercorridor adjacency graph."""

    def __init__(self, index_path: Path):
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        self.systems = {row["id"]: row for row in payload.get("systems", [])}
        self.edges = payload.get("edgesDisplay") or payload.get("edgesCanon") or []
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
