# URL Discovery Service - 真实用户路径 URL 发现服务

## 项目简介

这是一个专注于 **URL 发现** 的爬虫服务，使用 Playwright 模拟真实浏览器行为，通过多种机制捕获现代 Web 应用中的所有可访问 URL。

**核心特性：**
- ✅ 真实浏览器环境（Chromium）
- ✅ 支持 SPA（React / Next.js / Vue）
- ✅ 多种 URL 发现机制（7 种）
- ✅ 同域限制，BFS 遍历
- ✅ openGauss（PostgreSQL）持久化
- ✅ 纯 asyncpg，无 ORM

**明确不做：**
- ❌ 不抓取页面内容
- ❌ 不存储 HTML
- ❌ 不做 SEO 分析
- ❌ 不跨域爬取

## URL 发现机制

### 1. DOM Anchor（最高可信度）
提取所有 `a[href]` 元素，处理相对路径。

### 2. SPA 路由监听（核心）
监听 `page.on("framenavigated")`，捕获前端路由变化（`history.pushState` / `replaceState`）。

### 3. Network 请求捕获
监听 `page.on("request")`，捕获同域非静态资源的请求 URL。

### 4. HTTP Redirect 捕获
监听 `page.on("response")`，解析 30x 跳转的 `Location` header。

### 5. JS Runtime 资源
执行 `performance.getEntriesByType("resource")`，捕获动态加载的资源 URL。

### 6. 自动用户交互
自动点击 `button` / `[role="button"]`，触发可能的路由变化。

### 7. 文本兜底（最低优先级）
正则扫描 HTML 文本中的潜在路径。

## 技术栈

- **Python**: 3.11+
- **FastAPI**: Web 框架
- **Playwright**: 浏览器自动化
- **asyncpg**: PostgreSQL 异步驱动
- **openGauss**: 数据库（PostgreSQL 协议）

## 快速开始

### 1. 环境准备
```bash
# 克隆项目
git clone <repo-url>
cd url_discovery_service

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 2. 配置数据库

创建 `.env` 文件：
```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=url_discovery
```

### 3. 启动服务
```bash
uvicorn app.main:app --reload
```

服务将运行在 `http://localhost:8000`

## API 使用

### POST /crawl-urls

**请求示例：**
```bash
curl -X POST "http://localhost:8000/crawl-urls" \
  -H "Content-Type: application/json" \
  -d '{
    "start_url": "https://example.com",
    "max_depth": 3,
    "max_pages": 1000,
    "persist": true
  }'
```

**响应示例：**
```json
{
  "origin": "https://example.com",
  "task_id": 1,
  "count": 128,
  "urls": [
    "https://example.com",
    "https://example.com/about",
    "https://example.com/pricing",
    "https://example.com/blog/post-1"
  ]
}
```

## Docker 部署
```bash
# 构建镜像
docker build -t url-discovery-service .

# 运行容器
docker run -d \
  -p 8000:8000 \
  -e DB_HOST=your_db_host \
  -e DB_USER=postgres \
  -e DB_PASSWORD=your_password \
  --name url-discovery \
  url-discovery-service
```

## 数据库表结构

### web_urls（URL 表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL | 主键 |
| origin | TEXT | 域名 origin |
| url | TEXT | 完整 URL |
| url_path | TEXT | URL path |
| depth | INT | 爬取深度 |
| discovered_from | TEXT | 来源 URL |
| discovery_type | TEXT | 发现方式 |
| first_seen_at | TIMESTAMP | 首次发现时间 |
| last_seen_at | TIMESTAMP | 最后发现时间 |

### web_crawl_tasks（任务表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL | 主键 |
| origin | TEXT | 域名 origin |
| start_url | TEXT | 起始 URL |
| max_depth | INT | 最大深度 |
| max_pages | INT | 最大页面数 |
| status | TEXT | 任务状态 |
| total_urls | INT | 总 URL 数 |
| started_at | TIMESTAMP | 开始时间 |
| finished_at | TIMESTAMP | 结束时间 |

## 日志

服务使用 Python logging 模块，日志级别为 INFO。关键日志包括：

- 数据库连接状态
- 爬取进度（已访问页面数）
- URL 发现统计
- 错误信息

## 注意事项

1. **性能**：Playwright 是真实浏览器，资源消耗较大，建议合理设置 `max_pages`
2. **反爬**：目标站点可能有反爬机制，建议添加请求延迟
3. **超时**：默认页面超时 30 秒，可在配置中调整
4. **同域限制**：严格执行同域策略，不会跨域爬取

## License

MIT