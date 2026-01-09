"""
URL 处理工具函数
包含 URL 规范化、过滤、解析等功能
"""
import re
from typing import Optional
from urllib.parse import urlparse, urljoin, parse_qs, urlunparse
import logging

logger = logging.getLogger(__name__)


def normalize_url(base_url: str, href: str) -> Optional[str]:
    """
    URL 规范化处理
    
    Args:
        base_url: 基准 URL
        href: 待处理的 href
    
    Returns:
        规范化后的 URL，无效则返回 None
    """
    # 过滤无效协议
    if href.startswith(('javascript:', 'mailto:', 'tel:', 'data:')):
        return None
    
    # 空值检查
    if not href or href == '#':
        return None
    
    try:
        # 拼接相对路径
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        
        # 必须有 scheme 和 netloc
        if not parsed.scheme or not parsed.netloc:
            return None
        
        # 只支持 http/https
        if parsed.scheme not in ('http', 'https'):
            return None
        
        # 去除 fragment
        parsed = parsed._replace(fragment='')
        
        # 去除 UTM 参数
        if parsed.query:
            query_params = parse_qs(parsed.query)
            # 过滤 utm_ 开头的参数
            filtered_params = {k: v for k, v in query_params.items() if not k.startswith('utm_')}
            
            if filtered_params:
                # 重建 query string
                new_query = '&'.join(f"{k}={v[0]}" for k, v in filtered_params.items())
                parsed = parsed._replace(query=new_query)
            else:
                parsed = parsed._replace(query='')
        
        return urlunparse(parsed)
    
    except Exception as e:
        logger.warning(f"URL 规范化失败: {href}, 错误: {e}")
        return None


def is_same_origin(url1: str, url2: str) -> bool:
    """
    检查两个 URL 是否同域
    
    Args:
        url1: URL 1
        url2: URL 2
    
    Returns:
        是否同域
    """
    try:
        parsed1 = urlparse(url1)
        parsed2 = urlparse(url2)
        return (parsed1.scheme == parsed2.scheme and 
                parsed1.netloc == parsed2.netloc)
    except Exception:
        return False


def get_origin(url: str) -> str:
    """
    获取 URL 的 origin（scheme + netloc）
    
    Args:
        url: 完整 URL
    
    Returns:
        origin 字符串
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def get_url_path(url: str) -> str:
    """
    提取 URL 的 path 部分
    
    Args:
        url: 完整 URL
    
    Returns:
        path 字符串，默认为 '/'
    """
    parsed = urlparse(url)
    return parsed.path or '/'


def is_static_resource(url: str) -> bool:
    """
    判断 URL 是否为静态资源
    
    Args:
        url: URL 字符串
    
    Returns:
        是否为静态资源
    """
    # 静态资源扩展名列表
    static_extensions = {
        '.js', '.css', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
        '.ico', '.woff', '.woff2', '.ttf', '.eot', '.mp4', '.mp3',
        '.pdf', '.zip', '.tar', '.gz', '.xml', '.json'
    }
    
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    return any(path.endswith(ext) for ext in static_extensions)


def extract_urls_from_text(text: str, base_url: str) -> set:
    """
    从文本中提取潜在的 URL（兜底策略）
    
    Args:
        text: HTML 文本
        base_url: 基准 URL
    
    Returns:
        URL 集合
    """
    urls = set()
    
    # 匹配相对路径和绝对路径
    # 相对路径: /xxx/yyy
    # 绝对路径: http://xxx 或 https://xxx
    patterns = [
        r'href=["\']([^"\']+)["\']',
        r'src=["\']([^"\']+)["\']',
        r'(https?://[^\s<>"\']+)',
        r'(/[a-zA-Z0-9\-_/]+(?:\?[^\s<>"\']*)?)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            normalized = normalize_url(base_url, match)
            if normalized and is_same_origin(base_url, normalized):
                if not is_static_resource(normalized):
                    urls.add(normalized)
    
    return urls