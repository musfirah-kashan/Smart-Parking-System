def merge_sort(items, key=lambda x: x, reverse=False):
    """Merge Sort. Time: O(n log n). Returns a new sorted list."""
    if len(items) <= 1:
        return list(items)

    mid = len(items) // 2
    left = merge_sort(items[:mid], key, reverse)
    right = merge_sort(items[mid:], key, reverse)
    return _merge(left, right, key, reverse)


def _merge(left, right, key, reverse):
    result = []
    i = j = 0

    while i < len(left) and j < len(right):
        a, b = key(left[i]), key(right[j])
        take_left = a >= b if reverse else a <= b
        if take_left:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1

    result.extend(left[i:])
    result.extend(right[j:])
    return result


if __name__ == "__main__":
    data = [50, 230, 80, 120, 50]
    print("Before    :", data)
    print("Ascending :", merge_sort(data))
    print("Descending:", merge_sort(data, reverse=True))