"""Tick engine: movement, incidents, dispatch, reporting."""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Set, Tuple

from dispatch import (
    assign_volunteer,
    manager_for_checkpoint,
    pick_idle_checkpoint,
    return_volunteer,
    sort_open_incidents,
    bfs_distances,
)
from models import (
    STAFF_TYPES,
    Checkpoint,
    Incident,
    IncidentType,
    Manager,
    Person,
    PersonType,
    RANDOM_INCIDENT_TYPES,
    VenueLayout,
    Zone,
    ZoneKind,
    is_crowd,
)
from path_scheduler import pipeline_consume, proportional_split


def build_layout(
    n_gates: int,
    n_stalls: int,
    cap_stage: int,
    cap_stall_area: int,
    cap_desk: int,
    cap_path_storage: int,
    stall_caps: List[int],
    gate_throughputs: List[int],
    path_capacity: int,
) -> Tuple[VenueLayout, List[Tuple[int, str]]]:
    zones: Dict[int, Zone] = {}
    nid = 1

    def add(name: str, kind: ZoneKind, cap: int) -> int:
        nonlocal nid
        zid = nid
        nid += 1
        zones[zid] = Zone(id=zid, name=name, kind=kind, capacity=cap)
        return zid

    stage_id = add("stage", ZoneKind.STAGE, cap_stage)
    stall_area_id = add("stall_area", ZoneKind.STALL_AREA, cap_stall_area)
    path_id = add("path", ZoneKind.PATH, cap_path_storage)
    desk_id = add("lead_desk", ZoneKind.DESK, cap_desk)
    gate_ids = [add(f"gate_{i + 1}", ZoneKind.GATE, 10**9) for i in range(n_gates)]
    stall_ids = [add(f"stall_{i + 1}", ZoneKind.STALL, stall_caps[i]) for i in range(n_stalls)]

    def link(a: int, b: int) -> None:
        zones[a].neighbors.append(b)
        zones[b].neighbors.append(a)

    link(desk_id, stage_id)
    link(stage_id, path_id)
    link(path_id, stall_area_id)
    for g in gate_ids:
        link(g, stage_id)
    for s in stall_ids:
        link(stall_area_id, s)

    adj: Dict[int, Set[int]] = {z.id: set(z.neighbors) for z in zones.values()}
    stage_side = {stage_id, desk_id, *gate_ids}
    stall_side = {stall_area_id, *stall_ids}

    layout = VenueLayout(
        zones=zones,
        stage_id=stage_id,
        stall_area_id=stall_area_id,
        path_id=path_id,
        desk_id=desk_id,
        gate_ids=gate_ids,
        stall_ids=stall_ids,
        gate_throughput={gate_ids[i]: gate_throughputs[i] for i in range(n_gates)},
        path_capacity=path_capacity,
        adj=adj,
        stage_side=stage_side,
        stall_side=stall_side,
    )
    catalog = [(z.id, z.name) for z in zones.values()]
    return layout, catalog


def next_hop(layout: VenueLayout, src: int, dest: int) -> Optional[int]:
    if src == dest:
        return None
    dist = bfs_distances(layout, dest)
    best = None
    best_d = 10**9
    for nb in layout.adj[src]:
        d = dist.get(nb)
        if d is not None and d < best_d:
            best_d = d
            best = nb
    return best


def side_of(layout: VenueLayout, zone_id: int) -> str:
    if zone_id in layout.stage_side:
        return "stage"
    if zone_id in layout.stall_side:
        return "stall"
    return "path"


class Simulation:
    def __init__(
        self,
        layout: VenueLayout,
        people: Dict[int, Person],
        checkpoints: Dict[int, Checkpoint],
        managers: Dict[int, Manager],
        spawn_p: float,
        durations: Dict[IncidentType, int],
        max_ticks: int,
    ) -> None:
        self.layout = layout
        self.people = people
        self.checkpoints = checkpoints
        self.managers = managers
        self.spawn_p = spawn_p
        self.durations = durations
        self.max_ticks = max_ticks
        self.tick = 0
        self.incidents: List[Incident] = []
        self.next_incident_id = 1
        self.fire_stop = False
        self.log: List[str] = []
        self.moved: List[str] = []
        self.messages: List[str] = []
        self.path_wait_vol: List[int] = []
        self.path_wait_a: List[int] = []  # stage -> stalls
        self.path_wait_b: List[int] = []  # stalls -> stage
        self.gate_queues: Dict[int, List[int]] = {g: [] for g in layout.gate_ids}
        self._init_gate_queues()
        self._recount_occupancy()

    def _init_gate_queues(self) -> None:
        for p in self.people.values():
            if p.zone_id in self.layout.gate_ids and is_crowd(p):
                self.gate_queues[p.zone_id].append(p.id)

    def _recount_occupancy(self) -> None:
        for z in self.layout.zones.values():
            z.occupancy = 0
        for p in self.people.values():
            if is_crowd(p):
                self.layout.zones[p.zone_id].occupancy += 1

    def _can_enter(self, person: Person, zone_id: int) -> bool:
        if not is_crowd(person):
            return True
        z = self.layout.zones[zone_id]
        if z.kind == ZoneKind.GATE:
            return True
        return z.remaining() > 0

    def _move_person(self, person: Person, dest: int) -> None:
        old = person.zone_id
        if old == dest:
            return
        if is_crowd(person):
            self.layout.zones[old].occupancy -= 1
            self.layout.zones[dest].occupancy += 1
        person.zone_id = dest
        self.moved.append(f"P{person.id}({person.ptype.value}) {self.layout.zones[old].name} -> {self.layout.zones[dest].name}")

    def _open_duplicate(self, itype: IncidentType, zone_id: int) -> bool:
        return any(
            (not i.resolved) and i.itype == itype and i.zone_id == zone_id for i in self.incidents
        )

    def _spawn_incident(self, itype: IncidentType, zone_id: int, why: str) -> Optional[Incident]:
        if self._open_duplicate(itype, zone_id):
            return None
        inc = Incident(
            id=self.next_incident_id,
            itype=itype,
            zone_id=zone_id,
            created_tick=self.tick,
        )
        self.next_incident_id += 1
        self.incidents.append(inc)
        zname = self.layout.zones[zone_id].name
        self.log.append(f"NEW {itype.value} #{inc.id} at {zname} ({why})")
        if itype == IncidentType.FIRE:
            self.fire_stop = True
            self.log.append("FIRE/EVACUATION: show will stop after this tick.")
        return inc

    def _random_incidents(self) -> None:
        if random.random() >= self.spawn_p:
            return
        itype = random.choice(list(RANDOM_INCIDENT_TYPES))
        zone_id = random.choice(list(self.layout.zones.keys()))
        self._spawn_incident(itype, zone_id, "random")

    def _auto_incidents(self) -> None:
        for z in self.layout.zones.values():
            if z.kind == ZoneKind.GATE:
                continue
            occ = z.occupancy
            if z.kind == ZoneKind.PATH:
                occ = len(self.path_wait_vol) + len(self.path_wait_a) + len(self.path_wait_b)
            if occ > z.capacity:
                self._spawn_incident(IncidentType.OVERCROWDING, z.id, "occupancy > capacity")
        for gid in self.layout.gate_ids:
            q = len(self.gate_queues[gid])
            thr = self.layout.gate_throughput[gid]
            if q > thr:
                self._spawn_incident(IncidentType.GATE_JAM, gid, "gate queue > throughput")

    def _manage_buffers(self) -> None:
        available_buffers = [v for v in self.people.values() if v.is_buffer and v.checkpoint_id is None]
        if not available_buffers:
            return
        
        for cid, cp in self.checkpoints.items():
            if not cp.idle:
                if not available_buffers:
                    break
                dist = bfs_distances(self.layout, cp.zone_id)
                best_v = None
                best_d = float('inf')
                for v in available_buffers:
                    d = dist.get(v.zone_id, float('inf'))
                    if d < best_d:
                        best_d = d
                        best_v = v
                if best_v:
                    available_buffers.remove(best_v)
                    best_v.checkpoint_id = cp.id
                    best_v.home_zone_id = cp.zone_id
                    best_v.destination_id = cp.zone_id
                    cp.idle.append(best_v.id)
                    self.log.append(f"Buffer volunteer {best_v.id} assigned to occupy checkpoint {cp.id}")

    def _dispatch(self) -> None:
        for inc in sort_open_incidents(self.incidents):
            cid = pick_idle_checkpoint(self.layout, self.checkpoints, inc.zone_id)
            if cid is None:
                self.log.append(f"Incident #{inc.id} waiting: no idle volunteer")
                continue
            cp = self.checkpoints[cid]
            vid = assign_volunteer(cp)
            if vid is None:
                continue
            vol = self.people[vid]
            vol.busy = True
            vol.destination_id = inc.zone_id
            inc.assigned_volunteer_id = vid
            inc.assigned_checkpoint_id = cid
            mgr = manager_for_checkpoint(self.managers, cid)
            inc.assigned_manager_id = mgr.id if mgr else None
            mgr_name = mgr.name if mgr else "unassigned"
            zname = self.layout.zones[inc.zone_id].name
            msg = (
                f"LEAD -> {mgr_name} -> checkpoint {cid} -> volunteer {vid} "
                f"(incident #{inc.id} {inc.itype.value} @ {zname})"
            )
            self.messages.append(msg)
            self.log.append(msg)

    def _advance_jobs(self) -> None:
        for inc in self.incidents:
            if inc.resolved or inc.assigned_volunteer_id is None:
                continue
            vol = self.people[inc.assigned_volunteer_id]
            if vol.zone_id != inc.zone_id:
                continue
            if not inc.volunteer_arrived:
                inc.volunteer_arrived = True
                inc.remaining_ticks = self.durations[inc.itype]
                self.log.append(f"Volunteer {vol.id} arrived for incident #{inc.id}; {inc.remaining_ticks} ticks of work")
            assert inc.remaining_ticks is not None
            inc.remaining_ticks -= 1
            if inc.remaining_ticks <= 0:
                inc.resolved = True
                vol.busy = False
                vol.destination_id = vol.home_zone_id
                cp = self.checkpoints[inc.assigned_checkpoint_id]  # type: ignore[index]
                return_volunteer(cp, vol.id)
                self.log.append(
                    f"RESOLVED incident #{inc.id} ({inc.itype.value}); volunteer {vol.id} returns to tail of checkpoint {cp.id}"
                )

    def _needs_path(self, src: int, dest: int) -> bool:
        if dest is None:
            return False
        a, b = side_of(self.layout, src), side_of(self.layout, dest)
        return a != "path" and b != "path" and a != b

    def _enqueue_path_if_needed(self, person: Person) -> bool:
        dest = person.destination_id
        if dest is None or person.zone_id == dest:
            return False
        if not self._needs_path(person.zone_id, dest):
            return False
        direction_to_stalls = side_of(self.layout, person.zone_id) == "stage"
        if person.ptype == PersonType.VOLUNTEER:
            if person.id not in self.path_wait_vol:
                self.path_wait_vol.append(person.id)
            return True
        if direction_to_stalls:
            if person.id not in self.path_wait_a:
                self.path_wait_a.append(person.id)
        else:
            if person.id not in self.path_wait_b:
                self.path_wait_b.append(person.id)
        return True

    def _step_toward(self, person: Person) -> None:
        dest = person.destination_id
        if dest is None or person.zone_id == dest:
            return
        if self._enqueue_path_if_needed(person):
            return
        hop = next_hop(self.layout, person.zone_id, dest)
        if hop is None:
            return
        if hop == self.layout.path_id and dest != self.layout.path_id:
            self._enqueue_path_if_needed(person)
            return
        if not self._can_enter(person, hop):
            return
        self._move_person(person, hop)

    def _plan_movement(self) -> None:
        for p in self.people.values():
            if p.ptype == PersonType.LEAD:
                continue
            if p.zone_id in self.layout.gate_ids and is_crowd(p):
                continue
            if p.destination_id is None:
                continue
            self._step_toward(p)

    def _path_target_zone(self, person: Person, to_stalls: bool) -> int:
        dest = person.destination_id
        if dest == self.layout.path_id:
            return self.layout.path_id
        if to_stalls:
            return self.layout.stall_area_id
        return self.layout.stage_id

    def _apply_path(self) -> None:
        vol_ids = [vid for vid in self.path_wait_vol if vid in self.people]
        a_ids = [pid for pid in self.path_wait_a if pid in self.people]
        b_ids = [pid for pid in self.path_wait_b if pid in self.people]
        
        def send_vol(pid: int) -> bool:
            vol = self.people[pid]
            dest_side = side_of(self.layout, vol.destination_id) if vol.destination_id else "path"
            if dest_side == "stall":
                to_stalls = True
            elif dest_side == "stage":
                to_stalls = False
            else:
                to_stalls = side_of(self.layout, vol.zone_id) == "stage"
            
            target = self._path_target_zone(vol, to_stalls)
            if not self._can_enter(vol, target):
                return False
            self._move_person(vol, target)
            return True

        def send_a(pid: int) -> bool:
            person = self.people[pid]
            target = self._path_target_zone(person, True)
            if not self._can_enter(person, target):
                return False
            self._move_person(person, target)
            return True

        def send_b(pid: int) -> bool:
            person = self.people[pid]
            target = self._path_target_zone(person, False)
            if not self._can_enter(person, target):
                return False
            self._move_person(person, target)
            return True

        still_v, left = pipeline_consume(vol_ids, self.layout.path_capacity, send_vol)
        
        a_budget, b_budget = proportional_split(left, len(a_ids), len(b_ids))
        
        still_a, a_left = pipeline_consume(a_ids, a_budget, send_a)
        still_b, b_left = pipeline_consume(b_ids, b_budget, send_b)
        
        # Leftover pipeline for unused budgets
        extra_budget = a_left + b_left
        if extra_budget > 0:
            still_a, a_extra = pipeline_consume(still_a, extra_budget, send_a)
            still_b, _ = pipeline_consume(still_b, a_extra, send_b)

        self.path_wait_vol = still_v
        self.path_wait_a = still_a
        self.path_wait_b = still_b

    def _apply_gates(self) -> None:
        for gid in self.layout.gate_ids:
            thr = self.layout.gate_throughput[gid]
            remaining_q: List[int] = []
            moved_n = 0
            for pid in self.gate_queues[gid]:
                if moved_n >= thr:
                    remaining_q.append(pid)
                    continue
                person = self.people[pid]
                if not self._can_enter(person, self.layout.stage_id):
                    remaining_q.append(pid)
                    continue
                self._move_person(person, self.layout.stage_id)
                moved_n += 1
            self.gate_queues[gid] = remaining_q

    def step(self) -> None:
        self.tick += 1
        self.log = []
        self.moved = []
        self.messages = []
        self._random_incidents()
        self._auto_incidents()
        self._manage_buffers()
        self._dispatch()
        self._advance_jobs()
        self._plan_movement()
        self._apply_path()
        self._apply_gates()

    def report(self) -> str:
        lines = [f"======== TICK {self.tick} / {self.max_ticks} ========"]
        lines.append("Occupancy (crowd vs capacity):")
        for zid in sorted(self.layout.zones):
            z = self.layout.zones[zid]
            extra = ""
            if z.kind == ZoneKind.PATH:
                w = len(self.path_wait_vol) + len(self.path_wait_a) + len(self.path_wait_b)
                extra = f"  waiters={w}"
            if z.kind == ZoneKind.GATE:
                extra = f"  queue={len(self.gate_queues[z.id])} throughput={self.layout.gate_throughput[z.id]}"
            lines.append(f"  [{z.id}] {z.name}: {z.occupancy}/{z.capacity}{extra}")
        lines.append(
            f"Path queues: volunteers={self.path_wait_vol}  "
            f"stage->stalls={self.path_wait_a}  stalls->stage={self.path_wait_b}  "
            f"slots/tick={self.layout.path_capacity}"
        )
        lines.append("Checkpoints (idle volunteer queue, front first):")
        for cid in sorted(self.checkpoints):
            cp = self.checkpoints[cid]
            zname = self.layout.zones[cp.zone_id].name
            lines.append(f"  CP{cid} @{zname}: {list(cp.idle)}")
        lines.append("Active jobs:")
        active = [i for i in self.incidents if not i.resolved and i.assigned_volunteer_id]
        if not active:
            lines.append("  (none)")
        for i in active:
            zname = self.layout.zones[i.zone_id].name
            lines.append(
                f"  #{i.id} {i.itype.value} @{zname} volunteer={i.assigned_volunteer_id} "
                f"arrived={i.volunteer_arrived} remaining={i.remaining_ticks}"
            )
        lines.append("Open unassigned incidents:")
        waiting = [i for i in self.incidents if not i.resolved and i.assigned_volunteer_id is None]
        if not waiting:
            lines.append("  (none)")
        for i in waiting:
            zname = self.layout.zones[i.zone_id].name
            lines.append(f"  #{i.id} {i.itype.value} @{zname} since tick {i.created_tick}")
        lines.append("Manager messages:")
        if not self.messages:
            lines.append("  (none this tick)")
        for m in self.messages:
            lines.append(f"  {m}")
        lines.append("Events:")
        if not self.log:
            lines.append("  (none)")
        for e in self.log:
            lines.append(f"  {e}")
        lines.append("Moved:")
        if not self.moved:
            lines.append("  (none)")
        for m in self.moved:
            lines.append(f"  {m}")
        if self.fire_stop:
            lines.append("*** EVACUATION in progress — simulation stops after this report. ***")
        return "\n".join(lines)


def create_people(
    layout: VenueLayout,
    n_parents: int,
    n_performers: int,
    n_children: int,
    n_visitors: int,
    n_leads: int,
    checkpoint_specs: List[Tuple[int, int]],
    manager_assigns: List[List[int]],
    buffer_zones: List[int] = None,
) -> Tuple[Dict[int, Person], Dict[int, Checkpoint], Dict[int, Manager]]:
    if buffer_zones is None:
        buffer_zones = []
    people: Dict[int, Person] = {}
    pid = 1
    gates = layout.gate_ids
    gi = 0

    def place_crowd(ptype: PersonType, n: int) -> None:
        nonlocal pid, gi
        for _ in range(n):
            gate = gates[gi % len(gates)]
            gi += 1
            if ptype == PersonType.PERFORMER:
                dest = layout.stage_id
            else:
                dest = layout.stage_id if random.random() < 0.5 else random.choice(layout.stall_ids)
            people[pid] = Person(id=pid, ptype=ptype, zone_id=gate, destination_id=dest)
            pid += 1

    place_crowd(PersonType.PARENT, n_parents)
    place_crowd(PersonType.PERFORMER, n_performers)
    place_crowd(PersonType.CHILD, n_children)
    place_crowd(PersonType.VISITOR, n_visitors)

    for _ in range(n_leads):
        people[pid] = Person(
            id=pid,
            ptype=PersonType.LEAD,
            zone_id=layout.desk_id,
            destination_id=layout.desk_id,
            home_zone_id=layout.desk_id,
        )
        pid += 1

    checkpoints: Dict[int, Checkpoint] = {}
    for i, (zone_id, nvol) in enumerate(checkpoint_specs, start=1):
        cp = Checkpoint(id=i, zone_id=zone_id)
        for _ in range(nvol):
            people[pid] = Person(
                id=pid,
                ptype=PersonType.VOLUNTEER,
                zone_id=zone_id,
                destination_id=None,
                home_zone_id=zone_id,
                checkpoint_id=i,
            )
            cp.idle.append(pid)
            pid += 1
        checkpoints[i] = cp

    managers: Dict[int, Manager] = {}
    for i, cp_ids in enumerate(manager_assigns, start=1):
        home = checkpoints[cp_ids[0]].zone_id if cp_ids else layout.stage_id
        managers[i] = Manager(id=i, name=f"Manager {i}", checkpoint_ids=list(cp_ids), zone_id=home)
        people[pid] = Person(
            id=pid,
            ptype=PersonType.AREA_MANAGER,
            zone_id=home,
            destination_id=home,
            home_zone_id=home,
        )
        pid += 1

    for z_id in buffer_zones:
        people[pid] = Person(
            id=pid,
            ptype=PersonType.VOLUNTEER,
            zone_id=z_id,
            destination_id=None,
            home_zone_id=z_id,
            is_buffer=True,
            home_area_id=z_id,
        )
        pid += 1

    return people, checkpoints, managers
