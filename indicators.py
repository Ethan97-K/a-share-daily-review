# -*- coding: utf-8 -*-
"""技术指标计算与背离/趋势判定（纯实现，无第三方依赖）。

指标：EMA/MACD/MA/KDJ/威廉WR
判定：30/60分钟顶底背离、日线趋势（短期/中长期：向上/向下/横盘震荡）
"""
from dataclasses import dataclass, field


# ---------- 基础指标 ----------

def ema(vals, n):
    k = 2.0 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def sma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def ma_series(vals, n):
    out = []
    for i in range(len(vals)):
        if i + 1 < n:
            out.append(None)
        else:
            out.append(sum(vals[i + 1 - n:i + 1]) / n)
    return out


def macd(closes, fast=12, slow=26, signal=9):
    dif = [a - b for a, b in zip(ema(closes, fast), ema(closes, slow))]
    dea = ema(dif, signal)
    hist = [(a - b) * 2 for a, b in zip(dif, dea)]
    return dif, dea, hist


def kdj(rows, n=9):
    """rows: [{high, low, close}] -> (K, D, J) 最新值"""
    if len(rows) < n:
        n = len(rows)
    k, d = 50.0, 50.0
    for i in range(len(rows) - n, len(rows)):
        window = rows[max(0, i - n + 1):i + 1]
        hh = max(r["high"] for r in window)
        ll = min(r["low"] for r in window)
        rsv = (rows[i]["close"] - ll) / (hh - ll) * 100 if hh > ll else 50
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
    return k, d, 3 * k - 2 * d


def williams_r(rows, n=14):
    window = rows[-n:]
    hh = max(r["high"] for r in window)
    ll = min(r["low"] for r in window)
    if hh == ll:
        return -50.0
    return (hh - rows[-1]["close"]) / (hh - ll) * -100


# ---------- 背离检测 ----------

@dataclass
class DivergenceResult:
    kind: str = "无"          # 顶背离 / 底背离 / 无
    timeframe: str = ""        # 30分钟 / 60分钟 / 日线
    detail: str = ""
    confidence: str = "中"


def _find_peaks(vals, lookback=60, min_gap=3):
    """返回区间内局部极大值索引列表"""
    peaks = []
    for i in range(max(1, len(vals) - lookback), len(vals) - 1):
        if vals[i] >= vals[i - 1] and vals[i] >= vals[i + 1]:
            if not peaks or i - peaks[-1] >= min_gap:
                peaks.append(i)
    return peaks


def _find_troughs(vals, lookback=60, min_gap=3):
    troughs = []
    for i in range(max(1, len(vals) - lookback), len(vals) - 1):
        if vals[i] <= vals[i - 1] and vals[i] <= vals[i + 1]:
            if not troughs or i - troughs[-1] >= min_gap:
                troughs.append(i)
    return troughs


def detect_divergence(rows, timeframe="日线") -> DivergenceResult:
    """rows: [{close, ...}]（按时间升序）。基于收盘价与MACD柱的双重背离。"""
    if len(rows) < 35:
        return DivergenceResult(timeframe=timeframe, detail="K线不足35根，无法判定")
    closes = [r["close"] for r in rows]
    _, _, hist = macd(closes)
    seg = rows[-60:]
    h = hist[-60:]

    # 顶背离：价格两个峰抬高，MACD峰走低
    peaks = _find_peaks(closes[-60:])
    if len(peaks) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        if closes[-60:][p2] > closes[-60:][p1] and h[p2] < h[p1] and h[p2] < h[max(peaks)]:
            hp = max(h[p2], h[p1])
            return DivergenceResult("顶背离", timeframe,
                f"价格新高({closes[-60:][p2]:.2f}>{closes[-60:][p1]:.2f})而MACD柱峰走低({h[p2]:.2f}<{h[p1]:.2f})",
                "中高" if h[-1] < 0 else "中")

    # 底背离：价格两个谷降低，MACD谷抬高
    troughs = _find_troughs(closes[-60:])
    if len(troughs) >= 2:
        t1, t2 = troughs[-2], troughs[-1]
        if closes[-60:][t2] < closes[-60:][t1] and h[t2] > h[t1]:
            return DivergenceResult("底背离", timeframe,
                f"价格新低({closes[-60:][t2]:.2f}<{closes[-60:][t1]:.2f})而MACD柱谷抬高({h[t2]:.2f}>{h[t1]:.2f})",
                "中高" if h[-1] > 0 else "中")

    return DivergenceResult(timeframe=timeframe, detail="未检测到明显背离")


# ---------- 趋势判定 ----------

@dataclass
class TrendResult:
    short_term: str = "横盘震荡"   # 向上 / 向下 / 横盘震荡
    mid_term: str = "横盘震荡"
    basis: list = field(default_factory=list)
    confidence: str = "中"


def classify_trend(rows) -> TrendResult:
    """rows: 日线（升序）。均线系统+MACD+高低点结构 多因子投票。"""
    res = TrendResult()
    if len(rows) < 60:
        res.basis.append("日线不足60根，判定置信度低")
        return res
    closes = [r["close"] for r in rows]
    last = closes[-1]
    ma5 = sma(closes, 5)
    ma10 = sma(closes, 10)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    dif, dea, _ = macd(closes)

    # 短期：MA5/10/20 相对位置 + 30分钟MACD方向（由调用方传入分钟线则更准，这里用日线近似）
    short_votes = 0
    if last > ma5: short_votes += 1
    else: short_votes -= 1
    if ma5 > ma10: short_votes += 1
    else: short_votes -= 1
    if ma10 > ma20: short_votes += 1
    else: short_votes -= 1
    if dif[-1] > dea[-1]: short_votes += 1
    else: short_votes -= 1
    res.short_term = "向上" if short_votes >= 3 else ("向下" if short_votes <= -3 else "横盘震荡")

    # 中长期：MA20/60 关系 + 日线MACD零轴 + 60日高低点位置
    mid_votes = 0
    if ma20 > ma60: mid_votes += 1
    else: mid_votes -= 1
    if dif[-1] > 0: mid_votes += 1
    else: mid_votes -= 1
    hi60, lo60 = max(closes[-60:]), min(closes[-60:])
    pos = (last - lo60) / (hi60 - lo60) if hi60 > lo60 else 0.5
    if pos > 0.7: mid_votes += 1
    elif pos < 0.3: mid_votes -= 1
    res.mid_term = "向上" if mid_votes >= 2 else ("向下" if mid_votes <= -2 else "横盘震荡")

    res.basis = [
        f"MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f} MA60={ma60:.2f}",
        f"MACD DIF={dif[-1]:.2f} DEA={dea[-1]:.2f}（{'零上' if dif[-1]>0 else '零下'}）",
        f"收盘价处于60日区间 {(last-lo60)/(hi60-lo60)*100:.0f}% 分位",
    ]
    res.confidence = "高" if abs(short_votes) >= 3 and abs(mid_votes) >= 2 else "中"
    return res
