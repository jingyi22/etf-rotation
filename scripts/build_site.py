"""把 data/daily.json（每日推荐 + 实盘台账 + 模型验证）与 data/backtest.json（回测）
渲染成 docs/index.html（单页、无外部依赖）。"""
import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR, DOCS_DIR

E = html.escape


CSS = r"""
:root{
  color-scheme: light;
  --surface-0:#f6f6f4; --surface-1:#fcfcfb; --surface-2:#f0efec;
  --line:#e3e2dd; --line-strong:#cfcec8;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#7d7c76;
  --series-1:#2a78d6; --series-2:#eb6834;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --good-ink:#006300; --warning-ink:#7a5300; --critical-ink:#a52121;
  --amber-bg:#fff6e0; --amber-ink:#6b4a00; --amber-line:#f0d9a0;
  --radius:12px;
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:ui-monospace,SFMono-Regular,"Cascadia Mono",Consolas,monospace;
}
@media (prefers-color-scheme: dark){
  :root:where(:not([data-theme="light"])){
    color-scheme: dark;
    --surface-0:#111110; --surface-1:#1a1a19; --surface-2:#232322;
    --line:#2e2e2c; --line-strong:#44443f;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
    --series-1:#3987e5; --series-2:#d95926;
    --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
    --good-ink:#3fcf3f; --warning-ink:#fab219; --critical-ink:#ff8a8a;
    --amber-bg:#2a2415; --amber-ink:#f2c66d; --amber-line:#4a3d1d;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --surface-0:#111110; --surface-1:#1a1a19; --surface-2:#232322;
  --line:#2e2e2c; --line-strong:#44443f;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
  --series-1:#3987e5; --series-2:#d95926;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --good-ink:#3fcf3f; --warning-ink:#fab219; --critical-ink:#ff8a8a;
  --amber-bg:#2a2415; --amber-ink:#f2c66d; --amber-line:#4a3d1d;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--surface-0);color:var(--text-primary);font-family:var(--font);overflow-x:hidden;
  font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 64px}
header.top{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;justify-content:space-between;margin-bottom:6px}
h1{font-size:26px;line-height:1.25;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:19px;margin:0 0 4px;letter-spacing:-.005em}
h3{font-size:15px;margin:0 0 8px}
.sub{color:var(--text-secondary);font-size:13.5px;margin:0}
.muted{color:var(--text-muted)}
.updated{color:var(--text-muted);font-size:12.5px;font-variant-numeric:tabular-nums;white-space:nowrap;padding-top:6px}
.theme-btn{background:var(--surface-1);border:1px solid var(--line);color:var(--text-secondary);
  border-radius:8px;padding:5px 10px;font-size:12.5px;cursor:pointer;font-family:inherit}
.toc{display:flex;flex-wrap:wrap;gap:6px 14px;margin:14px 0 0;font-size:13px}
.toc a{color:var(--text-secondary);text-decoration:none;border-bottom:1px solid var(--line-strong)}
.toc a:hover{color:var(--series-1);border-color:var(--series-1)}
.banner{display:flex;gap:12px;align-items:flex-start;background:var(--amber-bg);color:var(--amber-ink);
  border:1px solid var(--amber-line);border-radius:var(--radius);padding:12px 16px;margin:18px 0 22px;font-size:13.5px}
.banner b{color:inherit}
.card{background:var(--surface-1);border:1px solid var(--line);border-radius:var(--radius);padding:20px 22px;margin:0 0 18px}
.card-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:14px}
.card-head .hint{color:var(--text-muted);font-size:12.5px;text-align:right}
.regime{display:grid;grid-template-columns:auto 1fr;gap:0 20px;align-items:center}
.regime .state{font-size:28px;font-weight:650;letter-spacing:-.01em}
.regime .state .dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:9px;vertical-align:3px}
.regime .state.defense{color:var(--warning-ink)}
.regime .state.risk{color:var(--good-ink)}
.regime p{margin:4px 0;color:var(--text-secondary);font-size:13.5px}
.regime .facts{color:var(--text-muted);font-size:12.5px;font-variant-numeric:tabular-nums}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:16px}
.kpi{background:var(--surface-2);border-radius:10px;padding:11px 13px}
.kpi .l{font-size:12px;color:var(--text-muted)}
.kpi .v{font-size:20px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.kpi .d{font-size:12px;color:var(--text-secondary)}
table{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}
th{color:var(--text-muted);font-weight:500;text-align:left;font-size:12px;padding:0 10px 8px 0;border-bottom:1px solid var(--line)}
th.r,td.r{text-align:right;padding-right:0;padding-left:14px}
td{padding:9px 10px 9px 0;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:none}
td code{font-family:var(--mono);font-size:12.5px;color:var(--text-secondary)}
td .nm{font-weight:520}
.badge{display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:99px;border:1px solid var(--line-strong);
  color:var(--text-secondary);margin-left:6px;vertical-align:1px;white-space:nowrap}
.badge.new{border-color:var(--series-1);color:var(--series-1)}
.badge.keep{border-color:var(--line-strong);color:var(--text-muted)}
.badge.buy{border-color:var(--series-1);color:var(--series-1)}
.badge.sell{border-color:var(--series-2);color:var(--series-2)}
.badge.def{border-color:var(--warning-ink);color:var(--warning-ink)}
.chart{position:relative;width:100%}
.chart.nav-chart svg{aspect-ratio:1000/300}
.chart.dd-chart svg{aspect-ratio:1000/150}
.chart.cand-chart svg{aspect-ratio:1000/160}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.chart .gridline{stroke:var(--line);stroke-width:1}
.chart .axis-text{fill:var(--text-muted);font-size:11px;font-family:var(--font)}
.chart .series-line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.chart .crosshair{stroke:var(--text-muted);stroke-width:1;opacity:0;pointer-events:none}
.chart .hit{fill:transparent;cursor:crosshair}
.legend{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin:0 0 10px;font-size:12.5px;color:var(--text-secondary)}
.legend .key{display:inline-flex;align-items:center;gap:7px}
.legend .key i{display:inline-block;width:18px;height:0;border-top:2px solid var(--series-1)}
.legend .key.b i{border-top-color:var(--series-2)}
.tooltip{position:absolute;pointer-events:none;max-width:220px;background:var(--surface-1);border:1px solid var(--line-strong);
  border-radius:8px;padding:9px 11px;font-size:12.5px;box-shadow:0 4px 16px rgba(0,0,0,.12);opacity:0;
  transition:opacity .08s;z-index:5;width:230px}
.tooltip .t{color:var(--text-muted);font-size:11.5px;margin-bottom:4px;font-variant-numeric:tabular-nums}
.tooltip .row{display:flex;align-items:center;justify-content:space-between;gap:14px;white-space:nowrap}
.tooltip .row i{display:inline-block;width:14px;height:0;border-top:2px solid var(--series-1)}
.tooltip .row.b i{border-top-color:var(--series-2)}
.tooltip .row b{font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap;flex-shrink:0}
.tooltip .row span{color:var(--text-secondary)}
details{border-top:1px solid var(--line);padding:10px 0 0;margin-top:8px}
details summary{cursor:pointer;color:var(--text-secondary);font-size:13px;list-style:none}
details summary::-webkit-details-marker{display:none}
details summary::before{content:"▸ ";color:var(--text-muted)}
details[open] summary::before{content:"▾ "}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:22px}
h3.sec{font-size:13px;color:var(--text-muted);text-transform:none;letter-spacing:.02em;margin:18px 0 8px;font-weight:500}
ul.notes{margin:6px 0 0;padding-left:18px;color:var(--text-secondary);font-size:13.5px}
ul.notes li{margin:4px 0}
footer{margin-top:26px;color:var(--text-muted);font-size:12.5px;line-height:1.7}
footer b{color:var(--text-secondary)}
.tag{display:inline-block;padding:1px 7px;border-radius:6px;background:var(--surface-2);color:var(--text-secondary);font-size:12px;margin-right:4px}
@media(max-width:820px){
  .kpis{grid-template-columns:repeat(2,1fr)}
  .cols{grid-template-columns:1fr}
  .regime{grid-template-columns:1fr}
  h1{font-size:22px}
  .wrap{padding:20px 14px 52px}
  .card{padding:16px}
  th,td{padding-right:6px}
  .hidesm{display:none}
  .card-head{flex-direction:column;align-items:flex-start;gap:4px}
  .card-head .hint{text-align:left}
}
"""

JS = r"""
(function(){
  var root=document.documentElement;
  var btn=document.getElementById('theme');
  function apply(mode){
    if(mode){root.setAttribute('data-theme',mode);}else{root.removeAttribute('data-theme');}
    btn.textContent = (mode==='dark'||(!mode&&matchMedia('(prefers-color-scheme: dark)').matches))?'☀ 浅色':'☾ 深色';
    document.querySelectorAll('.tooltip').forEach(function(t){t.style.opacity=0;});
  }
  btn.addEventListener('click',function(){
    var cur=root.getAttribute('data-theme');
    if(!cur){cur=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
    apply(cur==='dark'?'light':'dark');
  });
  apply(root.getAttribute('data-theme'));

  // 折线图：十字线 + tooltip（净值图与回撤图共用）
  function attach(chartEl,data,series){
    var svg=chartEl.querySelector('svg'), tip=chartEl.querySelector('.tooltip'),
        cross=chartEl.querySelector('.crosshair');
    var vb=svg.viewBox.baseVal, W=vb.width, H=vb.height;
    var x0=svg.getAttribute('data-x0')*1, x1=svg.getAttribute('data-x1')*1,
        y0=svg.getAttribute('data-y0')*1, y1=svg.getAttribute('data-y1')*1;
    function pt(evt){
      var r=svg.getBoundingClientRect();
      var x=(evt.clientX-r.left)/r.width*W;
      var i=Math.round((x-x0)/(x1-x0)*(data.length-1));
      return Math.max(0,Math.min(data.length-1,i));
    }
    function show(evt){
      var i=pt(evt), d=data[i], px=x0+(x1-x0)*i/(data.length-1);
      cross.setAttribute('x1',px);cross.setAttribute('x2',px);cross.style.opacity=1;
      var h='<div class="t">'+d.date+'</div>';
      series.forEach(function(s){
        var v=d[s.k]; if(v===null||v===undefined) return;
        h+='<div class="row'+(s.cls||'')+'"><i></i><span>'+s.name+'</span><b>'+(s.fmt? s.fmt(v):v)+'</b></div>';
      });
      tip.innerHTML=h; tip.style.opacity=1;
      var r=svg.getBoundingClientRect(), cr=chartEl.getBoundingClientRect();
      var left=px/W*r.width + (r.left-cr.left) + 14;
      var right = (cr.width - left);
      if(right < tip.offsetWidth+16){ left = px/W*r.width + (r.left-cr.left) - tip.offsetWidth - 14; }
      tip.style.left=left+'px';
      var fy=series.length? (data[i][series[0].k]||0):0;
      tip.style.top=Math.max(4, Math.min(cr.height-tip.offsetHeight-4, r.top-cr.top + 10));
    }
    svg.addEventListener('pointermove',show);
    svg.addEventListener('pointerleave',function(){tip.style.opacity=0;cross.style.opacity=0;});
  }
  document.querySelectorAll('.chart[data-k]').forEach(function(el){
    var data=window.__CHART__[el.getAttribute('data-k')];
    if(!data) return;
    var isDD=el.getAttribute('data-k')==='dd';
    attach(el,data, isDD
      ? [{k:'dd',name:'回撤',fmt:function(v){return (v*100).toFixed(1)+'%';}}]
      : [{k:'nav',name:'策略净值',fmt:function(v){return v.toFixed(3);}},
         {k:'bench',cls:'b',name:'沪深300',fmt:function(v){return v.toFixed(3);}}]);
  });
  // 表格视图开关
  document.querySelectorAll('[data-tbl]').forEach(function(b){
    b.addEventListener('click',function(){
      var t=document.getElementById(b.getAttribute('data-tbl'));
      var open=t.style.display!=='none'; t.style.display=open?'none':'block';
      b.textContent=open?'显示数据表':'收起数据表';
    });
  });
})();
"""


def svg_line(chart_id, rows, series, y_fmt, h=300, y0pad=0.06, baseline=None):
    """生成折线图 SVG 字符串。rows: [{date, k1:.., k2:..}]。"""
    W, H = 1000, h
    ml, mr, mt, mb = 52, 70, 14, 26
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    box = f' data-x0="{x0}" data-x1="{x1}" data-y0="{y0}" data-y1="{y1}"' 
    vals = []
    for r in rows:
        for s in series:
            v = r.get(s)
            if v is not None:
                vals.append(v)
    vmin, vmax = min(vals), max(vals)
    if baseline is not None:
        vmin = min(vmin, baseline)
        vmax = max(vmax, baseline)
    pad = (vmax - vmin) * y0pad or 0.01
    vmin, vmax = vmin - pad, vmax + pad
    n = len(rows)
    def X(i):
        return x0 + (x1 - x0) * i / max(1, n - 1)
    def Y(v):
        return y1 - (y1 - y0) * (v - vmin) / (vmax - vmin)
    # y 轴刻度
    ticks = 5
    ys = [vmin + (vmax - vmin) * k / ticks for k in range(ticks + 1)]
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="净值曲线"{box}>']
    for v in ys:
        y = Y(v)
        parts.append(f'<line class="gridline" x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="axis-text" x="{x0-10}" y="{y+4:.1f}" text-anchor="end">{y_fmt(v)}</text>')
    if baseline is not None:
        yb = Y(baseline)
        parts.append(f'<line x1="{x0}" x2="{x1}" y1="{yb:.1f}" y2="{yb:.1f}" '
                     f'stroke="var(--line-strong)" stroke-width="1"/>')
    # x 轴：每年 1 月第一个点
    seen = set()
    for i, r in enumerate(rows):
        y = r["date"][:4]
        if y not in seen and r["date"][5:7] <= "02":
            seen.add(y)
            parts.append(f'<text class="axis-text" x="{X(i):.1f}" y="{H-6}" text-anchor="middle">{y}</text>')
    colors = {"nav": "var(--series-1)", "bench": "var(--series-2)", "dd": "var(--series-1)"}
    for s in series:
        segs, cur = [], []
        for i, r in enumerate(rows):
            v = r.get(s)
            if v is None:
                if len(cur) > 1:
                    segs.append(cur)
                cur = []
            else:
                cur.append((X(i), Y(v)))
        if len(cur) > 1:
            segs.append(cur)
        for sg in segs:
            d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in sg)
            parts.append(f'<path class="series-line" d="{d}" stroke="{colors.get(s,"var(--series-1)")}"/>')
    # 末端直接标注（≤2 条线）
    last = rows[-1]
    for s in series:
        v = last.get(s)
        if v is None:
            continue
        parts.append(f'<text class="axis-text" x="{x1+8}" y="{Y(v)+4:.1f}" '
                     f'fill="{colors.get(s,"var(--series-1)")}" font-weight="600">{y_fmt(v)}</text>')
    parts.append(f'<line class="crosshair" x1="{x0}" x2="{x0}" y1="{y0}" y2="{y1}"/>')
    parts.append(f'<rect class="hit" x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}"/>')
    parts.append("</svg>")
    return "".join(parts)


def yuan(v):
    """金额（元）→ "1 亿元" / "1000 万元"。"""
    return f"{v / 1e8:g} 亿元" if v >= 1e8 else f"{v / 1e4:g} 万元"


def num(v, fmt, dash="—"):
    return dash if v is None else fmt(v)


def signed_pct(v, d=2):
    return num(v, lambda x: f"{x * 100:+.{d}f}%")


def plain_pct(v, d=1):
    return num(v, lambda x: f"{x * 100:.{d}f}%")


def tone(v):
    """正负着色只用文字颜色（good/critical ink），并保留 +/- 号，颜色不单独承载含义。"""
    if v is None:
        return ""
    return ' style="color:var(--good-ink)"' if v > 0 else (' style="color:var(--critical-ink)"' if v < 0 else "")


def section_today(daily, bt):
    rec = daily["recommendation"]
    risk_on = rec["mode"] == "risk"
    rows = []
    for h in sorted(rec["hold"], key=lambda x: -x["weight"]):
        badge = ('<span class="badge new">新买入</span>' if h["action"] == "buy"
                 else '<span class="badge keep">继续持有</span>')
        if not risk_on:
            badge = '<span class="badge def">防守</span>' + (badge if h["action"] == "buy" else "")
        rows.append(f"""<tr>
<td><code>{E(h['code'])}</code></td>
<td><span class="nm">{E(h['name'])}</span> {badge}</td>
<td class="r"><b>{h['weight'] * 100:.0f}%</b></td>
<td class="r hidesm">{num(h['rank'], str)}</td>
<td class="r hidesm">{num(h['close'], lambda x: f'{x:.3f}')}</td>
</tr>""")
    sells = "".join(f'<span class="badge sell">卖出 {E(s["name"])}</span> ' for s in rec["sells"]) \
        or '<span class="muted">无</span>'
    state_cls, state_txt = ("risk", "进攻") if risk_on else ("defense", "防守")
    gap = rec["hs300"] / rec["ma250"] - 1 if rec.get("ma250") else None
    desc = (f"沪深300 在年线上方，按模型「{E(rec['model'])}」持有排名靠前的 {len(rec['hold'])} 只 ETF。"
            if risk_on else "沪深300 在年线下方，模型排名照常计算，但仓位切换为防守组合：60% 国债 ETF + 40% 红利低波 ETF。")
    logged = "（今日推荐已写入台账，之后不再修改）" if rec.get("logged") is not None else ""
    return f"""
  <section class="card" id="today">
    <div class="card-head">
      <div><h2>今日推荐 · 下一交易日开盘执行</h2><p class="sub">{desc}</p></div>
      <div class="hint">信号日 {E(rec['signal_date'])} 收盘<br>沪深300 {rec['hs300']:.2f} · 年线 {num(rec.get('ma250'), lambda x: f'{x:.2f}')} · 偏离 {signed_pct(gap, 1)}</div>
    </div>
    <div class="regime">
      <div class="state {state_cls}"><span class="dot" style="background:{'var(--good)' if risk_on else 'var(--warning)'}"></span>{state_txt}</div>
      <div>
        <p>候选池 {rec['pool']} 只（近 20 日日均成交额 ≥ {yuan(bt['params']['min_amount'])}、上市满 {bt['params']['min_history']} 个交易日、同一指数只留成交额最大的一只）。{logged}</p>
        <p class="facts">卖出：{sells}</p>
      </div>
    </div>
    <p id="today-note" class="sub" style="margin:12px 0 0;display:none"></p>
    <div id="today-wrap" style="overflow-x:auto">
    </div>
    <noscript><div style="overflow-x:auto">
    <table style="margin-top:14px">
      <thead><tr><th>代码</th><th>名称</th><th class="r">目标权重</th><th class="r hidesm">模型排名</th><th class="r hidesm">信号日收盘</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div></noscript>
  </section>"""


def section_ranking(daily):
    rec = daily["recommendation"]
    rk = rec["ranking"][:15]
    keys = list(rk[0]["factors"]) if rk else []
    head = "".join(f'<th class="r">{E(rk[0]["factors"][k]["label"])}</th>' for k in keys)
    rows = []
    for r in rk:
        mark = ""
        if r["pick"] and rec["mode"] == "risk":
            mark = '<span class="badge new">入选</span>'
        elif r["pick"]:
            mark = '<span class="badge keep">进攻时入选</span>'
        fac = ""
        for k in keys:
            fx = r["factors"][k]
            v = fx["value"]
            vtxt = num(v, lambda x: f"{x * 100:+.1f}%" if k.startswith(("r", "dist", "dd")) else f"{x * 100:.2f}%")
            if fx["pct"] is None:
                fac += f'<td class="r">{vtxt}</td>'
            else:
                better = fx["pct"] if fx["w"] > 0 else 1 - fx["pct"]   # 按模型偏好的方向
                fac += (f'<td class="r">{vtxt}<div class="muted" style="font-size:11.5px">'
                        f'优于 {better * 100:.0f}% 的候选</div></td>')
        rows.append(f"""<tr>
<td class="r" style="width:30px;padding-right:14px">{r['rank']}</td>
<td><code>{E(r['code'])}</code></td>
<td><span class="nm">{E(r['name'])}</span> {mark}</td>
<td class="r"><b>{r['score']:+.3f}</b></td>
{fac}
<td class="r hidesm"{tone(r['r20'])}>{signed_pct(r['r20'], 1)}</td>
<td class="r hidesm">{r['amt_yi']:.2f} 亿</td>
</tr>""")
    w = daily["state"]["champion"]["weights"]
    wtxt = "、".join(f"{E(rk[0]['factors'][k]['label'])} {'+' if v > 0 else '−'}{abs(v):g}" for k, v in w.items()) if rk else ""
    return f"""
  <section class="card" id="rank">
    <div class="card-head"><div><h2>模型评分榜（前 15）</h2>
      <p class="sub">当前模型：{E(daily['state']['champion']['name'])}（{wtxt}，每项先在候选池内转为百分位再加权，分数做 {daily['state']['champion'].get('smooth', 0)} 日指数平滑）。"优于 x% 的候选"：按模型偏好的方向（距年线越高越好、波动越低越好），该 ETF 在当天候选池里的位置。</p></div></div>
    <div style="overflow-x:auto">
    <table>
      <thead><tr><th class="r" style="padding-right:14px">#</th><th>代码</th><th>名称</th><th class="r">评分</th>{head}<th class="r hidesm">20日涨跌</th><th class="r hidesm">日均成交额</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    <p class="sub" style="margin-top:10px">选样规则：从第 1 名往下取，跳过与已选 ETF 近 60 日收益相关系数 &gt; 0.9 的；已持有的 ETF 只要还在前 15 名就继续持有。</p>
  </section>"""


def acc_table(by, title_note):
    """准确度表：h=1/5/10 日。by[h] 含 top5 / pool / top5_up / top5_beat_med / days_top5_beat_pool / ic。"""
    rows = []
    for h in ("1", "5", "10"):
        x = by.get(h) or {}
        if not x or not x.get("n", x.get("days")):
            rows.append(f'<tr><td>{h} 日</td><td colspan="6" class="muted">样本不足，等待兑现</td></tr>')
            continue
        n = x.get("n", x.get("days"))
        ex = (x["top5"] - x["pool"]) if x.get("top5") is not None and x.get("pool") is not None else None
        ic = f'{x["ic"]:+.3f}' if x.get("ic") is not None else "—"
        rows.append(f"""<tr><td>{h} 日</td><td class="r">{n}</td>
<td class="r"><b>{plain_pct(x.get('top5_up'))}</b></td>
<td class="r"><b>{plain_pct(x.get('top5_beat_med'))}</b></td>
<td class="r">{plain_pct(x.get('days_top5_beat_pool'))}</td>
<td class="r"{tone(ex)}>{signed_pct(ex)}</td>
<td class="r hidesm">{ic}</td></tr>""")
    return f"""<div style="overflow-x:auto"><table>
<thead><tr><th>持有期</th><th class="r">样本（天）</th><th class="r">前 5 名上涨比例</th><th class="r">前 5 名跑赢候选池中位数</th>
<th class="r">前 5 均值跑赢池均值的天数</th><th class="r">前 5 − 池均（每期）</th><th class="r hidesm">Rank IC</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div><p class="sub" style="margin-top:8px">{title_note}</p>"""


def section_live(daily):
    live = daily["live"]
    n = live["n"]
    first = live["first"]
    rows = []
    for r in live["recent"][:15]:
        cells = ""
        for h in ("1", "5", "10"):
            x = r["h"].get(h)
            if not x:
                cells += '<td class="r muted">待兑现</td>'
                continue
            ex = (x["top5"] - x["pool"]) if x.get("top5") is not None and x.get("pool") is not None else None
            cells += f'<td class="r"{tone(ex)}>{signed_pct(x.get("top5"))}<div class="muted" style="font-size:11.5px">超额 {signed_pct(ex)}</div></td>'
        mode = '<span class="badge def">防守</span>' if r["mode"] == "defense" else '<span class="badge keep">进攻</span>'
        rows.append(f'<tr><td style="white-space:nowrap"><code>{r["signal_date"]}</code></td><td>{mode}</td>{cells}</tr>')
    body = "".join(rows) or '<tr><td colspan="5" class="muted">台账刚建立，第一条推荐要等 1 个交易日后才能兑现。</td></tr>'
    return f"""
  <section class="card" id="live">
    <div class="card-head"><div><h2>实盘推荐记录（样本外）</h2>
      <p class="sub">从 {E(first or '—')} 起，每个交易日收盘后把当天的推荐写进 <code>track/predictions.jsonl</code>，写入后不再修改；到期后用真实开盘价自动计算收益。这一节的数字没有任何事后调整，是判断模型是否有效的最终依据。</p></div>
      <div class="hint">已记录 {n} 个交易日</div></div>
    {acc_table(live['summary'], '口径：信号日次日开盘买入，持有 1/5/10 个交易日后开盘卖出；"前 5 名"是模型排名前 5（不论当天是否防守），用于检验排序本身的准确度。')}
    <h3 class="sec">最近 15 个信号日</h3>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>信号日</th><th>模式</th><th class="r">前 5 名 1 日</th><th class="r">5 日</th><th class="r">10 日</th></tr></thead>
      <tbody>{body}</tbody></table></div>
  </section>"""


def beat_range(sim):
    """留出期前 5 名跑赢候选池中位数的比例范围（1/5/10 日），页面文字统一引用这里，不写死数字。"""
    v = [x["top5_beat_med"] for x in sim["by"]["holdout"].values() if x.get("top5_beat_med") is not None]
    return f"{min(v) * 100:.0f}–{max(v) * 100:.0f}%" if v else "—"


def section_open(daily):
    """开盘复核：今日结果由浏览器读取 open.json（09:26 推送，不需要重建页面），历史对比由 CI 每日计算。"""
    o = daily.get("open_review") or {"n": 0, "rows": [], "summary": {}}
    rows = []
    for r in o["rows"]:
        cells = ""
        for h in ("1", "5", "10"):
            x = r["h"].get(h)
            if not x or None in x.values():
                cells += '<td class="r muted">待兑现</td>'
                continue
            d = x["open"] - x["close"]
            cells += (f'<td class="r">{signed_pct(x["open"])}<div class="muted" style="font-size:11.5px">'
                      f'收盘版 {signed_pct(x["close"])}，差 <span{tone(d)}>{signed_pct(d)}</span></div></td>')
        rows.append(f'<tr><td style="white-space:nowrap"><code>{r["trade_date"]}</code></td><td>{E(r["note"])}</td>{cells}</tr>')
    body = "".join(rows) or '<tr><td colspan="5" class="muted">还没有开盘复核记录。第一次复核在下一个交易日 09:26 之后。</td></tr>'
    s5 = o["summary"].get("5") or {}
    sm = (f'已复核 {o["n"]} 个交易日，其中 {o.get("n_changed", 0)} 天调整了持仓。'
          + (f'调整过的日子里，开盘复核版持有 5 日比收盘版平均 {signed_pct(s5["diff_changed"])}（{s5["n_changed"]} 天已兑现）。'
             if s5.get("diff_changed") is not None else "调整日的收益对比要等兑现后才有。"))
    return f"""
  <section class="card" id="open">
    <div class="card-head"><div><h2>开盘复核 · 09:26 集合竞价后</h2>
      <p class="sub">收盘给出的推荐里，需要新买入的 ETF 如果集合竞价高开超过 2%，就不追，换成下一名；继续持有和卖出不变；防守模式不调整。回测（日均成交额 ≥ 1 亿的 ETF）里这条规则在开发期几乎没触发，留出期略有帮助（日收益差 t=+0.67，不显著）。"低开优先买"那种更激进的调整在开发期扣掉额外滑点后变差，没有采用。</p></div></div>
    <div id="open-today" data-signal="{E(daily['recommendation']['signal_date'])}" data-mode="{E(daily['recommendation']['mode'])}"><p class="muted">正在读取今日开盘复核…</p></div>
    <p class="sub" style="margin-top:12px">{sm}</p>
    <div style="overflow-x:auto"><table style="margin-top:8px">
      <thead><tr><th>交易日</th><th>复核结果</th><th class="r">复核版 1 日</th><th class="r">5 日</th><th class="r">10 日</th></tr></thead>
      <tbody>{body}</tbody></table></div>
  </section>"""


OPEN_JS = r"""
(function(){
  var box=document.getElementById('open-today'); if(!box) return;
  var sig=box.getAttribute('data-signal');
  var mode=box.getAttribute('data-mode');
  function el(t,c,txt){var e=document.createElement(t); if(c) e.className=c; if(txt!=null) e.textContent=txt; return e;}
  function table(head, rows){
    var t=el('table'); t.style.marginTop='14px'; var th=el('thead'), tr=el('tr');
    head.forEach(function(h){ tr.appendChild(el('th',h[1]?'r':null,h[0])); }); th.appendChild(tr); t.appendChild(th);
    var tb=el('tbody'); rows.forEach(function(r){ var x=el('tr'); r.forEach(function(c,i){ x.appendChild(el('td',i?((r.r||{})[i]?'r':null):null,c)); }); tb.appendChild(x); });
    t.appendChild(tb); return t;
  }
  fetch('open.json?t='+Date.now()).then(function(r){ if(!r.ok) throw 0; return r.json(); }).then(function(o){
    box.textContent='';
    var mine = o.signal_date===sig && o.mode===mode;
    if(mine){
      var p=el('p'); p.appendChild(el('b',null,o.trade_date+' '+o.quote_time+' 复核：'+o.note+'。'));
      p.appendChild(document.createTextNode(' 规则：'+o.rule)); box.appendChild(p);
      var t=table([['代码',0],['名称',0],['权重',1],['竞价涨跌',1],['收盘排名',1]], o.hold.map(function(h){
        return [h.code, h.name, Math.round(h.weight*100)+'%',
                h.gap==null?'—':((h.gap>=0?'+':'')+(h.gap*100).toFixed(2)+'%'), h.rank==null?'—':String(h.rank)];
      }));
      box.appendChild(t);
      if(o.skipped && o.skipped.length){ box.appendChild(el('p','facts','跳过：'+o.skipped.map(function(s){return s.name+'（'+s.why+'）';}).join('、'))); }
      // 顶部持仓表切换为复核后的持仓
      var wrap=document.getElementById('today-wrap'), note=document.getElementById('today-note');
      if(wrap){
        wrap.textContent='';
        var rows=o.hold.map(function(h){
          var badge=el('span','badge '+(h.changed?'new':'keep'), h.changed?'开盘补位':'复核后持有');
          var nm=el('span','nm',h.name); var cell=el('td'); cell.appendChild(nm); cell.appendChild(document.createTextNode(' ')); cell.appendChild(badge);
          var r=el('tr');
          var c1=el('td'); c1.appendChild(el('code',null,h.code)); r.appendChild(c1); r.appendChild(cell);
          r.appendChild(el('td','r',Math.round(h.weight*100)+'%'));
          r.appendChild(el('td','r hidesm',h.rank==null?'—':String(h.rank)));
          r.appendChild(el('td','r hidesm',h.gap==null?'—':((h.gap*100).toFixed(2)+'%')));
          return r;
        });
        var t2=el('table'); t2.style.marginTop='14px';
        var th=el('thead'), tr=el('tr');
        [['代码',0],['名称',0],['目标权重',1],['模型排名',1],['竞价涨跌',1]].forEach(function(c){ tr.appendChild(el('th',c[1]?'r hidesm':'',c[0])); });
        th.appendChild(tr); t2.appendChild(th); var tb=el('tbody'); rows.forEach(function(r){ tb.appendChild(r); }); t2.appendChild(tb);
        wrap.appendChild(t2);
        if(note){ note.style.display=''; note.textContent='已按 '+o.reviewed_at.slice(11,16)+' 开盘复核更新持仓：'+o.note+'。上方汇总（卖出、候选池）仍为收盘信号口径。'; }
      }
    } else {
      box.appendChild(el('p','muted','今日（'+sig+' 收盘信号的下一个交易日）开盘复核尚未运行，最近一次是 '+o.trade_date+'。'));
    }
  }).catch(function(){ box.textContent=''; box.appendChild(el('p','muted','还没有开盘复核记录。')); });
})();
"""


def section_accuracy(daily):
    sim = daily["simulated"]
    a, z = sim["segments"]["dev"]
    h0 = sim["segments"]["holdout"][0]
    return f"""
  <section class="card" id="accuracy">
    <div class="card-head"><div><h2>历史准确度（模拟逐日推荐）</h2>
      <p class="sub">把当前模型放回历史，每天都按同样规则出一次推荐，统计之后 1/5/10 个交易日的表现（只计日均成交额 ≥ 1 亿的 ETF）。开发期（{a[:4]}–{int(h0[:4]) - 1}）用来选模型；留出期（{h0[:4]} 起）选模型时没有看过，更接近真实水平。</p></div></div>
    <h3 class="sec" style="margin-top:0">留出期 {h0[:4]} 起（未参与模型选择）</h3>
    {acc_table(sim['by']['holdout'], '')}
    <details><summary>开发期 {a[:4]}–{int(h0[:4]) - 1}（参与了模型选择，数字偏乐观）</summary>
    {acc_table(sim['by']['dev'], '')}
    </details>
    <ul class="notes">
      <li><b>怎么读</b>：随机挑 5 只，"跑赢候选池中位数"的期望是 50%；模型在留出期是 {beat_range(sim)}，<b>与随机差别很小</b>。候选池限定为日均成交额 ≥ 1 亿的 ETF 后，价量因子的排序能力很弱；单只 ETF 一两天的涨跌主要由市场整体决定。</li>
      <li><b>Rank IC</b>：模型分数与未来收益排名的相关系数，0 表示没有预测力。量化选股里 0.03–0.05 已属于可用水平。</li>
    </ul>
  </section>"""


def section_validation(daily):
    val, state = daily["validation"], daily["state"]
    champ = state["champion"]["name"]
    rows = []
    for nm, r in sorted(val["models"].items(), key=lambda kv: (kv[1]["role"] != "champion", -kv[1]["ic_mean"])):
        role = '<span class="badge new">当前模型</span>' if r["role"] == "champion" else '<span class="badge keep">挑战者</span>'
        t = r.get("t_vs_champ")
        rows.append(f"""<tr><td><span class="nm">{E(nm)}</span> {role}</td>
<td class="r"><b>{r['ic_mean']:+.3f}</b></td><td class="r">{plain_pct(r['ic_pos'], 0)}</td>
<td class="r"{tone(r['top5_minus_pool'])}>{signed_pct(r['top5_minus_pool'])}</td>
<td class="r">{plain_pct(r['top5_beat_med'])}</td>
<td class="r hidesm">{'—' if t is None else f'{t:+.2f}'}</td></tr>""")
    hist = []
    for hst in reversed(state["history"][-8:]):
        hist.append(f'<li><code>{E(hst["date"] or "建站")}</code> {E(hst.get("reason", ""))}'
                    + (f'（{E(hst["from"])} → {E(hst["to"])}）' if hst.get("event") == "promote" else "") + "</li>")
    dec = val.get("decision")
    today = (f'<p class="banner" style="margin:10px 0 0">今日自动晋级：{E(dec["from"])} → {E(dec["to"])}。{E(dec["reason"])}</p>'
             if dec else '<p class="sub" style="margin-top:10px">今日检查结果：没有挑战者满足晋级条件，模型保持不变。</p>')
    return f"""
  <section class="card" id="validation">
    <div class="card-head"><div><h2>每日自动验证与模型优化</h2>
      <p class="sub">每天收盘后，用最近 {val['window'][0]} ~ {val['window'][1]} 已经兑现的数据，重新比较当前模型「{E(champ)}」和 {len(val['models']) - 1} 个挑战者的 {val['horizon']} 日预测力。{E(val['rule'])}。门槛定得高，是为了避免追着短期噪声换模型。</p></div></div>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>模型</th><th class="r">Rank IC 均值</th><th class="r">IC 为正的天数</th><th class="r">前 5 − 池均</th><th class="r">前 5 跑赢中位数</th><th class="r hidesm">相对当前模型 t 值</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table></div>
    {today}
    <h3 class="sec">模型变更记录</h3>
    <ul class="notes">{''.join(hist)}</ul>
  </section>"""


def section_backtest(bt):
    st = bt["stats"]
    per = "".join(f"""<tr><td>{E(p['label'])}</td>
<td class="r"><b>{p['cagr'] * 100:+.1f}%</b></td><td class="r">{p['mdd'] * 100:.1f}%</td>
<td class="r">{p['sharpe']:.2f}</td><td class="r hidesm">{p['node_win'] * 100:.0f}%</td>
<td class="r hidesm">{p['turnover']:.1f}</td>
<td class="r muted">{p['no_defense_cagr'] * 100:+.1f}% / {p['no_defense_mdd'] * 100:.1f}%</td>
<td class="r muted">{p['bench_cagr'] * 100:+.1f}%</td></tr>""" for p in bt["periods"])
    yearly = "".join(
        f'<tr><td>{y}</td><td class="r"{tone(v)}>{v * 100:+.1f}%</td><td class="r muted">{num(bt["bench_yearly"].get(y), lambda x: f"{x * 100:+.1f}%")}</td></tr>'
        for y, v in sorted(bt["yearly"].items()))
    nav_svg = svg_line("nav", bt["curve"], ["nav", "bench"], lambda v: f"{v:.2f}", h=300, baseline=1.0)
    dd_svg = svg_line("dd", bt["dd"], ["dd"], lambda v: f"{v * 100:.0f}%", h=150, y0pad=0.03, baseline=0)

    def chip(label, value, sub):
        return f'<div class="kpi"><div class="l">{label}</div><div class="v">{value}</div><div class="d">{sub}</div></div>'

    ho = next(p for p in bt["periods"] if p["label"].startswith("留出"))
    return f"""
  <section class="card" id="backtest">
    <div class="card-head"><div><h2>组合回测（当前模型）</h2>
      <p class="sub">按推荐实际操作的结果：收盘出信号、次日开盘成交、单边成本 {bt['params']['cost'] * 100:.1f}%、跌破年线切防守。两条线都从 1.0 起算。</p></div></div>
    <div class="kpis" style="margin:0 0 18px">
      {chip(f"留出期年化（{bt['params']['holdout_start'][:4]} 起）", f"{ho['cagr'] * 100:.1f}%", f"沪深300 同期 {ho['bench_cagr'] * 100:+.1f}%")}
      {chip("留出期最大回撤", f"{ho['mdd'] * 100:.1f}%", f"沪深300 {ho['bench_mdd'] * 100:.1f}%")}
      {chip("完整区间年化", f"{st['cagr'] * 100:.1f}%", f"{bt['start'][:4]}–{bt['end'][:4]}，回撤 {st['mdd'] * 100:.1f}%")}
      {chip("年单边换手", f"{st['turnover']:.1f} 倍", f"已扣 {bt['params']['cost'] * 100:.1f}% 单边成本")}
    </div>
    <div class="legend"><span class="key"><i></i>策略</span><span class="key b"><i></i>沪深300</span></div>
    <h3 class="sec" style="margin-top:0">净值</h3>
    <div class="chart nav-chart" data-k="nav">{nav_svg}<div class="tooltip"></div></div>
    <h3 class="sec" style="margin-top:22px">回撤</h3>
    <div class="chart dd-chart" data-k="dd">{dd_svg}<div class="tooltip"></div></div>
    <div style="overflow-x:auto;margin-top:16px"><table>
      <thead><tr><th>区间</th><th class="r">年化</th><th class="r">最大回撤</th><th class="r">夏普</th><th class="r hidesm">5日胜率</th><th class="r hidesm">年换手</th><th class="r">不用防守（年化 / 回撤）</th><th class="r">沪深300</th></tr></thead>
      <tbody>{per}</tbody></table></div>
    <details><summary>数据表：分年收益</summary>
      <table style="margin-top:10px"><thead><tr><th>年份</th><th class="r">策略</th><th class="r">沪深300</th></tr></thead><tbody>{yearly}</tbody></table>
    </details>
  </section>"""


def defense_note(bt):
    """防守开关的作用，按回测数字自动生成，不写死结论。"""
    out = []
    for per in bt["periods"][1:]:
        out.append(f"{per['label']}：有防守 年化 {per['cagr'] * 100:+.1f}% / 回撤 {per['mdd'] * 100:.1f}%，"
                   f"不防守 {per['no_defense_cagr'] * 100:+.1f}% / {per['no_defense_mdd'] * 100:.1f}%")
    return "；".join(out) + "。"


def section_method(bt):
    p = bt["params"]
    return f"""
  <section class="card" id="method">
    <div class="cols">
      <div>
        <h2>方法</h2>
        <ul class="notes">
          <li><b>数据</b>：新浪财经 ETF 日线（份额折算处按价格跳变修补）与沪深300 日线，每个交易日收盘后自动更新。</li>
          <li><b>候选池</b>：只做 A 股股票型 ETF（剔除货币、债券、商品、跨境）；近 20 日日均成交额 ≥ {yuan(p['min_amount'])}；上市满 {p['min_history']} 个交易日；同一指数（名称中"ETF"之前相同）每天只留成交额最大的一只。全部按当天能看到的数据判断，不用未来信息。</li>
          <li><b>因子</b>：14 个价量特征（各周期涨跌、距均线、距高点、波动、成交额）。每天在候选池内转成百分位，模型只比较"同一天谁更好"，不预测大盘涨跌。</li>
          <li><b>模型选择</b>：{p['dev_start'][:4]}–{int(p['holdout_start'][:4]) - 1} 为开发期，比较单因子 IC 与 8 个组合方案后选定当前模型；{p['holdout_start'][:4]} 起为留出期，只用来检验，选模型时没有看过。（1 亿门槛下 2019 年以前每天只有 3–9 只候选，无法检验排序，所以开发期从 2020 年开始。）</li>
          <li><b>开盘复核</b>：每个交易日 09:26 集合竞价后，对需要新买入的 ETF 检查开盘价，高开超过 2% 的不追、由下一名补位；继续持有与卖出不变。与收盘版分别记账、到期对比。</li>
          <li><b>每日验证</b>：当前模型和挑战者每天都记录推荐，用最近约两年的已兑现数据比较 10 日 Rank IC，挑战者显著更好（t ≥ 2.5）才替换；变更自动记录在页面上。</li>
          <li><b>成交与防守</b>：收盘出信号、下一交易日开盘调仓，单边成本 {p['cost'] * 100:.1f}%；沪深300 低于 {p['defense_ma']} 日均线时换为 {p['defense_bond_w'] * 100:.0f}% 国债 ETF + {100 - p['defense_bond_w'] * 100:.0f}% 红利低波 ETF。</li>
        </ul>
      </div>
      <div>
        <h2>局限</h2>
        <ul class="notes">
          <li><b>选股能力弱</b>：在流动性好的 ETF 里，前 5 名跑赢候选池中位数的比例接近 50%（见"历史准确度"）。回测收益的大头来自持有站上年线、低波动的品种，以及熊市里的年线防守，而不是精确选中涨得最多的那只。</li>
          <li><b>风格偏防御</b>：模型偏好红利、银行、低波品种。科技、成长领涨的反弹日会明显跑输，例如 2026-11-23 候选池平均涨 1.4%，推荐组合跌 0.4%。</li>
          <li><b>防守开关</b>：{defense_note(bt)}</li>
          <li><b>幸存者偏差</b>：候选池来自今天仍能在新浪取到行情的 ETF，已清盘的没有进入历史。</li>
          <li><b>实盘记录才刚开始</b>：页面上的"历史准确度"是模拟，"实盘推荐记录"从台账建立当天起累计，样本足够之前请以前者为参考、以后者为准。</li>
          <li><b>未模拟冲击成本</b>，不处理涨跌停与停牌排队。</li>
        </ul>
        <p class="sub" style="margin-top:14px">代码、推荐台账与模型变更记录都在 GitHub：<a href="https://github.com/jingyi22/etf-rotation" style="color:var(--series-1)">jingyi22/etf-rotation</a></p>
      </div>
    </div>
  </section>"""


def main():
    daily = json.load(open(os.path.join(DATA_DIR, "daily.json"), encoding="utf-8"))
    bt = json.load(open(os.path.join(DATA_DIR, "backtest.json"), encoding="utf-8"))
    rec = daily["recommendation"]
    gen = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    nav = '<nav class="toc">' + "".join(
        f'<a href="#{a}">{b}</a>' for a, b in (("today", "今日推荐"), ("open", "开盘复核"), ("rank", "评分榜"), ("live", "实盘记录"),
                                                ("accuracy", "历史准确度"), ("validation", "自动验证"),
                                                ("backtest", "组合回测"), ("method", "方法与局限"))) + "</nav>"
    chart_data = json.dumps({"nav": bt["curve"], "dd": bt["dd"]}, ensure_ascii=False)
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF 轮动 · 每日推荐与自动验证</title>
<meta name="description" content="每个交易日收盘后按模型给出下一交易日的 ETF 推荐，推荐写入台账后自动兑现评分，每日自动验证与模型晋级。历史回测与统计，不构成投资建议。">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div>
      <h1>ETF 轮动 · 每日推荐</h1>
      <p class="sub">收盘后按模型给出下一交易日的持仓，09:26 集合竞价后再做一次开盘复核；推荐写入台账、到期自动验证；每日比较挑战者，显著更好才替换模型</p>
    </div>
    <div style="text-align:right">
      <div class="updated">信号日 {E(rec['signal_date'])} · 页面生成 {E(gen)}（北京时间）</div>
      <button class="theme-btn" id="theme" style="margin-top:6px">☾ 深色</button>
    </div>
  </header>
  {nav}
  <div class="banner">
    <div><b>这是模型推荐与统计记录，不是投资建议。</b>
    在流动性好的 ETF 里模型几乎没有选股优势，主要作用是持有趋势向上、低波动的品种并在熊市防守；任何一天、一周都可能亏钱。过去的表现不代表未来，本站不承诺任何收益。</div>
  </div>
  {section_today(daily, bt)}
  {section_open(daily)}
  {section_ranking(daily)}
  {section_live(daily)}
  {section_accuracy(daily)}
  {section_validation(daily)}
  {section_backtest(bt)}
  {section_method(bt)}
  <footer>
    <b>免责声明</b>：本站内容是公开行情数据上的模型输出、历史回测与统计，不构成证券投资咨询或买卖建议；ETF 交易有风险，历史收益不代表未来表现。
    数据来自新浪财经公开行情，可能存在缺口或错误，以交易所与基金公告为准。
  </footer>
</div>
<script>window.__CHART__={chart_data};</script>
<script>{JS}</script>
<script>{OPEN_JS}</script>
</body>
</html>
"""
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(os.path.join(DOCS_DIR, "today.json"), "w", encoding="utf-8") as fh:
        json.dump({k: rec[k] for k in ("signal_date", "exec", "model", "mode", "hold", "sells", "ranking", "open_ctx")},
                  fh, ensure_ascii=False, indent=1)
    sig = os.path.join(DOCS_DIR, "signals.json")
    if os.path.exists(sig):
        os.remove(sig)
    print(f"写入 docs/index.html（{len(page) / 1024:.0f} KB）与 docs/today.json")


if __name__ == "__main__":
    main()
