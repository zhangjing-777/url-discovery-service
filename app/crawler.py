"""
URL 发现爬虫 - 调用远程 Playwright 服务
"""
import logging
import httpx
from typing import Set, Optional, Dict
from collections import deque
from app.config import settings
from app.utils import (
    normalize_url, is_same_origin, get_origin,
    is_static_resource, extract_urls_from_text
)
from app.models import DiscoveredURL

logger = logging.getLogger(__name__)


class URLDiscoveryCrawler:
    """URL 发现爬虫 - 使用远程 Playwright 服务"""
    
    def __init__(self, start_url: str, max_depth: int, max_pages: int):
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.origin = get_origin(start_url)
        
        self.queue: deque = deque()
        self.visited: Set[str] = set()
        self.discovered_urls: Dict[str, DiscoveredURL] = {}
        
        # HTTP 客户端
        self.client = httpx.AsyncClient(timeout=60.0)
        
        logger.info(f"初始化爬虫: origin={self.origin}, playwright_service={settings.PLAYWRIGHT_SERVICE_URL}")
    
    async def crawl(self) -> Dict[str, DiscoveredURL]:
        """执行爬取任务"""
        try:
            self.queue.append((self.start_url, 0, None))
            
            while self.queue and len(self.visited) < self.max_pages:
                url, depth, discovered_from = self.queue.popleft()
                
                if url in self.visited or depth > self.max_depth:
                    continue
                
                logger.info(f"正在访问 [{len(self.visited)+1}/{self.max_pages}]: {url} (depth={depth})")
                
                self.visited.add(url)
                self._add_discovered_url(url, depth, discovered_from, 'dom')
                
                try:
                    new_urls = await self._discover_urls_from_page(url, depth)
                    
                    for new_url, discovery_type in new_urls:
                        if new_url not in self.visited and new_url not in [u for u, _, _ in self.queue]:
                            self.queue.append((new_url, depth + 1, url))
                            self._add_discovered_url(new_url, depth + 1, url, discovery_type)
                    
                    logger.info(f"从 {url} 发现 {len(new_urls)} 个新 URL")
                
                except Exception as e:
                    logger.error(f"访问页面失败: {url}, 错误: {e}")
                    continue
            
            logger.info(f"爬取完成，共发现 {len(self.discovered_urls)} 个 URL")
            return self.discovered_urls
        
        finally:
            await self.client.aclose()
    
    async def _discover_urls_from_page(self, url: str, depth: int) -> list:
        """
        调用 Playwright 服务发现 URL
        """
        discovered = set()
        
        try:
            # 调用远程 Playwright 服务
            response = await self.client.post(
                f"{settings.PLAYWRIGHT_SERVICE_URL}/render",
                json={
                    "url": url,
                    "timeout": 30000,
                    "wait_for": "networkidle"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Playwright 服务返回错误: {response.status_code}")
                return []
            
            data = response.json()
            
            if not data.get('success'):
                logger.error(f"渲染失败: {data.get('error')}")
                return []
            
            discovered_urls = data.get('discovered_urls', {})
            
            # 处理各类型 URL
            for discovery_type, urls in discovered_urls.items():
                if discovery_type == 'heuristic':
                    # 特殊处理：heuristic 返回的是 HTML
                    html_content = urls[0] if urls else ""
                    heuristic_urls = extract_urls_from_text(html_content, url)
                    discovered.update((u, 'heuristic') for u in heuristic_urls)
                else:
                    # 其他类型直接处理
                    for raw_url in urls:
                        # 规范化并过滤
                        normalized = normalize_url(url, raw_url)
                        if normalized and is_same_origin(self.origin, normalized):
                            if not is_static_resource(normalized):
                                discovered.add((normalized, discovery_type))
        
        except Exception as e:
            logger.error(f"调用 Playwright 服务失败: {e}")
        
        return list(discovered)
    
    def _add_discovered_url(self, url: str, depth: int, discovered_from: Optional[str], discovery_type: str):
        """记录发现的 URL"""
        if url not in self.discovered_urls:
            self.discovered_urls[url] = DiscoveredURL(
                url=url,
                depth=depth,
                discovered_from=discovered_from,
                discovery_type=discovery_type
            )