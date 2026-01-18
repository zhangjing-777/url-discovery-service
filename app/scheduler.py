"""
URL发现定时任务调度器
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from app.database import Database
from app.crawler import URLDiscoveryCrawler
from app.call_url_audit_img import call_cds_url_audit


logger = logging.getLogger(__name__)


class DiscoveryTaskScheduler:
    """URL发现任务调度器"""

    def __init__(self, db: Database):
        self.db = db
        self.running_tasks = {}  # 存储正在运行的任务ID
        self._shutdown = False

    async def start_scheduler(self):
        """启动任务调度器主循环"""
        logger.info("任务调度器启动")
        
        while not self._shutdown:
            try:
                await self.check_and_execute_tasks()
                await asyncio.sleep(10)  # 每10秒检查一次
            except Exception as e:
                logger.error(f"调度器错误: {e}", exc_info=True)
                await asyncio.sleep(30)
        
        logger.info("任务调度器已停止")

    async def stop_scheduler(self):
        """停止调度器"""
        self._shutdown = True

    async def check_and_execute_tasks(self):
        """检查并执行到期的任务"""
        try:
            # 查询需要执行的任务
            query = """
            SELECT id, task_name, base_url, source_type, tags, depth, 
                   strategy_type, strategy_contents, exclude_suffixes, execution_interval
            FROM url_discovery_tasks 
            WHERE is_active = TRUE 
            AND (next_execution_time IS NULL OR next_execution_time <= NOW())
            """

            async with self.db.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query)
                    tasks = await cur.fetchall()

            for task in tasks:
                task_id = task[0]
                
                # 避免重复执行
                if task_id in self.running_tasks:
                    continue

                # 创建任务执行协程
                task_coroutine = asyncio.create_task(
                    self.execute_task(
                        task_id=task_id,
                        task_name=task[1],
                        base_url=task[2],
                        source_type=task[3],
                        tags=task[4],
                        depth=task[5],
                        strategy_type=task[6],
                        strategy_contents=task[7],
                        exclude_suffixes=task[8],
                        execution_interval=task[9]
                    )
                )
                self.running_tasks[task_id] = task_coroutine

        except Exception as e:
            logger.error(f"检查任务失败: {e}", exc_info=True)

    async def execute_task(
        self,
        task_id: int,
        task_name: str,
        base_url: str,
        source_type: str,
        tags: Optional[str],
        depth: int,
        strategy_type: str,
        strategy_contents: str,
        exclude_suffixes: list,
        execution_interval: int
    ):
        """执行具体的URL发现任务"""
        logger.info(f"开始执行任务 {task_id}: {task_name}")
        
        try:
            # 更新最后执行时间
            await self._update_execution_time(task_id)

            # 1. 创建爬虫实例并执行爬取
            crawler = URLDiscoveryCrawler(base_url)
            discovered_urls = await crawler.crawl()

            # 2. 保存发现的URL到数据库
            await self.db.save_discovery_result(
                origin=base_url,
                discovery_result=discovered_urls,
                source_type=source_type,
                tags=tags
            )

            # 3. 获取需要审核的URL
            urls_to_audit = await self.db.get_needed_discovery_urls(
                origin=base_url,
                exclude_suffixes=exclude_suffixes
            )

            # 4. 调用审核接口
            success_count = 0
            fail_count = 0
            
            if urls_to_audit:
                success_count, fail_count = await call_cds_url_audit(
                    urls=urls_to_audit,
                    depth=depth,
                    strategy_type=strategy_type,
                    strategy_contents=strategy_contents
                )

            # 5. 更新任务统计和下次执行时间
            await self._update_task_result(
                task_id=task_id,
                success_count=success_count,
                fail_count=fail_count,
                execution_interval=execution_interval
            )

            logger.info(
                f"任务 {task_id} 执行完成: "
                f"发现URL {len(urls_to_audit)}, "
                f"审核成功 {success_count}, "
                f"失败 {fail_count}"
            )

        except Exception as e:
            logger.error(f"执行任务 {task_id} 失败: {e}", exc_info=True)
            
            # 即使失败也要更新下次执行时间
            try:
                await self._update_next_execution(task_id, execution_interval)
            except Exception as update_error:
                logger.error(f"更新失败任务的执行时间失败: {update_error}")

        finally:
            # 清理运行中的任务记录
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]

    async def _update_execution_time(self, task_id: int):
        """更新任务的最后执行时间"""
        sql = """
        UPDATE url_discovery_tasks 
        SET last_execution_time = NOW() 
        WHERE id = %s
        """
        
        async with self.db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (task_id,))

    async def _update_task_result(
        self,
        task_id: int,
        success_count: int,
        fail_count: int,
        execution_interval: int
    ):
        """更新任务执行结果和下次执行时间"""
        next_time = datetime.now() + timedelta(seconds=execution_interval)
        
        sql = """
        UPDATE url_discovery_tasks 
        SET success_counts = success_counts + %s,
            fail_counts = fail_counts + %s,
            next_execution_time = %s
        WHERE id = %s
        """
        
        async with self.db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql,
                    (success_count, fail_count, next_time, task_id)
                )

    async def _update_next_execution(self, task_id: int, execution_interval: int):
        """仅更新下次执行时间(用于失败情况)"""
        next_time = datetime.now() + timedelta(seconds=execution_interval)
        
        sql = """
        UPDATE url_discovery_tasks 
        SET next_execution_time = %s
        WHERE id = %s
        """
        
        async with self.db.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (next_time, task_id))