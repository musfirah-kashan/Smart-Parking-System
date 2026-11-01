"""Parking lot graph (Phase 8): BFS and Dijkstra.

Nodes are places (Entrance, sections, slots). Edges are roads, and each road
has a length in metres. Roads can be driven both ways.

BFS      -> fewest roads (ignores distance).
Dijkstra -> shortest total distance. Uses the MinHeap from min_heap.py.
"""
from .fifo_queue import FifoQueue
from .min_heap import MinHeap


class Graph:
    def __init__(self):
        self.adj = {}          # node -> list of (neighbour, distance)

    def add_edge(self, a, b, distance):
        self.adj.setdefault(a, []).append((b, distance))
        self.adj.setdefault(b, []).append((a, distance))

    def bfs_path(self, start, goal):
        """Path with the fewest edges. Time: O(V + E)."""
        if start not in self.adj or goal not in self.adj:
            return None

        parent = {start: None}
        queue = FifoQueue()
        queue.enqueue(start)

        while not queue.is_empty():
            node = queue.dequeue()
            if node == goal:
                break
            for neighbour, _ in self.adj[node]:
                if neighbour not in parent:
                    parent[neighbour] = node
                    queue.enqueue(neighbour)

        if goal not in parent:
            return None
        return _build_path(parent, goal)

    def dijkstra(self, start, goal):
        """Returns (total_distance, path) of the shortest route.
        Time: O((V + E) log V) with a binary heap."""
        if start not in self.adj or goal not in self.adj:
            return None

        dist = {start: 0}
        parent = {start: None}
        done = set()

        heap = MinHeap()
        heap.push((0, start), start)

        while not heap.is_empty():
            (d, node), _ = heap.pop_min()
            if node in done:
                continue
            done.add(node)
            if node == goal:
                break
            for neighbour, length in self.adj[node]:
                new_d = d + length
                if neighbour not in dist or new_d < dist[neighbour]:
                    dist[neighbour] = new_d
                    parent[neighbour] = node
                    heap.push((new_d, neighbour), neighbour)

        if goal not in done:
            return None
        return dist[goal], _build_path(parent, goal)

    def path_length(self, path):
        total = 0
        for a, b in zip(path, path[1:]):
            for neighbour, length in self.adj[a]:
                if neighbour == b:
                    total += length
                    break
        return total


def _build_path(parent, goal):
    path = []
    node = goal
    while node is not None:
        path.append(node)
        node = parent[node]
    path.reverse()
    return path


def build_parking_lot():
    """The lot from the project plan, plus one long direct road
    (Entrance - C) so BFS and Dijkstra give different answers."""
    g = Graph()
    g.add_edge("Entrance", "A", 10)
    g.add_edge("Entrance", "C", 100)
    g.add_edge("A", "B", 20)
    g.add_edge("A", "C", 15)
    g.add_edge("B", "D", 10)
    g.add_edge("B", "E", 12)
    g.add_edge("C", "F", 18)
    g.add_edge("D", "P1", 5)
    g.add_edge("E", "P2", 8)
    g.add_edge("F", "P3", 6)
    return g


if __name__ == "__main__":
    lot = build_parking_lot()
    for target in ("P1", "P3"):
        bfs = lot.bfs_path("Entrance", target)
        dist, best = lot.dijkstra("Entrance", target)
        print(f"To {target}:")
        print("  BFS      :", " -> ".join(bfs), f"({lot.path_length(bfs)} m)")
        print("  Dijkstra :", " -> ".join(best), f"({dist} m)")