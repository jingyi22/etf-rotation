# ETF 轮动 · 每日推荐与自动验证（etf-rotation）

每个交易日收盘后，按模型给出下一交易日开盘的 ETF 持仓；推荐写入只追加的台账，到期后用真实开盘价自动评分；
每天比较当前模型与挑战者，挑战者显著更好才替换。全部由 GitHub Actions 自动运行，结果发布在 GitHub Pages。

**线上页面**：https://jingyi22.github.io/etf-rotation/ ·
**今日推荐（JSON）**：https://jingyi22.github.io/etf-rotation/today.json

> 模型输出与统计记录，不是投资建议。留出期的预测优势很弱（前 5 名跑赢候选池中位数约 53–55%），任何一天都可能亏钱。

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

## 模型

- **候选池**：剔除货币、债券、商品、跨境；近 20 日日均成交额 ≥ 1000 万元；上市满 120 个交易日；同一指数每天只留成交额最大的一只（point-in-time，不用未来信息）。
- **特征**：14 个价量特征（各周期涨跌、距均线、距高点、波动、成交额），每天在候选池内转为百分位。
- **当前模型**：距 250 日均线 (+0.6) + 20 日波动 (−0.4)，分数 5 日指数平滑；取前 5，排名缓冲 10，与已选 ETF 60 日相关 > 0.9 则跳过。
- **防守**：沪深300 低于 250 日均线时，持 60% 国债 ETF + 40% 红利低波 ETF。
- **成交**：收盘出信号、次日开盘成交、单边成本 0.1%。

### 怎么选出来的

2016–2021 为开发期，2022 起为留出期。所有选择（单因子方向、候选池门槛、8 个组合候选）只看开发期，留出期只用于检验：

```bash
python scripts/research_pre.py    # 单因子 10 日 Rank IC，预注册因子方向
python scripts/research_pool.py   # 候选池门槛
python scripts/research_cand.py   # 8 个组合候选的组合回测
```

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

## 已知局限

- 预测力弱，收益主要来自大量交易日上的微弱优势与年线防守。
- 幸存者偏差：候选池来自今天仍能取到行情的 ETF。
- 未模拟冲击成本；不处理涨跌停与停牌排队；拆分修补是规则识别。
