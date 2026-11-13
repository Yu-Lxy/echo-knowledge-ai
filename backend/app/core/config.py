"""集中配置。业务配置项在 M1 随 ORM/存储层补充，环境变量禁止硬编码。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    app_name: str = "Echo Knowledge AI"
    debug: bool = False


settings = Settings()
