# -*- coding: utf-8 -*-
"""选股筛选模块（可插拔条件，预留扩展）。

内置策略：
  - volume_breakout 放量突破：量比>1.5、涨幅2-7%、站上MA20
  - macd_golden    MACD金叉：日线刚金叉且DIF零上
  - sector_leader  板块龙头：当日成交额前50中涨幅居前且板块净流入为正

自定义：继承 ScreenStrategy 实现 screen(candidates) 即可；或在
STRATEGIES 注册表添加新策略，无需改动主流程。
"""
import urllib.request, json

from data_sources import _http_json, secid_of
from indicators import sma, macd
from data_sources import fetch_kline as _fetch_kline_raw


def _fetch_kline(secid, klt=101, lmt=60):
    _, rows, _ = _fetch_kline_raw(secid, klt, lmt)
    return rows


def fetch_candidates(top=50):
    """全市场成交额前N的个股快照（候选池）。"""
    url = ("https://push2.eastmoney.com/api/qt/clist/get?"
           f"pn=1&pz={top}&po=1&np=1&fltt=2&fid=f6&"
           "fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&"
           "fields=f2,f3,f6,f8,f12,f14,f62")
    d = _http_json(url)
    out = []
    for it in d["data"]["diff"]:
        out.append({
            "code": it["f12"], "name": it["f14"],
            "close": it["f2"], "chg_pct": it["f3"],
            "amount_yi": round(it["f6"] / 1e8, 1),
            "turnover": it.get("f8"),                      # 换手率
            "main_net_yi": round(it["f62"] / 1e8, 2) if isinstance(it.get("f62"), (int, float)) else None,
        })
    return out


class ScreenStrategy:
    name = "base"
    desc = ""

    def screen(self, candidates):
        raise NotImplementedError


class VolumeBreakout(ScreenStrategy):
    name = "volume_breakout"
    desc = "放量突破：量能>20日均量1.5倍、涨幅2%~7%、站上MA20"

    def screen(self, candidates):
        hits = []
        for c in candidates:
            if not (2 <= (c["chg_pct"] or 0) <= 7):
                continue
            try:
                _, rows = _fetch_kline(secid_of(c["code"]), 101, 30)
            except Exception:
                continue
            closes = [r["close"] for r in rows]
            vol20 = sum(r["vol"] for r in rows[-21:-1]) / 20
            if vol20 and rows[-1]["vol"] / vol20 > 1.5 and closes[-1] > (sma(closes, 20) or 0):
                hits.append({**c, "reason": f"量能{rows[-1]['vol']/vol20:.1f}倍于20日均量，站上MA20"})
        return hits


class MacdGolden(ScreenStrategy):
    name = "macd_golden"
    desc = "MACD金叉：日线刚金叉且DIF位于零轴上方"

    def screen(self, candidates):
        hits = []
        for c in candidates:
            try:
                rows = _fetch_kline(secid_of(c["code"]), 101, 60)
            except Exception:
                continue
            dif, dea, _ = macd([r["close"] for r in rows])
            if len(dif) > 1 and dif[-1] > dea[-1] and dif[-2] <= dea[-2] and dif[-1] > 0:
                hits.append({**c, "reason": "日线MACD刚金叉且DIF零上"})
        return hits


STRATEGIES = {s.name: s for s in [VolumeBreakout(), MacdGolden()]}


def run_screener(strategy_name="volume_breakout", top=50):
    strat = STRATEGIES.get(strategy_name)
    if not strat:
        raise ValueError(f"未知策略 {strategy_name}，可选：{list(STRATEGIES)}")
    candidates = fetch_candidates(top)
    hits = strat.screen(candidates)
    hits.sort(key=lambda x: x["amount_yi"], reverse=True)
    return {"strategy": strat.name, "desc": strat.desc, "hits": hits[:10]}
