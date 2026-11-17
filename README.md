# 健身管家 FitPal

一个结合「私有文档」与「个人训练数据」的健身问答助手：你可以上传训练计划与营养资料，记录每天的
体重、睡眠与三餐。用自然语言提问时，涉及原理与计划的问题会严格依据资料回答并附引用出处；涉及
个人进展的问题（如"这周进步了吗""该不该休息""离目标还多远"）会基于你的真实记录回答，而不是编造。
内置公共知识库，新用户无需上传任何资料也能得到带出处的回答。

## 功能

- **账号体系**：注册与登录（JWT），每个用户的数据按用户隔离、互不可见。
- **资料库**：上传 PDF / Word / Markdown / TXT 文档，系统自动解析与切分入库；重复上传同一文件
  会通过 MD5 去重、直接复用已有结果。解析失败会给出原因并支持一键重试；删除时同步清理磁盘文件、
  向量与业务记录三处。上传做了安全校验——文件名清洗、格式白名单、文件头与编码检查，防止路径穿越
  与伪装文件。
- **公共知识库**：内置 23 份健身语料（训练进阶 / 营养补剂 / 人群场景 / 恢复损伤 / 体成分评估），
  由 system 账号持有、对全体用户可见；你上传的个人资料与其同权参与检索。
- **训练记录**：记录动作、重量、组数、次数，自动按「重量 × 组数 × 次数」统计容量；支持快速记录
  （只记动作名）与删除。
- **体征与饮食**：记录体重、睡眠时长与酸痛度；三餐（早 / 午 / 晚）可选填、可删除。
- **个人档案**：训练目标、目标体重、多条力量目标（动作名 + 目标重量，可增删）与长期忌口。
- **问答**：SSE 流式输出，附引用出处卡片；基于真实数据回答进展 / 恢复 / 目标进度；支持限定文档
  范围提问、历史会话回看，点赞反馈可修改、可取消。
- **统计**：资料数、训练天数、问答次数、好评率、最近体重与本周容量。
- **评估体系**：检索评估与端到端评估用同一条命令即可复现，见 [docs/EVALUATION.md](docs/EVALUATION.md)。
- **演示数据**：`scripts/seed_demo.py` 一键生成 demo 账号、示例语料与公共知识库。

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python 3.11 · FastAPI · SQLAlchemy 2 · SQLite |
| 检索 | ChromaDB（本地持久化 + 元数据过滤）· LangChain（文档解析与切分） |
| 模型 | OpenAI 兼容 API：BAAI/bge-m3 向量化、bge-reranker-v2-m3 重排，对话模型可替换 |
| 认证 | PyJWT + bcrypt |
| 前端 | Vue 3 · Vite · Element Plus · Axios；生产可用 nginx 反向代理（已配 SSE 缓冲关闭） |

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

- 首次启动会自动创建数据表（SQLite，`./data/jianshen.db`）。
- 在线接口文档：http://127.0.0.1:8000/docs
- 完整接口契约（含 SSE 事件协议与错误码）：[docs/API.md](docs/API.md)

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

一次执行完成四件事：① 创建 demo 账号（demo / demo1234）并写入三天训练、体重、睡眠 / 酸痛、
忌口与目标；② 给 demo 上传三份个人示例语料（samples/）；③ 重建公共知识库（samples/public/
下的 23 份语料）；④ 归一化存量向量元数据。

若只改了公共语料，可用 `python scripts/rebuild_public_kb.py` 单独重建公共库，而不会重置 demo 的
记录。语料清单与来源见 [scripts/corpus_manifest.py](scripts/corpus_manifest.py) 与
[docs/CORPUS_SOURCES.md](docs/CORPUS_SOURCES.md)。脚本可重复执行：记录类数据会重置，个人资料
通过 MD5 去重、不会重复入库。

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| SILICONFLOW_API_KEY | 必填 | 大模型平台 API Key；embedding 与 chat 未单独配置时共用此 key |
| EMBEDDING_BASE_URL / EMBEDDING_MODEL | https://api.siliconflow.cn/v1 / BAAI/bge-m3 | 向量化模型及其服务地址 |
| CHAT_BASE_URL / CHAT_MODEL | https://api.siliconflow.cn/v1 / deepseek-ai/DeepSeek-V3 | 对话模型及其服务地址，可替换 |
| CHAT_THINKING | 空（不传该参数） | 思考开关，供推理系模型使用（如小米 MiMo v2.6 的 enabled / disabled）；留空走服务端默认 |
| JWT_SECRET / JWT_TTL_HOURS | dev-secret-change-me / 72 | JWT 密钥与有效期，生产环境务必更换密钥 |
| CHUNK_SIZE / CHUNK_OVERLAP / TOPK | 500 / 80 / 5 | 文档切分与检索参数 |
| RERANK_BASE_URL / RERANK_MODEL | https://api.siliconflow.cn/v1 / BAAI/bge-reranker-v2-m3 | 检索精排模型；key 缺省复用 SILICONFLOW_API_KEY，设为空则退回纯向量粗排 |
| MAX_UPLOAD_MB | 20 | 单文件上传大小上限 |
| EMBEDDING_TIMEOUT / CHAT_TIMEOUT | 60 | 模型调用超时（秒），上游无响应时快速失败而不是长时间挂起 |
| DATA_DIR / SQLITE_PATH / UPLOAD_DIR / CHROMA_DB_PATH | ./data 等 | 数据目录（数据库、附件与向量库） |

## 目录结构

```
.
├── app/
│   ├── main.py             # 应用入口（路由注册、全局异常统一响应）
│   ├── config.py           # 环境变量配置
│   ├── db.py               # SQLAlchemy 模型
│   ├── auth.py             # JWT 签发与校验
│   ├── schemas.py          # 请求 / 响应模型
│   ├── resp.py             # 统一响应包络 {code, message, data}
│   ├── repositories/       # 数据访问层（users / documents / records / chat / summary）
│   ├── services/           # pipeline 解析切分 / document_service 编排 / index 向量索引 / rag 问答
│   └── routers/            # auth / documents / workouts / metrics / diets / preference / chat / conversations / stats
├── frontend/               # Vue 3 前端（登录 / 首页 / 资料 / 记录 / 问答）
├── scripts/
│   ├── seed_demo.py        # 演示数据种子（demo 账号 + 语料 + 公共库）
│   ├── corpus_manifest.py  # 公共语料清单（文件名 + 分类）
│   ├── rebuild_public_kb.py# 只重建公共知识库（不动 demo 记录）
│   ├── run_eval.py         # 检索评估（top1/3/5 命中率、MRR、来源多样性）
│   └── run_e2e_eval.py     # 端到端评估（真实问答 + LLM 判卷要点覆盖率）
├── samples/                # 个人示例语料 + public/ 公共知识库语料
├── docs/
│   ├── API.md              # 接口契约
│   ├── EVALUATION.md       # 评估手册（检索 + 端到端两级的跑法、指标与阈值）
│   └── CORPUS_SOURCES.md   # 公共语料来源与写作约定
└── requirements.txt
```