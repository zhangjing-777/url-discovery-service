"""
定时任务模型定义
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime


class DiscoveryTaskCreate(BaseModel):
    """创建定时任务请求模型"""
    task_name: str = Field(..., description="任务名称")
    base_url: HttpUrl = Field(..., description="目标URL")
    source_type: str = Field(..., description="来源类型")
    tags: Optional[str] = Field(None, description="标签")
    depth: int = Field(default=1, description="深度")
    strategy_type: str = Field(default="", description="策略类型")
    strategy_contents: str = Field(default="", description="策略内容")
    exclude_suffixes: List[str] = Field(default=['.js', '.css'], description="排除后缀列表")
    execution_interval: int = Field(..., description="执行间隔(秒)", gt=0)
    use_llm: bool = Field(default=False, description="是否用大模型分类discovery_urls")


class DiscoveryTaskUpdate(BaseModel):
    """更新任务请求模型"""
    task_name: Optional[str] = None
    base_url: Optional[HttpUrl] = None
    source_type: Optional[str] = None
    tags: Optional[str] = None
    depth: Optional[int] = None
    strategy_type: Optional[str] = None
    strategy_contents: Optional[str] = None
    exclude_suffixes: Optional[List[str]] = None
    execution_interval: Optional[int] = Field(None, gt=0)
    use_llm: Optional[bool] = False


class DiscoveryTaskResponse(BaseModel):
    """任务响应模型"""
    id: int
    task_name: str
    base_url: str
    source_type: str
    tags: Optional[str]
    depth: int
    strategy_type: str
    strategy_contents: str
    exclude_suffixes: List[str]
    execution_interval: int
    use_llm: bool
    next_execution_time: Optional[datetime]
    last_execution_time: Optional[datetime]
    create_time: datetime
    is_active: bool
    success_counts: int
    fail_counts: int
    