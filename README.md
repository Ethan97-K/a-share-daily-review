# A股每日复盘程序（a-share-review）

定时复盘任务的程序化引擎：数据抓取 → 指标计算 → 阶段判定 → HTML 报告，
AI 叙述层（新闻、事件日历、仓位建议）在报告基础上补充。

## 特性

- **数据三级降级**：本地 AKShare MCP → akshare 库 → 东方财富公开 API → 腾讯行情 API（双域名互备），所有数据标注来源与时点
- **指标引擎**（纯标准库，零第三方依赖）：MA / EMA / MACD / KDJ / 威廉 WR
- **背离检测**：60 分钟 / 30 分钟顶底背离（价格峰谷 vs MACD 柱峰谷双重确认）
- **趋势判定**：短期（1-2周）/ 中长期（1-3月）多因子投票，输出依据与置信度
- **阶段判定**：个股（底部/启动/主升初期/主升中段/鱼尾·高位回调/下降中继/顶部）与板块（启动/主升延续/退潮…）规则引擎，规则可增补
- **跟踪个股动态加载**：只需编辑 `D:\A股复盘增强配置.md` 第一节，程序自动读取，无需改代码
- **选股筛选**：可插拔策略（`volume_breakout` 放量突破 / `macd_golden` MACD金叉），继承 `ScreenStrategy` 即可扩展
- **博主逻辑接口**：读取配置文档第五节蒸馏的博主增强提示词，自动注入报告
- **HTML 报告**：浅底深字研报风格、红涨绿跌（A股惯例）、ECharts 图表、免责声明

## 用法

```bash
# 盘后完整复盘
python main.py --mode post

# 午间复盘
python main.py --mode noon

# 附带选股筛选（逗号分隔多策略）
python main.py --mode post --screener volume_breakout,macd_golden
```

输出：
- `a-share-daily-review-YYYYMMDD.html`（盘后）/ `a-share-noon-review-YYYYMMDD.html`（午间）
- `a-share-*-summary-YYYYMMDD.json`（结构化摘要，供 AI 叙述层消费）

## 配置

| 项 | 位置 |
|---|---|
| 跟踪个股 / 关注板块 / 交易规则 | `D:\A股复盘增强配置.md` 第一节（动态读取） |
| 博主蒸馏逻辑 | `D:\A股复盘增强配置.md` 第五节（粘贴博主文案→AI提炼写入→自动生效） |
| 指数清单 | `data_sources.py` 的 `INDEX_SECIDS` |
| 板块/阶段规则 | `stage.py` |
| 报告路径 | `main.py` 的 `OUT_DIR` |

## 模块结构

```
main.py            CLI 入口与流程编排
config_loader.py   配置文档解析（跟踪股/规则/博主提示词）
data_sources.py    数据源（东财/腾讯/AKShare MCP 三级降级）
indicators.py      技术指标与背离/趋势判定
stage.py           个股/板块阶段规则引擎
screener.py        可插拔选股筛选
blogger.py         博主逻辑注入接口
report.py          HTML 报告渲染
```

## 免责声明

本程序输出基于公开数据和量化分析，仅供研究复盘使用，不构成任何投资建议。市场有风险，投资需谨慎。过往表现不预示未来收益。
