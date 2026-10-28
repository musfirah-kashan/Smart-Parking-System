"""Binary Min Heap (Phase 6).

Stored in a plain list. For the item at index i:
    parent = (i - 1) // 2     left child = 2i + 1     right child = 2i + 2

The smallest key is always at index 0, so peek() is O(1) and
push() / pop_min() are O(log n).

Each entry is (key, value). Only the KEY is compared (never the value), so the
value can be any object. Use a tuple as key to break ties, e.g.
(distance, slot_number).
"""


class MinHeap:
    def __init__(self):
        self._a = []

    # ---------- public API ----------
    def push(self, key, value=None):
        self._a.append((key, value))
        self._sift_up(len(self._a) - 1)

    def pop_min(self):
        """Remove and return (key, value) with the smallest key (extractMin)."""
        if not self._a:
            raise IndexError("pop from empty heap")
        top = self._a[0]
        last = self._a.pop()
        if self._a:
            self._a[0] = last
            self._sift_down(0)
        return top

    def peek(self):
        """Look at the smallest (key, value) without removing it."""
        if not self._a:
            raise IndexError("peek at empty heap")
        return self._a[0]

    def is_empty(self):
        return not self._a

    def __len__(self):
        return len(self._a)

    @classmethod
    def build(cls, entries):
        """Build a heap from a list of (key, value) in O(n) (Floyd's heapify)."""
        heap = cls()
        heap._a = list(entries)
        for i in range(len(heap._a) // 2 - 1, -1, -1):
            heap._sift_down(i)
        return heap

    def copy(self):
        clone = MinHeap()
        clone._a = list(self._a)
        return clone

    # ---------- for the visualiser ----------
    def to_list(self):
        """The raw array, exactly as stored."""
        return list(self._a)

    def levels(self):
        """Array split into tree levels: [[root], [2 nodes], [4 nodes], ...]."""
        out = []
        start, width = 0, 1
        while start < len(self._a):
            out.append(self._a[start:start + width])
            start += width
            width *= 2
        return out

    # ---------- internals ----------
    def _sift_up(self, i):
        a = self._a
        while i > 0:
            parent = (i - 1) // 2
            if a[i][0] < a[parent][0]:
                a[i], a[parent] = a[parent], a[i]
                i = parent
            else:
                break

    def _sift_down(self, i):
        a = self._a
        n = len(a)
        while True:
            left, right = 2 * i + 1, 2 * i + 2
            smallest = i
            if left < n and a[left][0] < a[smallest][0]:
                smallest = left
            if right < n and a[right][0] < a[smallest][0]:
                smallest = right
            if smallest == i:
                break
            a[i], a[smallest] = a[smallest], a[i]
            i = smallest