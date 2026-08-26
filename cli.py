#!/usr/bin/env python3
"""News Categories SKILL —— 方案 B：命令行打标脚本。

把 9 个规则文件全文拼成 system prompt（确定性，不靠模型"读 URL"模拟），
调 DeepSeek API 对一篇文章打标，输出 JSON 并跑《返回结构.schema.json》硬校验。

用法：
  python3 cli.py                     # 打标《测试输入.md》（默认，开箱即用）
  python3 cli.py 我的文章.md          # 打标指定文件（支持「标题：/内容：」或 JSON 两种格式）
  python3 cli.py -i                  # 交互式：手动粘贴标题 + 正文
  python3 cli.py --model deepseek-reasoner   # 换模型（默认 deepseek-chat）

API Key（按优先级，任选其一）：
  1. 环境变量 DEEPSEEK_API_KEY
  2. 项目根目录 .env 文件，内容一行：DEEPSEEK_API_KEY=sk-xxx

依赖：openai、jsonschema（pip install -r requirements.txt）
"""
import argparse
import json
import os
import re
import sys

import validate as v

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 规则文件（按打标学习顺序拼接；不含《金标准样本.md》——那 16 万字只用于回归评测，不进 prompt）
RULE_FILES = [
    "通用规则.md",
    "主题.md",
    "实体.md",
    "组合规则.md",
    "收录标准.md",
    "返回结构.md",
    "实体同义词表.md",
]
SCHEMA_PATH = os.path.join(BASE_DIR, "返回结构.schema.json")
DEFAULT_INPUT = os.path.join(BASE_DIR, "测试输入.md")

INSTRUCTION = """你是"足球新闻分类打标器"。请严格遵循下面的《News Categories SKILL》规范，对用户提供的足球新闻文章打标。

输出要求（硬性）：
1. 只输出一个 JSON 对象，不要输出任何解释、前后缀、markdown 代码块标记。
2. 输出必须能通过《返回结构.schema.json》的 JSON Schema 硬校验。
3. theme.name / theme.sub 必须严格使用《主题.md》里的枚举名称，禁止同义替换或自造。
4. 实体命名遵循《实体.md》命名规范：人名用完整音译名（名·姓），球队/赛事/机构用官方中文全称。
5. 同一实体只出现一次；只打重点（required/core/significant），边缘提及不打。

以下是规范全文："""


def _p(name: str) -> str:
    return os.path.join(BASE_DIR, name)


def build_system_prompt() -> str:
    parts = [INSTRUCTION]
    for fname in RULE_FILES:
        with open(_p(fname), encoding="utf-8") as f:
            parts.append(f"\n\n<!-- 以下内容来自《{fname}》 -->\n\n" + f.read())
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        parts.append("\n\n<!-- 以下内容来自《返回结构.schema.json》 -->\n\n" + f.read())
    return "\n".join(parts)


# 模块加载时拼一次（规则是静态的，不必每次重读）
SYSTEM_PROMPT = build_system_prompt()


def load_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    env_path = _p(".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def get_client():
    key = load_api_key()
    if not key:
        sys.exit(
            "❌ 未找到 API Key。请二选一：\n"
            "  1. 设置环境变量：export DEEPSEEK_API_KEY=sk-xxx\n"
            "  2. 在项目根目录建 .env 文件，内容一行：DEEPSEEK_API_KEY=sk-xxx"
        )
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("❌ 缺少依赖 openai，请先执行：pip install -r requirements.txt")
    return OpenAI(api_key=key, base_url="https://api.deepseek.com")


def parse_article_text(text: str):
    """从「标题：… / 内容：…」格式（同《测试输入.md》）解析出 (title, body)。"""
    title = ""
    m = re.search(r"标题[:：]\s*(.+)", text)
    if m:
        title = m.group(1).strip()
    body = ""
    m = re.search(r"内容[:：]\s*\n?\s*(.*)", text, re.S)
    if m:
        body = m.group(1).strip()
    return title, body


def load_article(path: str):
    """读文件，返回 (title, lead, body)。支持 JSON 或「标题/内容」两种格式。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith(".json"):
        obj = json.loads(text)
        return obj.get("title", ""), obj.get("lead", ""), obj.get("body", "")
    title, body = parse_article_text(text)
    return title, "", body


def label(title: str, body: str, lead: str = "", model: str = "deepseek-chat") -> str:
    """调 DeepSeek 打标，返回模型输出的原始 JSON 字符串。"""
    article = {"title": title}
    if lead:
        article["lead"] = lead
    article["body"] = body
    resp = get_client().chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(article, ensure_ascii=False)},
        ],
    )
    return resp.choices[0].message.content


def run(title: str, body: str, lead: str = "", model: str = "deepseek-chat"):
    print("\n" + "=" * 60)
    print(f"[文章] 标题：{title}")
    print(f"[文章] 正文：{body[:60]}{'…' if len(body) > 60 else ''}")
    print("=" * 60)

    try:
        raw = label(title, body, lead, model)
    except Exception as e:  # noqa: BLE001 —— 把 API 错误原样展示
        print(f"\n❌ API 调用失败：{e}\n")
        return

    schema = v.load_schema()
    obj, msg = v.validate_one(raw, schema)

    print(f"\n[校验] {msg}")
    if obj is not None:
        theme = obj.get("theme") or {}
        sub = theme.get("sub") if theme else None
        n_ent = len(obj.get("entities") or [])
        included = obj.get("included")
        tag = "✅ 收录" if included else "🚫 不收录（included=false）"
        print(f"[摘要] {tag}  theme={theme.get('name')}/{sub}  entities={n_ent}")

    print("\n[输出 JSON]")
    try:
        pretty = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        print(pretty)
    except Exception:
        print(raw)  # 解析失败时退回原文
    print()


def main():
    parser = argparse.ArgumentParser(description="足球新闻分类打标 CLI")
    parser.add_argument("file", nargs="?", help="输入文件（默认《测试输入.md》；.json 或「标题/内容」格式）")
    parser.add_argument("-i", "--interactive", action="store_true", help="交互式粘贴标题+正文")
    parser.add_argument("--model", default="deepseek-chat", help="模型名（默认 deepseek-chat）")
    args = parser.parse_args()

    if args.interactive:
        print("交互模式：")
        title = input("标题：").strip()
        print("正文（粘贴后单独一行输入 END 结束）：")
        lines = []
        while True:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
        body = "\n".join(lines).strip()
        if not title or not body:
            sys.exit("❌ 标题和正文不能为空")
        run(title, body, model=args.model)
        return

    path = args.file or DEFAULT_INPUT
    if not os.path.exists(path):
        sys.exit(f"❌ 文件不存在：{path}")
    title, lead, body = load_article(path)
    if not title or not body:
        sys.exit(f"❌ 未能从文件解析出标题/正文（{path}）")
    run(title, body, lead, model=args.model)


if __name__ == "__main__":
    main()
