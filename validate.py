#!/usr/bin/env python3
"""News Categories SKILL —— 输出硬校验脚本。

校验打标结果是否符合《返回结构.schema.json》。

用法：
  python3 validate.py                 # 校验 测试输出.md（默认）
  python3 validate.py <文件.md>       # 校验指定 markdown 文件（抽第一个 JSON）
  python3 validate.py <文件.json>     # 校验纯 JSON 文件
  python3 validate.py --all           # 全量校验 金标准样本.md 的所有样本

依赖：jsonschema（pip install jsonschema）
"""
import json
import os
import re
import sys

SCHEMA = "返回结构.schema.json"
GOLDEN = "金标准样本.md"
DEFAULT = "测试输出.md"


def load_schema(path=SCHEMA):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_json(text):
    """从 markdown 文本抽取 JSON：优先 ```json 代码块，其次首 { 到末 }。"""
    m = re.search(r"```json\s*(.*?)\s*```", text, re.S)
    if m:
        return m.group(1)
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1:
        return None
    return text[s:e + 1]


def validate_one(raw, schema):
    """校验一段 JSON 文本，返回 (obj_or_None, 消息)。"""
    from jsonschema import Draft202012Validator

    try:
        obj = json.loads(raw)
    except Exception as ex:
        return None, f"JSON 解析失败: {ex}"
    errs = list(Draft202012Validator(schema).iter_errors(obj))
    if errs:
        detail = "\n".join(
            f"  - {'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
            for e in errs[:20]
        )
        return obj, "SCHEMA FAIL:\n" + detail
    return obj, "PASS"


def validate_file(path, schema):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith(".json"):
        raw = text
    else:
        raw = extract_json(text)
        if raw is None:
            print(f"✗ {path}: 未找到 JSON（无 ```json 代码块且无 {{ }} 括号）")
            return False
    obj, msg = validate_one(raw, schema)
    if obj is None:
        print(f"✗ {path}: {msg}")
        return False
    if msg == "PASS":
        theme = obj.get("theme") or {}
        sub = theme.get("sub") if theme else None
        n_ent = len(obj.get("entities") or [])
        print(f"✓ {path}: PASS  theme={theme.get('name')}/{sub}  entities={n_ent}")
        return True
    print(f"✗ {path}: {msg}")
    return False


def validate_all(schema):
    with open(GOLDEN, encoding="utf-8") as f:
        text = f.read()
    parts = re.split(r"\n## 样本\s*(\d+)", text)
    ok = 0
    bad = []
    for i in range(1, len(parts) - 1, 2):
        num = parts[i]
        body = parts[i + 1]
        raw = extract_json(body)
        if raw is None:
            bad.append((num, "无 JSON 代码块"))
            continue
        obj, msg = validate_one(raw, schema)
        if obj is None or msg != "PASS":
            bad.append((num, msg))
            continue
        ok += 1
    print(f"全量校验 {GOLDEN}：{ok} PASS, {len(bad)} FAIL")
    for num, msg in bad:
        print(f"  ✗ 样本{num}: {msg}")
    return len(bad) == 0


def main():
    schema = load_schema()
    args = sys.argv[1:]
    if "--all" in args or "-a" in args:
        ok = validate_all(schema)
    else:
        path = args[0] if args else DEFAULT
        if not os.path.exists(path):
            print(f"文件不存在: {path}")
            sys.exit(1)
        ok = validate_file(path, schema)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
