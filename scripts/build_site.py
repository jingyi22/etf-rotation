"""把 data/signals.json + data/backtest.json 渲染成 docs/index.html（单页、无外部依赖）。"""
import html
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR, DOCS_DIR

E = html.escape


def pct(x, d=1, sign=False):
    if x is None:
        return "—"
    s = f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"
    return s


def fmt_date(s):
    return s


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


def main():
    sig = json.load(open(os.path.join(DATA_DIR, "signals.json"), encoding="utf-8"))
    bt = json.load(open(os.path.join(DATA_DIR, "backtest.json"), encoding="utf-8"))
    st, bench = bt["stats"], bt["bench"]
    reg = sig["regime"]
    risk_on = reg["risk_on"]

    # ---- 当前持仓表 ----
    def cells(v, fmt):
        return fmt(v) if v is not None else "—"

    rows_html = []
    for h in sig["holdings"]:
        badge = '<span class="badge def">防守</span>' if not risk_on else (
            '<span class="badge new">新买</span>' if h["is_new"] else '<span class="badge keep">持有</span>')
        rows_html.append(f"""<tr>
<td><code>{E(h['code'])}</code></td>
<td><span class="nm">{E(h['name'])}</span>{badge}</td>
<td class="r">{h['weight']*100:.0f}%</td>
<td class="r hidesm">{h['score'] if h['score'] is not None else '—'}</td>
<td class="r hidesm">{h['rank'] if h['rank'] else '—'}</td>
<td class="r">{cells(h['dist252'], lambda v: f"{v*100:+.1f}%")}</td>
<td class="r hidesm">{cells(h['amt_yi'], lambda v: f"{v:.2f} 亿")}</td>
</tr>""")
    hold_table = "".join(rows_html)

    # ---- 打分榜 ----
    top_rows = []
    for k, t in enumerate(sig["top"], 1):
        mark = '<span class="badge keep">持有</span>' if t["held"] else ""
        top_rows.append(f"""<tr>
<td class="r" style="width:36px">{k}</td>
<td><code>{E(t['code'])}</code></td>
<td><span class="nm">{E(t['name'])}</span>{mark}</td>
<td class="r"><b>{t['score']:+.2f}</b></td>
<td class="r">{cells(t['dist252'], lambda v: f"{v*100:+.1f}%")}</td>
<td class="r">{cells(t['vol20'], lambda v: f"{v*100:.1f}%")}</td>
<td class="r hidesm">{cells(t['amt_yi'], lambda v: f"{v:.2f} 亿")}</td>
</tr>""")
    top_table = "".join(top_rows)

    # ---- 调仓记录 ----
    rec_html = []
    for r in sig["recent"]:
        stt = '<span class="badge def">转防守</span>' if r["switch"] and r["state"] == "defense" else (
            '<span class="badge buy">转进攻</span>' if r["switch"] else "")
        buys = " ".join(f'<span class="badge buy">买 {E(h["name"])}</span>' for h in r["buy"]) or '<span class="muted">—</span>'
        sells = " ".join(f'<span class="badge sell">卖 {E(h["name"])}</span>' for h in r["sell"]) or '<span class="muted">—</span>'
        rec_html.append(f'<tr><td style="white-space:nowrap"><code>{r["signal_date"]}</code>'
                        f'<div class="muted" style="font-size:12px">收盘信号</div></td>'
                        f'<td>{stt}{buys}</td><td class="hidesm">{sells}</td></tr>')
    rec_table = "".join(rec_html) or '<tr><td colspan="3" class="muted">近一年没有调仓</td></tr>'

    # ---- 分年表 ----
    yearly_rows = []
    for y in sorted(bt["yearly"]):
        a = bt["yearly"][y]
        b = bt["bench_yearly"].get(y)
        cls = "var(--good-ink)" if a >= 0 else "var(--critical-ink)"
        bcell = f"{b*100:+.1f}%" if b is not None else "—"
        yearly_rows.append(f'<tr><td>{y}</td><td class="r" style="color:{cls}">{a*100:+.1f}%</td>'
                           f'<td class="r muted">{bcell}</td></tr>')
    yearly_table = "".join(yearly_rows)

    # ---- 候选池数量折线图 ----
    cand_svg = ""
    cands = bt.get("candidates_per_chunk") or []
    if len(cands) > 4:
        W, H = 1000, 160
        ml, mr, mt, mb = 44, 20, 10, 22
        x0, x1, y0, y1 = ml, W - mr, mt, H - mb
        vmax = max(c["n"] for c in cands) * 1.15 or 1
        def X(i):
            return x0 + (x1 - x0) * i / max(1, len(cands) - 1)
        def Y(v):
            return y1 - (y1 - y0) * v / vmax
        p2 = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="候选池数量随时间">']
        for k in range(5):
            v = vmax * k / 4
            p2.append(f'<line class="gridline" x1="{x0}" x2="{x1}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>')
            p2.append(f'<text class="axis-text" x="{x0-8}" y="{Y(v)+4:.1f}" text-anchor="end">{v:.0f}</text>')
        d = "M" + " L".join(f"{X(i):.1f},{Y(c['n']):.1f}" for i, c in enumerate(cands))
        p2.append(f'<path class="series-line" d="{d}" stroke="var(--series-1)"/>')
        seen = set()
        for i, c in enumerate(cands):
            y = c["date"][:4]
            if y not in seen:
                seen.add(y)
                p2.append(f'<text class="axis-text" x="{X(i):.1f}" y="{H-6}" text-anchor="middle">{y}</text>')
        p2.append(f'<text class="axis-text" x="{x1+4}" y="{Y(cands[-1]["n"])+4:.1f}" fill="var(--series-1)" font-weight="600">{cands[-1]["n"]}</text>')
        p2.append("</svg>")
        cand_svg = ('<h3 class="sec" style="margin-top:20px">同一时刻符合条件的候选 ETF 数量（每半年一个点）</h3>'
                    '<div class="chart cand-chart">' + "".join(p2) + '</div>')

    # ---- 分区间表 ----
    per_rows = []
    for p in bt["periods"]:
        per_rows.append(f"""<tr><td>{E(p['label'])}</td>
<td class="r"><b>{p['cagr']*100:+.1f}%</b></td><td class="r">{p['mdd']*100:.1f}%</td>
<td class="r">{p['sharpe']:.2f}</td>
<td class="r muted">{p['no_defense_cagr']*100:+.1f}% / {p['no_defense_mdd']*100:.1f}%</td>
<td class="r muted">{p['bench_cagr']*100:+.1f}%</td></tr>""")
    per_table = "".join(per_rows)

    # ---- 图 ----
    curve = bt["curve"]
    nav_svg = svg_line("nav", curve, ["nav", "bench"], lambda v: f"{v:.2f}", h=300, baseline=1.0)
    dd_svg = svg_line("dd", bt["dd"], ["dd"], lambda v: f"{v*100:.0f}%", h=150, y0pad=0.03, baseline=0)
    chart_data = json.dumps({"nav": curve, "dd": bt["dd"]}, ensure_ascii=False)

    # ---- 分年柱状图（策略 vs 300） ----
    yr_svg = yearly_bars(bt)

    state_cls = "risk" if risk_on else "defense"
    state_txt = "进攻" if risk_on else "防守"
    state_desc = ("沪深300 位于年线上方，按评分持有 5 只 ETF。"
                  if risk_on else "沪深300 位于年线下方，转为防守组合：国债 ETF + 红利低波 ETF。")
    ma_txt = f"{reg['ma250']:.2f}" if reg["ma250"] else "—"
    gap = reg["pct_from_ma"]
    gap_txt = f"{gap*100:+.1f}%" if gap is not None else "—"

    def chip(label, value, sub):
        return f'<div class="kpi"><div class="l">{label}</div><div class="v">{value}</div><div class="d">{sub}</div></div>'

    gen = sig["generated_at"].replace("T", " ")

    page = f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF 轮动参考 · 低波趋势 + 年线防守</title>
<meta name="description" content="以公开数据回测的 ETF 日频轮动参考：低波与趋势评分、次日开盘调仓、年线防守。历史回测，非投资建议。">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div>
      <h1>ETF 轮动参考</h1>
      <p class="sub">低波 + 趋势评分选 ETF，沪深300 跌破年线切国债/红利防守 · 收盘出信号、次日开盘调仓</p>
    </div>
    <div style="text-align:right">
      <div class="updated">信号日期 {E(sig['asof'])} · 生成 {E(gen)}</div>
      <button class="theme-btn" id="theme" style="margin-top:6px">☾ 深色</button>
    </div>
  </header>

  <div class="banner">
    <div><b>这是历史回测，不是投资建议。</b>
    回测含幸存者偏差与参数选择偏差：候选池是"今天还在交易"的 ETF，参数参考了同一段历史。
    过去的表现不能预测未来，也不承诺任何收益。</div>
  </div>

  <section class="card">
    <div class="card-head">
      <div><h2>今日状态</h2><p class="sub">{E(state_desc)}</p></div>
      <div class="hint">沪深300 {reg['hs300']:.2f} · 年线 {ma_txt}<br>偏离年线 {gap_txt}</div>
    </div>
    <div class="regime">
      <div class="state {state_cls}"><span class="dot" style="background:{'var(--good)' if risk_on else 'var(--warning)'}"></span>{state_txt}</div>
      <div>
        <p><b>下一交易日开盘</b>按下表调仓；表中"新买"为相对上一交易日信号的变动。</p>
        <p class="facts">候选池 {sig['universe_size']} 只（近 20 日日均成交额 ≥ {bt['params']['min_amount_cap']/1e8:.1f} 亿、上市 ≥ 60 个交易日、已按同指数去重）</p>
      </div>
    </div>
    <div style="overflow-x:auto">
    <table class="stat" style="margin-top:16px">
      <thead><tr><th>代码</th><th>名称</th><th class="r">权重</th><th class="r hidesm">评分</th><th class="r hidesm">排名</th><th class="r">距年线</th><th class="r hidesm">日均成交额</th></tr></thead>
      <tbody>{hold_table}</tbody>
    </table></div>
    <div class="kpis">
      {chip("回测年化（2015 起）", pct(st['cagr']), f"沪深300 同期 {pct(bench['cagr'])}")}
      {chip("最大回撤", pct(st['mdd']), f"沪深300 {pct(bench['mdd'])}")}
      {chip("夏普（无风险 1.5%）", f"{st['sharpe']:.2f}", f"波动 {pct(st['vol'])}")}
      {chip("年单边换手", f"{st['turnover']:.1f} 倍", f"已扣 {bt['params']['cost']*100:.1f}% 单边成本")}
    </div>
  </section>

  <section class="card">
    <div class="card-head"><div><h2>净值与回撤</h2><p class="sub">扣费后，收盘信号、次日开盘成交；两条线都从 1.0 起算</p></div></div>
    <div class="legend"><span class="key"><i></i>策略</span><span class="key b"><i></i>沪深300</span></div>
    <h3 class="sec" style="margin-top:0">净值</h3>
    <div class="chart nav-chart" data-k="nav">{nav_svg}<div class="tooltip"></div></div>
    <h3 class="sec" style="margin-top:22px">回撤</h3>
    <div class="chart dd-chart" data-k="dd">{dd_svg}<div class="tooltip"></div></div>
    <details><summary>数据表：分年收益</summary>
      <table style="margin-top:10px"><thead><tr><th>年份</th><th class="r">策略</th><th class="r">沪深300</th></tr></thead>
      <tbody>{yearly_table}</tbody></table>
    </details>
  </section>

  <section class="card">
    <div class="card-head"><div><h2>稳健性：换一个起点还成立吗</h2>
      <p class="sub">同一套参数，只改回测起点。收益集中在 2024 年以后，早年的结果并不亮眼。</p></div></div>
    <div style="overflow-x:auto">
    <table>
      <thead><tr><th>区间</th><th class="r">年化</th><th class="r">最大回撤</th><th class="r">夏普</th><th class="r">不用防守（年化 / 回撤）</th><th class="r">沪深300 年化</th></tr></thead>
      <tbody>{per_table}</tbody>
    </table></div>
    <div style="margin-top:14px">{yr_svg}</div>
    {cand_svg}
    <ul class="notes">
      <li>收益不均匀：2015–2018 年化约 0%，2019–2020 年化 7.7%，2021–2023 年化 −1.3%，2024 年以来年化 21%。2024 年以来这一段是全部超额的主要来源，也是最大的不确定性。</li>
      <li>早年候选池很少：{bt['coverage']['first_full_year']} 年起可选 ETF 才超过 100 只；更早的年份里，同一时刻可交易的 ETF 往往不到 10 只，"选前 5"接近满仓持有全池。</li>
      <li>"不用防守"一列是把年线开关关掉的结果：防守组合在熊市压低回撤，代价是牛市少赚。</li>
      <li>参数没有按年份单独调优，但评分因子的取舍参考了 2015–2026 全样本的 IC，仍属样本内。</li>
    </ul>
  </section>

  <section class="card">
    <div class="card-head"><div><h2>当前评分榜</h2><p class="sub">候选池按合成分排序；"持有"为上一交易日已经在仓的 ETF</p></div></div>
    <div style="overflow-x:auto">
    <table>
      <thead><tr><th class="r" style="width:36px">#</th><th>代码</th><th>名称</th><th class="r">评分</th><th class="r">距年线</th><th class="r">20日波动</th><th class="r hidesm">日均成交额</th></tr></thead>
      <tbody>{top_table}</tbody>
    </table></div>
    <details><summary>评分怎么算</summary>
      <ul class="notes">
        <li><b>距年线</b>（权重 0.6）：收盘价 / 250 日均线 − 1，越高越好。对应"站上年线的 ETF 未来 5 日更可能上涨"。</li>
        <li><b>20 日波动</b>（权重 −0.4）：日收益标准差，越低越好。低波在 ETF 池里有稳定的正超额。</li>
        <li>两项各自在当日候选池内做 z-score 后加权，再按排名取前 5；已持有的 ETF 只要排名没有跌出前 15 就继续持有（排名缓冲，显著降低换手）。</li>
        <li>为什么不是"超跌反弹"：逐日 Rank IC 检验显示，20 日涨跌、60 日回撤等反转因子在全样本上 IC 接近 0 且方向反复；趋势与波动两个因子方向更稳定。方法与 IC 表见下节。</li>
      </ul>
    </details>
  </section>

  <section class="card">
    <div class="card-head"><div><h2>最近调仓记录</h2><p class="sub">只列持仓或状态发生变化的日子（最近 12 次）</p></div></div>
    <table>
      <thead><tr><th>信号日</th><th>买入 / 切换</th><th class="hidesm">卖出</th></tr></thead>
      <tbody>{rec_table}</tbody></table>
  </section>

  <section class="card">
    <div class="cols">
      <div>
        <h2>方法</h2>
        <ul class="notes">
          <li><b>收益来源</b>：日频在候选池里挑"站上年线 + 低波"的 5 只，趋势跟随为主；沪深300 跌破年线时切国债/红利防守。评分来自逐日 Rank IC 检验：距年线（+0.029）与低波（−0.038）方向最稳定，20 日涨跌、60 日回撤等反转因子全样本 IC 接近 0。</li>
          <li><b>数据</b>：新浪财经 ETF 日线（不复权，份额折算处按价格跳变与成交额连续性识别并修补）与沪深300 指数日线，每日收盘后更新。</li>
          <li><b>候选池</b>：剔除货币、债券、黄金商品、跨境（港股/美股/日经等）；近 20 日日均成交额 ≥ {bt['params']['min_amount']/1e8:.0f} 百万元（{bt['params']['cap_from'][:4]} 年起提高到 {bt['params']['min_amount_cap']/1e8:.0f} 百万元，因为 ETF 数量已扩容）；上市 ≥ 60 个交易日；近 120 日收益相关 &gt; 0.95 视为同一指数，只保留成交额最大的一只。</li>
          <li><b>选样</b>：距年线与低波两项合成评分排名前 {bt['params']['n_hold']}，等权；已持有且排名在前 {bt['params']['n_hold'] + bt['params']['rank_buffer']} 的继续持有。</li>
          <li><b>防守</b>：沪深300 收盘低于 250 日均线时，换为 {int(bt['params']['defense_bond_w']*100)}% 国债 ETF（511010）+ {100-int(bt['params']['defense_bond_w']*100)}% 红利低波 ETF。</li>
          <li><b>成交与成本</b>：收盘出信号、下一交易日开盘调仓，单边成本 {bt['params']['cost']*100:.1f}%（佣金 + 滑点），停牌按最近有效收盘价记账。</li>
        </ul>
      </div>
      <div>
        <h2>局限</h2>
        <ul class="notes">
          <li><b>幸存者偏差</b>：候选池来自"今天仍在交易、且能在新浪拿到行情"的 ETF，已退市的没有进入回测。</li>
          <li><b>样本内参数</b>：评分因子与缓冲宽度是先看全样本 IC 与回测再定的，2024 年后的表现好看有这一层原因。</li>
          <li><b>没有成交额冲击</b>：回测按收盘/开盘价成交，未模拟大额买入对盘口的影响。</li>
          <li><b>数据缺口</b>：新浪不复权序列的份额折算修补是规则识别，个别冷门 ETF 可能漏判；QDII/跨境已排除以避开溢价与折算。</li>
          <li><b>频率</b>：日频检查、次日开盘调仓，盘中不做任何干预；不处理涨跌停排队。</li>
          <li><b>近期回撤偏大</b>：2026 年内最大回撤 18%；一年约 5~10 次持仓变动，单次决策的胜率约 56%，连亏几轮是正常分布的一部分。</li>
        </ul>
        <p class="sub" style="margin-top:14px">代码与数据自动更新于 GitHub Actions，仓库：<a href="https://github.com/jingyi22/etf-rotation" style="color:var(--series-1)">jingyi22/etf-rotation</a></p>
      </div>
    </div>
  </section>

  <footer>
    <b>免责声明</b>：本站仅为公开数据上的历史回测与规则展示，不构成证券投资咨询或买卖建议；ETF 交易有风险，历史收益不代表未来表现。
    数据来自新浪财经公开行情，可能存在缺口或错误，以交易所与基金公告为准。
  </footer>
</div>
<script>window.__CHART__={chart_data};</script>
<script>{JS}</script>
</body>
</html>
"""
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    # 同时复制一份原始数据，便于查看
    with open(os.path.join(DOCS_DIR, "signals.json"), "w", encoding="utf-8") as f:
        json.dump(sig, f, ensure_ascii=False, indent=1)
    print(f"写入 docs/index.html（{len(page)/1024:.0f} KB）")


def yearly_bars(bt):
    """分年收益：策略 vs 沪深300，小倍数柱状。"""
    ys = sorted(bt["yearly"])
    n = len(ys)
    W, H = 1000, 190
    ml, mr, mt, mb = 44, 12, 10, 24
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    vals = [bt["yearly"][y] for y in ys] + [bt["bench_yearly"].get(y, 0) or 0 for y in ys]
    vmin, vmax = min(vals + [0]), max(vals + [0])
    pad = (vmax - vmin) * 0.1 or 0.05
    vmin, vmax = vmin - pad, vmax + pad
    def Y(v):
        return y1 - (y1 - y0) * (v - vmin) / (vmax - vmin)
    group_w = (x1 - x0) / n
    bw = min(16, group_w * 0.28)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="分年收益对比">']
    # 零线与网格
    for v in (0.0, vmax - pad, (vmax + vmin) / 2):
        yy = Y(v)
        parts.append(f'<line class="gridline" x1="{x0}" x2="{x1}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="axis-text" x="{x0-8}" y="{yy+4:.1f}" text-anchor="end">{v*100:.0f}%</text>')
    for i, y in enumerate(ys):
        cx = x0 + group_w * (i + 0.5)
        a = bt["yearly"][y]
        b = bt["bench_yearly"].get(y)
        ya, yz = Y(a), Y(0)
        top, hgt = min(ya, yz), abs(ya - yz)
        parts.append(f'<rect x="{cx-bw-1:.1f}" y="{top:.1f}" width="{bw}" height="{max(1,hgt):.1f}" rx="3" fill="var(--series-1)"/>')
        if b is not None:
            yb = Y(b)
            top, hgt = min(yb, yz), abs(yb - yz)
            parts.append(f'<rect x="{cx+1:.1f}" y="{top:.1f}" width="{bw}" height="{max(1,hgt):.1f}" rx="3" fill="var(--series-2)"/>')
        parts.append(f'<text class="axis-text" x="{cx:.1f}" y="{H-7}" text-anchor="middle">{y}</text>')
    parts.append("</svg>")
    return ('<div class="legend"><span class="key"><i style="width:10px;height:10px;border:0;background:var(--series-1)"></i>策略</span>'
            '<span class="key b"><i style="width:10px;height:10px;border:0;background:var(--series-2)"></i>沪深300</span></div>'
            + "".join(parts))


if __name__ == "__main__":
    main()
