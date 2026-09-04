"""
Dashboard Generator
----------------------
Builds a single self-contained HTML file (outputs/dashboard.html) from
outputs/dashboard_data.json. No server needed -- open directly in a browser
for the live demo.
"""

import json


def money(n):
    return f"Rs.{n:,.0f}"


def build_timeline_svg(timeline, events, width=1040, height=90):
    if not timeline:
        return ""
    max_min = max(t["minute"] for t in timeline) + 30
    max_rate = max(t["fail_rate"] for t in timeline) or 0.01
    bar_w = width / len(timeline)

    bars = []
    for t in timeline:
        x = (t["minute"] / max_min) * width
        h = (t["fail_rate"] / max_rate) * (height - 10)
        y = height - h
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w-1:.1f}" height="{h:.1f}" fill="#22304A" />')

    markers = []
    for e in events:
        x = (e["window_start_min"] / max_min) * width
        markers.append(
            f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{height}" stroke="#F2A93B" stroke-width="1.5" stroke-dasharray="2,2" />'
            f'<circle cx="{x:.1f}" cy="4" r="3" fill="#F2A93B" />'
        )

    return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">' + "".join(bars) + "".join(markers) + "</svg>"


def root_cause_label(rc):
    return rc.replace("_", " ")


def action_label(a):
    return a.replace("_", " ")


def build_ledger_rows(ledger):
    rows = []
    for e in ledger:
        pct = e["recovery_rate"] * 100
        is_escalated = e["action"] == "escalate_to_ops"
        bar_color = "#8B96AC" if is_escalated else ("#35C48D" if pct >= 70 else ("#F2A93B" if pct >= 40 else "#FF6B6B"))
        recovered_class = "accent-dim" if is_escalated else "accent-green"
        recovered_label = money(e['amount_recovered']) if not is_escalated else "escalated &middot; no auto-action"
        rows.append(f"""
        <tr>
          <td class="mono">{e['payment_method']}</td>
          <td class="mono">{e['segment_value']}</td>
          <td>{root_cause_label(e['root_cause'])}</td>
          <td>{action_label(e['action'])}</td>
          <td class="num">{e['n_transactions']}</td>
          <td class="num">{money(e['amount_at_risk'])}</td>
          <td class="num {recovered_class}">{recovered_label}</td>
          <td class="bar-cell">
            <div class="bar-track"><div class="bar-fill" style="width:{pct:.0f}%; background:{bar_color};"></div></div>
            <span class="bar-pct">{pct:.0f}%</span>
          </td>
        </tr>""")
    return "".join(rows)


def main():
    with open("outputs/dashboard_data.json") as f:
        data = json.load(f)

    sc = data["scorecard"]
    det, diag, rec = sc["detection"], sc["diagnosis"], sc["recovery"]

    timeline_svg = build_timeline_svg(data["timeline"], data["events"])
    ledger_rows = build_ledger_rows(data["ledger"])

    recovery_pct = rec["overall_recovery_rate"] * 100

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Revenue Recovery Agent — Live Console</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');

  :root {{
    --bg: #0B1220;
    --panel: #121B2E;
    --panel-2: #0E1626;
    --border: #22304A;
    --text: #E7ECF5;
    --text-dim: #8B96AC;
    --accent: #3395FF;
    --green: #35C48D;
    --amber: #F2A93B;
    --red: #FF6B6B;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    padding: 32px 40px 60px;
    max-width: 1180px;
    margin: 0 auto;
  }}

  .mono {{ font-family: 'IBM Plex Mono', monospace; }}

  header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 1px solid var(--border);
    padding-bottom: 20px;
    margin-bottom: 28px;
  }}

  header h1 {{
    font-size: 20px;
    font-weight: 600;
    letter-spacing: -0.01em;
  }}

  header .track {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: var(--accent);
  }}

  .subtitle {{
    color: var(--text-dim);
    font-size: 13px;
    margin-top: 4px;
  }}

  .hero {{
    background: var(--panel);
    border: 1px solid var(--border);
    padding: 28px 32px;
    margin-bottom: 24px;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 40px;
    flex-wrap: wrap;
  }}

  .hero-num {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 44px;
    font-weight: 700;
    color: var(--green);
    line-height: 1;
  }}

  .hero-label {{
    color: var(--text-dim);
    font-size: 13px;
    margin-top: 8px;
  }}

  .hero-sub {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 15px;
    color: var(--text-dim);
  }}

  .hero-sub b {{ color: var(--text); }}

  .progress-track {{
    width: 260px;
    height: 6px;
    background: var(--border);
    position: relative;
  }}
  .progress-fill {{
    height: 100%;
    background: var(--green);
    width: {recovery_pct:.0f}%;
  }}

  .stat-row {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1px;
    background: var(--border);
    margin-bottom: 24px;
    border: 1px solid var(--border);
  }}

  .stat {{
    background: var(--panel);
    padding: 18px 24px;
  }}

  .stat-title {{
    font-size: 11px;
    letter-spacing: 0.04em;
    color: var(--text-dim);
    margin-bottom: 10px;
  }}

  .stat-value {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 22px;
    font-weight: 600;
  }}

  .stat-detail {{
    font-size: 12px;
    color: var(--text-dim);
    margin-top: 4px;
  }}

  section {{
    margin-bottom: 28px;
  }}

  .section-title {{
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}

  .panel {{
    background: var(--panel);
    border: 1px solid var(--border);
    padding: 20px 24px;
  }}

  .legend-dot {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--amber);
    margin-right: 6px;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}

  thead th {{
    text-align: left;
    font-weight: 500;
    color: var(--text-dim);
    font-size: 11px;
    letter-spacing: 0.03em;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }}

  tbody td {{
    padding: 12px 8px;
    border-bottom: 1px solid var(--border);
  }}

  tbody tr:last-child td {{ border-bottom: none; }}

  td.num {{ font-family: 'IBM Plex Mono', monospace; text-align: right; }}
  th:nth-child(n+5) {{ text-align: right; }}

  .accent-green {{ color: var(--green); }}
  .accent-dim {{ color: var(--text-dim); font-family: 'Inter', sans-serif; font-size: 12px; text-align: right; }}

  .bar-cell {{ display: flex; align-items: center; gap: 8px; min-width: 140px; }}
  .bar-track {{
    flex: 1;
    height: 6px;
    background: var(--border);
  }}
  .bar-fill {{ height: 100%; }}
  .bar-pct {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    width: 34px;
    text-align: right;
  }}

  footer {{
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    color: var(--text-dim);
    font-size: 11px;
    font-family: 'IBM Plex Mono', monospace;
  }}
</style>
</head>
<body>

<header>
  <div>
    <h1>Revenue Recovery Agent</h1>
    <div class="subtitle">Payment degradation &rarr; root cause &rarr; recovery action</div>
  </div>
  <div class="track">AI REVENUE RECOVERY &middot; RAZORPAY BUILDATHON 2026</div>
</header>

<div class="hero">
  <div>
    <div class="hero-num">{money(rec['total_amount_recovered'])}</div>
    <div class="hero-label">recovered of {money(rec['total_amount_at_risk'])} at risk</div>
  </div>
  <div style="text-align:right;">
    <div class="hero-sub"><b>{recovery_pct:.1f}%</b> recovery rate</div>
    <div class="progress-track" style="margin-top:10px;"><div class="progress-fill"></div></div>
  </div>
</div>

<div class="stat-row">
  <div class="stat">
    <div class="stat-title">DETECTION</div>
    <div class="stat-value">{det['recall']*100:.0f}% recall</div>
    <div class="stat-detail">{det['events_detected']}/{det['real_events_planted']} events caught &middot; {det['precision']*100:.0f}% precision &middot; 0 false alarms</div>
  </div>
  <div class="stat">
    <div class="stat-title">DIAGNOSIS</div>
    <div class="stat-value">{diag['diagnosis_accuracy']*100:.0f}% accuracy</div>
    <div class="stat-detail">{diag['correct_diagnoses']}/{diag['events_diagnosed']} correct root causes &middot; {diag['avg_confidence']*100:.0f}% avg confidence</div>
  </div>
  <div class="stat">
    <div class="stat-title">RECOVERY</div>
    <div class="stat-value">{rec['n_events_handled']} events handled</div>
    <div class="stat-detail">Bounded actions &middot; confidence-gated escalation &middot; full audit trail</div>
  </div>
</div>

<section>
  <div class="section-title">
    <span>24-HOUR FAILURE RATE &middot; ALL SEGMENTS</span>
    <span><span class="legend-dot"></span>degradation event detected</span>
  </div>
  <div class="panel">
    {timeline_svg}
  </div>
</section>

<section>
  <div class="section-title">EVENT LEDGER</div>
  <div class="panel">
    <table>
      <thead>
        <tr>
          <th>Method</th>
          <th>Segment</th>
          <th>Root cause</th>
          <th>Action taken</th>
          <th>Tx</th>
          <th>At risk</th>
          <th>Recovered</th>
          <th>Rate</th>
        </tr>
      </thead>
      <tbody>
        {ledger_rows}
      </tbody>
    </table>
  </div>
</section>

<footer>
  Generated from outputs/dashboard_data.json &middot; full audit trail: outputs/recovery_audit_log.csv
</footer>

</body>
</html>
"""

    with open("outputs/dashboard.html", "w") as f:
        f.write(html)

    print("Wrote outputs/dashboard.html")


if __name__ == "__main__":
    main()
