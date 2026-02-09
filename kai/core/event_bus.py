"""
Event Bus - The Nervous System of Kai
======================================

LEARNING POINT: Observer Pattern (aka Publish-Subscribe)
---------------------------------------------------------
The Event Bus is one of the most powerful design patterns in software.
It allows different parts of your system to communicate WITHOUT knowing
about each other.

HOW IT WORKS:
  1. A module "subscribes" to an event type (e.g., "voice_detected")
  2. Another module "publishes" that event when something happens
  3. The Event Bus delivers the event to all subscribers
  4. Neither module needs to import or know about the other

WHY THIS MATTERS:
  - Modules stay independent (loose coupling)
  - You can add new features without modifying existing code (Open/Closed Principle)
  - Easy to test each module in isolation

REAL WORLD ANALOGY:
  Think of a radio station (publisher) and radios (subscribers).
  The station broadcasts. Any radio tuned to that frequency receives it.
  The station doesn't need to know how many radios are listening.

EXAMPLE USAGE:
    bus = EventBus()

    # Subscribe: "When you hear 'greeting', call this function"
    async def on_greeting(data):
        print(f"Hello, {data['name']}!")

    bus.subscribe("greeting", on_greeting)

    # Publish: "Hey everyone, a greeting happened!"
    await bus.publish("greeting", {"name": "Jazz"})
    # Output: Hello, Jazz!
"""

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine


# Type alias for readability — a handler is an async function that
# takes a dict and returns nothing
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """
    Central event bus that enables publish-subscribe communication
    between modules.

    LEARNING POINT: defaultdict
    ----------------------------
    `defaultdict(list)` automatically creates an empty list for any
    key that doesn't exist yet. So you can do:
        self._subscribers["new_event"].append(handler)
    without first checking if "new_event" exists.
    """

    def __init__(self):
        # Maps event names to lists of handler functions
        # Example: {"voice_detected": [handler1, handler2], "motion_detected": [handler3]}
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

        # Keeps a log of recent events for debugging
        self._event_history: list[dict[str, Any]] = []
        self._max_history = 100

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        Register a handler function to be called when an event occurs.

        Args:
            event_type: The name of the event to listen for (e.g., "voice_command")
            handler: An async function to call when this event is published
        """
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a previously registered handler."""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(handler)

    async def publish(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """
        Publish an event to all subscribers.

        LEARNING POINT: asyncio.gather
        --------------------------------
        `asyncio.gather(*tasks)` runs multiple async functions concurrently.
        This means ALL handlers for an event run at the same time, not one
        after another. This is much faster when you have multiple subscribers.

        Args:
            event_type: The name of the event
            data: Optional dictionary of event data
        """
        if data is None:
            data = {}

        # Add metadata to every event
        event = {
            "type": event_type,
            "data": data,
        }

        # Store in history for debugging
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)  # Remove oldest

        # Call all handlers for this event type concurrently
        handlers = self._subscribers.get(event_type, [])
        if handlers:
            results = await asyncio.gather(
                *(handler(data) for handler in handlers),
                return_exceptions=True,  # Don't let one failing handler crash the rest
            )
            # Log any exceptions from handlers
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    import traceback
                    tb = ''.join(traceback.format_exception(type(result), result, result.__traceback__))
                    print(f"[EventBus] Handler error for '{event_type}': {tb}")

    def get_history(self) -> list[dict[str, Any]]:
        """Return the recent event history (useful for debugging)."""
        return list(self._event_history)

    @property
    def subscriber_count(self) -> dict[str, int]:
        """Return how many handlers are registered per event type."""
        return {event: len(handlers) for event, handlers in self._subscribers.items()}
