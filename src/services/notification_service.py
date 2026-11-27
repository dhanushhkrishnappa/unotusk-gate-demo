\"\"\"
Compliant Notification Service.
Adheres to ADR-004 by relying purely on domain abstractions
and message event publishers without direct database drivers.
\"\"\"

from dataclasses import dataclass
from typing import Protocol


class EventPublisher(Protocol):
    def publish(self, topic: str, message: dict) -> bool:
        ...


@dataclass
class NotificationService:
    publisher: EventPublisher | None = None

    def dispatch_order_alert(self, order_id: str, recipient: str) -> dict:
        payload = {
            "order_id": order_id,
            "recipient": recipient,
            "status": "DISPATCHED",
        }
        if self.publisher:
            self.publisher.publish("notifications.orders", payload)
        return payload
