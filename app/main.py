"""
FastAPI 应用入口
提供 URL 发现 HTTP API
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from app.database import db
from app.scheduler import DiscoveryTaskScheduler
from app.task_routes import router as task_router, set_scheduler
from app.url_routes import router as url_router


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局调度器
scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时创建数据库连接池和调度器，关闭时释放资源
    """
    global scheduler
    
    # 启动
    logger.info("应用启动中...")
    await db.connect()
    
    # 初始化调度器
    try:
        scheduler = DiscoveryTaskScheduler(db)
        set_scheduler(scheduler)
        logger.info("任务调度器初始化成功")
        
        # 启动调度器
        scheduler_task = asyncio.create_task(scheduler.start_scheduler())
        logger.info("任务调度器启动成功")
    except Exception as e:
        logger.error(f"调度器启动失败: {e}")
        scheduler_task = None
    
    logger.info("应用启动完成")
    
    yield
    
    # 关闭
    logger.info("应用关闭中...")
    
    if scheduler:
        await scheduler.stop_scheduler()
    
    if scheduler_task:
        try:
            scheduler_task.cancel()
            await asyncio.wait_for(scheduler_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    
    await db.disconnect()
    logger.info("应用已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    root_path="/api/url-discovery-service",
    title="URL Discovery Service",
    description="真实用户路径 URL 发现且audit服务",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(url_router)
app.include_router(task_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)