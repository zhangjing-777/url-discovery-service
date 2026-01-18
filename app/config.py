"""
配置管理模块
支持从环境变量读取数据库连接信息
"""
from pydantic_settings import BaseSettings
from urllib.parse import quote_plus


class Settings(BaseSettings):
    """应用配置"""
    
    # 数据库配置（openGauss 使用 PostgreSQL 协议）
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "password"
    DB_NAME: str = "url_discovery"
    
    # Playwright 服务配置
    PLAYWRIGHT_SERVICE_URL: str
    
    #cds-url-audit-img中的cds_url_audit服务
    AUDIT_URL: str

    # 连接池配置
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 10

    class Config:
        env_file = ".env"
    
    @property
    def database_dsn(self) -> str:
        """构造数据库 DSN"""
        encoded_password = quote_plus(self.DB_PASSWORD)
        return f"postgresql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()