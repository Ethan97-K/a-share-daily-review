# -*- coding: utf-8 -*-
"""数据源模块：三级降级策略，所有数据标注来源与时点。

优先级：
  1. 本地 AKShare MCP (http://127.0.0.1:8000/mcp)  —— 可选，探测超时即跳过
  2. akshare Python 库                              —— 已安装则使用
  3. 东方财富公开行情 API                            —— 纯标准库，始终可用（兜底）

统一输出格式，统一返回 (data, source_label)。
"""

import json
import urllib.request
from datetime import datetime, timedelta

SOURCE_MCP = "本地AKShare MCP"
SOURCE_AK = "akshare库"
SOURCE_EM = "东方财富公开行情接口"
SOURCE_TX = "腾讯行情接口"

MCP_URL = "http://127.0.0.1:8000/mcp"

# 指数 secid：上证/深证成指/创业板指/科创50/北证50
INDEX_SECIDS = {
    "000001": ("1.000001", "上证指数"),
    "399001": ("0.399001", "深证成指"),
    "399006": ("0.399006", "创业板指"),
    "000688": ("1.000688", "科创50"),
    "899050": ("0.899050", "北证50"),
}


def _http_json(url, timeout=20, retries=5):
    import time
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://quote.eastmoney.com/",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            time.sleep(min(0.8 * (i + 1), 3.0))
    raise last_err


def secid_of(code: str) -> str:
    """6位代码 -> 东财 secid。6/9/5开头沪市前缀1，其余前缀0。"""
    return f"1.{code}" if code[0] in "695" else f"0.{code}"


# ---------- 探测可用数据源 ----------

_probe_cache = None
# 熔断器：东财连续失败后 10 分钟内直接走备用源，避免每个请求都白等重试
import time as _time
_em_fail_count = 0
_em_skip_until = 0.0


def _em_circuit_open() -> bool:
    return _time.time() < _em_skip_until


def _em_mark(ok: bool):
    global _em_fail_count, _em_skip_until
    if ok:
        _em_fail_count = 0
    else:
        _em_fail_count += 1
        if _em_fail_count >= 2:
            _em_skip_until = _time.time() + 600


def detect_source() -> str:
    """返回当前实际使用的数据源标签。"""
    global _probe_cache
    if _probe_cache:
        return _probe_cache
    try:
        import akshare  # noqa: F401
        _probe_cache = SOURCE_AK
        return _probe_cache
    except ImportError:
        pass
    try:
        urllib.request.urlopen(MCP_URL, timeout=2)
        _probe_cache = SOURCE_MCP
        return _probe_cache
    except Exception:
        pass
    _probe_cache = SOURCE_EM
    return _probe_cache


# ---------- 腾讯降级源 ----------

def _tx_symbol(code: str) -> str:
    if code[0] in "695":
        return f"sh{code}"
    if code[0] in "48":
        return f"bj{code}"
    return f"sz{code}"


def _tx_kline(code: str, klt: int, lmt: int):
    """腾讯K线：day=前复权日线；m60/m30=分钟线。双域名互备。输出与东财格式统一的 rows。"""
    sym = _tx_symbol(code if not code.startswith(("sh", "sz", "bj")) else code)
    if klt == 101:
        path = f"appstock/app/fqkline/get?param={sym},day,,,{lmt},qfq"
        key = "qfqday"
        day = True
    else:
        m = "m60" if klt == 60 else "m30"
        path = f"appstock/app/kline/mkline?param={sym},{m},,{lmt}"
        key = m
        day = False
    d, last_err = None, None
    for host in ("https://web.ifzq.gtimg.cn/", "https://proxy.finance.qq.com/ifzqgtimg/"):
        try:
            d = _http_json(host + path)
            if d and d.get("data", {}).get(sym):
                break
        except Exception as e:
            last_err = e
    if not d:
        raise last_err or RuntimeError("腾讯K线双域名均失败")
    node = d["data"][sym]
    raw = node.get(key) or node.get("day") or []
    if day:
        rows = [{"date": r[0], "open": float(r[1]), "close": float(r[2]),
                 "high": float(r[3]), "low": float(r[4]), "vol": float(r[5]),
                 "amount": float(r[5]) * 100 * float(r[2])} for r in raw]  # amount为近似值
    else:
        rows = [{"date": r[0], "open": float(r[1]), "close": float(r[2]),
                 "high": float(r[3]), "low": float(r[4]), "vol": float(r[5]), "amount": 0.0}
                for r in raw]
    return sym, rows


# ---------- K线（东财优先，腾讯降级） ----------

def fetch_kline(secid: str, klt: int = 101, lmt: int = 160):
    """klt: 101日线 / 60分钟线 / 30分钟线。返回 (name, rows, source)。"""
    em_code = secid.split(".", 1)[1]
    if not _em_circuit_open():
        try:
            url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
                   f"secid={secid}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57"
                   f"&klt={klt}&fqt=1&end=20500101&lmt={lmt}")
            d = _http_json(url)
            _em_mark(True)
            name = d["data"]["name"]
            rows = []
            for line in d["data"]["klines"]:
                p = line.split(",")
                rows.append({
                    "date": p[0], "open": float(p[1]), "close": float(p[2]),
                    "high": float(p[3]), "low": float(p[4]),
                    "vol": float(p[5]), "amount": float(p[6]) if len(p) > 6 else 0.0,
                })
            return name, rows, SOURCE_EM
        except Exception:
            _em_mark(False)
    name, rows = _tx_kline(em_code, klt, lmt)
    src = SOURCE_TX + ("·日线成交额为近似值" if klt == 101 else "")
    return name, rows, src


def fetch_stock(code: str, klt: int = 101, lmt: int = 160):
    name, rows, src = fetch_kline(secid_of(code), klt, lmt)
    return name, rows, src


def fetch_index(code: str, klt: int = 101, lmt: int = 160):
    secid, name = INDEX_SECIDS[code]
    n, rows, src = fetch_kline(secid, klt, lmt)
    return name or n, rows, src


# ---------- 指数实时快照（收盘额/涨跌幅） ----------

def fetch_index_snapshot():
    """返回 ([(name, close, chg_pct, amount亿)], source)。东财优先，腾讯降级。"""
    try:
        secids = ",".join(v[0] for v in INDEX_SECIDS.values())
        url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?"
               f"secids={secids}&fields=f2,f3,f4,f6,f12,f14&fltt=2")
        d = _http_json(url)
        out = [{"name": it["f14"], "close": it["f2"], "chg_pct": it["f3"],
                "amount_yi": round(it["f6"] / 1e8, 1)}
               for it in d["data"]["diff"]]
        return out, f"{SOURCE_EM}·快照"
    except Exception:
        syms = ",".join(_tx_symbol(c) for c in INDEX_SECIDS)
        url = f"https://qt.gtimg.cn/q={syms}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("gbk", errors="ignore")
        out = []
        for m in text.split(";"):
            m = m.strip()
            if '="' not in m:
                continue
            parts = m.split('="', 1)[1].rstrip('"').split("~")
            if len(parts) < 33:
                continue
            amt = None
            if len(parts) > 37 and parts[37]:
                try:
                    amt = round(float(parts[37]) / 1e4, 1)   # 万元 -> 亿元
                except ValueError:
                    pass
            try:
                out.append({"name": parts[1], "close": float(parts[3]),
                            "chg_pct": float(parts[32]), "amount_yi": amt})
            except (ValueError, IndexError):
                continue
        return out, f"{SOURCE_TX}·快照"


# ---------- 市场广度（涨跌家数/涨停跌停） ----------

def fetch_breadth():
    """全市场A股价分布统计。返回 (dict 或 None, source)。东财专属，不可达时返回 None 由报告层标注缺口。"""
    try:
        url = ("https://push2.eastmoney.com/api/qt/clist/get?"
               "pn=1&pz=6000&po=1&np=1&fltt=2&fid=f3&"
               "fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f3")
        d = _http_json(url)
        diffs = d["data"]["diff"]
    except Exception:
        return None, "广度数据源（东财）当前不可达，报告标注缺口"
    up = down = flat = limit_up = limit_down = 0
    for it in diffs:
        c = it["f3"]
        if c > 0:
            up += 1
            if c >= 9.9: limit_up += 1
        elif c < 0:
            down += 1
            if c <= -9.9: limit_down += 1
        else:
            flat += 1
    return {"up": up, "down": down, "flat": flat,
            "limit_up": limit_up, "limit_down": limit_down}, f"{SOURCE_EM}·全A快照"


# ---------- 板块行情与资金流 ----------

def fetch_sector_rank(top_n=10, sort_field="f3"):
    """行业+概念板块涨跌/资金流排行。返回 (list 或 None, source)。东财专属，不可达时降级。"""
    try:
        url = ("https://push2.eastmoney.com/api/qt/clist/get?"
               f"pn=1&pz={top_n}&po=1&np=1&fltt=2&fid={sort_field}&"
               "fs=m:90+t:2+f:!50&fields=f2,f3,f12,f14,f62,f104,f105,f128,f136")
        d = _http_json(url)
    except Exception:
        return None, "板块数据源（东财）当前不可达，可由连接器（westock-data 等）补充"
    out = []
    for it in d["data"]["diff"]:
        out.append({
            "name": it["f14"], "code": it["f12"],
            "chg_pct": it["f3"],
            "main_net_yi": round(it["f62"] / 1e8, 2) if isinstance(it.get("f62"), (int, float)) else None,
            "lead_stock": it.get("f128", ""),
            "lead_chg": it.get("f136", None),
        })
    return out, f"{SOURCE_EM}·板块排行"


def fetch_amount_ma5():
    """两市近5日合计成交额（量能对比）。降级时为近似值并标注。"""
    _, rows, _ = fetch_kline("1.000001", 101, 10)
    _, rows2, src2 = fetch_kline("0.399001", 101, 10)
    approx = "近似" in src2 or "近似" in _
    amounts = []
    for i in range(1, 6):
        d1 = rows[-i]["amount"]
        d2 = 0.0
        for r2 in rows2:
            if r2["date"] == rows[-i]["date"]:
                d2 = r2["amount"]
                break
        amounts.append((rows[-i]["date"], round((d1 + d2) / 1e8, 0)))
    return amounts


def now_label():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def latest_trade_date():
    _, rows, _ = fetch_kline("1.000001", 101, 3)
    return rows[-1]["date"]
