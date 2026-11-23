# ETF 轮动 · 每日推荐与自动验证（etf-rotation）

每个交易日收盘后，按模型给出下一交易日开盘的 ETF 持仓；推荐写入只追加的台账，到期后用真实开盘价自动评分；
每天比较当前模型与挑战者，挑战者显著更好才替换。全部由 GitHub Actions 自动运行，结果发布在 GitHub Pages。

**线上页面**：https://jingyi22.github.io/etf-rotation/ ·
**今日推荐（JSON）**：https://jingyi22.github.io/etf-rotation/today.json

> 模型输出与统计记录，不是投资建议。在日均成交额 ≥ 1 亿的 ETF 里，模型几乎没有选股优势（留出期前 5 名跑赢候选池中位数 51–53%，随机为 50%），任何一天都可能亏钱。

## 每日流程

| 步骤 | 脚本 | 产出 |
|---|---|---|
| 抓数 | `fetch_data.py` | 新浪 ETF 日线（串行，增量缓存）+ 沪深300 |
| 清洗 | `clean.py` | 修补份额折算造成的价格断崖 |
| 面板 | `universe.py` | 只保留 A 股股票型 ETF，`data/panel.npz` |
| 推荐 + 验证 | `track.py` | 今日推荐、追加台账 `track/predictions.jsonl`、兑现评分 `track/scored.json`、模型晋级 `track/model_state.json` |
| 台账检查 | `check_ledger.py` | 已提交的台账行被改动则 CI 失败，不推送 |
| 回测 | `score.py` | 当前模型的组合回测（开发期 / 留出期分开） |
| 页面 | `build_site.py` | `docs/index.html`、`docs/today.json` |
| 开盘复核（次日 09:26） | `open_review.py` | 读 `docs/today.json` + 新浪集合竞价价，追加 `track/open_review.jsonl`，写 `docs/open.json` |

## 模型

- **候选池**：剔除货币、债券、商品、跨境；近 20 日日均成交额 ≥ 1 亿元（2026-11-23 起，此前 1000 万下的超额主要来自冷门 ETF）；上市满 120 个交易日；同一指数每天只留成交额最大的一只（point-in-time，不用未来信息）。
- **特征**：14 个价量特征（各周期涨跌、距均线、距高点、波动、成交额），每天在候选池内转为百分位。
- **当前模型**：距 250 日均线 (+0.6) + 20 日波动 (−0.4)，分数 5 日指数平滑；取前 5，排名缓冲 10，与已选 ETF 60 日相关 > 0.9 则跳过。
- **防守**：沪深300 低于 250 日均线时，持 60% 国债 ETF + 40% 红利低波 ETF。
- **成交**：收盘出信号、次日开盘成交、单边成本 0.1%。

- **开盘复核**：次日 09:26 集合竞价后，需要新买入的 ETF 若高开 > 2% 则不追、由下一名补位；继续持有与卖出不变；防守模式不调整。

### 怎么选出来的

1 亿门槛下 2019 年以前每天只有 3–9 只候选，无法检验排序，所以开发期为 2020–2023，留出期为 2024 起。所有选择只看开发期，留出期只用于检验：

```bash
python scripts/research_liquid.py      # 流动性池：单因子 IC + 8 个组合候选的组合回测
python scripts/research_liquid_sig.py  # 候选相对现模型的差异是否显著（都不显著，保留现模型）
python scripts/research_open.py        # 开盘跳空的预测力（全池很强，但多来自冷门 ETF 开盘价噪声）
python scripts/research_open2.py       # 稳健性：按流动性分层、改用收盘价计算后效应基本消失
python scripts/research_open_bt.py     # "低开优先"组合回测：开发期扣额外滑点后变差，未采用
python scripts/research_open_guard.py  # "高开 >2% 不追"：无害、留出期略有帮助，采用
```

早期在 1000 万池上的研究（`research_pre/pool/cand.py`）保留作记录。

### 每日自动验证与优化

当前模型和 4 个挑战者每天都记录前 5 名。用最近 500 个已兑现交易日比较 10 日 Rank IC：
挑战者 IC 均值高出 ≥ 0.01、差值 t ≥ 2.5（按持有期折算重叠样本），且距上次变更 ≥ 60 个交易日，才自动晋级。
规则在 `scripts/config.py` 的 `MODEL_RULES`，变更历史写入 `track/model_state.json` 并显示在页面上。

## 本地运行

```bash
pip install -r requirements.txt
python scripts/fetch_data.py && python scripts/clean.py && python scripts/universe.py
python scripts/track.py && python scripts/score.py && python scripts/build_site.py
```

`data/` 是行情缓存（约 50 MB），不进仓库，CI 每次全量重建；`track/` 是推荐台账，进仓库。

### 开盘复核的定时运行

GitHub 定时任务常延迟 10–30 分钟，所以主路径放在本机：Windows 计划任务 `ETFRotation_OpenReview` 工作日 09:26 调用 `tools/open_review_task.cmd`
（这台电脑的组策略禁止计划任务直接启动 powershell，所以经由 .cmd 包一层），日志在 `%LOCALAPPDATA%\etf-rotation\open_review.log`。
电脑没开时 `.github/workflows/open_review.yml` 在 09:45 / 10:15 补跑；当天已复核过会直接跳过。

## 已知局限

- 预测力弱，收益主要来自大量交易日上的微弱优势与年线防守。
- 幸存者偏差：候选池来自今天仍能取到行情的 ETF。
- 未模拟冲击成本；不处理涨跌停与停牌排队；拆分修补是规则识别。
