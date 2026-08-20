from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    username: str | None = None
    is_pro: bool = False
    is_admin: bool = False
