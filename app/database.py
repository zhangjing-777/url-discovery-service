"""
数据库连接池管理
使用 asyncpg 直接操作 openGauss（PostgreSQL 协议）
"""
import asyncpg
import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)


class Database:
    """数据库连接池管理器"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """创建连接池"""
        logger.info(f"正在连接数据库: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
        
        try:
            self.pool = await asyncpg.create_pool(
                dsn=settings.database_dsn,
                min_size=settings.DB_POOL_MIN_SIZE,
                max_size=settings.DB_POOL_MAX_SIZE,
                command_timeout=60
            )
            logger.info("数据库连接池创建成功")
            
            # 初始化数据库表
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
        """初始化数据库表结构"""
        logger.info("开始初始化数据库表...")
        
        # URL 表
        create_urls_table = """
        CREATE TABLE IF NOT EXISTS web_urls (
            id              BIGSERIAL PRIMARY KEY,
            origin          TEXT NOT NULL,
            url             TEXT NOT NULL,
            url_path        TEXT NOT NULL,
            depth           INT NOT NULL,
            discovered_from TEXT,
            discovery_type  TEXT NOT NULL,
            first_seen_at   TIMESTAMP DEFAULT NOW(),
            last_seen_at    TIMESTAMP DEFAULT NOW(),
            CONSTRAINT uniq_origin_url UNIQUE (origin, url)
        );
        """
        
        # URL 表索引
        create_urls_indexes = """
        CREATE INDEX IF NOT EXISTS idx_web_urls_origin ON web_urls(origin);
        CREATE INDEX IF NOT EXISTS idx_web_urls_path ON web_urls(url_path);
        """
        
        # Crawl 任务表
        create_tasks_table = """
        CREATE TABLE IF NOT EXISTS web_crawl_tasks (
            id            BIGSERIAL PRIMARY KEY,
            origin        TEXT NOT NULL,
            start_url     TEXT NOT NULL,
            max_depth     INT NOT NULL,
            max_pages     INT NOT NULL,
            status        TEXT NOT NULL,
            total_urls    INT DEFAULT 0,
            started_at    TIMESTAMP DEFAULT NOW(),
            finished_at   TIMESTAMP
        );
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(create_urls_table)
            await conn.execute(create_urls_indexes)
            await conn.execute(create_tasks_table)
        
        logger.info("数据库表初始化完成")
    
    async def create_task(self, origin: str, start_url: str, max_depth: int, max_pages: int) -> int:
        """
        创建爬取任务记录
        
        Returns:
            task_id
        """
        query = """
        INSERT INTO web_crawl_tasks (origin, start_url, max_depth, max_pages, status)
        VALUES ($1, $2, $3, $4, 'running')
        RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            task_id = await conn.fetchval(query, origin, start_url, max_depth, max_pages)
        
        logger.info(f"创建爬取任务: task_id={task_id}, origin={origin}")
        return task_id
    
    async def update_task(self, task_id: int, status: str, total_urls: int):
        """更新任务状态"""
        query = """
        UPDATE web_crawl_tasks
        SET status = $1, total_urls = $2, finished_at = NOW()
        WHERE id = $3
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(query, status, total_urls, task_id)
        
        logger.info(f"更新任务状态: task_id={task_id}, status={status}, total_urls={total_urls}")
    
    async def save_url(self, origin: str, url: str, url_path: str, depth: int,
                      discovered_from: Optional[str], discovery_type: str):
        """
        保存 URL 到数据库
        使用 ON CONFLICT 处理重复 URL
        """
        query = """
        INSERT INTO web_urls (origin, url, url_path, depth, discovered_from, discovery_type)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (origin, url)
        DO UPDATE SET last_seen_at = NOW()
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(query, origin, url, url_path, depth, discovered_from, discovery_type)


# 全局数据库实例
db = Database()