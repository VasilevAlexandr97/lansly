from redis._parsers.encoders import Encoder
from redis.commands.core import AsyncScript


class MemoryRedis:
    """Минимальный транспорт для настоящего Redis Lock без сервера."""

    def __init__(self):
        self.values = {}
        self.acquires = self.releases = 0

    def get_encoder(self):
        return Encoder("utf-8", "strict", decode_responses=False)

    def register_script(self, script):
        return AsyncScript(self, script)

    async def set(self, name, token, nx=False, px=None):
        del px
        if nx and name in self.values:
            return False
        self.values[name] = token
        self.acquires += 1
        return True

    async def evalsha(self, sha, numkeys, name, token):
        del sha, numkeys
        if self.values.get(name) != token:
            return 0
        del self.values[name]
        self.releases += 1
        return 1


class NotificationStore:
    def __init__(self):
        self.rows = []

    async def bulk_insert(self, rows):
        self.rows.extend(rows)


class NotificationProjects:
    def __init__(self, projects):
        self.projects, self.calls = projects, []

    async def get_projects_by_ids(self, project_ids, **kwargs):
        self.calls.append((project_ids, kwargs))
        return [p for p in self.projects if p.id in project_ids]


class Recipients:
    def __init__(self, users):
        self.users, self.categories = users, []

    async def get_users_followed_to_category(self, category_id):
        self.categories.append(category_id)
        return self.users


class Filters:
    def __init__(self):
        self.words, self.prices = {}, {}

    async def get_stop_words_by_user_ids(self, ids):
        return {uid: self.words[uid] for uid in ids if uid in self.words}

    async def get_filter_by_user_ids(self, ids):
        return {uid: self.prices[uid] for uid in ids if uid in self.prices}


class Notifier:
    def __init__(self):
        self.sent = []
        self.fail_chats = set()
        self.fail_next = 0

    async def send_message(self, **kwargs):
        if self.fail_next:
            self.fail_next -= 1
            raise RuntimeError("Telegram unavailable")
        if kwargs["chat_id"] in self.fail_chats:
            raise RuntimeError("Telegram unavailable")
        self.sent.append(kwargs)
