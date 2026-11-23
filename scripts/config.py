import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
DOCS_DIR = os.path.join(ROOT, "docs")
KL_DIR = os.path.join(DATA_DIR, "kl")

# ---- 策略参数（集中在这里，回测与线上信号共用）----
PARAMS = {
    # 流动性：近 20 日平均成交额（元）下限。规模数据需另抓，回测里用成交额代理
    "min_amount": 10_000_000,    # 1000 万元/日（2019 年底前，ETF 池很小，门槛低一些）
    "min_amount_cap": 100_000_000,  # 2020 年后（ETF 数量已扩容）要求 1 亿元/日
    "cap_from": "2020-01-01",
    # 有效性：上市至少 N 个交易日才进入候选
    "min_history": 60,
    # 持仓
    "n_hold": 5,
    "min_hold_days": 0,       # 新买入后至少持有 N 个交易日才会被调出（0=不限制）
    "rank_buffer": 10,        # 已持有 ETF 排名跌出 n_hold+buffer 之外才卖（缓冲是关键经验）
    "dedupe_rho": 0.95,       # 近 120 日收益相关超过该值视为同一指数，只留成交额最大的一只
    "dedupe_window": 120,
    # 因子权重（横截面 z-score 加权），负号=反向
    # 权重来自逐日 Rank IC 研究（scripts/research.py，2015-2026 全样本）：
    # 距250日均线 +0.028、120日动量 +0.022、60日回撤 +0.015（浅回撤好）、20日波动 −0.038（低波好）
    "w_dist252": +0.60,       # 距 250 日均线（正 IC 最强：越靠上年线，未来 5 日越可能上涨）
    "w_vol20": -0.40,         # 20 日波动（负 IC 最强：低波明显占优）
    "w_r120": 0,              # 120 日动量：与距250日线高度重叠，去掉
    "w_dd60": 0,              # 60 日回撤：加上会降低表现
    "w_dist60": 0,            # 距 60 日均线：IC 不稳定，去掉
    # 防守（市场状态）：沪深300 收盘 < MA250 时切 60% 国债ETF + 40% 低波红利
    "defense_ma": 250,
    "defense_bond": "511010",
    "defense_defensive": ["515300", "515450", "515100"],  # 红利低波类，各 13.3%
    "defense_bond_w": 0.6,
    # 成本（单边，含佣金+滑点）与成交口径
    "cost": 0.001,
    "exec": "next_open",      # 收盘出信号、次日开盘成交
    "rebalance_days": 1,      # 每 N 个交易日检查一次调仓（1=每日检查）
    # 区间
    "start": "2015-01-05",
}
