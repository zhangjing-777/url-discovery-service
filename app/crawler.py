"""
核心 URL 发现爬虫
使用 Playwright 模拟真实浏览器行为，捕获所有可能的 URL
"""
import asyncio
import logging
from typing import Set, Optional, Dict
from collections import deque
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from app.config import settings
from app.utils import (
    normalize_url, is_same_origin, get_origin, get_url_path,
    is_static_resource, extract_urls_from_text
)
from app.models import DiscoveredURL

logger = logging.getLogger(__name__)


class URLDiscoveryCrawler:
    """
    真实用户路径 URL 发现爬虫
    
    职责：
    1. 使用 Playwright 模拟真实浏览器
    2. 通过多种机制发现 URL（DOM、SPA 路由、Network、JS Runtime 等）
    3. BFS 遍历，支持深度和页面数量限制
    4. 不抓取页面内容，只发现 URL
    """
    
    def __init__(self, start_url: str, max_depth: int, max_pages: int):
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.origin = get_origin(start_url)
        
        # URL 队列和去重集合
        self.queue: deque = deque()
        self.visited: Set[str] = set()
        self.discovered_urls: Dict[str, DiscoveredURL] = {}
        
        # Playwright 实例
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        
        logger.info(f"初始化爬虫: origin={self.origin}, max_depth={max_depth}, max_pages={max_pages}")
    
    async def crawl(self) -> Dict[str, DiscoveredURL]:
        """
        执行爬取任务
        
        Returns:
            发现的所有 URL 字典
        """
        async with async_playwright() as p:
            # 启动浏览器
            self.browser = await p.chromium.launch(
                headless=settings.BROWSER_HEADLESS
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            logger.info("Playwright 浏览器已启动")
            
            # 初始化队列
            self.queue.append((self.start_url, 0, None))
            
            # BFS 遍历
            while self.queue and len(self.visited) < self.max_pages:
                url, depth, discovered_from = self.queue.popleft()
                
                # 跳过已访问或超过深度限制的 URL
                if url in self.visited or depth > self.max_depth:
                    continue
                
                logger.info(f"正在访问 [{len(self.visited)+1}/{self.max_pages}]: {url} (depth={depth})")
                
                # 标记为已访问
                self.visited.add(url)
                
                # 记录当前 URL
                self._add_discovered_url(url, depth, discovered_from, 'dom')
                
                # 访问页面并发现新 URL
                try:
                    new_urls = await self._discover_urls_from_page(url, depth)
                    
                    # 将新发现的 URL 加入队列
                    for new_url, discovery_type in new_urls:
                        if new_url not in self.visited and new_url not in [u for u, _, _ in self.queue]:
                            self.queue.append((new_url, depth + 1, url))
                            self._add_discovered_url(new_url, depth + 1, url, discovery_type)
                    
                    logger.info(f"从 {url} 发现 {len(new_urls)} 个新 URL")
                
                except Exception as e:
                    logger.error(f"访问页面失败: {url}, 错误: {e}")
                    # 不中断整体流程，继续下一个 URL
                    continue
            
            logger.info(f"爬取完成，共发现 {len(self.discovered_urls)} 个 URL")
            return self.discovered_urls
    
    async def _discover_urls_from_page(self, url: str, depth: int) -> list:
        """
        从单个页面发现所有可能的 URL
        
        核心方法，整合所有 URL 发现机制：
        1. DOM Anchor（a[href]）
        2. SPA 路由监听（framenavigated）
        3. Network 请求捕获（request）
        4. HTTP Redirect 捕获（response）
        5. JS Runtime 资源（performance API）
        6. 自动用户行为触发（点击交互）
        7. 文本兜底（正则扫描）
        
        Returns:
            [(url, discovery_type), ...]
        """
        page = await self.context.new_page()
        
        # 设置超时
        page.set_default_timeout(settings.PAGE_TIMEOUT)
        
        # 用于收集发现的 URL
        discovered = set()
        
        # === 机制 2: SPA 路由变化监听 ===
        async def on_frame_navigated(frame):
            """监听前端路由变化（SPA）"""
            nav_url = frame.url
            if nav_url and is_same_origin(self.origin, nav_url):
                normalized = normalize_url(self.origin, nav_url)
                if normalized:
                    discovered.add((normalized, 'spa_nav'))
                    logger.debug(f"[SPA Nav] {normalized}")
        
        page.on("framenavigated", on_frame_navigated)
        
        # === 机制 3: Network 请求捕获 ===
        async def on_request(request):
            """监听网络请求"""
            req_url = request.url
            if is_same_origin(self.origin, req_url) and not is_static_resource(req_url):
                normalized = normalize_url(self.origin, req_url)
                if normalized:
                    discovered.add((normalized, 'network_request'))
                    logger.debug(f"[Network Req] {normalized}")
        
        page.on("request", on_request)
        
        # === 机制 4: HTTP Redirect 捕获 ===
        async def on_response(response):
            """监听 HTTP 响应，捕获 30x 跳转"""
            if 300 <= response.status < 400:
                location = response.headers.get('location')
                if location:
                    normalized = normalize_url(url, location)
                    if normalized and is_same_origin(self.origin, normalized):
                        discovered.add((normalized, 'network_redirect'))
                        logger.debug(f"[HTTP Redirect] {normalized}")
        
        page.on("response", on_response)
        
        try:
            # 访问页面
            await page.goto(url, wait_until='networkidle', timeout=settings.PAGE_TIMEOUT)
            
            # 等待页面加载完成
            await asyncio.sleep(2)
            
            # === 机制 1: DOM Anchor ===
            dom_urls = await self._extract_dom_anchors(page)
            discovered.update((u, 'dom') for u in dom_urls)
            logger.debug(f"[DOM] 发现 {len(dom_urls)} 个 anchor")
            
            # === 机制 5: JS Runtime 资源 ===
            js_runtime_urls = await self._extract_js_runtime_resources(page)
            discovered.update((u, 'js_runtime') for u in js_runtime_urls)
            logger.debug(f"[JS Runtime] 发现 {len(js_runtime_urls)} 个资源")
            
            # === 机制 6: 自动用户行为触发 ===
            interaction_urls = await self._trigger_user_interactions(page)
            discovered.update((u, 'spa_nav') for u in interaction_urls)
            logger.debug(f"[User Interaction] 发现 {len(interaction_urls)} 个 URL")
            
            # === 机制 7: 文本兜底 ===
            html_content = await page.content()
            heuristic_urls = extract_urls_from_text(html_content, url)
            discovered.update((u, 'heuristic') for u in heuristic_urls)
            logger.debug(f"[Heuristic] 发现 {len(heuristic_urls)} 个 URL")
        
        finally:
            await page.close()
        
        return list(discovered)
    
    async def _extract_dom_anchors(self, page: Page) -> set:
        """
        提取 DOM 中所有 a[href]
        最高可信度的 URL 来源
        """
        urls = set()
        
        try:
            # 获取所有带 href 的 anchor 元素
            anchors = await page.query_selector_all('a[href]')
            
            for anchor in anchors:
                href = await anchor.get_attribute('href')
                if href:
                    normalized = normalize_url(self.origin, href)
                    if normalized and is_same_origin(self.origin, normalized):
                        urls.add(normalized)
        
        except Exception as e:
            logger.warning(f"提取 DOM anchors 失败: {e}")
        
        return urls
    
    async def _extract_js_runtime_resources(self, page: Page) -> set:
        """
        使用 Performance API 获取 JS 运行时加载的资源
        """
        urls = set()
        
        try:
            # 执行 JS 获取性能条目
            resources = await page.evaluate('''
                () => {
                    return performance.getEntriesByType('resource').map(r => r.name);
                }
            ''')
            
            for resource_url in resources:
                if is_same_origin(self.origin, resource_url) and not is_static_resource(resource_url):
                    normalized = normalize_url(self.origin, resource_url)
                    if normalized:
                        urls.add(normalized)
        
        except Exception as e:
            logger.warning(f"提取 JS Runtime 资源失败: {e}")
        
        return urls
    
    async def _trigger_user_interactions(self, page: Page) -> set:
        """
        自动触发用户交互行为（点击按钮）
        捕获交互后产生的新 URL
        """
        urls = set()
        
        try:
            # 查找所有可点击元素
            selectors = [
                'button:not([type="submit"])',
                '[role="button"]',
                'a[role="button"]'
            ]
            
            for selector in selectors:
                elements = await page.query_selector_all(selector)
                
                # 限制点击次数，避免过度交互
                for element in elements[:5]:  # 最多点击 5 个元素
                    try:
                        # 检查是否包含危险关键词
                        text = await element.text_content()
                        if text and any(kw in text.lower() for kw in ['delete', 'logout', 'remove', 'sign out']):
                            continue
                        
                        # 记录当前 URL
                        current_url = page.url
                        
                        # 点击元素
                        await element.click(timeout=5000)
                        
                        # 等待可能的导航
                        await page.wait_for_load_state('networkidle', timeout=5000)
                        
                        # 检查 URL 是否变化
                        new_url = page.url
                        if new_url != current_url:
                            normalized = normalize_url(self.origin, new_url)
                            if normalized and is_same_origin(self.origin, normalized):
                                urls.add(normalized)
                        
                        # 返回原始页面
                        if new_url != current_url:
                            await page.goto(current_url, wait_until='networkidle', timeout=10000)
                    
                    except Exception as e:
                        logger.debug(f"点击元素失败: {e}")
                        continue
        
        except Exception as e:
            logger.warning(f"用户交互触发失败: {e}")
        
        return urls
    
    def _add_discovered_url(self, url: str, depth: int, discovered_from: Optional[str], discovery_type: str):
        """
        记录发现的 URL
        """
        if url not in self.discovered_urls:
            self.discovered_urls[url] = DiscoveredURL(
                url=url,
                depth=depth,
                discovered_from=discovered_from,
                discovery_type=discovery_type
            )