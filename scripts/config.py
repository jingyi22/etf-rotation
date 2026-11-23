import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
DOCS_DIR = os.path.join(ROOT, "docs")
KL_DIR = os.path.join(DATA_DIR, "kl")
TRACK_DIR = os.path.join(ROOT, "track")      # 每日推荐台账与模型状态（进仓库，CI 只追加不改写历史）

# ---- 策略参数（集中在这里，回测、每日推荐、自动验证共用）----
PARAMS = {
    # 候选池：近 20 日日均成交额下限（元）、上市满 N 个交易日
    "min_amount": 10_000_000,   # 1000 万元；开发期比较 1000万/2000万/5000万 后选定（research_pool.py）
    "min_history": 120,
    # 持仓
    "n_hold": 5,
    "rank_buffer": 10,        # 已持有 ETF 排名跌出 n_hold+buffer 之外才卖
    "corr_cap": 0.90,         # 选样时与已选 ETF 的 60 日收益相关 > 该值则跳过（避免买到同一行情）
    # 防守：沪深300 收盘 < MA250 时切 60% 国债ETF + 40% 红利低波
    "defense_ma": 250,
    "defense_bond": "511010",
    "defense_defensive": ["515300", "515450", "515100"],
    "defense_bond_w": 0.6,
    # 成交与成本
    "cost": 0.001,            # 单边（佣金 + 滑点）
    "start": "2015-01-05",
    # 研究划分：开发期用于选因子和方向，留出期只用于检验
    "dev_start": "2016-01-01",
    "holdout_start": "2022-01-01",
    "horizon": 10,            # 模型评估用的持有期（交易日）
}

# ---- 模型 ----
# 选择过程（2026-11-23，全部只看开发期 2016-2021，留出期 2022+ 只用于事后检验）：
#   1) 单因子 10 日 Rank IC：research_pre.py；2) 候选池门槛：research_pool.py；
#   3) 组合回测比较 8 个候选：research_cand.py → 开发期夏普最高的是"距年线 + 低波，分数 5 日平滑"。
# 冠军初始值；之后由 track.py 每日按 MODEL_RULES 自动验证、晋级，当前状态保存在 track/model_state.json
CHAMPION_INIT = {"name": "趋势+低波", "weights": {"dist250": 0.6, "vol20": -0.4}, "smooth": 5}

# 挑战者：每天与冠军一起记录、一起验证；满足晋级规则时替换冠军
CHALLENGERS = [
    {"name": "13因子等权", "smooth": 5, "weights": {
        "r5": 1, "r20": 1, "r60": 1, "r120": 1, "dist20": 1, "dist60": 1, "dist250": 1,
        "dd60": 1, "dd250": 1, "vol20": -1, "vol60": -1, "max20": -1, "amt_trend": -1}},
    {"name": "趋势3", "smooth": 5, "weights": {"dist250": 1, "dd250": 1, "dd60": 1}},
    {"name": "高点距离+低波", "smooth": 5, "weights": {"dd60": 1, "dd250": 1, "vol60": -1}},
    {"name": "低波3", "smooth": 5, "weights": {"vol20": -1, "vol60": -1, "max20": -1}},
]

# ---- 自动验证与优化规则 ----
MODEL_RULES = {
    "eval_window": 500,       # 比较冠军与挑战者用最近 N 个已兑现的交易日
    "promote_t": 2.5,         # 挑战者逐日 IC 差的 t 值（按持有期折算重叠；4 个挑战者，门槛高于 2）
    "promote_min_gap": 0.01,  # 且 IC 均值至少高出 0.01
    "cooldown": 60,           # 两次模型变更至少间隔 N 个交易日
    "horizons": (1, 5, 10),   # 每日推荐兑现后的统计持有期
}
