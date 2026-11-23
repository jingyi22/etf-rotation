# ETF 轮动参考（etf-rotation）

一个用公开行情数据复现并改进"ETF 超跌轮动"思路的静态站点：每天收盘后由 GitHub Actions 抓数、回测、生成页面，发布在 GitHub Pages。

**线上页面**：https://jingyi22.github.io/etf-rotation/

> 历史回测，不是投资建议。有一定数量的样本内参数选择，详见页面"局限"一节。

## 策略

候选池（剔除货币/债券/黄金商品/跨境，近 20 日日均成交额门槛，上市 ≥ 60 交易日，按近 120 日相关性去重）里：

- **选样**：`距 250 日均线`（权重 0.6）+ `20 日低波`（权重 −0.4）合成评分排名前 5，等权；
  已持有且排名在前 15 的继续持有（排名缓冲，显著降低换手）。因子方向来自逐日 Rank IC 检验（`scripts/research.py`）。
- **防守**：沪深300 收盘跌破 250 日均线时，切 60% 国债 ETF（511010）+ 40% 红利低波 ETF。
- **成交**：收盘出信号、下一交易日开盘调仓；单边成本 0.1%；停牌按最近有效收盘价记账。

回测（2015-01 ~ 2026-11，扣费后）：年化约 5.9%，最大回撤 34.5%，夏普 0.33，年单边换手 4.9 倍；同期沪深300 年化 1.0%、最大回撤 46.7%。
2024 年以来年化 20.8%，早年的结果接近零——收益分布很不均匀，这是最大的风险来源。

## 数据与流程

数据源为新浪财经（akshare `fund_etf_hist_sina` / `stock_zh_index_daily`），不依赖东财。

```
scripts/fetch_data.py   # ETF 列表 + 全量日线（增量缓存于 data/kl/）+ 沪深300 日线
scripts/clean.py        # 修补份额折算（拆分）造成的价格断崖
scripts/universe.py     # 剔除货币/债券/跨境，相关性+名称去重，生成 data/panel.npz
scripts/score.py        # 回测 + 今日信号 → data/backtest.json / data/signals.json
scripts/build_site.py   # 渲染 docs/index.html（单页，无外部依赖）
scripts/research.py     # 因子 Rank IC 研究（可选，用于复查权重）
```

本地运行：

```bash
pip install -r requirements.txt
python scripts/fetch_data.py && python scripts/clean.py && python scripts/universe.py
python scripts/score.py && python scripts/build_site.py
```

`.github/workflows/update.yml` 在每个交易日收盘后（北京时间 16:30）自动执行上述流程并提交 `docs/`。

`data/` 是行情缓存与中间结果（ETF 日线约 50 MB），已在 `.gitignore` 中；CI 每次从新浪全量重建（约 4 分钟），仓库只保留脚本与生成的页面。

## 已知局限

- 幸存者偏差：候选池来自今天仍在交易、且新浪能取到行情的 ETF。
- 参数样本内：因子与缓冲宽度先看全样本结果再定。
- 未模拟成交额冲击；不处理涨跌停排队；拆分修补是规则识别，个别冷门 ETF 可能漏判。
