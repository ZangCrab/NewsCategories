#!/usr/bin/env python3
"""News Categories SKILL —— 覆盖审计脚本。

核对 51 子类 / 8 实体类型 / included:false 在金标准样本中的覆盖，
标出缺口（0 实例的子类或实体类型）。

用法：
  python3 check_coverage.py
"""
import json
import re
import sys

GOLDEN = "金标准样本.md"

# 主类 -> 子类枚举（《主题.md》第二节的硬编码镜像；改子类时需同步）
MAIN_CLASSES = {
    "比赛报道": ["前瞻", "赛前预告", "首发确认", "战报", "赛果", "延期取消"],
    "转会与合同": ["转入转出", "租借", "续约", "解约退役", "教练更迭"],
    "伤病与停赛": ["伤病更新", "复出时间表", "停赛"],
    "场外与花边": ["生活动态", "社交媒体热点", "更衣室轶事", "球迷文化", "庆典公益", "社区关系", "球场安保", "法律纠纷"],
    "财务与商业": ["财政公平", "薪资帽", "赞助合同", "转会费构成", "俱乐部财务", "球票商品", "资本运作"],
    "深度分析": ["数据统计", "战术拆解", "专访", "人物特写", "媒体点评", "评论观点", "历史数据对比"],
    "行政与管理": ["规则变更", "章程", "纪律处分", "赛事抽签", "官员任免", "官方公告"],
    "历史与文化": ["经典回顾", "里程碑纪念", "名宿致敬", "逝世悼念"],
    "比赛预测": ["排名奖项", "比分预测", "胜负倾向", "赔率变化", "博彩解读"],
}
ENTITY_TYPES = ["event", "team", "player", "coach", "organization", "referee", "executive", "agent"]


def extract_json(text):
    m = re.search(r"```json\s*(.*?)\s*```", text, re.S)
    if m:
        return m.group(1)
    s = text.find("{")
    e = text.rfind("}")
    return text[s:e + 1] if s != -1 and e != -1 else None


def main():
    with open(GOLDEN, encoding="utf-8") as f:
        text = f.read()
    parts = re.split(r"\n## 样本\s*(\d+)", text)

    sub_count = {}      # (主类, 子类) -> 样本数
    entity_count = {}   # 实体类型 -> 出现次数
    entity_samples = {}  # 实体类型 -> [样本号]
    total = 0
    included_false = 0

    for i in range(1, len(parts) - 1, 2):
        num = parts[i]
        body = parts[i + 1]
        raw = extract_json(body)
        if raw is None:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        total += 1
        if obj.get("included") is False:
            included_false += 1
            continue
        theme = obj.get("theme") or {}
        name = theme.get("name")
        for s in (theme.get("sub") or []):
            sub_count[(name, s)] = sub_count.get((name, s), 0) + 1
        for e in (obj.get("entities") or []):
            t = e.get("type")
            entity_count[t] = entity_count.get(t, 0) + 1
            entity_samples.setdefault(t, []).append(num)

    print(f"金标准样本总数: {total}（其中 included:false = {included_false}）\n")

    # 子类覆盖
    print("== 子类覆盖 ==")
    missing_subs = []
    for main, subs in MAIN_CLASSES.items():
        covered = sum(1 for s in subs if sub_count.get((main, s), 0) > 0)
        print(f"  {main}: {covered}/{len(subs)}")
        for s in subs:
            n = sub_count.get((main, s), 0)
            if n == 0:
                missing_subs.append((main, s))
                print(f"      ✗ 缺口  {s}: {n}")
    total_subs = sum(len(v) for v in MAIN_CLASSES.values())
    covered_subs = total_subs - len(missing_subs)
    print(f"  —— 子类覆盖: {covered_subs}/{total_subs}")

    # 实体类型覆盖
    print("\n== 实体类型覆盖 ==")
    missing_ent = []
    for t in ENTITY_TYPES:
        n = entity_count.get(t, 0)
        if n == 0:
            missing_ent.append(t)
            print(f"  ✗ 缺口  {t}: {n}")
        else:
            samples = ",".join(entity_samples.get(t, []))
            print(f"  ✓ {t}: {n} 次（样本 {samples}）")
    print(f"  —— 实体类型覆盖: {len(ENTITY_TYPES) - len(missing_ent)}/{len(ENTITY_TYPES)}")

    print()
    if missing_subs or missing_ent:
        print("⚠ 存在缺口：")
        for main, s in missing_subs:
            print(f"  - 子类 {main}·{s}")
        for t in missing_ent:
            print(f"  - 实体类型 {t}")
        return 1
    print("✅ 51 子类 + 8 实体类型 全部有实例，无缺口。")
    if included_false == 0:
        print("⚠ 提醒：included:false 样本数为 0（建议至少 1 个反例样本）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
