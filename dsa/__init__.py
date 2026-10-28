"""Hand-written data structures used by the Smart Parking System.

Nothing in this package uses Python's built-in dict/heapq/queue for the
actual algorithm - every structure is implemented from scratch so it can be
explained in the DSA viva.
"""
from .hash_table import HashTable
from .min_heap import MinHeap
from .fifo_queue import FifoQueue
from .priority_queue import PriorityQueue

__all__ = ["HashTable", "MinHeap", "FifoQueue", "PriorityQueue"]