"""Charts (Altair). One quiet style everywhere: thin marks, hairline grid, the accent
colour for data, text colours for labels, and a hover readout on every chart."""
import altair as alt
import pandas as pd

from ui import ACCENT, CARD, GRID, MUTED, SANS, TEXT, TEXT2, dur

HOVER_DATE = alt.Tooltip("date:T", title="Date", format="%a, %b %d")


def style(chart):
    return (chart.properties(background="transparent", padding={"left": 2, "right": 6, "top": 8, "bottom": 2})
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor=GRID, gridWidth=1, domain=False,
                            ticks=False, labelFont=SANS, titleFont=SANS, labelFontSize=11, labelPadding=8)
            .configure_axisX(grid=False)
            .configure_title(font=SANS, color=TEXT2, fontSize=12, fontWeight=600, anchor="start", offset=10)
            .configure_text(font=SANS)
            .configure_concat(spacing=18))


def padded_domain(start, end, hours=14):
    """A date range with a little room at each end, as ISO strings (Vega-Lite ignores
    plain numbers here and collapses the axis)."""
    return [(pd.Timestamp(start) - pd.Timedelta(hours=hours)).isoformat(),
            (pd.Timestamp(end) + pd.Timedelta(hours=hours)).isoformat()]


def with_segments(df, gap_days=3):
    """Number each run of consecutive nights so lines break across gaps (watch not worn)."""
    df = df.sort_values("date").copy()
    df["segment"] = (df["date"].diff().dt.days > gap_days).cumsum()
    return df


def bar_size(n, width=340, most=14):
    return max(2, min(most, int(width / max(n, 1) * 0.6)))


def recent_scores(nights, usual, start, end):
    """A sparkline of the last week of sleep scores against a dashed 'usual' line (no axes:
    hover a point for its night and score)."""
    d = nights.copy()
    d["slept"] = d["total_sleep_hours"].map(dur)
    xs = alt.Scale(domain=padded_domain(start, end))
    x = alt.X("date:T", title=None, scale=xs, axis=None)
    low = min(d["sleep_score"].min(), usual) - 8
    high = max(d["sleep_score"].max(), usual) + 6
    ys = alt.Scale(domain=[max(0, low), min(100, high)])
    y = alt.Y("sleep_score:Q", title=None, scale=ys, axis=None)
    y_usual = alt.Y("v:Q", title=None, scale=ys, axis=None)
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", clear="pointerout", empty=False)
    base = alt.Chart(with_segments(d, 1)).encode(x=x)
    usual_df = pd.DataFrame({"date": [pd.Timestamp(start)], "v": [usual], "t": [f"usual {usual:.0f}"]})
    layers = [
        alt.Chart(usual_df).mark_rule(color=ACCENT, strokeDash=[5, 5], strokeWidth=1.5, opacity=0.6).encode(y=y_usual),
        alt.Chart(usual_df).mark_text(align="left", dy=-8, dx=-6, color=MUTED, fontSize=11).encode(
            x=x, y=y_usual, text="t:N"),
        base.mark_rule(color=MUTED, strokeWidth=1).encode(opacity=alt.condition(hover, alt.value(0.45), alt.value(0))),
        base.mark_line(color=ACCENT, strokeWidth=2.5, strokeCap="round", strokeJoin="round").encode(
            y=y, detail="segment:N"),
        base.mark_point(filled=True, size=72, color=TEXT, stroke=ACCENT, strokeWidth=3, opacity=1).encode(
            y=y, tooltip=[HOVER_DATE, alt.Tooltip("sleep_score:Q", title="Score"),
                          alt.Tooltip("slept:N", title="Asleep")]).add_params(hover),
    ]
    return style(alt.layer(*layers).properties(height=84))


Y_AXIS_WIDTH = 34  # same width on both nightly charts so their dates line up


def nightly_hours(nights, need_hours, start, end):
    """Hours asleep each night (bars) against your sleep need (dashed line)."""
    d = nights.sort_values("date").copy()
    d["slept"] = d["total_sleep_hours"].map(dur)
    xs = alt.Scale(domain=padded_domain(start, end))
    top = max(10, float(d["total_sleep_hours"].max()) + 0.5)
    ys = alt.Scale(domain=[0, top])
    tip = [HOVER_DATE, alt.Tooltip("slept:N", title="Asleep"), alt.Tooltip("sleep_score:Q", title="Score")]
    # No date labels: the score chart right below shares these dates and labels them
    x = alt.X("date:T", title=None, scale=xs, axis=alt.Axis(format="%b %d", tickCount=5, labels=False, ticks=False))
    y_axis = alt.Axis(values=[0, 5, 10], labelExpr="datum.value + 'h'", minExtent=Y_AXIS_WIDTH, maxExtent=Y_AXIS_WIDTH)
    bars = alt.Chart(d).mark_bar(color=ACCENT, cornerRadiusEnd=3, size=bar_size(len(d))).encode(
        x=x, y=alt.Y("total_sleep_hours:Q", title=None, scale=ys, axis=y_axis), tooltip=tip)
    need_df = pd.DataFrame({"date": [pd.Timestamp(end)], "v": [need_hours], "t": [f"need {dur(need_hours)}"]})
    y_need = alt.Y("v:Q", title=None, scale=ys, axis=y_axis)
    need_rule = alt.Chart(need_df).mark_rule(color=TEXT, strokeDash=[5, 5], strokeWidth=1.5, opacity=0.6).encode(y=y_need)
    need_text = alt.Chart(need_df).mark_text(align="right", dy=-8, dx=10, color=TEXT2, fontSize=11, fontWeight=600).encode(
        x=x, y=y_need, text="t:N")
    return style(alt.layer(bars, need_rule, need_text).properties(height=150, title="Hours asleep"))


def nightly_scores(nights, start, end):
    """Sleep score each night, on the same dates as nightly_hours."""
    d = with_segments(nights)
    d["slept"] = d["total_sleep_hours"].map(dur)
    tip = [HOVER_DATE, alt.Tooltip("sleep_score:Q", title="Score"), alt.Tooltip("slept:N", title="Asleep")]
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", clear="pointerout", empty=False)
    x = alt.X("date:T", title=None, scale=alt.Scale(domain=padded_domain(start, end)),
              axis=alt.Axis(format="%b %d", tickCount=5, labelAngle=0))
    y = alt.Y("sleep_score:Q", title=None, scale=alt.Scale(domain=[30, 100]),
              axis=alt.Axis(values=[40, 70, 100], minExtent=Y_AXIS_WIDTH, maxExtent=Y_AXIS_WIDTH))
    base = alt.Chart(d).encode(x=x)
    return style(alt.layer(
        base.mark_rule(color=MUTED, strokeWidth=1).encode(opacity=alt.condition(hover, alt.value(0.45), alt.value(0))),
        base.mark_line(color=ACCENT, strokeWidth=2, strokeCap="round", strokeJoin="round").encode(y=y, detail="segment:N"),
        base.mark_point(filled=True, size=64, color=TEXT, stroke=ACCENT, strokeWidth=2.5).encode(
            y=y, opacity=alt.condition(hover, alt.value(1), alt.value(0)), tooltip=tip).add_params(hover),
    ).properties(height=120, title="Sleep score"))


STAGE_COLORS = {"Deep": "#1c5cab", "Light": "#86b6ef", "REM": "#9b7be8"}  # also used by the bar above the chart


def nightly_stages(nights, start, end):
    """Deep, light and REM hours each night, stacked (deep at the bottom)."""
    d = nights.melt(id_vars=["date"], value_vars=["deep_hours", "light_hours", "rem_hours"],
                    var_name="col", value_name="hours")
    d["stage"] = d["col"].map({"deep_hours": "Deep", "light_hours": "Light", "rem_hours": "REM"})
    d["order"] = d["stage"].map({"Deep": 0, "Light": 1, "REM": 2})
    d["time"] = d["hours"].map(dur)
    x = alt.X("date:T", title=None, scale=alt.Scale(domain=padded_domain(start, end)),
              axis=alt.Axis(format="%b %d", tickCount=5, labelAngle=0))
    y = alt.Y("hours:Q", title=None, stack="zero",
              axis=alt.Axis(values=[0, 5, 10], labelExpr="datum.value + 'h'", minExtent=Y_AXIS_WIDTH,
                            maxExtent=Y_AXIS_WIDTH))
    color = alt.Color("stage:N", legend=None, scale=alt.Scale(domain=list(STAGE_COLORS),
                                                              range=list(STAGE_COLORS.values())))
    tip = [HOVER_DATE, alt.Tooltip("stage:N", title="Stage"), alt.Tooltip("time:N", title="Time")]
    bars = alt.Chart(d).mark_bar(size=bar_size(len(nights)), stroke=CARD, strokeWidth=1).encode(
        x=x, y=y, color=color, order=alt.Order("order:Q"), tooltip=tip)
    return style(bars.properties(height=150))


def score_by_length(by_length):
    """Average score for each band of hours slept. Faded bars rest on fewer than 5 nights."""
    d = by_length[by_length["nights"] > 0].copy()
    d["reliable"] = d["nights"] >= 5
    d["label"] = d["score"].round().astype(int).astype(str)
    x = alt.X("band:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, labelColor=TEXT2, labelFontSize=12))
    tip = [alt.Tooltip("band:N", title="Slept"), alt.Tooltip("score:Q", title="Average score", format=".0f"),
           alt.Tooltip("nights:Q", title="Nights")]
    base = alt.Chart(d).encode(x=x, tooltip=tip)
    return style(alt.layer(
        base.mark_bar(color=ACCENT, cornerRadiusEnd=4, size=24).encode(
            y=alt.Y("score:Q", title=None, scale=alt.Scale(domain=[0, 100]), axis=None),
            opacity=alt.condition("datum.reliable", alt.value(1), alt.value(0.4))),
        base.mark_text(dy=-9, color=TEXT, fontSize=13, fontWeight=600).encode(y="score:Q", text="label:N"),
    ).properties(height=170))


def weekly_hours(weekly, this_week):
    """Training hours per week. The current week is faded because it isn't finished."""
    d = weekly.copy()
    d["current"] = d["week"] == this_week
    d["time"] = d["hours"].map(dur)
    d["load"] = d["load"].round()
    x = alt.X("week:T", title=None, axis=alt.Axis(format="%b %d", tickCount=6, labelAngle=0),
              scale=alt.Scale(domain=padded_domain(d["week"].min(), d["week"].max(), hours=4 * 24)))
    tip = [alt.Tooltip("week:T", title="Week of", format="%b %d"), alt.Tooltip("time:N", title="Training"),
           alt.Tooltip("sessions:Q", title="Workouts"), alt.Tooltip("load:Q", title="Load")]
    bars = alt.Chart(d).mark_bar(color=ACCENT, cornerRadiusEnd=4, size=bar_size(len(d), most=24)).encode(
        x=x, tooltip=tip,
        y=alt.Y("hours:Q", title=None, axis=alt.Axis(tickCount=4, labelExpr="datum.value + 'h'")),
        opacity=alt.condition("datum.current", alt.value(0.45), alt.value(1)))
    return style(bars.properties(height=170))


def weight_trend(w, start, end, unit="lb", factor=1.0, smooth=True):
    """Weight over time. With regular weigh-ins (`smooth`): dots for each weigh-in plus a
    7-day average line. With only a few: one line through the weigh-ins themselves.
    `factor` converts kg to the display unit."""
    d = w.copy()
    d["v"] = d["kg"] * factor
    d["avg"] = d["trend"] * factor
    d["v_t"] = d["v"].map(lambda v: f"{v:.1f} {unit}")
    d["avg_t"] = d["avg"].map(lambda v: f"{v:.1f} {unit}")
    line_col = "avg" if smooth else "v"
    lo, hi = float(min(d["v"].min(), d[line_col].min())), float(max(d["v"].max(), d[line_col].max()))
    pad = max(1.0 * factor, (hi - lo) * 0.25)
    ys = alt.Scale(domain=[lo - pad, hi + pad], zero=False, nice=False)
    long_view = (pd.Timestamp(end) - pd.Timestamp(start)).days > 300  # show years so "Apr" isn't ambiguous
    x = alt.X("date:T", title=None, scale=alt.Scale(domain=padded_domain(start, end, hours=24)),
              axis=alt.Axis(format="%b %Y" if long_view else "%b %d", tickCount=5, labelAngle=0))
    y_axis = alt.Axis(tickCount=4, format=".0f", minExtent=Y_AXIS_WIDTH, maxExtent=Y_AXIS_WIDTH)
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", clear="pointerout", empty=False)
    tip = [HOVER_DATE, alt.Tooltip("v_t:N", title="Weigh-in")]
    if smooth:
        tip.append(alt.Tooltip("avg_t:N", title="7-day average"))
    base = alt.Chart(d).encode(x=x)  # one continuous line through every weigh-in
    point_style = (dict(color=TEXT2, stroke=CARD, strokeWidth=2) if smooth          # raw weigh-ins, quiet
                   else dict(color=TEXT, stroke=ACCENT, strokeWidth=2.5))          # they ARE the line
    return style(alt.layer(
        base.mark_rule(color=MUTED, strokeWidth=1).encode(opacity=alt.condition(hover, alt.value(0.45), alt.value(0))),
        base.mark_line(color=ACCENT, strokeWidth=2, strokeCap="round", strokeJoin="round").encode(
            y=alt.Y(f"{line_col}:Q", title=None, scale=ys, axis=y_axis)),
        base.mark_point(filled=True, size=64, opacity=1, **point_style).encode(
            y=alt.Y("v:Q", title=None, scale=ys, axis=y_axis), tooltip=tip).add_params(hover),
    ).properties(height=180))


REST_GREY = "#6b7482"  # rest days in the calorie chart (3:1 against the card)


def daily_burn(d, avg, start, end):
    """Calories burned each day: workout days in the accent colour, rest days grey,
    and a dashed line at your average."""
    d = d.copy()
    d["kind"] = d["trained"].map({True: "Workout day", False: "Rest day"})
    d["total_t"] = d["cal_total"].map(lambda v: f"{v:,.0f} cal")
    d["active_t"] = d["cal_active"].map(lambda v: f"{v:,.0f} cal")
    x = alt.X("date:T", title=None, scale=alt.Scale(domain=padded_domain(start, end)),
              axis=alt.Axis(format="%b %d", tickCount=5, labelAngle=0))
    top = float(d["cal_total"].max()) * 1.08
    ys = alt.Scale(domain=[0, top], nice=False)
    ticks = list(range(0, int(top) + 1, 1000))  # 0, 1k, 2k, 3k...
    y_axis = alt.Axis(values=ticks, labelExpr="datum.value === 0 ? '0' : datum.value / 1000 + 'k'",
                      minExtent=Y_AXIS_WIDTH, maxExtent=Y_AXIS_WIDTH)
    color = alt.Color("kind:N", legend=None,
                      scale=alt.Scale(domain=["Workout day", "Rest day"], range=[ACCENT, REST_GREY]))
    tip = [HOVER_DATE, alt.Tooltip("total_t:N", title="Burned"), alt.Tooltip("active_t:N", title="From moving"),
           alt.Tooltip("kind:N", title="Day")]
    bars = alt.Chart(d).mark_bar(cornerRadiusEnd=3, size=bar_size(len(d))).encode(
        x=x, y=alt.Y("cal_total:Q", title=None, scale=ys, axis=y_axis), color=color, tooltip=tip)
    avg_df = pd.DataFrame({"v": [avg]})
    rule = alt.Chart(avg_df).mark_rule(color=TEXT, strokeDash=[5, 5], strokeWidth=1.5, opacity=0.6).encode(
        y=alt.Y("v:Q", title=None, scale=ys, axis=y_axis))
    return style(alt.layer(bars, rule).properties(height=170))


def daily_steps(d, goal, start, end, weekly=False):
    """Steps per day (days that hit your goal in the accent colour, others grey), or average
    steps a day per week for long periods. Dashed line = your step goal."""
    d = d.dropna(subset=["steps"]).copy()
    if weekly:
        from insights import week_start
        d = d.assign(date=d["date"].map(week_start)).groupby("date", as_index=False)["steps"].mean()
        d["kind"] = "Week"
        tip = [alt.Tooltip("date:T", title="Week of", format="%b %d"), alt.Tooltip("steps_t:N", title="Avg a day")]
        colors = alt.value(ACCENT)
    else:
        d["kind"] = (d["steps"] >= (goal or 0)).map({True: "Goal hit", False: "Under goal"})
        tip = [HOVER_DATE, alt.Tooltip("steps_t:N", title="Steps"), alt.Tooltip("kind:N", title="Goal")]
        colors = alt.Color("kind:N", legend=None,
                           scale=alt.Scale(domain=["Goal hit", "Under goal"], range=[ACCENT, REST_GREY]))
    d["steps_t"] = d["steps"].map(lambda v: f"{v:,.0f}")
    top = float(max(d["steps"].max(), goal or 0)) * 1.1
    ys = alt.Scale(domain=[0, top], nice=False)
    step = 10000 if top > 18000 else 5000 if top > 9000 else 2500
    y_axis = alt.Axis(values=list(range(0, int(top) + 1, step)), minExtent=Y_AXIS_WIDTH, maxExtent=Y_AXIS_WIDTH,
                      labelExpr="datum.value === 0 ? '0' : datum.value / 1000 + 'k'")
    x = alt.X("date:T", title=None, scale=alt.Scale(domain=padded_domain(start, end, hours=96 if weekly else 14)),
              axis=alt.Axis(format="%b %d", tickCount=3, labelAngle=0))
    bars = alt.Chart(d).mark_bar(cornerRadiusEnd=3, size=bar_size(len(d), most=14)).encode(
        x=x, y=alt.Y("steps:Q", title=None, scale=ys, axis=y_axis), color=colors, tooltip=tip)
    layers = [bars]
    if goal:
        layers.append(alt.Chart(pd.DataFrame({"v": [goal]})).mark_rule(
            color=TEXT, strokeDash=[5, 5], strokeWidth=1.5, opacity=0.6).encode(
            y=alt.Y("v:Q", title=None, scale=ys, axis=y_axis)))
    return style(alt.layer(*layers).properties(height=160))


def food_history(d, key, unit, start, end):
    """What you ate on each logged day (bars) and that day's target (white tick)."""
    fmt = lambda v: "" if pd.isna(v) else f"{v:,.0f} {unit}"
    d = d.assign(eaten_t=d[key].map(fmt), target_t=d[f"t_{key}"].map(fmt))
    top = float(pd.concat([d[key], d[f"t_{key}"]]).max()) * 1.1
    ys = alt.Scale(domain=[0, top], nice=False)
    y_axis = alt.Axis(tickCount=3, minExtent=Y_AXIS_WIDTH, maxExtent=Y_AXIS_WIDTH)
    x = alt.X("date:T", title=None, scale=alt.Scale(domain=padded_domain(start, end)),
              axis=alt.Axis(format="%b %d", tickCount=3, labelAngle=0))
    tip = [HOVER_DATE, alt.Tooltip("eaten_t:N", title="Eaten"), alt.Tooltip("target_t:N", title="Target")]
    size = bar_size(30)
    bars = alt.Chart(d).mark_bar(cornerRadiusEnd=3, size=size, color=ACCENT).encode(
        x=x, y=alt.Y(f"{key}:Q", title=None, scale=ys, axis=y_axis), tooltip=tip)
    ticks = alt.Chart(d).mark_tick(color=TEXT, thickness=2, size=size + 6).encode(
        x=x, y=alt.Y(f"t_{key}:Q", title=None, scale=ys, axis=y_axis), tooltip=tip)
    return style(alt.layer(bars, ticks).properties(height=160))


def vo2_trend(v):
    """VO2 max readings: Garmin updates them every week or two, so show every point."""
    d = v.sort_values("date").copy()
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", clear="pointerout", empty=False)
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%b %d", tickCount=5, labelAngle=0))
    y = alt.Y("vo2max:Q", title=None, scale=alt.Scale(zero=False, nice=True), axis=alt.Axis(tickCount=3))
    base = alt.Chart(d).encode(x=x)
    return style(alt.layer(
        base.mark_rule(color=MUTED, strokeWidth=1).encode(opacity=alt.condition(hover, alt.value(0.45), alt.value(0))),
        base.mark_line(color=ACCENT, strokeWidth=2, strokeCap="round", strokeJoin="round").encode(y=y),
        base.mark_point(filled=True, size=60, color=ACCENT, stroke=CARD, strokeWidth=2, opacity=1).encode(
            y=y, tooltip=[HOVER_DATE, alt.Tooltip("vo2max:Q", title="VO₂ max", format=".1f")]).add_params(hover),
    ).properties(height=140))
