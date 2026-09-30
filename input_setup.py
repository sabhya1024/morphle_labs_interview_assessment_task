"""Validated CLI prompts for venue setup."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from models import IncidentType, RANDOM_INCIDENT_TYPES


def ask_int(prompt: str, minimum: int = 0, maximum: Optional[int] = None) -> int:
    while True:
        raw = input(f"{prompt} ").strip()
        try:
            value = int(raw)
        except ValueError:
            print("  Enter an integer.")
            continue
        if value < minimum:
            print(f"  Must be >= {minimum}.")
            continue
        if maximum is not None and value > maximum:
            print(f"  Must be <= {maximum}.")
            continue
        return value


def ask_float(prompt: str, minimum: float = 0.0, maximum: float = 1.0) -> float:
    while True:
        raw = input(f"{prompt} ").strip()
        try:
            value = float(raw)
        except ValueError:
            print("  Enter a number.")
            continue
        if value < minimum or value > maximum:
            print(f"  Must be between {minimum} and {maximum}.")
            continue
        return value


def ask_id_list(prompt: str, allowed: List[int], expect_count: Optional[int] = None) -> List[int]:
    allowed_set = set(allowed)
    while True:
        raw = input(f"{prompt} ").strip()
        if not raw:
            ids: List[int] = []
        else:
            try:
                ids = [int(p) for p in raw.replace(",", " ").split()]
            except ValueError:
                print("  Enter space- or comma-separated integers.")
                continue
        if expect_count is not None and len(ids) != expect_count:
            print(f"  Enter exactly {expect_count} id(s).")
            continue
        if any(i not in allowed_set for i in ids):
            print(f"  Allowed ids: {allowed}")
            continue
        if len(ids) != len(set(ids)):
            print("  Duplicate ids are not allowed.")
            continue
        return ids


def collect_setup() -> dict:
    print("=== Venue operations simulation — setup ===")
    max_ticks = ask_int("Max ticks:", minimum=1)
    print("\n-- Crowd (total people coming) --")
    total_people = ask_int("Total people coming (parents + performers + children + visitors):", minimum=0)
    while True:
        n_parents = ask_int("  of which parents:", minimum=0)
        n_performers = ask_int("  of which performers:", minimum=0)
        n_children = ask_int("  of which children:", minimum=0)
        n_visitors = ask_int("  of which general visitors:", minimum=0)
        summed = n_parents + n_performers + n_children + n_visitors
        if summed == total_people:
            break
        print(f"  Those four counts sum to {summed}, not {total_people}. Enter them again.")
    print("\n-- Staff --")
    print("  One lead manager at the desk (you).")
    n_area_mgrs = ask_int("Number of area managers:", minimum=1)
    n_volunteers_total_hint = ask_int(
        "Expected duty volunteers (must match the sum you assign to checkpoints next):",
        minimum=1,
    )
    n_buffers = ask_int("Buffer volunteers (cover a checkpoint when all duty volunteers there are busy):", minimum=0)

    print("\n-- Layout sizes --")
    n_gates = ask_int("Number of gates:", minimum=1)
    n_stalls = ask_int("Number of stalls:", minimum=1)
    n_checkpoints = ask_int("Number of checkpoints:", minimum=1)
    if n_area_mgrs > n_checkpoints:
        print("  Note: more managers than checkpoints; some managers may own none until you assign.")

    print("\n-- Capacities --")
    cap_stage = ask_int("Stage area capacity:", minimum=0)
    cap_stall_area = ask_int("Stall area (plaza) capacity:", minimum=0)
    cap_desk = ask_int("Lead desk capacity (staff sitting there):", minimum=1)
    cap_path_storage = ask_int(
        "Path waiting-area capacity (overcrowding if waiters exceed this; 0 = use path throughput):",
        minimum=0,
    )
    stall_caps: List[int] = []
    for i in range(n_stalls):
        stall_caps.append(ask_int(f"Capacity of stall {i + 1}:", minimum=0))
    gate_throughputs: List[int] = []
    for i in range(n_gates):
        gate_throughputs.append(ask_int(f"Gate {i + 1} throughput (people per tick into stage):", minimum=0))
    path_capacity = ask_int("Path slots per tick:", minimum=0)
    if cap_path_storage == 0:
        cap_path_storage = max(path_capacity, 1)

    print("\nZone ids will be printed after the map is built. Checkpoints attach to those ids.")

    spawn_p = ask_float("Random incident probability per tick (0.0–1.0):", 0.0, 1.0)
    print("\n-- Resolution duration (ticks) per incident type --")
    durations: Dict[IncidentType, int] = {}
    for itype in RANDOM_INCIDENT_TYPES:
        durations[itype] = ask_int(f"Ticks to resolve {itype.value}:", minimum=1)

    return {
        "max_ticks": max_ticks,
        "n_parents": n_parents,
        "n_performers": n_performers,
        "n_children": n_children,
        "n_visitors": n_visitors,
        "n_leads": 1,
        "n_area_mgrs": n_area_mgrs,
        "n_volunteers_expected": n_volunteers_total_hint,
        "n_buffers": n_buffers,
        "n_gates": n_gates,
        "n_stalls": n_stalls,
        "n_checkpoints": n_checkpoints,
        "cap_stage": cap_stage,
        "cap_stall_area": cap_stall_area,
        "cap_desk": cap_desk,
        "cap_path_storage": cap_path_storage,
        "stall_caps": stall_caps,
        "gate_throughputs": gate_throughputs,
        "path_capacity": path_capacity,
        "spawn_p": spawn_p,
        "durations": durations,
    }


def collect_checkpoints_and_managers(
    n_checkpoints: int,
    n_area_mgrs: int,
    n_volunteers_expected: int,
    zone_catalog: List[Tuple[int, str]],
    n_buffers: int,
) -> Tuple[List[Tuple[int, int]], List[List[int]], List[int]]:
    """Returns checkpoint specs, manager assignments, and buffer station zone ids."""
    print("\n-- Zone catalog --")
    allowed = []
    for zid, name in zone_catalog:
        print(f"  {zid}: {name}")
        allowed.append(zid)

    print("\n-- Checkpoints --")
    cps: List[Tuple[int, int]] = []
    vol_sum = 0
    for i in range(n_checkpoints):
        zid = ask_int(f"Checkpoint {i + 1} attached to zone id:", minimum=min(allowed), maximum=max(allowed))
        while zid not in allowed:
            print(f"  Zone id must be one of {allowed}.")
            zid = ask_int(f"Checkpoint {i + 1} attached to zone id:", minimum=min(allowed), maximum=max(allowed))
        nvol = ask_int(f"Volunteers at checkpoint {i + 1}:", minimum=0)
        cps.append((zid, nvol))
        vol_sum += nvol

    if vol_sum != n_volunteers_expected:
        print(
            f"  Volunteer sum at checkpoints is {vol_sum}, expected {n_volunteers_expected}. "
            "Using the checkpoint sum."
        )
    if vol_sum < 1:
        print("  Need at least one volunteer; placing 1 at checkpoint 1.")
        z0, _ = cps[0]
        cps[0] = (z0, 1)

    cp_ids = list(range(1, n_checkpoints + 1))
    print("\n-- Managers (each owns one or more checkpoint ids) --")
    print(f"  Checkpoint ids: {cp_ids}")
    owned: set[int] = set()
    mgr_assigns: List[List[int]] = []
    for i in range(n_area_mgrs):
        remaining = [c for c in cp_ids if c not in owned]
        if i == n_area_mgrs - 1 and remaining:
            print(f"  Last manager receives leftover checkpoints {remaining}.")
            ids = remaining
        else:
            ids = ask_id_list(
                f"Manager {i + 1} checkpoint ids (from remaining {remaining}):",
                remaining if remaining else cp_ids,
            )
            ids = [x for x in ids if x not in owned]
        mgr_assigns.append(ids)
        owned.update(ids)

    leftover = [c for c in cp_ids if c not in owned]
    if leftover:
        print(f"  Unassigned checkpoints {leftover} given to manager 1.")
        mgr_assigns[0].extend(leftover)

    buffer_zones: List[int] = []
    if n_buffers > 0:
        print("\n-- Buffer volunteers (stationed in different areas) --")
        for i in range(n_buffers):
            zid = ask_int(f"Buffer volunteer {i + 1} stationed at zone id:", minimum=min(allowed), maximum=max(allowed))
            while zid not in allowed:
                print(f"  Zone id must be one of {allowed}.")
                zid = ask_int(f"Buffer volunteer {i + 1} stationed at zone id:", minimum=min(allowed), maximum=max(allowed))
            buffer_zones.append(zid)

    return cps, mgr_assigns, buffer_zones
