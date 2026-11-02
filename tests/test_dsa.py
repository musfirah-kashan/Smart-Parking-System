"""Unit tests for the data structures.   Run from the project folder:

    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock
from dsa import HashTable, MinHeap, FifoQueue, PriorityQueue
from dsa import parking_engine as pe


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

class AllocationScoringTests(unittest.TestCase):
    """Phase 10: score = distance + TYPE_PENALTY * (rank of the slot type)."""

    def _pick(self, vehicle_type, priority, **slots):
        """slots example: vip=[(100, "V1")], normal=[(10, "N1")]  -> (distance, number)."""
        heaps = {t: MinHeap.build([((d, n), n) for d, n in items])
                 for t, items in slots.items()}
        vehicle = SimpleNamespace(vehicle_type=vehicle_type, priority=priority)
        with mock.patch.object(pe, "db") as fake_db:
            fake_db.session.get.side_effect = lambda model, slot_id: slot_id
            return pe.pick_best_slot(vehicle, heaps), heaps

    def test_much_nearer_normal_beats_far_vip_slot(self):
        slot, _ = self._pick("Car", "VIP", vip=[(100, "V1")], normal=[(10, "N1")])
        self.assertEqual(slot, "N1")             # 10 + penalty < 100

    def test_slightly_farther_vip_slot_still_wins(self):
        slot, _ = self._pick("Car", "VIP", vip=[(30, "V1")], normal=[(10, "N1")])
        self.assertEqual(slot, "V1")             # 30 < 10 + penalty

    def test_equal_score_keeps_the_better_type(self):
        slot, _ = self._pick("Car", "Disabled",
                             handicapped=[(pe.TYPE_PENALTY, "H1")],
                             normal=[(0, "N1")])
        self.assertEqual(slot, "H1")             # strict < : tie goes to type 0

    def test_normal_vehicle_never_gets_a_special_slot(self):
        slot, _ = self._pick("Car", "Normal",
                             vip=[(1, "V1")], ev=[(1, "E1")],
                             normal=[(50, "N1"), (20, "N2")])
        self.assertEqual(slot, "N2")             # nearest NORMAL slot

    def test_bike_prefers_bike_bay(self):
        slot, _ = self._pick("Bike", "Normal", bike=[(10, "B1")], normal=[(5, "N1")])
        self.assertEqual(slot, "B1")

    def test_nothing_free_returns_none(self):
        slot, _ = self._pick("Car", "EV", normal=[])
        self.assertIsNone(slot)

    def test_only_the_winning_heap_is_popped(self):
        slot, heaps = self._pick("Car", "VIP", vip=[(30, "V1"), (60, "V2")],
                                 normal=[(10, "N1")])
        self.assertEqual(slot, "V1")
        self.assertEqual(len(heaps["vip"]), 1)   # V1 removed
        self.assertEqual(len(heaps["normal"]), 1)  # untouched


class DynamicPriorityTests(unittest.TestCase):
    """Phase 10: aging - after AGING_MINUTES a vehicle moves up, at most MAX_BOOST levels."""

    NOW = datetime(2026, 11, 1, 12, 0)

    def _rank(self, base, waited_minutes):
        return pe.effective_rank(base, self.NOW - timedelta(minutes=waited_minutes), self.NOW)

    def test_no_boost_before_the_first_period(self):
        self.assertEqual(self._rank(4, 0), 4)
        self.assertEqual(self._rank(4, pe.AGING_MINUTES - 1), 4)

    def test_one_level_after_the_first_period(self):
        self.assertEqual(self._rank(4, pe.AGING_MINUTES), 4 - min(1, pe.MAX_BOOST))

    def test_boost_is_capped_at_max_boost(self):
        long_wait = 10 * pe.AGING_MINUTES
        self.assertEqual(self._rank(4, long_wait), 4 - pe.MAX_BOOST)
        self.assertEqual(self._rank(3, long_wait), 3 - pe.MAX_BOOST)

    def test_nobody_drops_below_rank_1(self):
        self.assertEqual(self._rank(1, 10 * pe.AGING_MINUTES), 1)

    def test_emergency_stays_on_top(self):
        self.assertEqual(self._rank(0, 10 * pe.AGING_MINUTES), 0)

    def test_missing_join_time_means_no_boost(self):
        self.assertEqual(pe.effective_rank(4, None, self.NOW), 4)

    def test_fresh_vip_still_beats_a_normal_that_has_not_waited_long(self):
        pq = PriorityQueue()
        pq.push("normal", self._rank(4, pe.AGING_MINUTES - 1), order=1)
        pq.push("vip", 3, order=2)
        self.assertEqual([x for _, x in pq.ordered()], ["vip", "normal"])

    def test_aged_normal_never_passes_disabled_or_emergency(self):
        pq = PriorityQueue()
        pq.push("old-normal", self._rank(4, 10 * pe.AGING_MINUTES), order=1)
        pq.push("new-disabled", 1, order=2)
        pq.push("emergency", 0, order=3)
        ranked = [x for _, x in pq.ordered()]
        self.assertEqual(ranked[:2], ["emergency", "new-disabled"])
        self.assertEqual(ranked[-1], "old-normal")


if __name__ == "__main__":
    unittest.main()