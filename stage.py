# -*- coding: utf-8 -*-
"""阶段判定规则引擎：个股与板块的阶段标签。

个股阶段：底部 / 启动 / 主升初期 / 主升中段 / 鱼尾·高位回调 / 下降中继 / 顶部
板块阶段：启动 / 主升初期 / 主升中段 / 鱼尾 / 老龙反抽 / 退潮

规则可扩展：STAGE_RULES 按顺序投票，命中即返回，便于后续增补条件。
"""
from indicators import sma, macd, kdj


def _ma_state(closes):
    ma5, ma10 = sma(closes, 5), sma(closes, 10)
    ma20, ma60 = sma(closes, 20), sma(closes, 60)
    above = lambda m: closes[-1] > m if m else False
    return {
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
        "bull": above(ma5) and above(ma10) and ma5 > ma10 and ma10 > ma20,   # 多头排列
        "bear": (not above(ma5)) and (not above(ma10)) and ma10 < ma20,      # 空头排列
        "above_ma60": above(ma60),
    }


def classify_stock_stage(rows, main_net_5d=None) -> dict:
    """rows: 日线升序。main_net_5d: 5日主力净额（亿元，可 None）。
    返回 {stage, color, basis[], key_levels{support,resist}}"""
    closes = [r["close"] for r in rows]
    st = _ma_state(closes)
    dif, dea, hist = macd(closes)
    golden = dif[-1] > dea[-1] and dif[-2] <= dea[-2] if len(dif) > 1 else False
    dead = dif[-1] < dea[-1] and dif[-2] >= dea[-2] if len(dif) > 1 else False
    macd_bull = dif[-1] > dea[-1] and dif[-1] > 0
    hi60, lo60 = max(r["high"] for r in rows[-60:]), min(r["low"] for r in rows[-60:])
    pos = (closes[-1] - lo60) / (hi60 - lo60) if hi60 > lo60 else 0.5
    vol20 = sum(r["vol"] for r in rows[-20:]) / 20
    vol_now = rows[-1]["vol"]
    shrink = vol_now < vol20 * 0.8
    k, d, j = kdj(rows)

    basis = [
        f"均线{'多头' if st['bull'] else '空头' if st['bear'] else '纠缠'}排列；"
        f"价格{'站上' if st['above_ma60'] else '跌破'}MA60({st['ma60']:.2f})" if st["ma60"] else "均线数据不足",
        f"MACD DIF={dif[-1]:.2f} DEA={dea[-1]:.2f}（{'金叉' if dif[-1]>dea[-1] else '死叉'}，{'零上' if dif[-1]>0 else '零下'}）",
        f"60日区间分位 {pos*100:.0f}%；今日量能为20日均量的 {vol_now/vol20:.2f} 倍" if vol20 else "量能数据不足",
    ]

    # 规则按优先级匹配
    if pos > 0.9 and dead and (main_net_5d is not None and main_net_5d < 0):
        stage, color = "鱼尾 · 高位回调", "#d97706"
    elif pos > 0.92 and (hist[-1] < hist[-2] if len(hist) > 1 else False):
        stage, color = "顶部 · 动能衰竭", "#7c3aed"
    elif st["bull"] and macd_bull and (main_net_5d is None or main_net_5d > 0):
        stage = "主升初期" if pos < 0.6 else "主升中段"
        color = "#dc2626"
    elif golden and (main_net_5d is None or main_net_5d > 0) and pos < 0.5:
        stage, color = "启动", "#dc2626"
    elif st["bear"] and dif[-1] < 0:
        stage, color = "下降中继", "#16a34a"
        if j < 20 and shrink:
            basis.append("KDJ深度超卖+明显缩量：具备技术性反弹条件，但趋势未反转")
    elif st["above_ma60"] and pos < 0.4:
        stage, color = "底部区域", "#0891b2"
    else:
        stage, color = "震荡 · 方向待选择", "#6b7280"

    support = round(min(rows[-3]["low"] for r in rows[-3:]), 2)
    resist = round(st["ma20"], 2) if st["ma20"] and closes[-1] < st["ma20"] else round(hi60, 2)
    return {
        "stage": stage, "color": color, "basis": basis,
        "key_levels": {"support": support, "resist": resist},
        "extra": {"kdj_j": round(j, 1), "macd_golden": golden, "macd_dead": dead,
                  "vol_vs_ma20": round(vol_now / vol20, 2) if vol20 else None},
    }


def classify_sector_stage(chg_pct, main_net_yi, pos_20d=None) -> dict:
    """简化板块阶段判定：当日涨跌+主力净额+近20日位置。"""
    if pos_20d is None:
        pos_20d = 0.5
    if chg_pct >= 2 and main_net_yi and main_net_yi > 0:
        stage = "启动 · 放量上攻" if pos_20d < 0.5 else "主升延续"
    elif chg_pct >= 1:
        stage = "偏强 · 观察量能持续性"
    elif chg_pct <= -2 and main_net_yi and main_net_yi < -5:
        stage = "退潮 · 主力撤离"
    elif chg_pct <= -1:
        stage = "回调 · 分歧加大"
    else:
        stage = "震荡整理"
    return {"stage": stage,
            "basis": f"涨跌{chg_pct:+.2f}%、主力净额{main_net_yi or 0:+.1f}亿、20日分位{pos_20d*100:.0f}%"}
