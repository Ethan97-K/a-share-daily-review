# -*- coding: utf-8 -*-
"""A股每日复盘程序 · CLI 入口

用法：
  python main.py --mode post          # 盘后完整复盘（默认）
  python main.py --mode noon          # 午间复盘
  python main.py --mode post --screener volume_breakout   # 附带选股筛选
  python main.py --mode post --screener volume_breakout,macd_golden

输出：a-share-{daily|noon}-review-YYYYMMDD.html（workspace 报告目录）
定时任务通过 automation 触发本脚本，AI 在报告基础上补充叙述层后交付。
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import load_config
from data_sources import (detect_source, fetch_index, fetch_index_snapshot,
                          fetch_breadth, fetch_amount_ma5, fetch_sector_rank,
                          latest_trade_date, now_label, SOURCE_EM)
from indicators import detect_divergence, classify_trend
from stage import classify_stock_stage
from blogger import get_blogger_module

WORKSPACE = r"C:\Users\Administrator\WorkBuddy\2026-09-13-17-14-58"
OUT_DIR = WORKSPACE

DISCLAIMER = ("以上内容基于公开数据和量化分析，仅供参考，不构成投资建议。市场有风险，投资需谨慎。"
              "任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，必要时咨询持牌专业机构。"
              "过往表现不预示未来收益。")

INDEX_CODES = ["000001", "399001", "399006", "000688", "899050"]


def run(mode="post", screener_strategies=None):
    print(f"[1/6] 配置加载与数据源探测…")
    cfg = load_config()
    src = detect_source()
    print(f"      配置文档：{'已读取' if cfg['config_exists'] else '未找到(使用默认跟踪股)'}；"
          f"跟踪 {len(cfg['tracked'])} 只；数据源：{src}")

    print(f"[2/6] 拉取指数行情与市场广度…")
    trade_date = latest_trade_date()
    indices, snap_src = fetch_index_snapshot()
    breadth, br_src = fetch_breadth()
    amounts = fetch_amount_ma5()

    print(f"[3/6] 指数多周期趋势与背离分析（日线+60分钟+30分钟）…")
    index_analysis = {}
    kline_sources = set()
    for code in INDEX_CODES[:3]:  # 核心三指数做背离/趋势
        name, d_rows, src1 = fetch_index(code, 101, 160)
        _, h60, _ = fetch_index(code, 60, 160)
        _, h30, _ = fetch_index(code, 30, 160)
        kline_sources.add(src1)
        trend = classify_trend(d_rows)
        divergences = [detect_divergence(h60, "60分钟"), detect_divergence(h30, "30分钟")]
        index_analysis[name] = {"trend": trend, "divergences": divergences}

    print(f"[4/6] 跟踪个股阶段判定…")
    tracked, chart_series, chart_names = [], [], []
    dates_ref = None
    for code, name in cfg["tracked"]:
        try:
            sname, rows, src1 = _fetch_stock(code)
            kline_sources.add(src1)
        except Exception as e:
            print(f"      ! {code} 拉取失败：{e}")
            continue
        closes = [r["close"] for r in rows]
        closes60 = closes[-60:]
        base = closes60[0]
        chart_names.append(f"{name or sname} {code}")
        chart_series.append({"name": f"{name or sname} {code}", "type": "line",
                             "data": [round(v / base * 100, 2) for v in closes60]})
        dates_ref = [r["date"] for r in rows[-60:]]
        stage_info = classify_stock_stage(rows)
        tracked.append({
            "code": code, "name": name or sname,
            "close": closes[-1], "chg_pct": round((closes[-1] / closes[-2] - 1) * 100, 2),
            "vol_vs_ma20": stage_info["extra"]["vol_vs_ma20"],
            "stage_info": stage_info,
        })
    tracked_chart = {"dates": dates_ref, "names": chart_names, "series": chart_series} if dates_ref else {}

    print(f"[5/6] 板块排行与选股筛选…")
    sectors, sec_src = fetch_sector_rank(10)
    screener_results = []
    if screener_strategies:
        from screener import run_screener
        for sname in screener_strategies:
            try:
                screener_results.append(run_screener(sname.strip()))
            except Exception as e:
                print(f"      ! 筛选策略 {sname} 失败：{e}")

    print(f"[6/6] 渲染 HTML 报告…")
    from report import render
    ctx = {
        "mode": mode,
        "date": trade_date,
        "generated_at": now_label(),
        "indices": indices,
        "snapshot_source": snap_src,
        "breadth": breadth,
        "amounts": amounts,
        "index_analysis": index_analysis,
        "tracked": tracked,
        "tracked_chart": tracked_chart,
        "sectors": sectors,
        "sector_source": sec_src,
        "screener": screener_results[0] if screener_results else None,
        "blogger": get_blogger_module(cfg),
        "sources": f"{src}；{snap_src}；{sec_src}",
        "disclaimer": DISCLAIMER,
    }
    html = render(ctx)

    tag = "daily" if mode == "post" else "noon"
    date_compact = trade_date.replace("-", "")
    out_path = os.path.join(OUT_DIR, f"a-share-{tag}-review-{date_compact}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"完成：{out_path}")

    # 结构化摘要输出（供 automation 的 AI 叙述层使用）
    summary = {
        "report_path": out_path, "trade_date": trade_date, "source": src,
        "indices": indices, "breadth": breadth,
        "index_trends": {n: {"short": a["trend"].short_term, "mid": a["trend"].mid_term,
                             "divergence": [d.kind for d in a["divergences"] if d.kind != "无"] or "无"}
                         for n, a in index_analysis.items()},
        "tracked": [{k: t[k] for k in ("code", "name", "close", "chg_pct")} | {"stage": t["stage_info"]["stage"]}
                    for t in tracked],
        "sectors": (sectors or [])[:5],
        "screener": screener_results,
        "blogger_active": ctx["blogger"]["active"],
        "config_missing_note": None if cfg["config_exists"] else "配置文档未找到，使用默认跟踪股",
    }
    with open(os.path.join(OUT_DIR, f"a-share-{tag}-summary-{date_compact}.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:2000])
    return out_path


def _fetch_stock(code):
    from data_sources import fetch_stock
    return fetch_stock(code)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="A股每日复盘程序")
    ap.add_argument("--mode", choices=["post", "noon"], default="post", help="post=盘后完整复盘 noon=午间复盘")
    ap.add_argument("--screener", type=str, default="", help="选股策略，逗号分隔：volume_breakout,macd_golden")
    args = ap.parse_args()
    strategies = [s for s in args.screener.split(",") if s] or None
    run(args.mode, strategies)
