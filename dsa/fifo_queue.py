"""FIFO Queue built on a singly linked list (Phase 6, step 1).

    enqueue ->  [Car A] -> [Car B] -> [Car C] -> [Car D]  -> dequeue
                 head                              tail

First come, first served. enqueue / dequeue / peek are all O(1) because we
keep a pointer to both the head and the tail.
"""


class _Node:
    __slots__ = ("value", "next")

    def __init__(self, value):
        self.value = value
        self.next = None


class FifoQueue:
    def __init__(self):
        self._head = None
        self._tail = None
        self._size = 0

    def enqueue(self, value):
        node = _Node(value)
        if self._tail is None:
            self._head = self._tail = node
        else:
            self._tail.next = node
            self._tail = node
        self._size += 1

    def dequeue(self):
        if self._head is None:
            raise IndexError("dequeue from empty queue")
        node = self._head
        self._head = node.next
        if self._head is None:
            self._tail = None
        self._size -= 1
        return node.value

    def peek(self):
        if self._head is None:
            raise IndexError("peek at empty queue")
        return self._head.value

    def is_empty(self):
        return self._size == 0

    def __len__(self):
        return self._size

    def __iter__(self):
        node = self._head
        while node is not None:
            yield node.value
            node = node.next

    def to_list(self):
        return list(self)