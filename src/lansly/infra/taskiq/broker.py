from taskiq import SimpleRetryMiddleware, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from lansly.main.config import config

result_backend = RedisAsyncResultBackend(
    redis_url=config.redis.connection_url,
    result_ex_time=3600,
)
broker = RedisStreamBroker(
    url=config.redis.connection_url,
).with_result_backend(result_backend)

notification_broker = RedisStreamBroker(
    url=config.redis.connection_url,
    queue_name="project-notifications",
    consumer_group_name="project-notifications",
    consumer_id="0",
    xread_count=1,
    unacknowledged_lock_timeout=60,
).with_middlewares(
    SimpleRetryMiddleware(default_retry_count=3),
)

scheduler = TaskiqScheduler(broker, sources=[LabelScheduleSource(broker)])
