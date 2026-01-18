"""
URL发现相关路由
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from app.database import db
from app.crawler import URLDiscoveryCrawler
from app.call_url_audit_img import call_cds_url_audit


logger = logging.getLogger(__name__)

router = APIRouter(tags=["URL发现"])


class CrawlRequest(BaseModel):
    """爬取请求模型"""
    base_url: HttpUrl
    source_type: str
    tags: Optional[str] = None
    depth: int = Field(default=1, description="深度")
    strategy_type: str = Field(default="", description="策略类型")
    strategy_contents: str = Field(default="", description="策略内容")
    exclude_suffixes: list[str] = Field(default=['.js', '.css'], description="排除带特定后缀的url")


@router.get("/")
async def root():
    """健康检查"""
    return {"status": "ok", "service": "URL Discovery Service"}


@router.post("/crawl-urls-audit")
async def crawl_urls_audit(request: CrawlRequest):
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
        入库发现的所有 URL 列表, 并对discovered_urls进行audit
    """
    base_url = str(request.base_url)
    source_type = str(request.source_type)
    try:
        
        # 创建爬虫实例
        crawler = URLDiscoveryCrawler(base_url)
        
        # 执行爬取
        discovered_urls = await crawler.crawl()

        await db.save_discovery_result(base_url, discovered_urls, source_type, request.tags)
        
        # 执行audit
        urls = await db.get_needed_discovery_urls(base_url, request.exclude_suffixes)  
        success_count, fail_count = await call_cds_url_audit(
            urls, 
            request.depth, 
            request.strategy_type,
            request.strategy_contents
        )     
        return {"success_count": success_count, "fail_count": fail_count}
    
    except Exception as e:
        logger.error(f"爬取失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"爬取失败: {str(e)}")


@router.post("/get-all-sitemap-urls")
async def get_all_sitemap_urls():
    """获取所有sitemap来源的URL"""
    try:
        res = await db.get_all_for_source_type("sitemap")       
        return res
    
    except Exception as e:
        logger.error(f"查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/get-all-key_page-urls")
async def get_all_key_page_urls():
    """获取所有key_page来源的URL"""
    try:
        res = await db.get_all_for_source_type("key_page")       
        return res
    
    except Exception as e:
        logger.error(f"查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/get-recent-sitemap-urls")
async def get_recent_sitemap_urls():
    """获取最近5分钟内的sitemap来源URL"""
    try:
        res = await db.get_recent_for_source_type("sitemap")       
        return res
    
    except Exception as e:
        logger.error(f"查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/get-recent-key_page-urls")
async def get_recent_key_page_urls():
    """获取最近5分钟内的key_page来源URL"""
    try:
        res = await db.get_recent_for_source_type("key_page")       
        return res
    
    except Exception as e:
        logger.error(f"查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")