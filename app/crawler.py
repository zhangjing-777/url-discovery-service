import logging
import httpx
from urllib.parse import urljoin, urlparse
from typing import Dict, Any, Set
from app.config import settings


logger = logging.getLogger(__name__)


class URLDiscoveryCrawler:
    """
    URL 发现爬虫
    - 调用远程 Playwright 服务
    - 清洗 & 分类 URLs
    """

    GARBAGE_PREFIXES = (
        "javascript:",
        "mailto:",
        "tel:",
        "about:",
        "data:",
        "#",
    )

    MEDIA_EXTENSIONS = (
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
        ".mp4", ".webm", ".mov", ".avi", ".mkv", ".pdf",
    )

    ASSET_EXTENSIONS = (
        ".js", ".css",
        ".ttf", ".otf", ".woff", ".woff2",
        ".map",
    )

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)

    # =========================
    # 对外唯一入口
    # =========================
    async def crawl(self) -> Dict[str, list]:
        """
        获取并分类 URL
        """
        data = await self._fetch_from_playwright()
        return self._classify(data)

    # =========================
    # Playwright 调用
    # =========================
    async def _fetch_from_playwright(self) -> Dict[str, Any]:
        try:
            resp = await self.client.post(
                f"{settings.PLAYWRIGHT_SERVICE_URL}/render",
                json={
                    "url": self.base_url,
                    "timeout": 30000,
                    "wait_for": "networkidle",
                },
            )

            if resp.status_code != 200:
                logger.error(f"Playwright 返回错误: {resp.status_code}")
                return {}

            return resp.json()

        except Exception as e:
            logger.exception("调用 Playwright 服务失败")
            return {}

    # =========================
    # URL 分类核心逻辑
    # =========================
    def _classify(self, discovery_result: Dict[str, Any]) -> Dict[str, list]:
        normal: Set[str] = set()
        media: Set[str] = set()
        asset: Set[str] = set()
        garbage: Set[str] = set()

        discovered = discovery_result.get("discovered_urls", {})

        for items in discovered.values():
            if not isinstance(items, list):
                continue

            for raw in items:
                self._handle_raw_url(
                    raw,
                    normal,
                    media,
                    asset,
                    garbage,
                )

        return {
            "normal_urls": sorted(normal),
            "media_urls": sorted(media),
            "asset_urls": sorted(asset),
            "garbage_links": sorted(garbage),
        }

    # =========================
    # 单条 URL 处理
    # =========================
    def _handle_raw_url(
        self,
        raw: str,
        normal: Set[str],
        media: Set[str],
        asset: Set[str],
        garbage: Set[str],
    ) -> None:
        if not raw:
            return

        raw = raw.strip()

        # ① 垃圾前缀
        if raw.startswith(self.GARBAGE_PREFIXES):
            garbage.add(raw)
            return

        # ② 绝对路径补全
        full_url = urljoin(self.base_url, raw)
        parsed = urlparse(full_url)

        # 非 http(s)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            garbage.add(raw)
            return

        clean_url = parsed._replace(fragment="").geturl()
        path = parsed.path.lower()

        # ③ 分类
        if path.endswith(self.MEDIA_EXTENSIONS):
            media.add(clean_url)
        elif path.endswith(self.ASSET_EXTENSIONS):
            asset.add(clean_url)
        else:
            normal.add(clean_url)
