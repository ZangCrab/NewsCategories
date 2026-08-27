#!/usr/bin/env python3
"""从规则文件动态生成网页底部说明板块（主题表 / 实体表 / 收录标准表）。

目的：网页展示永远与《主题.md》《实体.md》《收录标准.md》一致，
避免在 app.py 里硬编码造成两处漂移。规则文件一旦改动，app.py 启动时
本模块重读重生成，无需再改代码。
"""
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

THEME_MD = os.path.join(BASE_DIR, "主题.md")
ENTITY_MD = os.path.join(BASE_DIR, "实体.md")
CRITERIA_MD = os.path.join(BASE_DIR, "收录标准.md")
RETURN_MD = os.path.join(BASE_DIR, "返回结构.md")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _split_row(line):
    """'| a | b | c |' -> ['a', 'b', 'c']（去掉首尾因 | 产生的空单元格）。"""
    parts = line.split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.strip() for p in parts]


def _is_separator(cells):
    """表格分隔行，如 '| --- | --- |'。"""
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def _tables(text):
    """按出现顺序 yield (表头, [数据行...])，每行是 cell 列表。"""
    rows = []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            rows.append(_split_row(line))
        elif rows:
            yield rows[0], [r for r in rows[1:] if not _is_separator(r)]
            rows = []
    if rows:
        yield rows[0], [r for r in rows[1:] if not _is_separator(r)]


def _find_table(text, header_prefix):
    """按表头前几列精确匹配，返回数据行；找不到抛错。"""
    header_prefix = tuple(header_prefix)
    for header, data in _tables(text):
        if tuple(header[: len(header_prefix)]) == header_prefix:
            return data
    raise RuntimeError(f"规则文件中找不到表头为 {header_prefix} 的表格")


def load_themes():
    """《主题.md》→ [(主类, [子类...]), ...]，保持文件顺序。"""
    data = _find_table(_read(THEME_MD), ("主类（name）",))
    out = []
    for row in data:
        if len(row) < 2:
            continue
        name = row[0]
        subs = re.findall(r"`([^`]+)`", row[1])
        if name and subs:
            out.append((name, subs))
    if not out:
        raise RuntimeError("《主题.md》主类枚举表解析为空")
    return out


def load_entities():
    """《实体.md》→ [(type, 含义), ...]。"""
    data = _find_table(_read(ENTITY_MD), ("type", "含义"))
    out = [(row[0].strip("` "), row[1]) for row in data if len(row) >= 2]
    if not out:
        raise RuntimeError("《实体.md》实体类型表解析为空")
    return out


def load_criteria():
    """《收录标准.md》→ {主类: {子类: 收录标准}}，主类取自 '### N. 主类' 标题。"""
    result = {}
    current = None
    pending = None

    def flush():
        nonlocal pending
        if pending is not None and current:
            header = pending[0]
            if header and header[0] == "子类":
                d = result.setdefault(current, {})
                for row in pending[1:]:
                    if _is_separator(row):
                        continue
                    if len(row) >= 2 and row[0]:
                        d[row[0]] = row[1]
        pending = None

    for line in _read(CRITERIA_MD).splitlines():
        s = line.strip()
        m = re.match(r"^###\s+\d+[.、]\s*(.+?)\s*$", s)
        if m:
            flush()
            current = m.group(1)
        elif s.startswith("|"):
            if pending is None:
                pending = []
            pending.append(_split_row(s))
        else:
            flush()
    flush()
    if not result:
        raise RuntimeError("《收录标准.md》第一部分表格解析为空")
    return result


def load_source_types():
    """《返回结构.md》→ [(type, 报道方身份, 例子), ...]。"""
    data = _find_table(_read(RETURN_MD), ("type", "报道方身份（原文定性）"))
    out = [(row[0], row[1], row[2]) for row in data if len(row) >= 3]
    if not out:
        raise RuntimeError("《返回结构.md》source 的 type 枚举表解析为空")
    return out


def build_skill_explain():
    """生成网页底部说明板块的 markdown（主题表 + 收录标准表 + 实体表 + source 表）。"""
    themes = load_themes()
    entities = load_entities()
    criteria = load_criteria()
    source_types = load_source_types()

    n_subs = sum(len(subs) for _, subs in themes)

    lines = [
        "---",
        "## 📖 SKILL 双轨制打标原理",
        "",
        "本 SKILL 用**两条互相独立、必须组合**的轨道给足球新闻打标：",
        "",
        "- **主题（`theme`）** —— 回答「这篇文章是什么**体裁/话题**」。单选一个主类 + 1–2 个子类。",
        "- **实体（`entities`）** —— 回答「这篇内容关于**谁 / 什么比赛**」。只打重点（`required` 第一优先级 / `core` 核心论断对象 / `significant` 显著提及）。",
        "",
        "二者互不影响；另附**消息来源（`source`，选填，对象化 `type`/`reporter`/`quote`）**标注「谁报道的」，以及 `transfers` / `coach_changes` / `matches` 关系列表（选填）、`reason`（理由，必填）。",
        "",
        f"### 主题（{len(themes)} 主类 · {n_subs} 子类）",
        "",
        "| 主类 | 子类 |",
        "| --- | --- |",
    ]
    for name, subs in themes:
        lines.append(f"| {name} | " + " · ".join(subs) + " |")

    lines += [
        "",
        f"### 收录标准（{len(themes)} 主类 · {n_subs} 子类 · 判定标准）",
        "",
        "| 主类 | 子类 | 收录标准 |",
        "| --- | --- | --- |",
    ]
    missing = []
    for name, subs in themes:
        d = criteria.get(name, {})
        for sub in subs:
            std = d.get(sub, "").strip()
            if not std:
                std = "⚠️ 《收录标准.md》未定义收录标准"
                missing.append(f"{name}/{sub}")
            lines.append(f"| {name} | {sub} | {std} |")

    lines += [
        "",
        "> **边界模糊时怎么判**：一篇文章只打一个主类；按「第一信息价值」（读者最关心的信息是什么）判定，标题优先 + 导语辅助。完整正反例与多主类归属见《收录标准.md》。",
        "",
        f"### 实体（{len(entities)} 种类型）",
        "",
        "| type | 含义 |",
        "| --- | --- |",
    ]
    for typ, meaning in entities:
        lines.append(f"| `{typ}` | {meaning} |")

    lines += [
        "",
        "### 消息来源（source）",
        "",
        "`source` 为**选填**，对象化 `type` / `reporter` / `quote` 三字段，标注「这则消息是谁报道/发布的」。",
        "",
        "**划分方式**：看**报道方身份（谁说的）**，不看消息内容。`type` 为 4 值枚举：",
        "",
        "| type | 报道方身份（谁说的） | 例子 |",
        "| --- | --- | --- |",
    ]
    for typ, identity, example in source_types:
        lines.append(f"| {typ} | {identity} | {example} |")

    lines += [
        "",
        "- `type` —— 报道方类型（上表 4 值枚举）。",
        "- `reporter` —— 报道方名称（自由文本：人名/机构名/网友等，不可枚举）。",
        "- `quote` —— 原文原句，一字不差。",
        "",
        "**防臆造硬约束**：`quote` 引用不出原文原句 = 无来源 = 整个 `source` 省略；不得据常识/上下文/实体名推断报道方。`source` 与 `entities` 独立——source 标注「谁发的」，entities 标注「讲的是谁」。",
        "",
        "> 主题主类/子类与实体类型的枚举合法性由《主题.md》《实体.md》定义，《返回结构.schema.json》硬校验。",
    ]

    if missing:
        print(
            "⚠️ 漂移告警：以下子类在《主题.md》存在、但《收录标准.md》缺收录标准——"
            + "、".join(missing),
            file=sys.stderr,
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_skill_explain())
    print("\n\n[OK] 主题/实体/收录标准均已从规则文件生成。")
