from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int
    API_HASH: str

    BLACKLIST_TASK: list[str] = ['Compete for $100k Airdrop in PVP battles in Pixelton', 'Play MONEY DOGS',
                                 'Play Captain Tsubasa RIVALS on TON!']
    USE_REF: bool = False
    REF_ID: str = ''

    USE_PROXY_FROM_FILE: bool = False

    # 新增 SLEEP_BETWEEN_START 配置
    SLEEP_BETWEEN_START: list[int] = [10, 60]

    # 一次请求随机点击的次数
    CLICK_COUNT: list[int] = [100, 250]

settings = Settings()


