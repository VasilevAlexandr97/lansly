from abc import abstractmethod
from datetime import datetime
from typing import Protocol
from uuid import UUID

from lansly.notifications.models import (
    ChannelNotification,
    ProjectNotification,
)


class ProjectNotificationQueue(Protocol):
    @abstractmethod
    async def enqueue(self, project_ids: list[UUID]) -> None:
        raise NotImplementedError


class ProposalGeneratedNotificationQueue(Protocol):
    @abstractmethod
    async def enqueue_succeeded(self, user_id: UUID, project_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def enqueue_failed(self, user_id: UUID) -> None:
        raise NotImplementedError


class SubscriptionActivatedNotificationQueue(Protocol):
    @abstractmethod
    async def enqueue(self, user_id: UUID) -> None:
        raise NotImplementedError


class SubscriptionRenewalNotificationQueue(Protocol):
    @abstractmethod
    async def enqueue_renewed(
        self,
        user_id: UUID,
        new_expires_at: datetime,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def enqueue_retry(
        self,
        user_id: UUID,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def enqueue_revoked(self, user_id: UUID) -> None:
        raise NotImplementedError


class ProjectNotificationGateway:
    @abstractmethod
    async def bulk_upsert(
        self,
        notifications: list[ProjectNotification],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get(
        self,
        project_id: UUID,
        user_id: UUID,
    ) -> ProjectNotification | None:
        raise NotImplementedError


class ChannelNotificationGateway:
    @abstractmethod
    async def bulk_insert(
        self,
        notifications: list[ChannelNotification],
    ) -> None:
        raise NotImplementedError
