"""Priority path crossing: volunteers first, then proportional crowd, leftover slots pipelined."""

from __future__ import annotations

from typing import Callable, List, Sequence, Tuple


def proportional_split(slots: int, demand_a: int, demand_b: int) -> Tuple[int, int]:
    """Hamilton largest remainder, then leftover demand so bandwidth is not wasted.

    Example: 5 waiting at stage vs 10 at stalls, 3 slots -> 1 and 2 (1:2 ratio).
    """
    if slots <= 0 or demand_a + demand_b <= 0:
        return 0, 0
    total = demand_a + demand_b
    raw_a = slots * demand_a / total
    raw_b = slots * demand_b / total
    give_a = int(raw_a)
    give_b = int(raw_b)
    leftover = slots - give_a - give_b
    frac_a = raw_a - give_a
    frac_b = raw_b - give_b
    while leftover > 0:
        if frac_a >= frac_b:
            give_a += 1
            frac_a = -1.0
        else:
            give_b += 1
            frac_b = -1.0
        leftover -= 1
    give_a = min(give_a, demand_a)
    give_b = min(give_b, demand_b)
    unused = slots - give_a - give_b
    if unused > 0:
        extra_a = min(unused, demand_a - give_a)
        give_a += extra_a
        unused -= extra_a
        extra_b = min(unused, demand_b - give_b)
        give_b += extra_b
    return give_a, give_b


def pipeline_consume(
    queue: Sequence[int],
    budget: int,
    try_move: Callable[[int], bool],
) -> Tuple[List[int], int]:
    """Walk the queue in order. A blocked person keeps their place; the next person
    may take the slot (pipeline so bandwidth is not wasted).
    Returns (still_waiting, unused_budget).
    """
    still: List[int] = []
    left = max(0, budget)
    for pid in queue:
        if left <= 0:
            still.append(pid)
            continue
        if try_move(pid):
            left -= 1
        else:
            still.append(pid)
    return still, left

def schedule_path(
    slots: int,
    vol_ids: List[int],
    a_ids: List[int],
    b_ids: List[int]
) -> Tuple[set[int], set[int], set[int]]:
    mv, ma, mb = set(), set(), set()
    left = slots

    # 1. Volunteers priority
    for vid in vol_ids:
        if left > 0:
            mv.add(vid)
            left -= 1
        else:
            break

    # 2. Proportional split for remaining
    if left > 0:
        a_budget, b_budget = proportional_split(left, len(a_ids), len(b_ids))
        
        # We need to pipeline them. If someone can move, they take the budget.
        # But here, schedule_path just decides WHO gets to move based on the budget.
        # It doesn't actually execute the move, so it assumes they CAN move.
        # Actually, in simulation.py, it says:
        # `mv, ma, mb = schedule_path(...)`
        # `if vid in mv: if not send(vid): still_v.append(...)`
        # So we just take the first N from a_ids and b_ids.
        
        for pid in a_ids:
            if a_budget > 0:
                ma.add(pid)
                a_budget -= 1
        for pid in b_ids:
            if b_budget > 0:
                mb.add(pid)
                b_budget -= 1
                
    return mv, ma, mb
