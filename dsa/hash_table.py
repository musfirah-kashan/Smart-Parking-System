"""Hash Table with separate chaining (Phase 5).

Concept:   key  ->  hash function  ->  bucket index  ->  chain of nodes

    "ABC123" -> hash -> bucket 7 -> [ABC123 -> info] -> [XYZ456 -> info]

Average cost of put / get / remove is O(1). Worst case is O(n) if every key
lands in the same bucket, but the table doubles its size whenever the load
factor passes 0.75, so chains stay short.
"""


class _Node:
    __slots__ = ("key", "value", "next")

    def __init__(self, key, value, nxt=None):
        self.key = key
        self.value = value
        self.next = nxt


class HashTable:
    def __init__(self, capacity=16, max_load=0.75):
        self._capacity = max(4, capacity)
        self._buckets = [None] * self._capacity
        self._size = 0
        self._max_load = max_load
        self.resize_count = 0
        self.last_probes = 0      # how many chain nodes the last get() looked at

    # ---------- hash function ----------
    def _hash(self, key):
        """djb2 string hash: h = h * 33 + character."""
        h = 5381
        for ch in str(key):
            h = (h * 33 + ord(ch)) & 0xFFFFFFFF
        return h % self._capacity

    # ---------- core operations ----------
    def put(self, key, value):
        """Insert a key, or overwrite its value if the key already exists."""
        idx = self._hash(key)
        node = self._buckets[idx]
        while node is not None:
            if node.key == key:
                node.value = value
                return
            node = node.next

        # new key goes at the head of the chain (O(1))
        self._buckets[idx] = _Node(key, value, self._buckets[idx])
        self._size += 1

        if self._size / self._capacity > self._max_load:
            self._resize()

    def get(self, key, default=None):
        idx = self._hash(key)
        node = self._buckets[idx]
        probes = 0
        while node is not None:
            probes += 1
            if node.key == key:
                self.last_probes = probes
                return node.value
            node = node.next
        self.last_probes = max(probes, 1)
        return default

    def remove(self, key):
        """Delete a key. Returns True if it existed."""
        idx = self._hash(key)
        node = self._buckets[idx]
        prev = None
        while node is not None:
            if node.key == key:
                if prev is None:
                    self._buckets[idx] = node.next
                else:
                    prev.next = node.next
                self._size -= 1
                return True
            prev = node
            node = node.next
        return False

    def contains(self, key):
        sentinel = object()
        return self.get(key, sentinel) is not sentinel

    # ---------- resizing ----------
    def _resize(self):
        """Double the number of buckets and re-insert every node."""
        old = self._buckets
        self._capacity *= 2
        self._buckets = [None] * self._capacity
        self._size = 0
        self.resize_count += 1
        for head in old:
            node = head
            while node is not None:
                self.put(node.key, node.value)
                node = node.next

    # ---------- helpers ----------
    def items(self):
        for head in self._buckets:
            node = head
            while node is not None:
                yield node.key, node.value
                node = node.next

    def keys(self):
        for k, _ in self.items():
            yield k

    def values(self):
        for _, v in self.items():
            yield v

    def __len__(self):
        return self._size

    def __contains__(self, key):
        return self.contains(key)

    def stats(self):
        """Numbers shown on the DSA Lab page."""
        used = 0
        longest = 0
        for head in self._buckets:
            if head is not None:
                used += 1
                length = 0
                node = head
                while node is not None:
                    length += 1
                    node = node.next
                longest = max(longest, length)
        return {
            "capacity": self._capacity,
            "size": self._size,
            "load_factor": round(self._size / self._capacity, 2),
            "used_buckets": used,
            "longest_chain": longest,
            "resizes": self.resize_count,
        }

    def bucket_view(self, limit=12):
        """First `limit` non-empty buckets as (index, [keys in chain])."""
        rows = []
        for idx, head in enumerate(self._buckets):
            if head is None:
                continue
            chain = []
            node = head
            while node is not None:
                chain.append(node.key)
                node = node.next
            rows.append((idx, chain))
            if len(rows) >= limit:
                break
        return rows