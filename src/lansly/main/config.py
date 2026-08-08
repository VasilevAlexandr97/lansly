import logging
import os

from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent.parent.parent.parent.resolve()


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    user: str
    password: str
    database: str

    @property
    def connection_url(self):
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @property
    def psycopg_connection_url(self):
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass(frozen=True)
class RedisConfig:
    host: str
    port: str
    password: str

    @property
    def connection_url(self):
        return f"redis://:{self.password}@{self.host}:{self.port}"

    @property
    def async_connection_url(self):
        return f"async+{self.connection_url}"


@dataclass(frozen=True)
class TelegramBotConfig:
    token: str


@dataclass(frozen=True)
class KworkConfig:
    login: str
    password: str
    ref_id: int | None = None


@dataclass(frozen=True)
class PolzaConfig:
    api_key: str
    base_url: str


@dataclass(frozen=True)
class YookassaConfig:
    shop_id: str
    secret_key: str


@dataclass(frozen=True)
class WebConfig:
    templates_dir: Path = (
        PROJECT_DIR / "src" / "lansly" / "apps" / "web" / "templates"
    )
    static_dir: Path = (
        PROJECT_DIR / "src" / "lansly" / "apps" / "web" / "static"
    )


@dataclass(frozen=True)
class AdminPanelConfig:
    session_secret_key: str
    session_ttl: int = 86400


@dataclass(frozen=True)
class Config:
    postgres: PostgresConfig
    redis: RedisConfig
    telegram_bot: TelegramBotConfig
    kwork: KworkConfig
    polza: PolzaConfig
    yookassa: YookassaConfig
    admin_panel: AdminPanelConfig
    web: WebConfig
    telegram_channel_id: int | None = None
    debug: bool = field(default=False)


def get_required_env(env_var: str) -> str:
    value = os.getenv(env_var)
    if not value:
        raise ValueError(f"Environment variable {env_var} is required")
    return value


def get_optional_env(env_var: str) -> str | None:
    return os.getenv(env_var)


def get_config() -> Config:
    telegram_channel_id = get_optional_env("TELEGRAM_CHANNEL_ID")
    if telegram_channel_id is not None:
        channel_id = int(telegram_channel_id)
        if channel_id >= 0:
            logger.warning(
                f"TELEGRAM_CHANNEL_ID={channel_id} "
                "should be negative for Telegram channel",
            )
            telegram_channel_id = None
        else:
            telegram_channel_id = channel_id
    kwork_ref_id = get_optional_env("KWORK_REF_ID")
    if kwork_ref_id is not None:
        kwork_ref_id = int(kwork_ref_id)
    return Config(
        postgres=PostgresConfig(
            host=get_required_env("POSTGRES_HOST"),
            port=int(get_required_env("POSTGRES_PORT")),
            user=get_required_env("POSTGRES_USER"),
            password=get_required_env("POSTGRES_PASSWORD"),
            database=get_required_env("POSTGRES_DATABASE"),
        ),
        redis=RedisConfig(
            host=get_required_env("REDIS_HOST"),
            port=get_required_env("REDIS_PORT"),
            password=get_required_env("REDIS_PASSWORD"),
        ),
        telegram_bot=TelegramBotConfig(
            token=get_required_env("TELEGRAM_BOT_TOKEN"),
        ),
        kwork=KworkConfig(
            login=get_required_env("KWORK_USERNAME"),
            password=get_required_env("KWORK_PASSWORD"),
            ref_id=kwork_ref_id,
        ),
        polza=PolzaConfig(
            api_key=get_required_env("POLZA_API_KEY"),
            base_url=get_required_env("POLZA_BASE_URL"),
        ),
        yookassa=YookassaConfig(
            shop_id=get_required_env("YOOKASSA_SHOP_ID"),
            secret_key=get_required_env("YOOKASSA_SECRET_KEY"),
        ),
        admin_panel=AdminPanelConfig(
            session_secret_key=get_required_env(
                "ADMIN_PANEL_SESSION_SECRET_KEY",
            ),
            session_ttl=int(get_required_env("ADMIN_PANEL_SESSION_TTL")),
        ),
        web=WebConfig(),
        telegram_channel_id=telegram_channel_id,
        debug=get_optional_env("DEBUG") in ("True", "true", "1"),
    )


config = get_config()
