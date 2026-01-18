import asyncio
import aiohttp
import logging
from typing import List, Tuple
from app.config import settings


logger = logging.getLogger(__name__)


async def call_cds_url_audit(urls: List[str], depth: int, strategy_type: str, strategy_contents: str) -> Tuple[int, int]:
    """调用cds_url_audit接口"""
    try:
        async with aiohttp.ClientSession() as session:
            # CDS URL审核接口地址
            payload = {
                "urls": urls,
                "depth": depth,
                "strategy_type": strategy_type,
                "strategy_contents": strategy_contents
            }
            
            async with session.post(settings.AUDIT_URL, json=payload, timeout=300) as response:
                if response.status == 200:
                    result = await response.json()
                    success_count = result.get('success_count', 0)
                    fail_count = result.get('fail_count', 0)
                    return success_count, fail_count
                else:
                    error_text = await response.text()
                    logger.error(f"审核接口返回错误 {response.status}: {error_text}")
                    return 0, len(urls)
                    
    except asyncio.TimeoutError:
        logger.error(f"审核接口调用超时: {urls}")
        return 0, len(urls)
    except Exception as e:
        logger.error(f"调用审核接口失败，URLs: {urls}, 错误: {e}")
        return 0, len(urls)  # 异常情况下，全部算作失败