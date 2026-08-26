#!/usr/bin/env python3
"""News Categories SKILL —— 交互式打标网页（Gradio）。

复用 cli.py 的核心（system prompt 拼装、API Key 读取），套一个 Gradio 网页壳。
老板只需贴文章 → 点「打标」→ 看 JSON + schema 校验结果，不用碰代码和 key。

用法：
  python3 app.py            # 本地 http://127.0.0.1:7860
  python3 app.py --share    # 额外生成一个公网链接，直接发给老板远程测试

依赖：openai、jsonschema、gradio（pip install -r requirements.txt）
"""
import argparse
import json

import gradio as gr

import cli  # 复用：SYSTEM_PROMPT、load_api_key()
import validate

MODEL = "deepseek-chat"  # 打标用这个就够；要换模型改这里

# 老板点一下就能测的示例文章（战报 / 转会 / 非足球反例）
EXAMPLES = [
    [
        "利物浦 3-1 逆转热刺，萨拉赫梅开二度",
        "",
        "利物浦在主场 3-1 逆转热刺。上半场热刺由孙兴慜先拔头筹，下半场萨拉赫梅开二度反超，补时阶段若塔再下一城。第 78 分钟主裁判迈克尔·奥利弗经 VAR 提示判定热刺手球送点，萨拉赫主罚命中，判罚引发热刺主帅波斯特科格鲁赛后强烈不满。",
    ],
    [
        "Here we go！奥斯梅恩加盟切尔西，转会费 7500 万欧",
        "",
        "据知名记者罗马诺消息，那不勒斯前锋奥斯梅恩以 7500 万欧元转会费加盟切尔西，双方签约五年。",
    ],
    [
        "德约科维奇宣布退役",
        "",
        "塞尔维亚网球天王诺瓦克·德约科维奇今日通过社交媒体宣布，将在本年度美网结束后正式退役，结束其长达二十余年的职业生涯。",
    ],
]


def _get_client():
    """返回 (client_or_None, err_msg)。错误以字符串返回给页面，而不是 sys.exit 杀服务。"""
    key = cli.load_api_key()
    if not key:
        return None, "❌ 服务器未配置 API Key：请设置环境变量 DEEPSEEK_API_KEY，或在项目根目录建 .env（DEEPSEEK_API_KEY=sk-xxx）"
    try:
        from openai import OpenAI
    except ImportError:
        return None, "❌ 服务器缺少 openai 依赖：pip install -r requirements.txt"
    return OpenAI(api_key=key, base_url="https://api.deepseek.com"), None


def label_web(title: str, lead: str, body: str):
    """对一篇文章打标，返回 (JSON 展示, 校验摘要)。"""
    if not (title or "").strip() or not (body or "").strip():
        return "", "⚠️ 标题和正文都不能为空"

    client, err = _get_client()
    if err:
        return "", err

    article = {"title": title.strip()}
    if (lead or "").strip():
        article["lead"] = lead.strip()
    article["body"] = body.strip()

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": cli.SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(article, ensure_ascii=False)},
            ],
        )
        raw = resp.choices[0].message.content
    except Exception as e:  # noqa: BLE001 —— 把 API 错误原样展示给页面
        return "", f"❌ API 调用失败：{e}"

    obj, msg = validate.validate_one(raw, validate.load_schema())

    try:
        pretty = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
    except Exception:
        pretty = raw

    if obj is None:
        return pretty, msg

    if msg == "PASS":
        theme = obj.get("theme") or {}
        sub = theme.get("sub") if theme else None
        n_ent = len(obj.get("entities") or [])
        tag = "✅ 收录" if obj.get("included") else "🚫 不收录（included=false）"
        summary = f"{msg}  {tag}  theme={theme.get('name')}/{sub}  entities={n_ent}"
    else:
        summary = msg
    return pretty, summary


def build_ui():
    with gr.Blocks(title="足球新闻分类打标 Demo", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            "# ⚽ 足球新闻分类打标 Demo\n\n"
            "贴一篇足球新闻，点「打标」，实时查看标注结果与 JSON Schema 硬校验。\n\n"
            "> 后端：规则全文作为 system prompt + DeepSeek（`deepseek-chat`，temperature=0）"
            " + 《返回结构.schema.json》硬校验。"
        )
        with gr.Row():
            with gr.Column(scale=1):
                title = gr.Textbox(label="标题（必填）", placeholder="如：利物浦 3-1 逆转热刺，萨拉赫梅开二度")
                lead = gr.Textbox(label="导语 / 摘要（可选）", placeholder="可留空")
                body = gr.Textbox(label="正文（必填）", lines=10, placeholder="粘贴文章正文全文……")
                btn = gr.Button("打标", variant="primary")
                gr.Examples(examples=EXAMPLES, inputs=[title, lead, body], label="点击示例快速填入")
            with gr.Column(scale=1):
                out_json = gr.Code(label="标注结果 JSON", language="json")
                out_valid = gr.Textbox(label="Schema 校验", lines=5)

        btn.click(label_web, inputs=[title, lead, body], outputs=[out_json, out_valid])
    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="足球新闻分类打标网页")
    parser.add_argument("--share", action="store_true", help="生成公网分享链接，发给老板远程测试")
    args = parser.parse_args()

    build_ui().launch(server_name="0.0.0.0", share=args.share)
