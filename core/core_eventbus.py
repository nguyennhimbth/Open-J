"""Open-J Core Event Bus Module.
Re-exports from core.event_bus for backwards compatibility.
"""

from core.event_bus import EventBus, event_bus

__all__ = ["EventBus", "event_bus"]