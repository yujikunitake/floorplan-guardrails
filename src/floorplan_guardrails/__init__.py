"""floorplan-guardrails: geração de plantas baixas com verificação determinística."""

from floorplan_guardrails.rules import RulesError, Ruleset, load_rules
from floorplan_guardrails.schema import (
    EXTERIOR,
    ROOM_TYPES,
    Door,
    FloorPlan,
    Room,
    RoomType,
    Wall,
    Window,
)
from floorplan_guardrails.validator import Violation, validate

__all__ = [
    "EXTERIOR",
    "ROOM_TYPES",
    "Door",
    "FloorPlan",
    "Room",
    "RoomType",
    "Ruleset",
    "RulesError",
    "Violation",
    "Wall",
    "Window",
    "load_rules",
    "validate",
]
