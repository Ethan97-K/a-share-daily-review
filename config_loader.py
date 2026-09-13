# -*- coding: utf-8 -*-
"""配置加载：解析《A股复盘增强配置》文档，动态获取跟踪个股/板块/交易规则/博主增强提示词。

文档路径可通过环境变量 REVIEW_CONFIG 覆盖，默认 D:\\A股复盘增强配置.md。
跟踪个股解析规则：在一节中匹配 `^\\s*-\\s*(\\d{6})\\s*([\\u4e00-\\u9fa5A-Za-z0-9*]+)?` 行。
"""
import os
import re

DEFAULT_CONFIG_PATH = r"D:\A股复盘增强配置.md"

# 增加跟踪股票时只需编辑配置文档第一节，程序自动读取，无需改代码
DEFAULT_TRACKED = ["002396", "601890", "603629"]


def _secid(code: str) -> str:
    """6位代码 -> 东财 secid。沪市(6/9/5开头)前缀1，深市/北交前缀0。"""
    if code[0] in "69 5".replace(" ", ""):
        return f"1.{code}"
    return f"0.{code}"


def load_config(path: str | None = None) -> dict:
    path = path or os.environ.get("REVIEW_CONFIG", DEFAULT_CONFIG_PATH)
    cfg = {
        "config_path": path,
        "config_exists": os.path.exists(path),
        "tracked": [],           # [(code, name)]
        "focus_sectors": [],
        "trade_rules": [],
        "blogger_prompts": [],   # 第五节增强提示词原文行
        "blogger_raw": "",
    }
    if not cfg["config_exists"]:
        cfg["tracked"] = [(c, "") for c in DEFAULT_TRACKED]
        return cfg

    with open(path, encoding="utf-8") as f:
        text = f.read()

    # 按节切分
    m1 = re.search(r"##\s*一、[\s\S]*?(?=\n##\s|\Z)", text)
    m5 = re.search(r"##\s*五、[\s\S]*?(?=\n##\s|\Z)", text)

    if m1:
        sec1 = m1.group(0)
        # 跟踪个股：形如 "- 002396 星网锐捷" 或行内 "002396 星网锐捷；..."
        seen = set()
        for m in re.finditer(r"(\d{6})\s*[\s：:]?\s*([\u4e00-\u9fa5A-Za-z0-9*]{2,10})?", sec1):
            code, name = m.group(1), (m.group(2) or "").strip("；;，, ")
            if code not in seen:
                seen.add(code)
                cfg["tracked"].append((code, name))
        if not cfg["tracked"]:
            cfg["tracked"] = [(c, "") for c in DEFAULT_TRACKED]
        # 重点板块
        ms = re.search(r"重点关注板块[^：]*：\n([\s\S]*?)(?=\n- \*\*|\n##|\Z)", sec1)
        if ms:
            cfg["focus_sectors"] = [s.strip("；;，, 。") for s in ms.group(1).strip().splitlines()
                                    if s.strip() and not s.strip().startswith("例")]
        # 交易规则
        mr = re.search(r"交易规则[^：]*：\n([\s\S]*?)(?=\n- \*\*|\n##|\Z)", sec1)
        if mr:
            cfg["trade_rules"] = [s.strip("；;，, 。") for s in mr.group(1).strip().splitlines()
                                  if s.strip() and not s.strip().startswith("例")]

    if m5:
        raw = m5.group(0)
        body = raw.split("：", 1)[-1].strip()
        lines = [l.strip() for l in body.splitlines()
                 if l.strip() and l.strip() != "---" and "等待" not in l
                 and not l.startswith(">") and not l.startswith("##") and not l.startswith("#")]
        cfg["blogger_prompts"] = lines
        cfg["blogger_raw"] = body

    return cfg


if __name__ == "__main__":
    import json
    print(json.dumps(load_config(), ensure_ascii=False, indent=2))
