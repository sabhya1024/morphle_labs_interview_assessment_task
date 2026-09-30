"""Core entities for the venue simulation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional, Set


class PersonType(str, Enum):
    PARENT = "parent"
    PERFORMER = "performer"
    CHILD = "child"
    VISITOR = "visitor"
    LEAD = "lead"
    AREA_MANAGER = "area_manager"
    VOLUNTEER = "volunteer"


STAFF_TYPES = {
    PersonType.LEAD,
    PersonType.AREA_MANAGER,
    PersonType.VOLUNTEER,
}


class IncidentType(str, Enum):
    FIRE = "fire/evac"
    MEDICAL = "medical"
    FIGHTING = "fighting"
    LOST_CHILD = "lost child"
    OVERCROWDING = "overcrowding"
    GATE_JAM = "gate jam"
    FOOD_SHORTAGE = "food shortage"


INCIDENT_PRIORITY = {
    IncidentType.FIRE: 0,
    IncidentType.MEDICAL: 1,
    IncidentType.FIGHTING: 2,
    IncidentType.LOST_CHILD: 3,
    IncidentType.OVERCROWDING: 4,
    IncidentType.GATE_JAM: 5,
    IncidentType.FOOD_SHORTAGE: 6,
}

RANDOM_INCIDENT_TYPES = (
    IncidentType.FIRE,
    IncidentType.MEDICAL,
    IncidentType.FIGHTING,
    IncidentType.LOST_CHILD,
    IncidentType.OVERCROWDING,
    IncidentType.GATE_JAM,
    IncidentType.FOOD_SHORTAGE,
)


class ZoneKind(str, Enum):
    STAGE = "stage"
    STALL_AREA = "stall_area"
    PATH = "path"
    DESK = "desk"
    GATE = "gate"
    STALL = "stall"


@dataclass
class Zone:
    id: int
    name: str
    kind: ZoneKind
    capacity: int
    neighbors: List[int] = field(default_factory=list)
    occupancy: int = 0  # crowd only (non-staff)

    def remaining(self) -> int:
        return max(0, self.capacity - self.occupancy)


@dataclass
class Person:
    id: int
    ptype: PersonType
    zone_id: int
    destination_id: Optional[int] = None
    home_zone_id: Optional[int] = None
    checkpoint_id: Optional[int] = None
    busy: bool = False
    is_buffer: bool = False
    home_area_id: Optional[int] = None  # original zone for buffer volunteers


@dataclass
class Checkpoint:
    id: int
    zone_id: int
    idle: Deque[int] = field(default_factory=deque)  # volunteer person ids


@dataclass
class Manager:
    id: int
    name: str
    checkpoint_ids: List[int]
    zone_id: int


@dataclass
class Incident:
    id: int
    itype: IncidentType
    zone_id: int
    created_tick: int
    assigned_volunteer_id: Optional[int] = None
    assigned_checkpoint_id: Optional[int] = None
    assigned_manager_id: Optional[int] = None
    volunteer_arrived: bool = False
    remaining_ticks: Optional[int] = None
    resolved: bool = False


@dataclass
class Job:
    incident_id: int
    volunteer_id: int
    checkpoint_id: int


@dataclass
class VenueLayout:
    zones: Dict[int, Zone]
    stage_id: int
    stall_area_id: int
    path_id: int
    desk_id: int
    gate_ids: List[int]
    stall_ids: List[int]
    gate_throughput: Dict[int, int]
    path_capacity: int
    adj: Dict[int, Set[int]]
    stage_side: Set[int]
    stall_side: Set[int]


def is_crowd(person: Person) -> bool:
    return person.ptype not in STAFF_TYPES
