"""
数据库连接池管理
使用 psycopg (v3) 直接操作 openGauss / PostgreSQL
"""
import logging
from typing import Optional
import asyncio
from psycopg.rows import dict_row
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
            source_type TEXT NOT NULL,
            tags TEXT DEFAULT NULL,
            first_seen_at   TIMESTAMP DEFAULT NOW(),
            last_seen_at    TIMESTAMP DEFAULT NOW(),
            CONSTRAINT uniq_origin_url UNIQUE (origin, discovery_url)
        );
        """

        create_urls_indexes = """
        CREATE INDEX IF NOT EXISTS idx_web_urls_origin ON web_urls(origin);
        CREATE INDEX IF NOT EXISTS idx_web_urls_path ON web_urls(discovery_url);
        CREATE INDEX IF NOT EXISTS idx_web_source_type ON web_urls(source_type);
        CREATE INDEX IF NOT EXISTS idx_web_urls_source_time ON web_urls(source_type, first_seen_at, last_seen_at);
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
        source_type: str,
        tags: str,
        concurrency: int = 10,
    ):
        sem = asyncio.Semaphore(concurrency)

        async def _save_one(dtype, url):
            async with sem:
                await self.save_url(
                    origin=origin,
                    discovery_url=url,
                    discovery_type=dtype,
                    source_type=source_type,
                    tags=tags,
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
        source_type: str,
        tags: str
    ):
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # 1️⃣ 先尝试插入（不存在才插）
                insert_sql = """
                INSERT INTO web_urls
                    (origin, discovery_url, discovery_type, source_type, tags)
                SELECT
                    %s, %s, %s, %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM web_urls
                    WHERE origin = %s AND discovery_url = %s
                )
                """

                await cur.execute(
                    insert_sql,
                    (
                        origin, discovery_url, discovery_type, source_type, tags, 
                        origin, discovery_url
                    ),
                )

                # 2️⃣ 无论插没插，更新 last_seen_at
                update_sql = """
                UPDATE web_urls
                SET last_seen_at = NOW()
                WHERE origin = %s AND discovery_url = %s
                """

                await cur.execute(update_sql, (origin, discovery_url))

    async def get_all_for_source_type(self, source_type: str):
        sql = """
        SELECT *
        FROM web_urls
        WHERE source_type = %s
        ORDER BY first_seen_at ASC
        """

        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, (source_type,))
                rows = await cur.fetchall()

        return rows
    
    async def get_recent_for_source_type(self, source_type: str):
        sql = """
        SELECT *
        FROM web_urls
        WHERE source_type = %s
          AND last_seen_at - first_seen_at <= INTERVAL '5 minute'
        ORDER BY first_seen_at ASC
        """

        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, (source_type,))
                rows = await cur.fetchall()

        return rows

    async def get_needed_discovery_urls(self, origin: str, exclude_suffixes:list[str]):
        """
        获取短时间内新增的 URL，
        并排除确定为静态资源的后缀（以 list 形式维护）
        """

        sql = """
        SELECT discovery_url
        FROM web_urls
        WHERE origin = %s
        AND NOT EXISTS (
                SELECT 1
                FROM unnest(%s::text[]) AS ext
                WHERE discovery_url ILIKE '%%' || ext
                OR discovery_url ILIKE '%%' || ext || '?%%'
            )
        ORDER BY first_seen_at ASC
        """

        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, (origin, exclude_suffixes))
                rows = await cur.fetchall()

        return [row["discovery_url"] for row in rows]


# 全局数据库实例
db = Database()
