# Aider Code Review 中间件

基于 [Aider](https://github.com/paul-gauthier/aider) 的自动化代码审查中间件服务，支持内网 vLLM 部署。

## ✨ 特性

- 🔗 **Webhook集成**：支持 GitLab、Gitea、GitHub Enterprise
- 🔄 **轮询模式**：定时检测新提交/MR，无需配置 Webhook
- 🤖 **双策略审查**：
  - **Commit审查**：每次提交后快速增量审查
  - **MR审查**：合并请求时深度全面审查
- 📦 **智能分批**：
  - 大型代码变更自动按 Token 限制分批
  - 保留 Repo Map 全仓库上下文感知
  - 实时显示批次执行进度
- ⏰ **生效时间过滤**：只审查指定时间之后的提交
- 📝 **详细报告**：
  - 包含类名/函数名定位
  - 问题代码片段展示
  - 修复代码建议
- 🔒 **内网友好**：适配 vLLM 内网部署场景
- 📊 **Web仪表盘**：可视化统计分析
- ⚙️ **在线配置**：通过Web页面配置，实时生效，无需重启

## 🖥️ Web 仪表盘

访问 `http://<server>:5000/` 查看仪表盘，包含：

- **概览统计**：审查总数、问题分布、质量评分
- **审查记录**：历史审查列表和详情，批次进度显示
- **提交人统计**：按开发者统计代码质量
- **项目统计**：按项目统计审查情况
- **仓库管理**：添加/编辑轮询仓库，配置生效时间
- **⚙️ 系统设置**：在线配置Git/vLLM/Aider参数，Token限制


## 架构

```
┌─────────────┐     Webhook      ┌─────────────────┐     ┌──────────┐
│ Git Platform│ ───────────────► │  Review Server  │ ──► │  vLLM    │
│ (GitLab等)  │                  │   (FastAPI)     │     │  API     │
└─────────────┘                  └────────┬────────┘     └──────────┘
                                          │
                     ┌────────────────────┼────────────────────┐
                     │                    │                    │
                     ▼                    ▼                    ▼
              ┌──────────┐         ┌──────────┐         ┌──────────┐
              │  SQLite  │         │   Web    │         │  Git     │
              │  (统计)  │         │ Dashboard│         │ Comment  │
              └──────────┘         └──────────┘         └──────────┘
```

## 快速开始

### 1. 外网构建镜像

```bash
cd ai_code_review
./scripts/build.sh
# 输出: aider-reviewer_latest.tar.gz
```

### 2. 内网部署

**方式一：使用 docker run 脚本（推荐）**

```bash
# 启动服务
./scripts/run.sh

# 停止服务
./scripts/stop.sh
```

**方式二：使用 docker-compose**

```bash
docker-compose up -d
```

### 3. 配置系统参数

启动后访问 `http://<server_ip>:5000/`，点击 **⚙️ 系统设置**：

| 配置项 | 说明 |
|--------|------|
| **Git平台类型** | gitlab / gitea / github |
| **服务器地址** | 如 `http://code.kf.zjnx.net` |
| **HTTP用户名/密码** | 用于克隆私有仓库 |
| **API地址** | 如 `http://code.kf.zjnx.net/api/v4` |
| **API Token** | 用于回写评论 |
| **启用评论回写** | 开关控制是否发布审查评论 |
| **vLLM API地址** | 如 `http://192.168.1.100:8000/v1` |
| **模型名称** | 如 `openai/qwen-2.5-coder-32b` |

> 💡 所有配置修改后**立即生效**，无需重启容器

### 4. 配置 Webhook

在 Git 平台配置 Webhook：
- **URL**: `http://<server_ip>:5000/webhook`
- **触发事件**: Push events, Merge request events

## 目录结构

```
ai_code_review/
├── review_server.py      # FastAPI主服务 + API
├── config.py             # 配置管理（环境变量默认值）
├── settings.py           # 动态配置管理（数据库存储）
├── utils.py              # 工具函数
├── models.py             # 数据库模型
├── database.py           # 数据库管理
├── statistics.py         # 统计服务
├── static/               # Web仪表盘
│   ├── index.html
│   ├── style.css
│   └── app.js
├── data/                 # 数据库文件(自动创建)
├── Dockerfile
├── docker-compose.yml
├── scripts/
│   ├── build.sh          # 外网构建脚本
│   ├── deploy.sh         # 内网部署脚本
│   ├── run.sh            # docker run 启动脚本
│   └── stop.sh           # 停止服务脚本
└── README.md
```

## API 接口

### 统计API

| 端点 | 说明 |
|------|------|
| `GET /api/stats/overview` | 概览统计 |
| `GET /api/stats/daily-trend` | 每日趋势 |
| `GET /api/stats/authors` | 提交人统计 |
| `GET /api/stats/projects` | 项目统计 |
| `GET /api/stats/reviews` | 审查记录列表 |
| `GET /api/stats/review/{task_id}` | 审查详情 |

### 设置API

| 端点 | 说明 |
|------|------|
| `GET /api/settings` | 获取所有配置 |
| `POST /api/settings` | 批量更新配置 |

### 操作API

| 端点 | 说明 |
|------|------|
| `POST /webhook` | Git Webhook |
| `POST /review` | 手动触发审查 |
| `GET /health` | 健康检查 |

## License

MIT

---

## 📦 智能分批审查

当代码变更涉及大量文件时，系统会自动按 Token 限制分批执行：

### 配置项

| 设置项 | 说明 | 默认值 |
|--------|------|--------|
| 单次审查Token上限 | 超出后自动分批 | 100,000 |
| RepoMap Token数 | 仓库地图上下文大小 | 262,144 |

### 特性

- ✅ 每批次保留完整 Repo Map（全仓库感知）
- ✅ 实时显示批次执行进度
- ✅ 单批次失败不影响其他批次
- ✅ 自动合并多批次报告

---

## ⏰ 生效时间过滤

添加仓库时可设置"生效时间"，只有该时间之后的提交/MR才会触发审查。

**使用场景**：
- 新接入仓库时，避免审查历史提交
- 只关注特定时间节点后的代码变更

---

## 📝 审查报告格式

审查报告包含详细的问题定位信息：

```markdown
**问题 1: SQL注入风险**
- 📍 **位置**: `UserService.findById()` @ `services/user.py:42`
- ❌ **问题代码**:
  ```python
  query = f"SELECT * FROM users WHERE id = {user_id}"
  ```
- ✅ **建议修复**:
  ```python
  query = "SELECT * FROM users WHERE id = ?"
  cursor.execute(query, (user_id,))
  ```
- 💡 **原因**: 直接拼接用户输入存在SQL注入风险
```
