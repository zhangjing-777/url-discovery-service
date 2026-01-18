# URL Discovery Service

真实用户路径 URL 发现与审核服务，支持定时任务调度。

## 功能特性

- **URL 发现**: 通过 Playwright 模拟真实浏览器行为，多维度发现网页中的 URL
- **URL 分类**: 自动分类为 normal_urls、media_urls、asset_urls、garbage_links
- **自动审核**: 集成 CDS URL 审核接口，自动过滤和审核发现的 URL
- **定时任务**: 支持创建定时任务，按指定间隔自动执行 URL 发现和审核
- **数据持久化**: 使用 OpenGauss 数据库存储发现的 URL 和任务配置

## 技术栈

- **框架**: FastAPI + Uvicorn
- **数据库**: OpenGauss (PostgreSQL 协议)
- **浏览器自动化**: Playwright (远程服务)
- **异步处理**: asyncio + aiohttp
- **部署**: Docker + Docker Compose

## 快速开始

### 1. 环境准备

创建 `.env` 文件：
```env
# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=url_discovery

# Playwright 服务地址
PLAYWRIGHT_SERVICE_URL=http://playwright-service:8080

# CDS 审核服务地址
AUDIT_URL=http://cds-url-audit:8000/api/cds-url-audit-img/cds_url_audit
```

### 2. 启动服务
```bash
# Docker 部署
docker-compose up -d

# 本地开发
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. 访问文档

- API 文档: http://localhost:8217/api/url-discovery-service/docs
- 健康检查: http://localhost:8217/api/url-discovery-service/

## API 接口

### URL 发现接口

#### 手动触发爬取
```http
POST /api/url-discovery-service/crawl-urls-audit
Content-Type: application/json

{
  "base_url": "https://example.com",
  "source_type": "key_page",
  "depth": 1,
  "strategy_type": "default",
  "strategy_contents": "",
  "exclude_suffixes": [".js", ".css"]
}
```

#### 查询已发现的 URL
```http
POST /api/url-discovery-service/get-all-sitemap-urls
POST /api/url-discovery-service/get-all-key_page-urls
POST /api/url-discovery-service/get-recent-sitemap-urls
POST /api/url-discovery-service/get-recent-key_page-urls
```

### 定时任务接口

#### 创建定时任务
```http
POST /api/url-discovery-service/discovery-tasks
Content-Type: application/json

{
  "task_name": "每日巡检-example.com",
  "base_url": "https://example.com",
  "source_type": "key_page",
  "depth": 1,
  "execution_interval": 3600,
  "strategy_type": "default",
  "strategy_contents": "",
  "exclude_suffixes": [".js", ".css"]
}
```

#### 任务管理
```http
GET    /api/url-discovery-service/discovery-tasks           # 列出所有任务
GET    /api/url-discovery-service/discovery-tasks/{id}      # 获取任务详情
PUT    /api/url-discovery-service/discovery-tasks/{id}      # 更新任务
DELETE /api/url-discovery-service/discovery-tasks/{id}      # 删除任务
POST   /api/url-discovery-service/discovery-tasks/{id}/start  # 启动任务
POST   /api/url-discovery-service/discovery-tasks/{id}/stop   # 停止任务
GET    /api/url-discovery-service/discovery-tasks/{id}/status # 查询状态
```

## 数据库表结构

### web_urls - URL 发现记录表
```sql
- id: 主键
- origin: 源URL
- discovery_url: 发现的URL
- discovery_type: URL类型 (normal_urls/media_urls/asset_urls/garbage_links)
- source_type: 来源类型 (sitemap/key_page)
- tags: 标签
- first_seen_at: 首次发现时间
- last_seen_at: 最后发现时间
```

### url_discovery_tasks - 定时任务表
```sql
- id: 主键
- task_name: 任务名称
- base_url: 目标URL
- source_type: 来源类型
- depth: 爬取深度
- execution_interval: 执行间隔(秒)
- next_execution_time: 下次执行时间
- is_active: 是否激活
- success_counts: 成功次数
- fail_counts: 失败次数
```

## URL 发现机制

系统通过以下方式发现 URL：

1. **DOM Anchor**: 解析 `<a href="">` 标签
2. **SPA 路由**: 监听 framenavigated 事件
3. **Network 请求**: 捕获网络请求中的 URL
4. **HTTP Redirect**: 捕获重定向目标
5. **JS Runtime**: 通过 Performance API 获取资源
6. **用户交互**: 模拟点击触发动态加载
7. **文本扫描**: 正则匹配页面文本中的 URL

## URL 分类规则

- **normal_urls**: 普通页面链接
- **media_urls**: 媒体文件 (.png/.jpg/.mp4/.pdf 等)
- **asset_urls**: 静态资源 (.js/.css/.woff 等)
- **garbage_links**: 无效链接 (javascript:/mailto:/tel: 等)

## 架构说明
```
url-discovery-service (FastAPI)
    ↓ HTTP 调用
playwright-service (浏览器自动化)
    ↓ 返回发现的 URLs
url-discovery-service
    ↓ 存储到数据库
OpenGauss Database
    ↓ 调用审核接口
cds-url-audit-img (审核服务)
```

## 注意事项

- 本服务不包含 Playwright，需要单独部署 Playwright 服务
- 数据库使用 OpenGauss，兼容 PostgreSQL 协议
- 定时任务调度器每 10 秒检查一次到期任务
- 创建任务后会立即执行一次，然后按间隔定时执行
- ARM64 环境请使用 `registry.cn-hangzhou.aliyuncs.com/library/python:3.11-slim` 镜像

## 日志

应用日志位置：标准输出 (stdout)

日志级别：INFO

查看日志：
```bash
docker logs -f url-discovery-service
```
