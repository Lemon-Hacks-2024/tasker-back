import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    RMQ_HOST: str
    RMQ_PORT: int
    RMQ_USER: str
    RMQ_PASSWORD: str

    RMQ_QUEUE: str

    AXENIX_LOGIN: str
    AXENIX_PASSWORD: str

    BACK_X_KEY: str

    model_config = SettingsConfigDict(env_file=".env")

    @property
    def amqp_url(self):
        return f"amqp://{self.RMQ_USER}:{self.RMQ_PASSWORD}@{self.RMQ_HOST}:{self.RMQ_PORT}"

    @property
    def axenix_auth_data(self):
        return {
            "email": self.AXENIX_LOGIN,
            "password": self.AXENIX_PASSWORD
        }

    @staticmethod
    def setup_logging() -> None:
        """Настройка логирования"""
        import yaml
        import logging.config
        with open("logging.yaml", "r") as f:
            config = yaml.safe_load(f.read())
            logging.config.dictConfig(config)

    @staticmethod
    def setup_architecture():
        """Настройка архитектуры приложения"""
        current_dir = os.getcwd()
        if not os.path.exists(f"{current_dir}/logs"):
            print("Creating")
            os.makedirs(f"{current_dir}/logs/debug/")
            os.makedirs(f"{current_dir}/logs/info/")
            os.makedirs(f"{current_dir}/logs/error/")
            os.makedirs(f"{current_dir}/logs/warning/")
        else:
            print("Directories exists")


settings = Settings()
