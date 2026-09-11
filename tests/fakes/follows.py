from datetime import UTC, datetime
from uuid import uuid7

from lansly.preferences.models import UserCategoryFollow


class Identity:
    def __init__(self):
        self.user_id = uuid7()

    async def get_current_user_id(self):
        return self.user_id


class Subscription:
    def __init__(self, pro=False):
        self.pro = pro
        self.users = []

    async def is_pro_user(self, user_id):
        self.users.append(user_id)
        return self.pro


class FollowGateway:
    def __init__(self, categories=()):
        self.categories = {c.id: c for c in categories}
        self.follows = {}
        self.added = []
        self.error = None
        self.count_override = None
        self.source_counts = {}
        self.direction_counts = []
        self.calls = []

    def seed(self, user_id, category_id, active=True):
        row = UserCategoryFollow(
            user_id=user_id,
            category_id=category_id,
            is_active=active,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            updated_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        self.follows[user_id, category_id] = row
        return row

    async def get_category(self, category_id):
        return self.categories.get(category_id)

    async def get(self, user_id, category_id):
        return self.follows.get((user_id, category_id))

    async def add(self, row):
        if self.error:
            raise self.error
        self.added.append(row)
        self.follows[row.user_id, row.category_id] = row

    async def get_count_followed_categories(self, user_id):
        if self.count_override is not None:
            return self.count_override
        return sum(
            row.is_active
            for (uid, _), row in self.follows.items()
            if uid == user_id
        )

    async def get_subcategories_with_follow_status(self, user_id, parent_id):
        self.calls.append(("subcategories", user_id, parent_id))
        return [
            (
                c,
                bool(
                    (row := self.follows.get((user_id, c.id)))
                    and row.is_active,
                ),
            )
            for c in self.categories.values()
            if c.parent_id == parent_id
        ]

    async def deactivate_all(self, user_id):
        self.calls.append(("deactivate", user_id))
        for (uid, _), row in self.follows.items():
            if uid == user_id:
                row.is_active = False

    async def get_followed_category_counts_by_source(self, user_id):
        self.calls.append(("sources", user_id))
        return self.source_counts

    async def get_directions_with_follow_counts(self, user_id, source):
        self.calls.append(("directions", user_id, source))
        return self.direction_counts
