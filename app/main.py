"""
FastAPI 应用入口
提供 URL 发现 HTTP API
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from app.config import settings
from app.database import db
from app.models import CrawlRequest, CrawlResponse
from app.crawler import URLDiscoveryCrawler
from app.utils import get_origin, get_url_path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时创建数据库连接池，关闭时释放资源
    """
    # 启动
    logger.info("应用启动中...")
    await db.connect()
    logger.info("应用启动完成")
    
    yield
    
    # 关闭
    logger.info("应用关闭中...")
    await db.disconnect()
    logger.info("应用已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="URL Discovery Service",
    description="真实用户路径 URL 发现服务",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """健康检查"""
    return {"status": "ok", "service": "URL Discovery Service"}


@app.post("/crawl-urls", response_model=CrawlResponse)
async def crawl_urls(request: CrawlRequest):
    """
    URL 发现接口
    
    使用 Playwright 模拟真实浏览器行为，通过多种机制发现 URL：
    1. DOM Anchor（a[href]）
    2. SPA 路由监听（framenavigated）
    3. Network 请求捕获（request）
    4. HTTP Redirect 捕获（response）
    5. JS Runtime 资源（performance API）
    6. 自动用户行为触发（点击交互）
    7. 文本兜底（正则扫描）
    
    Args:
        request: 爬取请求参数
    
    Returns:
        发现的所有 URL 列表
    """
    start_url = str(request.start_url)
    origin = get_origin(start_url)
    
    logger.info(f"收到爬取请求: start_url={start_url}, max_depth={request.max_depth}, max_pages={request.max_pages}, persist={request.persist}")
    
    task_id = None
    
    try:
        # 如果需要持久化，创建任务记录
        if request.persist:
            task_id = await db.create_task(
                origin=origin,
                start_url=start_url,
                max_depth=request.max_depth,
                max_pages=request.max_pages
            )
        
        # 创建爬虫实例
        crawler = URLDiscoveryCrawler(
            start_url=start_url,
            max_depth=request.max_depth,
            max_pages=request.max_pages
        )
        
        # 执行爬取
        discovered_urls = await crawler.crawl()
        
        # 持久化 URL
        if request.persist:
            logger.info(f"开始持久化 {len(discovered_urls)} 个 URL...")
            
            for url_obj in discovered_urls.values():
                await db.save_url(
                    origin=origin,
                    url=url_obj.url,
                    url_path=get_url_path(url_obj.url),
                    depth=url_obj.depth,
                    discovered_from=url_obj.discovered_from,
                    discovery_type=url_obj.discovery_type
                )
            
            # 更新任务状态
            await db.update_task(task_id, 'completed', len(discovered_urls))
            logger.info("URL 持久化完成")
        
        # 构造响应
        url_list = sorted(discovered_urls.keys())
        
        return CrawlResponse(
            origin=origin,
            task_id=task_id,
            count=len(url_list),
            urls=url_list
        )
    
    except Exception as e:
        logger.error(f"爬取失败: {e}", exc_info=True)
        
        # 更新任务状态为失败
        if task_id:
            await db.update_task(task_id, 'failed', 0)
        
        raise HTTPException(status_code=500, detail=f"爬取失败: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)