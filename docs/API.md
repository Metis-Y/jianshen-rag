# 05 · 接口文档

> 设计契约，编码以此为准。所有接口前置 `/api`；明文 JSON 统一包裹
> `{ "code": 1, "message": "ok", "data": ... }`；code=1 成功，非 0 失败。

## 0. 通用约定

- **鉴权**：除 `/auth/register`、`/auth/login` 外，请求头必须带 `Authorization: Bearer <JWT>`；
  缺失/失效 → HTTP 401，`code: 40100`
- **错误码**：

| code | 含义 |
| --- | --- |
| 1 | 成功 |
| 40010 | 参数缺失/格式错误（message 指明字段） |
| 40100 | 未认证 / token 失效 |
| 40301 | 无权限（访问他人资源） |
| 40401 | 资源不存在 |
| 41301 | 文件超过大小上限（20MB） |
| 50060 | 文档解析失败后重试仍失败 |
| 50202 | 模型 API 不可用（流未开始时返回；流已开始走 SSE error 事件） |
| 50000 | 系统错误 |

- **分页**：`?page=1&size=10` → `data: { total, page, size, list: [...] }`

## 1. 认证 /auth

### POST /auth/register —— 注册

入参 body：

```json
{ "username": "frank", "password": "abc123456" }
```

返回：

```json
{ "code": 1, "message": "ok", "data": { "id": 1, "username": "frank" } }
```

用户名重复 → 40010（message: "用户名已存在"）。

### POST /auth/login —— 登录

入参：`{ "username": "frank", "password": "abc123456" }`

返回：`data: { "token": "eyJ...", "exp": 1774000000 }`

### GET /auth/me —— 当前用户（含偏好）

返回：

```json
{ "data": { "id": 1, "username": "frank", "goal": "减脂", "allergies": ["牛奶"] } }
```

## 2. 偏好 /preference

### GET /preference

返回：`data: { "goal": "减脂", "allergies": ["牛奶"], "targetWeight": 78, "targetStrengthName": "深蹲", "targetStrengthValue": 100 }`
（未设置时 goal=null、allergies=[]、目标字段均为 null）

### PUT /preference

入参：`{ "goal": "增肌", "allergies": ["花生", "牛奶"], "targetWeight": 80, "targetStrengthName": "卧推", "targetStrengthValue": 120 }`
（字段均可选，整体覆盖；targetWeight 目标体重 kg；targetStrengthName 目标力量动作自选，
不填默认"深蹲"，targetStrengthValue 对应目标重量 kg）

返回：更新后的完整偏好对象。

## 3. 资料 /documents（训练计划、营养等文档）

### POST /documents —— 上传（同步处理）

Content-Type: `multipart/form-data`

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| file | 是 | PDF/Word/MD，≤20MB |
| category | 否 | `plan` / `diet` / `other` |

返回（三个分支）：

```json
// 成功：
{ "data": { "docId": 7, "filename": "腿部计划.pdf", "status": "READY", "chunkCount": 24, "dedup": false } }
// 秒传（同用户同 MD5 且 READY）：
{ "data": { "docId": 3, "filename": "腿部计划.pdf", "status": "READY", "chunkCount": 24, "dedup": true } }
// 解析失败：
{ "data": { "docId": 8, "filename": "x.pdf", "status": "FAILED", "failReason": "无法提取文本（疑似扫描件）" } }
```

### GET /documents —— 列表

Query：`page, size, category?`

返回：`data: { total, list: [ { docId, filename, category, status, chunkCount, sizeBytes, createdAt } ] }`

### GET /documents/{id} —— 详情

返回：单条同上 + `failReason`。

### POST /documents/{id}/retry —— 失败重试

入参无。返回同上传成功/失败分支（重新解析入库）。

### DELETE /documents/{id} —— 删除

**三处同步**：磁盘文件 + Chroma 向量（where doc_id）+ 业务记录。
返回：`{ "code": 1, "data": null }`。删除后相关问答 → "知识库中没有相关内容"。

## 4. 记录 /workouts、/metrics、/diets

### POST /workouts —— 记一次训练

入参：

```json
{
  "date": "2026-11-02",
  "exercises": [
    { "name": "深蹲", "weight": 80, "sets": 5, "reps": 5 },
    { "name": "硬拉", "weight": 100, "sets": 3, "reps": 5 }
  ],
  "note": "状态不错"
}
```

快速模式：`exercises` 里只填 `name`（weight/sets/reps 缺省，不入容量统计）。
返回：`data: { "id": 12, "volume": 3500 }`（volume = Σ weight×sets×reps）。

### GET /workouts?from=&to= —— 区间训练

返回：

```json
{ "data": { "totalVolume": 12000, "records": [ { "id": 12, "date": "2026-11-02",
  "volume": 3500, "exercises": [...], "note": "..." } ] } }
```

### POST /metrics —— 记体重/体征

入参：`{ "date": "2026-11-02", "weight": 72.3, "bodyFat": null, "sleepHours": 7.5, "soreness": 3 }`
（bodyFat 预留；sleepHours 睡眠时长小时、soreness 酸痛度 1~5，用于恢复线问答）

返回：`data: { "id": 5 }`

### GET /metrics?from=&to=

返回：`data: { "latest": { "date": "2026-11-02", "weight": 72.3, "sleepHours": 7.5, "soreness": 3 }, "delta": -0.6, "series": [ { "date": "...", "weight": 72.9, "sleepHours": 7.0, "soreness": 2 }, ... ] }`

### POST /diets —— 记一餐饮食

入参：`{ "date": "2026-11-02", "meal": "午餐", "content": "鸡胸肉+糙米+西兰花" }`
（meal 可选：早餐/午餐/晚餐，分餐分别提交；avoid 为历史兼容字段，表单已不再提交——忌口只走偏好长期忌口）

返回：`data: { "id": 3 }`

### GET /diets?from=&to=

返回：`data: { "records": [ { "id": 3, "date": "...", "meal": "午餐", "content": "...", "avoid": [...] } ] }`

### DELETE /diets/{id} —— 删除一条饮食记录

仅限本人（他人记录 403）。返回：`{ "code": 1, "data": null }`。

## 5. 问答 /chat（SSE）

### POST /chat

入参：

```json
{ "question": "我最近一周训练进步了吗？", "conversationId": 2, "documentIds": [7] }
```

- `conversationId` 可选：不传新建会话，响应 done 事件里回传
- `documentIds` 可选：限定检索范围；不传全库（自己的文档）

响应 `text/event-stream`，事件序列：

```text
event: citations
data: [{"idx":1,"docTitle":"腿部训练计划","source":"第2章","text":"深蹲日安排……"}]

event: message
data: {"delta":"你本周训练总容量"}

event: message
data: {"delta":" 12000kg，体重下降 0.6kg [1]"}

event: done
data: {"conversationId":2,"messageId":9}
```

| event | 触发 | data |
| --- | --- | --- |
| citations | 首个 token 前 | 引用数组 `[{idx, docTitle, source, text(前80字)}]` |
| message | 逐 token | `{delta}` |
| done | 结束 | `{conversationId, messageId}` |
| error | 上游失败 | `{message}` |

后端每次提问都**先聚合 SQLite 真实数据**（容量/体重/睡眠/酸痛/目标进度）作为【我的数据】块、
再检索 topK 文档块作为【资料】块拼进 Prompt；用哪个来源、以及"记录不足/没有相关内容"等
退化话术，均由模型按系统提示词自行判断，禁止编造。

## 6. 会话与反馈

| 方法 | 路径 | 入参 | 返回 |
| --- | --- | --- | --- |
| GET | /conversations?page=&size= | — | `{total, list:[{id,title,createdAt}]}` |
| GET | /conversations/{id}/messages | — | `{list:[{id,role,content,citations,feedback,createdAt}]}`（feedback 为当前用户的反馈：true/false，未反馈 null） |
| DELETE | /conversations/{id} | — | `{ "code": 1, "data": null }` |
| POST | /messages/{id}/feedback | `{ "positive": true }`（true 有帮助 / false 没帮助 / null 取消） | `{ "code": 1, "data": null }` |

### GET /stats

返回：

```json
{ "data": { "docCount": 4, "logDays": 12, "qaCount": 30,
  "positiveRate": 0.85, "latestWeight": 72.3, "weekVolume": 12000 } }
```