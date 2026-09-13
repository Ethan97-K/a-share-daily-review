# -*- coding: utf-8 -*-
"""HTML 报告生成：浅底深字研报风格、红涨绿跌（A股惯例）、ECharts 图表、来源标注。"""
import json


def _cls(v):
    if v is None:
        return ""
    return "up" if v > 0 else ("down" if v < 0 else "")


def _fmt(v, suffix=""):
    if v is None:
        return "—"
    return f"{v}{suffix}"


def _fmt_pct(v):
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def render(ctx: dict) -> str:
    """ctx 键：mode/date/indices/breadth/amounts/index_analysis/tracked/sectors/
    screener/blogger/sources/generated_at/disclaimer"""
    mode = ctx["mode"]
    title = "A股盘后复盘报告" if mode == "post" else "A股午间复盘报告"
    idx_rows = ""
    for it in ctx["indices"]:
        idx_rows += (f"<tr><td><b>{it['name']}</b></td>"
                     f"<td>{it['close']}</td>"
                     f"<td class='{_cls(it['chg_pct'])}'>{_fmt_pct(it['chg_pct'])}</td>"
                     f"<td>{_fmt(it['amount_yi'])} 亿</td></tr>")

    br = ctx.get("breadth") or {}
    amounts = ctx.get("amounts") or []
    amount_html = ""
    if amounts:
        today_amt, avg5 = amounts[-1][1], sum(a for _, a in amounts[:-1]) / max(1, len(amounts) - 1)
        ratio = today_amt / avg5 if avg5 else 0
        level = ("天量天价" if ratio > 1.4 else "放量分歧" if ratio > 1.15 else
                 "温和放量" if ratio > 0.9 else "缩量观望" if ratio > 0.7 else "地量地价")
        amount_html = (f"<div class='kpi'>两市合计 <b>{today_amt:,.0f} 亿</b> ｜ "
                       f"对比5日均量 <b class='{_cls(ratio-1)}'>{ratio:.2f} 倍</b> ｜ "
                       f"量能等级：<b>{level}</b></div>")

    ana = ctx.get("index_analysis") or {}
    ana_rows = ""
    for name, a in ana.items():
        divs = "；".join(f"{d.timeframe}{d.kind}" if d.kind != "无" else f"{d.timeframe}无背离"
                         for d in a["divergences"])
        ana_rows += (f"<tr><td><b>{name}</b></td>"
                     f"<td class='{ 'up' if a['trend'].short_term=='向上' else 'down' if a['trend'].short_term=='向下' else ''}'>"
                     f"{a['trend'].short_term}</td>"
                     f"<td class='{ 'up' if a['trend'].mid_term=='向上' else 'down' if a['trend'].mid_term=='向下' else ''}'>"
                     f"{a['trend'].mid_term}</td>"
                     f"<td>{divs or '—'}</td>"
                     f"<td class='note'>{'<br>'.join(a['trend'].basis)}</td>"
                     f"<td>{a['trend'].confidence}</td></tr>")

    # 跟踪个股卡片
    cards = ""
    for t in ctx.get("tracked") or []:
        cards += f"""
    <div class="card" style="border-top-color:{t['stage_info']['color']};">
      <div class="name">{t['code']} {t['name']}</div>
      <span class="stage" style="background:{t['stage_info']['color']};">{t['stage_info']['stage']}</span>
      <p>{t['close']} 元（<span class='{_cls(t["chg_pct"])}'>{_fmt_pct(t['chg_pct'])}</span>）｜
         量比20日均量 {t['vol_vs_ma20']} 倍<br>
         {'<br>'.join(t['stage_info']['basis'])}<br>
         支撑 <b>{t['stage_info']['key_levels']['support']}</b> ／ 压力 <b>{t['stage_info']['key_levels']['resist']}</b></p>
    </div>"""

    chart_data = json.dumps(ctx.get("tracked_chart") or {}, ensure_ascii=False)
    tracked_chart_html = ""
    if ctx.get("tracked_chart"):
        tracked_chart_html = f"""
  <div class="panel"><h2>跟踪个股近60日走势对比（归一化，起点=100）</h2>
    <div id="chart_tracked"></div>
    <div class="src">来源：{ctx.get('kline_source','东方财富公开行情接口')}（前复权日线）</div>
  </div>"""

    # 板块排行
    sec_rows = ""
    for s in ctx.get("sectors") or []:
        sec_rows += (f"<tr><td><b>{s['name']}</b></td>"
                     f"<td class='{_cls(s['chg_pct'])}'>{_fmt_pct(s['chg_pct'])}</td>"
                     f"<td class='{_cls(s['main_net_yi'])}'>{_fmt(s['main_net_yi'])} 亿</td>"
                     f"<td>{s.get('lead_stock') or '—'}"
                     f"（<span class='{_cls(s.get('lead_chg'))}'>{_fmt_pct(s.get('lead_chg'))}</span>）</td></tr>")
    sector_html = ""
    if sec_rows:
        sector_html = f"""
  <div class="panel"><h2>活跃板块 TOP10（按涨跌幅）</h2>
    <table><tr><th>板块</th><th>涨跌幅</th><th>主力净额</th><th>领涨股（涨幅）</th></tr>{sec_rows}</table>
    <div class="src">来源：{ctx.get('sector_source','')}</div>
  </div>"""

    # 选股筛选
    sc = ctx.get("screener")
    screener_html = ""
    if sc:
        rows = "".join(f"<tr><td>{h['code']} {h['name']}</td>"
                       f"<td class='{_cls(h['chg_pct'])}'>{_fmt_pct(h['chg_pct'])}</td>"
                       f"<td>{h['amount_yi']} 亿</td><td>{h['reason']}</td></tr>"
                       for h in sc["hits"]) or "<tr><td colspan=4>本策略今日无命中</td></tr>"
        screener_html = f"""
  <div class="panel"><h2>选股筛选 · {sc['strategy']}</h2>
    <div class="note">{sc['desc']}</div>
    <table><tr><th>个股</th><th>涨跌幅</th><th>成交额</th><th>命中理由</th></tr>{rows}</table>
  </div>"""

    # 博主模块
    bg = ctx.get("blogger") or {}
    blogger_html = ""
    if bg.get("active"):
        items = "".join(f"<li>{p}</li>" for p in bg["prompts"])
        blogger_html = f"<div class='panel'><h2>{bg['title']}</h2><ul class='note'>{items}</ul></div>"
    else:
        blogger_html = f"<div class='panel note'>📥 {bg.get('hint','')}</div>"

    chart_tracked_js = """
var TD = __TRACKED_DATA__;
if (TD.dates) {
  var ct = echarts.init(document.getElementById('chart_tracked'));
  ct.setOption({ tooltip:{trigger:'axis'}, legend:{data:TD.names},
    grid:{left:50,right:24,top:40,bottom:60},
    dataZoom:[{type:'slider',height:18,bottom:12}],
    xAxis:{type:'category',data:TD.dates},
    yAxis:{type:'value',name:'归一化(起点=100)',scale:true},
    series:TD.series });
}
""".replace("__TRACKED_DATA__", chart_data)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} · {ctx['date']}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  body {{ font-family:"Microsoft YaHei","PingFang SC",sans-serif; background:#f7f8fa; color:#1f2329; margin:0; padding:24px; }}
  .wrap {{ max-width: 1000px; margin:0 auto; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .sub {{ color:#6b7280; font-size:13px; margin-bottom:20px; }}
  .cards {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:24px; }}
  .card {{ flex:1; min-width:280px; background:#fff; border-radius:10px; padding:16px 18px; box-shadow:0 1px 4px rgba(0,0,0,.06); border-top:4px solid #888; }}
  .card .name {{ font-size:15px; font-weight:600; }}
  .stage {{ display:inline-block; margin-top:8px; padding:4px 10px; border-radius:6px; color:#fff; font-size:13.5px; font-weight:600; }}
  .card p {{ font-size:12.5px; color:#4b5563; margin:10px 0 0; line-height:1.6; }}
  .panel {{ background:#fff; border-radius:10px; padding:18px 20px; box-shadow:0 1px 4px rgba(0,0,0,.06); margin-bottom:24px; }}
  .panel h2 {{ font-size:16px; margin:0 0 12px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
  th,td {{ border:1px solid #e5e7eb; padding:7px 9px; text-align:left; vertical-align:top; }}
  th {{ background:#f3f4f6; font-weight:600; }}
  .up {{ color:#dc2626; font-weight:600; }}
  .down {{ color:#16a34a; font-weight:600; }}
  .kpi {{ font-size:14px; margin-bottom:10px; }}
  .note {{ font-size:12px; color:#6b7280; line-height:1.7; }}
  .src {{ font-size:11.5px; color:#9ca3af; margin-top:8px; }}
  .disclaimer {{ margin-top:24px; padding:14px 16px; background:#fffbeb; border:1px solid #fde68a; border-radius:8px; font-size:12.5px; color:#78350f; line-height:1.7; }}
  #chart_tracked {{ width:100%; height:360px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{title}（{ctx['date']}）</h1>
  <div class="sub">生成于 {ctx['generated_at']} ｜ 数据来源：{ctx.get('sources','')} ｜ 模式：{'盘后完整复盘' if mode=='post' else '午间盘中复盘'}</div>

  <div class="panel"><h2>① 指数概览</h2>
    <table><tr><th>指数</th><th>收盘/现价</th><th>涨跌幅</th><th>成交额</th></tr>{idx_rows}</table>
    {amount_html}
    <div class="kpi">上涨 <b class="up">{br.get('up','—')}</b> 家 ｜ 下跌 <b class="down">{br.get('down','—')}</b> 家 ｜
      涨停 {br.get('limit_up','—')} ／ 跌停 {br.get('limit_down','—')}</div>
    <div class="src">{ctx.get('snapshot_source','')}</div>
  </div>

  <div class="panel"><h2>② 趋势与背离判定</h2>
    <table><tr><th>指数</th><th>短期(1-2周)</th><th>中长期(1-3月)</th><th>背离信号</th><th>判定依据</th><th>置信度</th></tr>{ana_rows}</table>
  </div>

  <div class="cards">{cards or '<div class="card note">跟踪个股为空：请在 D:\\A股复盘增强配置.md 第一节添加。</div>'}</div>
  {tracked_chart_html}

  {sector_html}
  {screener_html}
  {blogger_html}

  <div class="panel note"><b>说明</b><br>
  · 趋势/背离/阶段均为量化规则判定（多因子投票），置信度供参考；叙述层解读（新闻、事件日历、仓位建议）由 AI 在对话中补充。<br>
  · 增加跟踪股票：编辑 D:\\A股复盘增强配置.md 第一节即可，下次运行自动纳入。选股策略扩展见 screener.py。</div>

  <div class="disclaimer"><b>免责声明</b>：{ctx.get('disclaimer','')}</div>
</div>
<script>{chart_tracked_js}</script>
</body>
</html>"""
