"""Route planner (Phase 8): connects the Graph to the real parking slots.

The roads are fixed. Every slot from the database is attached to one of the
last sections (D, E, F), and its distance is the walk from that section.
"""
from .graph import Graph

ROADS = [
    ("Entrance", "A", 10),
    ("Entrance", "C", 100),  
    ("A", "B", 20),
    ("A", "C", 15),
    ("B", "D", 10),
    ("B", "E", 12),
    ("C", "F", 18),
]
SECTIONS = ["D", "E", "F"]


def build_lot(slots):
    g = Graph()
    for a, b, d in ROADS:
        g.add_edge(a, b, d)
    for i, s in enumerate(slots):
        g.add_edge(SECTIONS[i % len(SECTIONS)], s.slot_number, max(s.distance or 0, 1))
    return g


def plan_route(slots, target):
    """Returns BFS and Dijkstra results for Entrance -> target, or None."""
    g = build_lot(slots)
    if target not in g.adj:
        return None
    bfs = g.bfs_path("Entrance", target)
    dist, best = g.dijkstra("Entrance", target)
    return {
        "bfs_path": bfs,
        "bfs_m": g.path_length(bfs),
        "dij_path": best,
        "dij_m": dist,
    }