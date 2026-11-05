# 健身管家 FitPal

基于**私有文档 + 个人训练数据**的健身问答助手：上传训练计划与营养资料，记录每天的训练、
体重、睡眠与三餐，用自然语言提问。计划与饮食类回答严格依据资料并附引用出处；
"这周进步了吗 / 该不该休息 / 离目标多远"基于你的真实记录数据回答，不编造。
内置**公共知识库**：新用户什么都不传也能得到带出处的回答。

## 功能

- **账号体系**：注册 / 登录（JWT），数据按用户隔离
- **资料库**：上传 PDF / Word / Markdown，自动解析与切分；支持秒传（MD5）、
  失败原因提示、重试、删除（磁盘 + 向量 + 记录三处同步清理）
- **公共知识库**：内置 9 份健身语料（训练 / 饮食 / 恢复 / 安全），system 账号持有，
  全体用户检索可见；你上传的个人资料优先级相同、按相关性参与检索
- **训练记录**：动作/重量/组数/次数，自动统计容量（Σ重量×次数×组数）；快速记录模式；删除
- **体征与饮食**：体重 + 睡眠时长 + 酸痛度；三餐（早/午/晚）可选填、可删除
- **个人档案**：训练目标、目标体重、多条力量目标（动作名 + 重量，可增删）、长期忌口（一次设置）
- **问答**：SSE 流式输出 + 引用出处卡片；基于真实数据回答进展/恢复/目标进度；
  限定文档范围提问；历史会话回看、点赞反馈可修改可取消
- **统计**：资料数 / 训练天数 / 问答次数 / 好评率 / 最近体重 / 本周容量
- **演示数据**：`scripts/seed_demo.py` 一键生成 demo 账号、示例语料与公共库（见下）

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python 3.11 · FastAPI · SQLAlchemy 2 · SQLite |
| 检索 | ChromaDB（本地持久化，元数据过滤）+ LangChain（文档解析/切分） |
| 模型 | OpenAI 兼容 API（硅基流动：bge-m3 Embedding + 对话模型按配置可换） |
| 认证 | PyJWT + bcrypt |
| 前端 | Vue 3 · Vite · Element Plus · Axios，nginx 反向代理（可选，已配 SSE buffering off） |

## 快速开始

### 1. 后端

```bash
conda create -n jianshen-rag python=3.11 -y
conda activate jianshen-rag
pip install -r requirements.txt

# 配置大模型 API Key（必须）
# Windows PowerShell:  $env:SILICONFLOW_API_KEY="sk-xxxx"
# Linux/macOS:        export SILICONFLOW_API_KEY="sk-xxxx"

uvicorn app.main:app --port 8000
```

- 启动后自动建表（SQLite，`./data/jianshen.db`）
- 交互式接口文档：http://127.0.0.1:8000/docs
- 完整接口契约（含 SSE 事件协议与错误码）：[docs/API.md](docs/API.md)

### 2. 前端

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173（/api 由 Vite 代理到 8000）
```

生产构建 + nginx（可选）：

```bash
npm run build        # 前端产物 dist/
# nginx 配置见 frontend/nginx/conf/nginx.conf（默认 8090 端口）
```

### 3. 演示数据（可选）

```bash
python scripts/seed_demo.py
```

一次执行完成四件事：① 创建 demo 账号（demo / demo1234）并写入 3 天训练、体重、
睡眠/酸痛、忌口与目标；② 给 demo 上传 3 份个人示例语料（samples/）；
③ 重建公共知识库（samples/public/ 下 9 份语料）；④ 归一化存量向量元数据。
可重复执行（记录类会重置，资料走 MD5 秒传）。

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| SILICONFLOW_API_KEY | 必填 | 大模型平台 API Key（embedding 与 chat 未单独配置时共用） |
| EMBEDDING_BASE_URL / EMBEDDING_MODEL | https://api.siliconflow.cn/v1 / BAAI/bge-m3 | 向量模型 |
| CHAT_BASE_URL / CHAT_MODEL | https://api.siliconflow.cn/v1 / deepseek-ai/DeepSeek-V3 | 对话模型（可按平台替换） |
| JWT_SECRET / JWT_TTL_HOURS | dev-secret-change-me / 72 | 生产必须改密钥 |
| CHUNK_SIZE / CHUNK_OVERLAP / TOPK | 500 / 80 / 5 | 切分与检索参数 |
| MAX_UPLOAD_MB | 20 | 上传大小上限 |
| DATA_DIR / SQLITE_PATH / UPLOAD_DIR / CHROMA_DB_PATH | ./data 等 | 数据目录（数据库/附件/向量库） |

## 目录结构

```
.
├── app/
│   ├── main.py            # 应用入口（路由注册、全局异常统一响应）
│   ├── config.py          # 环境变量配置
│   ├── db.py              # SQLAlchemy 模型
│   ├── auth.py            # JWT 签发与校验
│   ├── schemas.py         # 请求/响应模型
│   ├── resp.py            # 统一响应包络 {code, message, data}
│   ├── repositories/      # 数据访问层（users/documents/records/chat/summary 查询下沉）
│   ├── services/          # pipeline 解析切分 / document_service 文档编排 /
│   │                      # index 向量索引 / rag 聚合与双块 Prompt 问答
│   └── routers/           # auth / documents / workouts / metrics / diets /
│                          # preference / chat / conversations / stats
├── frontend/              # Vue 3 前端（登录/资料/记录/问答/首页）
├── scripts/seed_demo.py   # 演示数据种子（demo 账号 + 语料 + 公共库）
├── samples/               # 个人示例语料 + public/ 公共知识库语料
├── docs/API.md            # 接口契约
└── requirements.txt
```