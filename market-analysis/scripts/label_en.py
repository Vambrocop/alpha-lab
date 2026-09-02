"""label_en.py — 因子/规律标签的中→英规则翻译(数据层双语·共享单一实现)。

为什么用**规则**而不是手抄映射表:这类标签是组合生成的(资产 × 条件 × 阈值),
如 "NASDAQ RSI超买>75"、"BTC近20日涨>5%"、"标普500 月份效应"。手抄一张表的话,
上游一加新因子/新阈值就漏译;按片段翻则**新组合自动跟上**,且数字原样保留、不会漂移。
同一思路已在 build_signals._macro_en / market_structure.LABELS_EN 用过,这里抽成共享件。

用法:`from label_en import label_en; label_en("BTC在MA200上方") -> "BTC above MA200"`
翻不动的片段原样留中文(诚实回落:宁可显示中文,也不显示空白或机翻乱码)。
"""
import re

# 片段替换表:**长的放前面**(避免 "月份效应" 被 "月份" 先吃掉)
_FRAGMENTS = [
    # 资产/指数
    # 口径前缀(placebo scope 用):放在资产名之前,长片段优先
    ("日频", "Daily"), ("月频", "Monthly"), ("年频", "Annual"),
    ("年份尾数", "Year-ending digit"), ("总统任期年", "Presidential term year"),
    ("假日效应(节前)", "Holiday effect (pre-holiday)"),
    ("标普500", "S&P 500"), ("标普", "S&P 500"), ("纳指100", "NASDAQ 100"),
    ("纳斯达克综合", "NASDAQ Composite"), ("纳斯达克", "NASDAQ"), ("纳指", "NASDAQ"),
    ("费城半导体", "PHLX Semis"), ("比特币", "Bitcoin"), ("黄金", "Gold"), ("原油", "Oil"),
    ("美元指数", "US Dollar Index"), ("美元", "US Dollar"), ("高收益利差", "HY spread"),
    ("信用利差", "credit spread"), ("收益率曲线", "yield curve"),
    # 技术条件
    ("在MA200上方", " above MA200"), ("在MA200下方", " below MA200"),
    ("上方", " above"), ("下方", " below"),
    ("RSI超买", "RSI overbought "), ("RSI超卖", "RSI oversold "),
    ("低波动", " low volatility "), ("高波动", " high volatility "),
    ("近20日涨", " 20-day gain "), ("近20日跌", " 20-day drop "),
    ("动量", " momentum"), ("金叉", "golden cross"), ("死叉", "death cross"),
    ("回撤", "drawdown"), ("反弹", "bounce"), ("超跌", "oversold"),
    # 日历/季节
    ("星期效应", "day-of-week effect"), ("月份效应", "month-of-year effect"),
    ("周内效应", "day-of-week effect"), ("假日效应", "holiday effect"),
    ("季节性", "seasonality"), ("九月效应", "September effect"), ("九月", "September"),
    ("十年位", "decade digit"), ("任期年", "presidential-term year"),
    ("税季", "tax season"), ("税损收割", "tax-loss harvesting"),
    ("圣诞", "Christmas"), ("感恩节", "Thanksgiving"), ("节前", "pre-holiday"),
    ("节后", "post-holiday"), ("月内第", "week "), ("周最强", " of month strongest"),
    ("周偏弱", " of month weaker"),
    # 事件(实测漏网:SVB/圣诞行情/地区银行 等)
    ("倒闭", " collapse"), ("地区银行", "regional banks"), ("行情", " rally"),
    ("疫情", "pandemic"), ("封锁", " lockdown"), ("加息", "rate hike"), ("降息", "rate cut"),
    ("贸易战", "trade war"), ("升级", " escalation"), ("缓和", " relief"),
    ("地缘冲击", "geopolitical shock"), ("银行危机", "banking crisis"),
    ("突破", " breakthrough"), ("飙升", " spike"), ("首次", "first "),
    # 体制/事件
    ("倒挂", "inversion"), ("体制", "regime"), ("恐慌", " fear"), ("贪婪", " greed"),
    ("次日", "next day"), ("前向", "forward"), ("基率", "base rate"),
    # 实测第二批漏网
    ("油价", "Oil price"), ("年份尾数", "year-digit"), ("尾数", "digit"),
    ("总统任期年", "presidential-term year"), ("总统", "presidential "),
    ("期限结构", " term structure"), ("波动率", "volatility"), ("利率", "rates"),
    ("大盘", "broad market"), ("个股", "single stock"), ("指数", " index"),
    ("上涨", " up"), ("下跌", " down"), ("买入", " buy"), ("卖出", " sell"),
    # 实测第三批漏网
    ("隔夜", "overnight"), ("走弱", " weakens"), ("走强", " strengthens"),
    ("为负", " negative"), ("为正", " positive"), ("直接", "direct"),
    # 单位/连接
    ("月度胜率", "monthly win rate"), ("日度胜率", "daily win rate"),
    ("胜率", "win rate"), ("均值", "mean"), ("中位", "median"), ("样本", "sample"),
    ("效应", " effect"), ("月", "M"), ("日", "d"), ("年", "y"),
]


def label_en(zh):
    """中文标签 → 英文(按片段;数字/符号/未知词原样保留)。非字符串或空 → 原样返回。"""
    if not isinstance(zh, str) or not zh:
        return zh
    out = zh
    for a, b in _FRAGMENTS:
        out = out.replace(a, b)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def is_fully_translated(zh):
    """是否已无中文残留——供测试/诊断用,判断片段表是否覆盖到位。"""
    return not re.search(r"[一-龥]", label_en(zh) or "")
