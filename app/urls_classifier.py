"""
URL 智能分类系统 - 完全基于 LLM 分类
使用 OpenRouter API 调用大模型进行 URL 分析和分类
"""

import asyncio
import aiohttp
import json
import logging
from typing import List, Dict
from urllib.parse import urlparse
from app.config import settings

logger = logging.getLogger(__name__)


class LLMURLClassifier:
    """基于 LLM 的 URL 分类器"""
    
    def __init__(self,  main_url: str, url_list: List[str]):
        """
        初始化分类器
        
        Args:
            main_url: 主 URL，用于上下文分析
        """
        self.api_key = settings.OPENROUTER_API_KEY
        self.main_url = main_url
        self.main_domain = urlparse(main_url).netloc
        self.url_list = url_list
        self.model = settings.MODEL
        self.openrouter_base_url = settings.OPENROUTER_ENDPOINT
        self.timeout = aiohttp.ClientTimeout(total=60)
        self.max_retries = 3
    
    def _build_classification_prompt(self) -> str:

        prompt = f"""
        你是一个专业的 URL 分析与安全识别专家。请对一组 URL 进行精确分类。

        【任务上下文】
        - 主 URL: {self.main_url}
        - 主域名: {self.main_domain}
        - URL 数量: {len(self.url_list)}

        【URL 列表】
        {json.dumps(self.url_list, indent=2, ensure_ascii=False)}

        ━━━━━━━━━━━━━━━━━━
        【分类规则（严格按优先级）】

        ⚠️ 每个 URL **必须且只能**归入一个分类。

        ### 1️⃣ 可访问明显异常的url（abnormal，最高优先级）
        **定义：**
        > abnormal = 「明显异常」 ∩ 「可访问的网站或图片 URL」

        **异常判断条件（任一命中即可）：**
        - 域名与主域名 `{self.main_domain}` 不一致，且不是其子域或合理关联域
        - 使用非 http/https 协议（如 javascript:, data:, mailto:, tel: 等）
        - URL 格式明显异常或像代码片段（HTML/CSS/JS）
        - 包含明显注入或攻击特征（XSS / SQL 注入 / 特殊字符异常）
        - URL 编码异常、特殊字符过多

        说明：
        - 若 URL 本身不可访问 → 不属于此类
        - 若是图片或网页，但明显异常 → 归入此类

        ---

        ### 2️⃣ 不可访问的url
        **定义：**
        - 明显不可达、占位、测试或本地 URL

        **特征示例：**
        - localhost / 127.0.0.1 / example.com
        - 明显 404 / undefined / null / test 路径
        - 无效或明显错误的域名

        ---

        ### 3️⃣ 可访问图片的url
        **定义：**
        - 明确指向图片资源，且非异常

        **特征：**
        - 图片扩展名（jpg/png/webp/svg/ico/avif 等）
        - 常见图片路径（/img/ /images/ /avatar /thumbnail）
        - 图片 CDN 或图床

        ---

        ### 4️⃣ 除图片以外的多媒体类的url
        **定义：**
        - 可访问的非图片多媒体或文件资源

        **包括但不限于：**
        - 视频（YouTube / Bilibili / mp4 / webm 等）
        - 音频（mp3 / wav / podcast 等）
        - 字体（Google Fonts / woff / ttf 等）
        - 文档（pdf / docx / pptx / xlsx）
        - 压缩包（zip / rar / 7z）
        - 流媒体（m3u8 / mpd）

        ---

        ### 5️⃣ 可访问网站的url
        **定义：**
        - 正常、可访问、无明显异常的 HTTP/HTTPS 页面或接口

        **包括：**
        - HTML 页面
        - Web 应用路由
        - API 接口
        - 合理的外部链接

        ━━━━━━━━━━━━━━━━━━
        【补充判定原则】

        - 子域名（blog., api., cdn.）视为主域一致
        - http 与 https 不构成异常
        - 正常参数（utm, id, page 等）不构成异常
        - 短链接（bit.ly, t.co 等）视为异常
        - CDN 域名可能是合法的
        - 端口号存在不直接视为异常
        - 国际化域名（IDN）是合法的

        ━━━━━━━━━━━━━━━━━━
        【输出要求】

        - 仅输出 JSON，不要解释文字
        - 每个 URL 只出现一次，不遗漏、不重复

        输出格式：
        {{
        "accessible_website_urls": [],
        "accessible_image_urls": [],
        "accessible_abnormal_urls": [],
        "non_image_multimedia_urls": [],
        "inaccessible_urls": []
        }}

        开始分析：
        """
        return prompt
    
    async def call_openrouter_api(self) -> Dict:
        """
        调用 OpenRouter API
        
        Args:
            prompt: 完整的提示词
            
        Returns:
            API 响应的 JSON 数据
        """
        prompt = self._build_classification_prompt()
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.2,  # 较低温度确保一致性
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/url-classifier",
            "X-Title": "URL Classifier Pro"
        }
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"调用 OpenRouter API (尝试 {attempt + 1}/{self.max_retries})...")
                    
                    async with session.post(
                        self.openrouter_base_url,
                        json=payload,
                        headers=headers,
                        timeout=self.timeout
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            content = data['choices'][0]['message']['content']
                            
                            # 记录 token 使用情况
                            usage = data.get('usage', {})
                            logger.info(f"Token 使用: 输入={usage.get('prompt_tokens', 0)}, "
                                      f"输出={usage.get('completion_tokens', 0)}, "
                                      f"总计={usage.get('total_tokens', 0)}")
                            
                            return self._parse_response(content)
                        else:
                            error_text = await response.text()
                            logger.error(f"API 错误 (状态码 {response.status}): {error_text}")
                            
                            if response.status == 429:  # Rate limit
                                wait_time = 2 ** attempt * 5
                                logger.warning(f"触发速率限制，等待 {wait_time} 秒...")
                                await asyncio.sleep(wait_time)
                                continue
                            
                except asyncio.TimeoutError:
                    logger.warning(f"API 超时 (尝试 {attempt + 1}/{self.max_retries})")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except Exception as e:
                    logger.error(f"API 调用异常: {e}")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
        
        raise Exception("OpenRouter API 调用失败，已达到最大重试次数")
    
    def _parse_response(self, content: str) -> Dict:
        """
        解析 LLM 返回的 JSON 响应
        
        Args:
            content: LLM 返回的文本内容
            
        Returns:
            解析后的字典
        """
        try:
            # 移除可能的 markdown 代码块标记
            content = content.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.startswith('```'):
                content = content[3:]
            if content.endswith('```'):
                content = content[:-3]
            
            content = content.strip()
            
            # 解析 JSON
            result = json.loads(content)
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            logger.error(f"原始内容: {content[:500]}...")
            
            # 尝试提取 JSON 部分
            try:
                import re
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    return json.loads(json_match.group())
            except:
                pass
            
            raise Exception(f"无法解析 LLM 响应为 JSON: {str(e)}")
