"""
数据模型定义
包含请求/响应模型和内部数据结构
"""
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl


class CrawlRequest(BaseModel):
    """爬取请求模型"""
    start_url: HttpUrl
    max_depth: int = Field(default=3, ge=1, le=10)
    max_pages: int = Field(default=1000, ge=1, le=10000)
    persist: bool = True


class CrawlResponse(BaseModel):
    """爬取响应模型"""
    origin: str
    task_id: Optional[int] = None
    count: int
    urls: List[str]


class DiscoveredURL(BaseModel):
    """发现的 URL 内部模型"""
    url: str
    depth: int
    discovered_from: Optional[str] = None
    discovery_type: str  # dom, spa_nav, network_request, network_redirect, js_runtime, heuristic