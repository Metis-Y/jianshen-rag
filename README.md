# 健身管家 FitPal

一个结合「私有文档」与「个人训练数据」的健身问答助手。可以上传训练计划与营养资料，记录每天的
体重、睡眠与三餐，用自然语言提问：涉及原理与计划的问题依据资料回答并附引用出处，涉及个人进展的
问题（"这周进步了吗""该不该休息""离目标还多远"）基于真实记录回答，不编造。内置公共知识库，
新用户无需上传资料也能得到带出处的回答。

问答支持两种模式：**固定管道**（检索 → 聚合 → 拼装 → 生成）与**工具调用**（模型自主选择
`search_docs` 检索资料 / `get_my_data` 查询真实数据），通过环境变量切换，旧管道保留为降级兜底。

## 功能

- **账号体系**：注册、登录（JWT），用户数据按账号隔离、互不可见。
- **资料库**：上传 PDF / Word / Markdown / TXT，自动解析、切分并向量化；重复上传通过 MD5
  去重复用已有结果；解析失败给出原因并支持重试；删除走「置 DELETED → 清磁盘/切片/向量 →
  删记录」，进程中断残留由启动扫描兜底。上传侧做安全校验：文件名清洗、格式白名单、文件头与
  编码检查。
- **公共知识库**：内置 23 份健身语料，覆盖训练、营养、恢复、损伤、体成分与人群场景，对全体
  用户可见，与个人资料同权参与检索。
- **训练记录**：记录动作、重量、组数、次数，自动按「重量 × 组数 × 次数」统计容量；支持快速
  记录、删除与动作明细展开。
- **体征与饮食**：记录体重、睡眠时长、酸痛度；三餐（早 / 午 / 晚），均可删除。
- **个人档案**：训练目标、目标体重、多条力量目标（动作名 + 目标重量）、长期忌口。
- **问答**：SSE 流式输出，附引用出处卡片；只回答健身相关问题，超出范围直接拒绝；数据类回答
  只引用真实记录、不编造；支持限定文档范围提问、历史会话回看、反馈可修改可取消。
- **统计**：资料数、训练天数、问答次数、好评率、最近体重、本周容量。
- **评估体系**：检索评估（59 题）与端到端评估（LLM 判卷要点覆盖率）各一条命令复现，见
  [docs/评估手册.md](docs/评估手册.md)。
- **演示数据**：`scripts/seed_demo.py` 生成 demo 账号、示例语料与公共知识库。

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python 3.11 · FastAPI · SQLAlchemy 2 · SQLite |
| 检索 | ChromaDB（本地持久化 + 元数据过滤）· LangChain（解析与切分） |
| 模型 | OpenAI 兼容 API：BAAI/bge-m3 向量化、bge-reranker-v2-m3 重排、对话模型可替换；支持函数式工具调用 |
| 认证 | PyJWT + bcrypt |
| 前端 | Vue 3 · Vite · Element Plus · Axios；生产用 nginx 反向代理（含 SSE 缓冲关闭） |

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

- 首次启动自动创建数据表（SQLite，`./data/jianshen.db`）。
- 在线接口文档：http://127.0.0.1:8000/docs
- 接口契约（含 SSE 事件协议与错误码）：[docs/API.md](docs/API.md)

### 2. 前端

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173（/api 由 Vite 代理到 8000）
```

生产构建（可选）：

```bash
npm run build        # 生成前端产物 dist/
# nginx 配置见 frontend/nginx/conf/nginx.conf（默认 8090 端口）
```

### 3. 演示数据（可选）

```bash
python scripts/seed_demo.py
```

一次执行创建 demo 账号（demo / demo1234）并写入三天训练、体重、睡眠/酸痛、忌口与目标；给 demo
上传三份个人示例语料；重建公共知识库；归一化存量向量元数据。

只改公共语料时，用 `python scripts/rebuild_public_kb.py` 单独重建公共库，不重置 demo 记录。语料
清单与来源见 [scripts/corpus_manifest.py](scripts/corpus_manifest.py) 与
[docs/语料来源.md](docs/语料来源.md)。脚本可重复执行：记录类数据会重置，个人资料通过 MD5 去重、
不重复入库。

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| SILICONFLOW_API_KEY | 必填 | 大模型平台 API Key；embedding 与 chat 未单独配置时共用 |
| EMBEDDING_BASE_URL / EMBEDDING_MODEL | https://api.siliconflow.cn/v1 / BAAI/bge-m3 | 向量化模型及服务地址 |
| CHAT_BASE_URL / CHAT_MODEL | https://api.siliconflow.cn/v1 / deepseek-ai/DeepSeek-V3 | 对话模型及服务地址，可替换 |
| CHAT_THINKING | 空（不传该参数） | 思考开关，供推理系模型使用（如 MiMo 的 enabled / disabled），留空走服务端默认 |
| AGENT_MODE | on | 问答模式：on = 工具调用（模型自选工具），off = 固定管道 |
| JWT_SECRET / JWT_TTL_HOURS | dev-secret-change-me / 72 | JWT 密钥与有效期，生产务必更换 |
| CHUNK_SIZE / CHUNK_OVERLAP / TOPK | 500 / 80 / 5 | 文档切分与检索参数 |
| RERANK_BASE_URL / RERANK_MODEL | https://api.siliconflow.cn/v1 / BAAI/bge-reranker-v2-m3 | 检索精排模型；key 缺省复用 SILICONFLOW_API_KEY，设为空退回纯向量粗排 |
| EMBEDDING_TIMEOUT / CHAT_TIMEOUT | 60 | 模型调用超时（秒） |
| MAX_UPLOAD_MB | 20 | 单文件上传上限 |
| DATA_DIR / SQLITE_PATH / UPLOAD_DIR / CHROMA_DB_PATH | ./data 等 | 数据目录（数据库、附件、向量库） |

## 目录结构

```
.
├── app/
│   ├── main.py             # 应用入口（路由注册、全局异常、启动恢复与后台清理）
│   ├── config.py           # 环境变量配置
│   ├── db.py               # SQLAlchemy 模型
│   ├── auth.py             # JWT 签发与校验
│   ├── schemas.py          # 请求 / 响应模型
│   ├── resp.py             # 统一响应包络 {code, message, data}
│   ├── repositories/       # 数据访问层（users / documents / records / chat / summary）
│   ├── services/           # pipeline 解析切分 / document_service 编排 / index 向量索引 / rag 问答与工具调用
│   └── routers/            # auth / documents / workouts / metrics / diets / preference / chat / conversations / stats
├── frontend/               # Vue 3 前端（登录 / 首页 / 资料 / 记录 / 问答）
├── scripts/
│   ├── seed_demo.py        # 演示数据种子（demo 账号 + 语料 + 公共库）
│   ├── corpus_manifest.py  # 公共语料清单（文件名 + 分类）
│   ├── rebuild_public_kb.py# 只重建公共知识库（不动 demo 记录）
│   ├── run_eval.py         # 检索评估（top1/3/5、MRR、来源多样性）
│   └── run_e2e_eval.py     # 端到端评估（真实问答 + LLM 判卷要点覆盖率）
├── samples/                # 个人示例语料 + public/ 公共知识库语料
├── docs/
│   ├── API.md              # 接口契约
│   ├── 评估手册.md         # 评估手册（检索 + 端到端两级的跑法、指标与阈值）
│   └── 语料来源.md         # 公共语料来源与写作约定
└── requirements.txt
```