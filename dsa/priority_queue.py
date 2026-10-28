"""Priority Queue built on the MinHeap (Phase 6, step 3).

Smaller number = more important. Every entry gets the key (rank, order):

    rank   -> priority class (0 = Emergency ... 4 = Normal)
    order  -> arrival number, so two vehicles with the SAME rank are served
              first-come-first-served (the queue stays "stable").

push() / pop() are O(log n), peek() is O(1).
"""
from .min_heap import MinHeap


class PriorityQueue:
    def __init__(self):
        self._heap = MinHeap()
        self._counter = 0

    def push(self, item, rank, order=None):
        if order is None:
            self._counter += 1
            order = self._counter
        self._heap.push((rank, order), item)

    def pop(self):
        """Remove and return the most important item."""
        _, item = self._heap.pop_min()
        return item

    def peek(self):
        return self._heap.peek()[1]

    def is_empty(self):
        return self._heap.is_empty()

    def __len__(self):
        return len(self._heap)

    def ordered(self):
        """Items in the order they WOULD be served (does not change the queue)."""
        clone = self._heap.copy()
        out = []
        while not clone.is_empty():
            key, item = clone.pop_min()
            out.append((key[0], item))
        return out