# 健身管家 FitPal

基于**私有文档 + 个人训练数据**的健身问答助手：上传训练计划与营养资料，记录每天的训练、
体重和饮食，用自然语言提问。计划与饮食类回答严格依据上传资料并附引用出处；
效果类问题（"这周进步了吗"）基于你的真实记录数据回答，不编造。

## 功能

- **账号体系**：注册 / 登录（JWT），数据按用户隔离
- **资料库**：上传 PDF / Word / Markdown，自动解析与切分；支持秒传（MD5）、
  失败原因提示、重试、删除（三处同步清理）
- **训练记录**：记录动作/重量/组数/次数，自动统计训练容量；支持快速记录模式
- **体征与饮食**：体重/体脂记录，饮食日志与忌口标签（长期忌口一次设置）
- **问答**：SSE 流式输出 + 引用出处；支持限定在指定文档内提问；历史会话可回看、可反馈

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python 3.11 · FastAPI · SQLAlchemy 2 · SQLite |
| 检索 | ChromaDB（本地持久化） + LangChain（文档解析/切分） |
| 模型 | OpenAI 兼容 API（默认硅基流动：bge-m3 Embedding + DeepSeek 对话模型） |
| 认证 | PyJWT + bcrypt |
| 前端 | Vue 3 · Vite · Element Plus · Axios，nginx 反向代理（可选） |

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
# nginx 配置见 frontend/nginx/conf/nginx.conf（默认 8090 端口，已配置 SSE buffering off）
```

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| SILICONFLOW_API_KEY | 必填 | 大模型平台 API Key |
| SILICONFLOW_BASE_URL | https://api.siliconflow.cn/v1 | OpenAI 兼容地址 |
| EMBEDDING_MODEL | BAAI/bge-m3 | 向量模型 |
| CHAT_MODEL | deepseek-ai/DeepSeek-V3 | 对话模型 |
| JWT_SECRET | dev-secret-change-me | 生产必须修改 |
| CHUNK_SIZE / CHUNK_OVERLAP | 500 / 80 | 切分参数 |
| MAX_UPLOAD_MB | 20 | 上传上限 |
| SQLITE_PATH | ./data/jianshen.db | 数据库路径 |

## 目录结构

```
.
├── app/
│   ├── main.py            # 应用入口（路由、全局异常统一响应）
│   ├── config.py          # 环境变量配置
│   ├── db.py              # SQLAlchemy 模型
│   ├── auth.py            # JWT 签发与校验
│   ├── schemas.py         # 请求/响应模型
│   ├── resp.py            # 统一响应包络
│   ├── services/          # 文档解析/切分、业务编排
│   └── routers/           # auth / documents 等接口路由
├── frontend/              # Vue 3 前端（dev: vite proxy）
├── docs/API.md            # 接口文档
└── requirements.txt
```