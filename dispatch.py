"""Incident priority dispatch to nearest checkpoint with a round-robin volunteer queue."""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

from models import (
    INCIDENT_PRIORITY,
    Checkpoint,
    Incident,
    Manager,
    VenueLayout,
)


def bfs_distances(layout: VenueLayout, start: int) -> Dict[int, int]:
    dist = {start: 0}
    q = deque([start])
    while q:
        u = q.popleft()
        for v in layout.adj.get(u, ()):
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


def nearest_checkpoints_order(
    layout: VenueLayout,
    checkpoints: Dict[int, Checkpoint],
    incident_zone_id: int,
) -> List[int]:
    """Checkpoint ids sorted by hop distance of their attached zone, then id."""
    dist = bfs_distances(layout, incident_zone_id)
    items: List[Tuple[int, int, int]] = []
    for cid, cp in checkpoints.items():
        d = dist.get(cp.zone_id, 10**9)
        items.append((d, cid, cp.zone_id))
    items.sort()
    return [cid for _, cid, _ in items]


def manager_for_checkpoint(managers: Dict[int, Manager], checkpoint_id: int) -> Optional[Manager]:
    for m in managers.values():
        if checkpoint_id in m.checkpoint_ids:
            return m
    return None


def pick_idle_checkpoint(
    layout: VenueLayout,
    checkpoints: Dict[int, Checkpoint],
    incident_zone_id: int,
) -> Optional[int]:
    for cid in nearest_checkpoints_order(layout, checkpoints, incident_zone_id):
        if checkpoints[cid].idle:
            return cid
    return None


def sort_open_incidents(incidents: List[Incident]) -> List[Incident]:
    open_ones = [i for i in incidents if not i.resolved and i.assigned_volunteer_id is None]
    open_ones.sort(key=lambda i: (INCIDENT_PRIORITY[i.itype], i.created_tick, i.id))
    return open_ones


def assign_volunteer(
    checkpoint: Checkpoint,
) -> Optional[int]:
    if not checkpoint.idle:
        return None
    return checkpoint.idle.popleft()


def return_volunteer(checkpoint: Checkpoint, volunteer_id: int) -> None:
    checkpoint.idle.append(volunteer_id)
