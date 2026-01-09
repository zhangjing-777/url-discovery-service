"""
配置管理模块
支持从环境变量读取数据库连接信息
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""
    
    # 数据库配置（openGauss 使用 PostgreSQL 协议）
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "password"
    DB_NAME: str = "url_discovery"
    
    # 连接池配置
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 10

    # Playwright 服务配置
    PLAYWRIGHT_SERVICE_URL: str = "http://localhost:8000"
    
    # 爬虫默认配置
    DEFAULT_MAX_DEPTH: int = 3
    DEFAULT_MAX_PAGES: int = 1000
    
    class Config:
        env_file = ".env"
    
    @property
    def database_dsn(self) -> str:
        """构造数据库 DSN"""
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()