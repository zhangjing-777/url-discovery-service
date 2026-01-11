"""
数据库连接池管理
使用 psycopg (v3) 直接操作 openGauss / PostgreSQL
"""
import logging
from typing import Optional
import asyncio
import psycopg
from psycopg_pool import AsyncConnectionPool

from app.config import settings

logger = logging.getLogger(__name__)


class Database:
    """数据库连接池管理器（psycopg async）"""

    def __init__(self):
        self.pool: Optional[AsyncConnectionPool] = None

    async def connect(self):
        """创建连接池"""
        logger.info(
            f"正在连接数据库: "
            f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
        )

        try:
            # psycopg 使用连接字符串（dsn）
            self.pool = AsyncConnectionPool(
                conninfo=settings.database_dsn,
                min_size=settings.DB_POOL_MIN_SIZE,
                max_size=settings.DB_POOL_MAX_SIZE,
                timeout=60,
                open=True,
            )

            logger.info("数据库连接池创建成功")

            # ⚠️ 强烈建议：DDL 不放在应用启动
            # 如果你现在还想保留，也可以用
            await self._init_tables()

        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    async def disconnect(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            logger.info("数据库连接池已关闭")

    async def _init_tables(self):
        """初始化数据库表结构（可选）"""
        logger.info("开始初始化数据库表...")

        create_urls_table = """
        CREATE TABLE IF NOT EXISTS web_urls (
            id              BIGSERIAL PRIMARY KEY,
            origin          TEXT NOT NULL,
            discovery_url             TEXT NOT NULL,
            discovery_type  TEXT NOT NULL,
            first_seen_at   TIMESTAMP DEFAULT NOW(),
            last_seen_at    TIMESTAMP DEFAULT NOW(),
            CONSTRAINT uniq_origin_url UNIQUE (origin, discovery_url)
        );
        """

        create_urls_indexes = """
        CREATE INDEX IF NOT EXISTS idx_web_urls_origin ON web_urls(origin);
        CREATE INDEX IF NOT EXISTS idx_web_urls_path ON web_urls(discovery_url);
        """

        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(create_urls_table)
                await cur.execute(create_urls_indexes)

        logger.info("数据库表初始化完成")

    async def save_discovery_result(
        self,
        origin: str,
        discovery_result: dict,
        concurrency: int = 10,
    ):
        sem = asyncio.Semaphore(concurrency)

        async def _save_one(dtype, url):
            async with sem:
                await self.save_url(
                    origin=origin,
                    discovery_url=url,
                    discovery_type=dtype,
                )

        tasks = []

        for discovery_type, urls in discovery_result.items():
            if not isinstance(urls, list):
                continue

            for discovery_url in urls:
                tasks.append(
                    asyncio.create_task(
                        _save_one(discovery_type, discovery_url)
                    )
                )

        await asyncio.gather(*tasks)


    async def save_url(
        self,
        origin: str,
        discovery_url: str,
        discovery_type: str,
    ):
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # 1️⃣ 先尝试插入（不存在才插）
                insert_sql = """
                INSERT INTO web_urls
                    (origin, discovery_url, discovery_type)
                SELECT
                    %s, %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM web_urls
                    WHERE origin = %s AND discovery_url = %s
                )
                """

                await cur.execute(
                    insert_sql,
                    (
                        origin, discovery_url, discovery_type, origin, discovery_url
                    ),
                )

                # 2️⃣ 无论插没插，更新 last_seen_at
                update_sql = """
                UPDATE web_urls
                SET last_seen_at = NOW()
                WHERE origin = %s AND discovery_url = %s
                """

                await cur.execute(update_sql, (origin, discovery_url))




# 全局数据库实例
db = Database()
