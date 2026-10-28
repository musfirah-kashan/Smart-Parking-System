"""Unit tests for the data structures.   Run from the project folder:

    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dsa import HashTable, MinHeap, FifoQueue, PriorityQueue


class HashTableTests(unittest.TestCase):
    def test_put_get_update_remove(self):
        h = HashTable()
        h.put("ABC123", "P17")
        h.put("XYZ456", "P24")
        self.assertEqual(h.get("ABC123"), "P17")
        h.put("ABC123", "P99")                      # update, size must not grow
        self.assertEqual(len(h), 2)
        self.assertEqual(h.get("ABC123"), "P99")
        self.assertTrue(h.remove("XYZ456"))
        self.assertFalse(h.remove("XYZ456"))
        self.assertIsNone(h.get("XYZ456"))

    def test_resize_keeps_every_key(self):
        h = HashTable(capacity=4)
        for i in range(500):
            h.put(f"CAR{i}", i)
        self.assertGreater(h.resize_count, 0)
        self.assertEqual(len(h), 500)
        self.assertTrue(all(h.get(f"CAR{i}") == i for i in range(500)))
        self.assertLessEqual(h.stats()["load_factor"], 0.75)

    def test_collisions_are_chained(self):
        h = HashTable(capacity=4, max_load=100)     # never resize -> force collisions
        for i in range(20):
            h.put(f"K{i}", i)
        self.assertGreater(h.stats()["longest_chain"], 1)
        self.assertTrue(all(h.get(f"K{i}") == i for i in range(20)))


class MinHeapTests(unittest.TestCase):
    def test_pops_in_sorted_order(self):
        heap = MinHeap()
        for d in [50, 20, 80, 30, 10, 60]:
            heap.push((d,), f"P{d}")
        self.assertEqual(heap.peek()[1], "P10")
        self.assertEqual([heap.pop_min()[1] for _ in range(6)],
                         ["P10", "P20", "P30", "P50", "P60", "P80"])
        self.assertTrue(heap.is_empty())

    def test_build_equals_push(self):
        data = [((d, f"S{d}"), d) for d in [9, 4, 7, 1, 8, 2, 6]]
        built = MinHeap.build(data)
        out = [built.pop_min()[1] for _ in range(len(data))]
        self.assertEqual(out, sorted(d for _, d in data))

    def test_tie_break_by_second_key_part(self):
        heap = MinHeap.build([((5.0, "B2"), 2), ((5.0, "A1"), 1)])
        self.assertEqual(heap.pop_min()[1], 1)

    def test_empty_errors(self):
        with self.assertRaises(IndexError):
            MinHeap().pop_min()


class QueueTests(unittest.TestCase):
    def test_fifo(self):
        q = FifoQueue()
        for car in "ABCD":
            q.enqueue(car)
        self.assertEqual(q.peek(), "A")
        self.assertEqual([q.dequeue() for _ in range(4)], list("ABCD"))
        self.assertTrue(q.is_empty())

    def test_priority_queue_order_and_stability(self):
        pq = PriorityQueue()
        pq.push("normal-1", 4, order=1)
        pq.push("vip", 3, order=2)
        pq.push("normal-2", 4, order=3)
        pq.push("emergency", 0, order=4)
        pq.push("ev", 2, order=5)
        self.assertEqual([x for _, x in pq.ordered()],
                         ["emergency", "ev", "vip", "normal-1", "normal-2"])
        self.assertEqual(len(pq), 5)                # ordered() must not consume
        self.assertEqual(pq.pop(), "emergency")


if __name__ == "__main__":
    unittest.main()