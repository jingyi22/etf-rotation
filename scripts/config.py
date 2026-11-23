import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
DOCS_DIR = os.path.join(ROOT, "docs")
KL_DIR = os.path.join(DATA_DIR, "kl")
TRACK_DIR = os.path.join(ROOT, "track")      # 每日推荐台账与模型状态（进仓库，CI 只追加不改写历史）

# ---- 策略参数（集中在这里，回测、每日推荐、自动验证共用）----
PARAMS = {
    # 候选池：近 20 日日均成交额下限（元）、上市满 N 个交易日
    "min_amount": 100_000_000,  # 1 亿元（2026-11-23 起）。1000 万门槛下的超额主要来自冷门 ETF，实际难以成交
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
    # 1 亿门槛下 2016-2019 每天只有 3-9 只候选，排序检验无意义，开发期从 2020 年开始
    "dev_start": "2020-01-01",
    "holdout_start": "2024-01-01",
    "horizon": 10,            # 模型评估用的持有期（交易日）
}

# ---- 模型 ----
# 候选池版本：变更时 track.py 会在 model_state.json 的 history 里记一笔
UNIVERSE_VERSION = "日均成交额≥1亿（2026-11-23 起；此前为≥1000万）"
# 选择过程（全部只看开发期，留出期只用于事后检验）：
#   v1（2026-11-23 上午，≥1000万池，开发期 2016-2021）：research_pre/pool/cand.py → "趋势+低波"
#   v2（2026-11-23 下午，≥1亿池，开发期 2020-2023）：research_liquid.py / research_liquid_sig.py
#     8 个候选里没有一个相对"趋势+低波"显著更好（中期动量开发期夏普 0.63 vs 0.53，但日收益差 t=0.71、
#     10 日 IC 反而更低 t=-1.27），按晋级规则（t≥2.5）保留现模型，把中期动量加入挑战者
# 冠军初始值；之后由 track.py 每日按 MODEL_RULES 自动验证、晋级，当前状态保存在 track/model_state.json
CHAMPION_INIT = {"name": "趋势+低波", "weights": {"dist250": 0.6, "vol20": -0.4}, "smooth": 5}

# 挑战者：每天与冠军一起记录、一起验证；满足晋级规则时替换冠军
CHALLENGERS = [
    {"name": "中期动量", "smooth": 5, "weights": {"r60": 1, "r120": 1}},
    {"name": "趋势3", "smooth": 5, "weights": {"dist250": 1, "dd250": 1, "dd60": 1}},
    {"name": "低波3", "smooth": 5, "weights": {"vol20": -1, "vol60": -1, "max20": -1}},
    {"name": "13因子等权", "smooth": 5, "weights": {
        "r5": 1, "r20": 1, "r60": 1, "r120": 1, "dist20": 1, "dist60": 1, "dist250": 1,
        "dd60": 1, "dd250": 1, "vol20": -1, "vol60": -1, "max20": -1, "amt_trend": -1}},
]

# ---- 开盘复核（本机 09:26 集合竞价后运行 open_review.py）----
# 研究（research_open*.py，≥1亿池）：
#   低开优先重排新买入：开发期日收益差 t=-0.80~+0.04，扣 0.1% 额外滑点后为负 → 不作为默认
#   高开 >2% 的新买入不追、顺延下一名：开发期 t=0.00（几乎没触发）、留出期 t=+0.67 → 无害、略有帮助，采用
# 开盘复核版与收盘版分别记账、到期对比，见网站"开盘复核"一节
OPEN_REVIEW = {
    "skip_gap": 0.02,         # 新买入候选高开超过 2% 则不买，由下一名补位
    "window": ("09:25:30", "11:30:00"),   # 北京时间；本机 09:26 运行，CI 兜底（GitHub 定时任务常延迟）
}

# ---- 自动验证与优化规则 ----
MODEL_RULES = {
    "eval_window": 500,       # 比较冠军与挑战者用最近 N 个已兑现的交易日
    "promote_t": 2.5,         # 挑战者逐日 IC 差的 t 值（按持有期折算重叠；4 个挑战者，门槛高于 2）
    "promote_min_gap": 0.01,  # 且 IC 均值至少高出 0.01
    "cooldown": 60,           # 两次模型变更至少间隔 N 个交易日
    "horizons": (1, 5, 10),   # 每日推荐兑现后的统计持有期
}
