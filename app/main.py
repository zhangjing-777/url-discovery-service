"""
FastAPI 应用入口
提供 URL 发现 HTTP API
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from app.database import db
from app.crawler import URLDiscoveryCrawler


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


class CrawlRequest(BaseModel):
    """爬取请求模型"""
    base_url: HttpUrl

@app.post("/crawl-urls")
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
        入库发现的所有 URL 列表
    """
    base_url = str(request.base_url)
    try:
        
        # 创建爬虫实例
        crawler = URLDiscoveryCrawler(base_url)
        
        # 执行爬取
        discovered_urls = await crawler.crawl()

        res = await db.save_discovery_result(base_url, discovered_urls)
        
        return discovered_urls
    
    except Exception as e:
        logger.error(f"爬取失败: {e}", exc_info=True)
        
        raise HTTPException(status_code=500, detail=f"爬取失败: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)