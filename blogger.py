# -*- coding: utf-8 -*-
"""博主复盘逻辑接口（蒸馏预留）。

读取《A股复盘增强配置》第五节「增强提示词区」中已蒸馏的博主逻辑，
注入复盘报告的「博主视角」模块。内容为空时该模块自动隐藏并提示待补充。

蒸馏流程（人工触发）：
  1. 将博主开盘/收盘视频文案粘贴到配置文档第四节
  2. 让 AI 分析提炼成增强提示词写入第五节
  3. 本模块自动读取并应用于每次复盘
"""
from config_loader import load_config


def get_blogger_module(cfg=None):
    cfg = cfg or load_config()
    if cfg["blogger_prompts"]:
        return {
            "active": True,
            "title": "博主复盘逻辑（蒸馏自配置文档第五节）",
            "prompts": cfg["blogger_prompts"],
        }
    return {
        "active": False,
        "title": "博主复盘逻辑（待蒸馏）",
        "prompts": [],
        "hint": "配置文档第五节暂无增强提示词。将博主（如复利OKK）视频文案粘贴至第四节后，"
                "由 AI 提炼写入第五节即可自动启用本模块。",
    }
