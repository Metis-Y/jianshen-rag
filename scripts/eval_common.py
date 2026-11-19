"""评测题库 MD 解析：tests/eval_set.md → items 列表。

格式约定：
- `## 标签` 之后到下一个 `##` 之间的题都属于该标签；
- `### 问题` 开始一题（前面的序号会被去掉）；
- 题下字段行：
  - `expect: 文档名`（单一出处）
  - `expects: A；B`（多出处，分号分隔，命中任一即对）
  - `points: 要点1；要点2`（端到端评估的答案要点，分号分隔）
"""
import re


def load_eval_set(path: str) -> list[dict]:
    items: list[dict] = []
    tag = "未分类"
    cur: dict | None = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip()
            if not line or line.startswith("# ") or line.startswith(">"):
                continue
            if line.startswith("## "):
                tag = line[3:].strip()
            elif line.startswith("### "):
                if cur:
                    items.append(cur)
                question = re.sub(r"^\d+[\.、]\s*", "", line[4:].strip())
                cur = {"question": question, "tag": tag}
            elif cur is not None:
                if line.startswith("expect:"):
                    cur["expectDoc"] = line[len("expect:"):].strip()
                elif line.startswith("expects:"):
                    cur["expectDocs"] = [x.strip() for x in line[len("expects:"):].split("；") if x.strip()]
                elif line.startswith("points:"):
                    cur["keyPoints"] = [x.strip() for x in line[len("points:"):].split("；") if x.strip()]
    if cur:
        items.append(cur)
    return items