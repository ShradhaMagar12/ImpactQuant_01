from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from flask import Flask, jsonify, render_template, request
from plotly.subplots import make_subplots
from plotly.utils import PlotlyJSONEncoder
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, confusion_matrix, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

APP_ROOT = Path(__file__).resolve().parent
DATA_PATH = APP_ROOT / "data" / "final_optimized_dataset.csv"
POWER_BI_EMBED_URL = os.environ.get("POWER_BI_EMBED_URL", "").strip()

COLORS = {
    "teal": "#00f5d4",
    "indigo": "#5b6af8",
    "amber": "#ffb830",
    "rose": "#ff4d6d",
    "lime": "#7fff6e",
    "text": "#cdd8f0",
    "dim": "#4a5980",
    "grid": "rgba(255,255,255,0.06)",
}

IMPACT_ORDER = ["Low", "Medium", "High"]
NATURAL_KEYWORDS = {
    "earthquake",
    "tsunami",
    "cyclone",
    "hurricane",
    "typhoon",
    "flood",
    "heatwave",
    "landslide",
    "mudslide",
    "wildfire",
    "storm",
}
MAN_MADE_KEYWORDS = {
    "oil spill",
    "chemical",
    "explosion",
    "industrial",
    "factory",
    "cyber",
    "attack",
    "war",
    "terror",
    "strike",
    "pandemic",
    "sanction",
}
DISPLAY_COLUMNS = [
    "Company",
    "Sector",
    "Disaster",
    "Type",
    "Disaster_Category",
    "Location",
    "Disaster_Date",
    "Before_Price",
    "After_Price",
    "Change (%)",
    "Impact",
    "Recovery_Days",
    "Sector_Impact_Score",
    "Sector_Resilience_Score",
]

app = Flask(__name__, template_folder="templates", static_folder="static")


def create_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def scale_to_100(values: pd.Series) -> pd.Series:
    values = values.astype(float)
    if values.nunique(dropna=False) <= 1:
        return pd.Series(np.full(len(values), 50.0), index=values.index)
    scaled = (values - values.min()) / (values.max() - values.min())
    return (scaled * 100).clip(0, 100)


def infer_disaster_category(disaster_type: str, disaster_name: str) -> str:
    text = f"{disaster_type} {disaster_name}".lower()
    if any(keyword in text for keyword in MAN_MADE_KEYWORDS):
        return "Man-made"
    if any(keyword in text for keyword in NATURAL_KEYWORDS):
        return "Natural"
    return "Natural"


def classify_impact(change_pct: float) -> str:
    if change_pct <= -5:
        return "High"
    if change_pct <= -2:
        return "Medium"
    return "Low"


def build_sector_profiles(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("Sector", dropna=False)
    stats = grouped.agg(
        Avg_Change=("Change (%)", "mean"),
        Volatility=("Change (%)", lambda s: float(s.std(ddof=0))),
        Event_Count=("Disaster", "count"),
        High_Impact_Ratio=("Impact", lambda s: float((s == "High").mean())),
        Positive_Ratio=("Change (%)", lambda s: float((s > 0).mean())),
    ).reset_index()
    negative_mag = grouped["Change (%)"].apply(
        lambda s: float(abs(s[s < 0].mean())) if (s < 0).any() else 0.0
    ).rename("Negative_Magnitude")
    stats = stats.merge(negative_mag, on="Sector", how="left")

    neg_scale = scale_to_100(stats["Negative_Magnitude"]) / 100
    vol_scale = scale_to_100(stats["Volatility"]) / 100
    event_scale = scale_to_100(stats["Event_Count"]) / 100
    avg_scale = scale_to_100(stats["Avg_Change"]) / 100

    stats["Sector_Impact_Score"] = (
        (neg_scale * 45)
        + (vol_scale * 25)
        + (stats["High_Impact_Ratio"] * 20)
        + (event_scale * 10)
    ).round(2)
    stats["Sector_Resilience_Score"] = (
        (stats["Positive_Ratio"] * 45)
        + (avg_scale * 35)
        + ((1 - vol_scale) * 20)
    ).round(2)
    return stats[
        [
            "Sector",
            "Avg_Change",
            "Volatility",
            "Event_Count",
            "Sector_Impact_Score",
            "Sector_Resilience_Score",
        ]
    ]


def estimate_recovery_days(
    change_pct: float,
    impact_score: float,
    resilience_score: float,
    type_volatility: float,
) -> int:
    drawdown = max(-change_pct, 0)
    rebound = max(change_pct, 0)
    base_days = (
        3
        + (drawdown * 1.9)
        + (type_volatility * 0.8)
        + (impact_score / 15)
        - (resilience_score / 20)
        - (rebound * 0.8)
    )
    return int(np.clip(round(base_days), 1, 45))


@lru_cache(maxsize=1)
def load_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df.columns = [column.strip() for column in df.columns]
    df["Disaster_Date"] = pd.to_datetime(df["Disaster_Date"], errors="coerce")

    numeric_columns = ["Before_Price", "After_Price", "Change (%)"]
    categorical_columns = ["Company", "Sector", "Disaster", "Type", "Location", "Impact"]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
        df[column] = df[column].fillna(df[column].median())

    for column in categorical_columns:
        df[column] = df[column].fillna("Unknown").astype(str).str.strip()

    df = df.dropna(subset=["Disaster_Date"]).drop_duplicates().reset_index(drop=True)
    df["Impact"] = df["Impact"].str.title()
    df["Type"] = df["Type"].str.lower()
    df["Year"] = df["Disaster_Date"].dt.year
    df["Month"] = df["Disaster_Date"].dt.month
    df["Quarter"] = df["Disaster_Date"].dt.to_period("Q").astype(str)
    df["Disaster_Category"] = df.apply(
        lambda row: infer_disaster_category(row["Type"], row["Disaster"]),
        axis=1,
    )

    sector_profiles = build_sector_profiles(df)
    df = df.merge(sector_profiles, on="Sector", how="left")

    global_volatility = float(df["Change (%)"].std(ddof=0) or 0)
    type_volatility = df.groupby("Type")["Change (%)"].transform(
        lambda s: float(s.std(ddof=0)) if len(s) > 1 else global_volatility
    )
    df["Recovery_Days"] = [
        estimate_recovery_days(change, impact, resilience, volatility or global_volatility)
        for change, impact, resilience, volatility in zip(
            df["Change (%)"],
            df["Sector_Impact_Score"],
            df["Sector_Resilience_Score"],
            type_volatility,
        )
    ]
    df["Disaster_Frequency"] = df.groupby("Disaster")["Disaster"].transform("count")
    return df.sort_values(["Disaster_Date", "Company"]).reset_index(drop=True)


def request_payload() -> dict:
    if request.method == "POST":
        return request.get_json(silent=True) or {}
    return request.args.to_dict()


def parse_filters() -> dict:
    payload = request_payload()

    def pick(*keys: str, default: str = "") -> str:
        for key in keys:
            value = payload.get(key)
            if value is not None and value != "":
                return str(value)
        return default

    return {
        "company": pick("company", default="All"),
        "sector": pick("sector", default="All"),
        "disaster_category": "Natural",
        "event_type": pick("event_type", "type", default="All"),
        "location": pick("location", default="All"),
        "start_date": pick("start_date", "date_from", default=""),
        "end_date": pick("end_date", "date_to", default=""),
        "event": pick("event", "event_label", default=""),
    }


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    filtered = df.copy()
    if filters["company"] not in {"", "All"}:
        filtered = filtered[filtered["Company"] == filters["company"]]
    if filters["sector"] not in {"", "All"}:
        filtered = filtered[filtered["Sector"] == filters["sector"]]
    if filters["disaster_category"] not in {"", "All", "Both"}:
        filtered = filtered[filtered["Disaster_Category"] == filters["disaster_category"]]
    if filters["event_type"] not in {"", "All"}:
        filtered = filtered[filtered["Type"] == filters["event_type"].lower()]
    if filters["location"] not in {"", "All"}:
        filtered = filtered[filtered["Location"] == filters["location"]]
    if filters["event"]:
        filtered = filtered[
            filtered["Disaster"].str.contains(filters["event"], case=False, na=False)
        ]
    if filters["start_date"]:
        start = pd.to_datetime(filters["start_date"], errors="coerce")
        if pd.notna(start):
            filtered = filtered[filtered["Disaster_Date"] >= start]
    if filters["end_date"]:
        end = pd.to_datetime(filters["end_date"], errors="coerce")
        if pd.notna(end):
            filtered = filtered[filtered["Disaster_Date"] <= end]
    return filtered.sort_values(["Disaster_Date", "Company"]).reset_index(drop=True)


def format_date(value: pd.Timestamp | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def serialize_figure(fig: go.Figure) -> dict:
    return json.loads(json.dumps(fig, cls=PlotlyJSONEncoder))


def style_figure(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Outfit, sans-serif", "color": COLORS["text"]},
        margin={"l": 48, "r": 24, "t": 56, "b": 48},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "bgcolor": "rgba(0,0,0,0)",
        },
    )
    fig.update_xaxes(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"])
    fig.update_yaxes(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"])
    return fig


def empty_figure(title: str, message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        showarrow=False,
        font={"size": 16, "color": COLORS["text"]},
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
    )
    fig.update_layout(title=title)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return style_figure(fig)


def build_line_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Stock Trend", "No records match the current filters.")

    ordered = df.sort_values("Disaster_Date")
    if ordered["Company"].nunique() == 1:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=ordered["Disaster_Date"],
                y=ordered["Before_Price"],
                mode="lines+markers",
                name="Before Price",
                line={"color": COLORS["teal"], "width": 3},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=ordered["Disaster_Date"],
                y=ordered["After_Price"],
                mode="lines+markers",
                name="After Price",
                line={"color": COLORS["indigo"], "width": 3},
            )
        )
        fig.update_layout(title="Before vs After Price Trend")
        fig.update_yaxes(title_text="Price")
    else:
        trend = (
            ordered.groupby(["Disaster_Date", "Company"], as_index=False)["Change (%)"]
            .mean()
            .sort_values("Disaster_Date")
        )
        fig = px.line(
            trend,
            x="Disaster_Date",
            y="Change (%)",
            color="Company",
            markers=True,
            color_discrete_sequence=[
                COLORS["teal"],
                COLORS["indigo"],
                COLORS["amber"],
                COLORS["rose"],
                COLORS["lime"],
            ],
            title="Stock Impact Trend by Company",
        )
        fig.update_yaxes(title_text="Change (%)")
    return style_figure(fig)


def build_bar_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Impact per Disaster", "Add or relax filters to see event-level impact.")

    impact_df = (
        df.groupby("Disaster", as_index=False)
        .agg(
            Avg_Change=("Change (%)", "mean"),
            Type=("Type", lambda s: s.mode().iat[0]),
            Location=("Location", lambda s: s.mode().iat[0]),
        )
        .assign(Magnitude=lambda frame: frame["Avg_Change"].abs())
        .sort_values("Magnitude", ascending=False)
        .head(12)
        .sort_values("Avg_Change")
        .reset_index(drop=True)
    )
    impact_df["Impact_Level"] = impact_df["Avg_Change"].apply(classify_impact)
    fig = px.bar(
        impact_df,
        x="Disaster",
        y="Avg_Change",
        color="Impact_Level",
        title="Impact per Disaster (%)",
        hover_data=["Type", "Location"],
        color_discrete_map={
            "High": COLORS["rose"],
            "Medium": COLORS["amber"],
            "Low": COLORS["lime"],
        },
    )
    fig.update_layout(xaxis_title="", yaxis_title="Average Change (%)")
    return style_figure(fig)


def build_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Correlation Heatmap", "No numeric relationships to display yet.")

    encoded = pd.DataFrame(
        {
            "Company": pd.factorize(df["Company"])[0],
            "Sector": pd.factorize(df["Sector"])[0],
            "Type": pd.factorize(df["Type"])[0],
            "Category": pd.factorize(df["Disaster_Category"])[0],
            "Year": df["Year"],
            "Before Price": df["Before_Price"],
            "After Price": df["After_Price"],
            "Change (%)": df["Change (%)"],
            "Recovery Days": df["Recovery_Days"],
            "Impact Score": df["Sector_Impact_Score"],
            "Resilience Score": df["Sector_Resilience_Score"],
        }
    )
    corr = encoded.corr(numeric_only=True).round(2)
    fig = px.imshow(
        corr,
        text_auto=".2f",
        color_continuous_scale=[
            [0, "#081020"],
            [0.5, COLORS["indigo"]],
            [1, COLORS["teal"]],
        ],
        aspect="auto",
        title="Correlation Heatmap",
    )
    return style_figure(fig)


def build_box_plot(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Volatility Distribution", "No volatility distribution is available for this slice.")

    axis = "Sector" if df["Sector"].nunique() > 1 else "Company"
    fig = px.box(
        df,
        x=axis,
        y="Change (%)",
        color="Impact",
        points="outliers",
        title="Volatility Distribution",
        color_discrete_map={
            "High": COLORS["rose"],
            "Medium": COLORS["amber"],
            "Low": COLORS["lime"],
        },
    )
    fig.update_layout(xaxis_title="", yaxis_title="Change (%)")
    return style_figure(fig)


def build_sector_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "Sector",
                "avg_change",
                "volatility",
                "recovery_days",
                "impact_score",
                "resilience_score",
                "events",
            ]
        )

    summary = (
        df.groupby("Sector", as_index=False)
        .agg(
            avg_change=("Change (%)", "mean"),
            volatility=("Change (%)", lambda s: float(s.std(ddof=0))),
            recovery_days=("Recovery_Days", "mean"),
            impact_score=("Sector_Impact_Score", "mean"),
            resilience_score=("Sector_Resilience_Score", "mean"),
            events=("Disaster", "count"),
        )
        .sort_values("impact_score", ascending=False)
        .reset_index(drop=True)
    )
    return summary.round(2)


def build_sector_chart(df: pd.DataFrame) -> go.Figure:
    summary = build_sector_summary(df)
    if summary.empty:
        return empty_figure("Sector Comparison", "No sector comparison is available for the current filters.")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=summary["Sector"],
            y=summary["impact_score"],
            name="Impact Score",
            marker_color=COLORS["rose"],
            opacity=0.8,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            x=summary["Sector"],
            y=summary["resilience_score"],
            name="Resilience Score",
            marker_color=COLORS["teal"],
            opacity=0.8,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=summary["Sector"],
            y=summary["avg_change"],
            name="Avg Change (%)",
            mode="lines+markers",
            line={"color": COLORS["amber"], "width": 3},
        ),
        secondary_y=True,
    )
    fig.update_layout(title="Sector Comparison")
    fig.update_yaxes(title_text="Score", range=[0, 100], secondary_y=False)
    fig.update_yaxes(title_text="Average Change (%)", secondary_y=True)
    return style_figure(fig)


def build_frequency_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Disaster Frequency Timeline", "No event frequency is available for the current filters.")

    frequency = (
        df.groupby("Year", as_index=False)
        .agg(
            disaster_count=("Disaster", "nunique"),
            avg_change=("Change (%)", "mean"),
        )
        .sort_values("Year")
    )
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=frequency["Year"],
            y=frequency["disaster_count"],
            name="Disaster Count",
            marker_color=COLORS["teal"],
            opacity=0.75,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=frequency["Year"],
            y=frequency["avg_change"],
            name="Avg Change (%)",
            mode="lines+markers",
            line={"color": COLORS["amber"], "width": 3},
        ),
        secondary_y=True,
    )
    fig.update_layout(title="Disaster Frequency Timeline")
    fig.update_yaxes(title_text="Unique Disasters", secondary_y=False)
    fig.update_yaxes(title_text="Average Change (%)", secondary_y=True)
    return style_figure(fig)


def build_location_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Location Impact Map", "No location impact is available for the current filters.")

    location_summary = (
        df.groupby("Location", as_index=False)
        .agg(
            avg_change=("Change (%)", "mean"),
            events=("Disaster", "count"),
            volatility=("Change (%)", lambda s: float(s.std(ddof=0))),
        )
        .sort_values("events", ascending=False)
        .head(12)
    )
    fig = px.scatter(
        location_summary,
        x="events",
        y="avg_change",
        size="volatility",
        color="avg_change",
        text="Location",
        color_continuous_scale=[[0, COLORS["rose"]], [0.5, COLORS["amber"]], [1, COLORS["teal"]]],
        title="Location Impact Snapshot",
        labels={"events": "Event Count", "avg_change": "Average Change (%)"},
    )
    fig.update_traces(textposition="top center")
    return style_figure(fig)


def build_histogram_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Change Distribution", "No distribution is available for the current filters.")

    fig = px.histogram(
        df,
        x="Change (%)",
        nbins=28,
        color="Impact",
        opacity=0.82,
        title="Change Distribution",
        color_discrete_map={
            "High": COLORS["rose"],
            "Medium": COLORS["amber"],
            "Low": COLORS["lime"],
        },
    )
    fig.update_layout(bargap=0.06)
    return style_figure(fig)


def build_impact_pie_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Impact Class Split", "No impact class split is available for the current filters.")

    counts = df["Impact"].value_counts().reindex(IMPACT_ORDER, fill_value=0).reset_index()
    counts.columns = ["Impact", "Count"]
    fig = px.pie(
        counts,
        names="Impact",
        values="Count",
        hole=0.5,
        title="Impact Class Split",
        color="Impact",
        color_discrete_map={
            "High": COLORS["rose"],
            "Medium": COLORS["amber"],
            "Low": COLORS["lime"],
        },
    )
    return style_figure(fig)


def build_type_mix_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Disaster Mix", "No disaster mix is available for the current filters.")

    mix = df["Type"].value_counts().reset_index()
    mix.columns = ["Type", "Count"]
    fig = px.pie(
        mix,
        names="Type",
        values="Count",
        hole=0.52,
        title="Disaster Mix",
        color_discrete_sequence=[COLORS["teal"], COLORS["indigo"], COLORS["amber"], COLORS["rose"], COLORS["lime"]],
    )
    return style_figure(fig)


def build_sector_avg_bar_chart(df: pd.DataFrame) -> go.Figure:
    summary = build_sector_summary(df)
    if summary.empty:
        return empty_figure("Average Change by Sector", "No sector analysis is available for the current filters.")

    fig = px.bar(
        summary.sort_values("avg_change"),
        x="Sector",
        y="avg_change",
        color="avg_change",
        title="Average Change by Sector",
        color_continuous_scale=[[0, COLORS["rose"]], [0.5, COLORS["amber"]], [1, COLORS["teal"]]],
        labels={"avg_change": "Average Change (%)"},
    )
    fig.update_layout(xaxis_title="", yaxis_title="Average Change (%)")
    return style_figure(fig)


def build_disaster_type_bar_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Average Change by Disaster Type", "No disaster-type analysis is available for the current filters.")

    type_avg = (
        df.groupby("Type", as_index=False)["Change (%)"]
        .mean()
        .sort_values("Change (%)")
    )
    fig = px.bar(
        type_avg,
        x="Type",
        y="Change (%)",
        color="Change (%)",
        title="Average Change by Disaster Type",
        color_continuous_scale=[[0, COLORS["rose"]], [0.5, COLORS["amber"]], [1, COLORS["teal"]]],
    )
    fig.update_layout(xaxis_title="", yaxis_title="Average Change (%)")
    return style_figure(fig)


def build_year_type_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Year vs Type Heatmap", "No year-by-type relationship is available for the current filters.")

    pivot = (
        df.pivot_table(
            index="Type",
            columns="Year",
            values="Change (%)",
            aggfunc="mean",
        )
        .sort_index()
        .sort_index(axis=1)
    )
    fig = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale=[[0, COLORS["rose"]], [0.5, "#162133"], [1, COLORS["teal"]]],
        text_auto=".1f",
        title="Year vs Type Heatmap",
    )
    return style_figure(fig)


def build_sector_bubble_chart(df: pd.DataFrame) -> go.Figure:
    summary = build_sector_summary(df)
    if summary.empty:
        return empty_figure("Sector Risk Matrix", "No sector risk matrix is available for the current filters.")

    fig = px.scatter(
        summary,
        x="impact_score",
        y="resilience_score",
        size="events",
        color="avg_change",
        text="Sector",
        color_continuous_scale=[[0, COLORS["rose"]], [0.5, COLORS["amber"]], [1, COLORS["teal"]]],
        title="Sector Risk Matrix",
        labels={
            "impact_score": "Impact Score",
            "resilience_score": "Resilience Score",
            "avg_change": "Avg Change (%)",
        },
    )
    fig.update_traces(textposition="top center")
    fig.update_xaxes(range=[0, 100])
    fig.update_yaxes(range=[0, 100])
    return style_figure(fig)


def build_multivariate_scatter_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Multivariate Relationship", "No multivariate relationship is available for the current filters.")

    fig = px.scatter(
        df,
        x="Before_Price",
        y="Change (%)",
        size=df["After_Price"].clip(lower=1),
        color="Sector",
        symbol="Impact",
        hover_data=["Company", "Disaster", "Location", "Year"],
        title="Multivariate View: Before Price vs Change (%)",
    )
    return style_figure(fig)


def build_price_scatter_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Before vs After Price", "No price scatter is available for the current filters.")

    fig = px.scatter(
        df,
        x="Before_Price",
        y="After_Price",
        size=df["Change (%)"].abs().clip(lower=0.1),
        color="Impact",
        hover_data=["Company", "Disaster", "Sector", "Location"],
        title="Before vs After Price",
        color_discrete_map={
            "High": COLORS["rose"],
            "Medium": COLORS["amber"],
            "Low": COLORS["lime"],
        },
    )
    return style_figure(fig)


def build_outlier_scatter_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Outlier Detection", "No outlier view is available for the current filters.")

    frame = df.copy()
    z_scores = np.abs(stats.zscore(frame["Change (%)"], nan_policy="omit"))
    if isinstance(z_scores, np.ndarray):
        frame["Z_Score"] = z_scores
    else:
        frame["Z_Score"] = np.zeros(len(frame))
    frame["Outlier_Flag"] = np.where(frame["Z_Score"] > 2, "Outlier", "Regular")

    fig = px.scatter(
        frame,
        x="Disaster_Date",
        y="Change (%)",
        color="Outlier_Flag",
        size=frame["Z_Score"].clip(lower=0.3),
        hover_data=["Company", "Disaster", "Sector", "Location"],
        title="Outlier Detection Over Time",
        color_discrete_map={"Outlier": COLORS["rose"], "Regular": COLORS["teal"]},
    )
    return style_figure(fig)


def compute_normality_test(df: pd.DataFrame) -> dict:
    series = df["Change (%)"].dropna()
    if len(series) < 3:
        return {
            "sample_size": int(len(series)),
            "statistic": None,
            "p_value": None,
            "conclusion": "Not enough samples for a Shapiro-Wilk normality test.",
        }

    stat_value, p_value = stats.shapiro(series)
    return {
        "sample_size": int(len(series)),
        "statistic": round(float(stat_value), 4),
        "p_value": round(float(p_value), 4),
        "conclusion": "Distribution looks approximately normal." if p_value > 0.05 else "Distribution is not normal.",
    }


def compute_hypothesis_test(df: pd.DataFrame) -> dict:
    high = df[df["Impact"] == "High"]["Change (%)"].dropna()
    others = df[df["Impact"] != "High"]["Change (%)"].dropna()

    alpha = 0.05  # significance level

    if len(high) < 2 or len(others) < 2:
        return {
            "test_type": "Independent Two-Sample T-Test",
            "null_hypothesis": "H0: μ1 = μ2 (No difference in mean stock price change)",
            "alternative_hypothesis": "H1: μ1 ≠ μ2 (Significant difference exists)",
            "significance_level": alpha,

            "high_samples": int(len(high)),
            "other_samples": int(len(others)),

            "high_mean": round(float(high.mean()), 2) if len(high) else None,
            "other_mean": round(float(others.mean()), 2) if len(others) else None,

            "high_std": round(float(high.std()), 2) if len(high) else None,
            "other_std": round(float(others.std()), 2) if len(others) else None,

            "t_statistic": None,
            "p_value": None,

            "formula": "t = (x̄1 - x̄2) / sqrt((s1²/n1) + (s2²/n2))",

            "decision": "Insufficient data",
            "interpretation": "Need at least two samples in each group to run the t-test.",
        }

    # Perform Welch’s t-test
    t_stat, p_val = stats.ttest_ind(high, others, equal_var=False)

    significant = p_val < alpha

    return {
        "test_type": "Independent Two-Sample T-Test (Welch’s)",
        "null_hypothesis": "H0: μ1 = μ2 (No difference in mean stock price change)",
        "alternative_hypothesis": "H1: μ1 ≠ μ2 (Significant difference exists)",
        "significance_level": alpha,

        "high_samples": int(len(high)),
        "other_samples": int(len(others)),

        "high_mean": round(float(high.mean()), 2),
        "other_mean": round(float(others.mean()), 2),

        "high_std": round(float(high.std()), 2),
        "other_std": round(float(others.std()), 2),

        "t_statistic": round(float(t_stat), 4),
        "p_value": round(float(p_val), 4),

        "formula": "t = (x̄1 - x̄2) / sqrt((s1²/n1) + (s2²/n2))",

        "decision": "Reject H0" if significant else "Fail to Reject H0",

        "interpretation": (
            "High-impact disasters significantly affect stock-price change."
            if significant
            else "No statistically significant difference observed."
        ),
    }
def build_hypothesis_comparison_chart(hypothesis: dict) -> go.Figure:
    if hypothesis["high_mean"] is None or hypothesis["other_mean"] is None:
        return empty_figure("Hypothesis Comparison", "Not enough samples to compare high-impact events with other events.")

    compare_df = pd.DataFrame(
        {
            "Group": ["High Impact", "Others"],
            "Average Change (%)": [hypothesis["high_mean"], hypothesis["other_mean"]],
        }
    )
    fig = px.bar(
        compare_df,
        x="Group",
        y="Average Change (%)",
        color="Group",
        title="Hypothesis Test Comparison",
        color_discrete_sequence=[COLORS["rose"], COLORS["teal"]],
    )
    return style_figure(fig)


@lru_cache(maxsize=1)
def train_models() -> dict:
    df = load_dataset().copy()
    features = ["Company", "Sector", "Type", "Disaster_Category", "Location", "Year", "Before_Price"]
    X = df[features]
    y_class = df["Impact"]
    y_reg = df["Change (%)"]

    X_train, X_test, y_class_train, y_class_test, y_reg_train, y_reg_test = train_test_split(
        X,
        y_class,
        y_reg,
        test_size=0.2,
        random_state=42,
        stratify=y_class,
    )

    categorical_features = ["Company", "Sector", "Type", "Disaster_Category", "Location"]
    numeric_features = ["Year", "Before_Price"]

    classifier = Pipeline(
        steps=[
            (
                "preprocessor",
                ColumnTransformer(
                    transformers=[
                        ("categorical", create_encoder(), categorical_features),
                        ("numeric", "passthrough", numeric_features),
                    ]
                ),
            ),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=250,
                    max_depth=12,
                    min_samples_leaf=2,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )
    regressor = Pipeline(
        steps=[
            (
                "preprocessor",
                ColumnTransformer(
                    transformers=[
                        ("categorical", create_encoder(), categorical_features),
                        ("numeric", "passthrough", numeric_features),
                    ]
                ),
            ),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=250,
                    max_depth=14,
                    min_samples_leaf=2,
                    random_state=42,
                ),
            ),
        ]
    )

    classifier.fit(X_train, y_class_train)
    regressor.fit(X_train, y_reg_train)

    class_predictions = classifier.predict(X_test)
    reg_predictions = regressor.predict(X_test)

    labels = [label for label in IMPACT_ORDER if label in y_class.unique()]
    cm = confusion_matrix(y_class_test, class_predictions, labels=labels)
    accuracy = accuracy_score(y_class_test, class_predictions)
    rmse = float(np.sqrt(mean_squared_error(y_reg_test, reg_predictions)))
    mae = mean_absolute_error(y_reg_test, reg_predictions)
    r2 = r2_score(y_reg_test, reg_predictions)

    classifier_features = classifier.named_steps["preprocessor"].get_feature_names_out()
    regressor_features = regressor.named_steps["preprocessor"].get_feature_names_out()

    classifier_importance = (
        pd.DataFrame(
            {
                "feature": classifier_features,
                "importance": classifier.named_steps["model"].feature_importances_,
            }
        )
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )
    regressor_importance = (
        pd.DataFrame(
            {
                "feature": regressor_features,
                "importance": regressor.named_steps["model"].feature_importances_,
            }
        )
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )

    return {
        "classifier": classifier,
        "regressor": regressor,
        "features": features,
        "classification": {
            "accuracy": round(float(accuracy), 4),
            "labels": labels,
            "confusion_matrix": cm.tolist(),
            "feature_importance": classifier_importance.to_dict(orient="records"),
        },
        "regression": {
            "rmse": round(float(rmse), 4),
            "mae": round(float(mae), 4),
            "r2": round(float(r2), 4),
            "feature_importance": regressor_importance.to_dict(orient="records"),
        },
        "evaluation": {
            "class_actual": y_class_test.tolist(),
            "class_predicted": class_predictions.tolist(),
            "reg_actual": [float(value) for value in y_reg_test.tolist()],
            "reg_predicted": [float(value) for value in reg_predictions.tolist()],
        },
    }


def pretty_feature_name(raw_name: str) -> str:
    clean = raw_name.replace("categorical__", "").replace("numeric__", "")
    for prefix in ["Company_", "Sector_", "Type_", "Disaster_Category_", "Location_"]:
        if clean.startswith(prefix):
            return clean.replace(prefix, f"{prefix[:-1]}: ")
    return clean.replace("_", " ")


def build_confusion_matrix_chart(model_bundle: dict) -> go.Figure:
    classification = model_bundle["classification"]
    fig = px.imshow(
        classification["confusion_matrix"],
        x=classification["labels"],
        y=classification["labels"],
        text_auto=True,
        color_continuous_scale=[
            [0, "#081020"],
            [0.5, COLORS["indigo"]],
            [1, COLORS["teal"]],
        ],
        title="Confusion Matrix",
        labels={"x": "Predicted", "y": "Actual", "color": "Count"},
    )
    return style_figure(fig)


def build_feature_importance_chart(model_bundle: dict) -> go.Figure:
    importance = pd.DataFrame(model_bundle["classification"]["feature_importance"]).head(12).copy()
    importance["feature"] = importance["feature"].map(pretty_feature_name)
    importance = importance.sort_values("importance", ascending=True)
    fig = px.bar(
        importance,
        x="importance",
        y="feature",
        orientation="h",
        title="Feature Importance",
        color="importance",
        color_continuous_scale=[[0, COLORS["indigo"]], [1, COLORS["teal"]]],
    )
    fig.update_layout(xaxis_title="Importance", yaxis_title="")
    return style_figure(fig)


def build_regression_importance_chart(model_bundle: dict) -> go.Figure:
    importance = pd.DataFrame(model_bundle["regression"]["feature_importance"]).head(12).copy()
    importance["feature"] = importance["feature"].map(pretty_feature_name)
    importance = importance.sort_values("importance", ascending=True)
    fig = px.bar(
        importance,
        x="importance",
        y="feature",
        orientation="h",
        title="Regressor Feature Importance",
        color="importance",
        color_continuous_scale=[[0, COLORS["amber"]], [1, COLORS["teal"]]],
    )
    fig.update_layout(xaxis_title="Importance", yaxis_title="")
    return style_figure(fig)


def build_actual_vs_predicted_chart(model_bundle: dict) -> go.Figure:
    evaluation = model_bundle["evaluation"]
    actual = evaluation["reg_actual"]
    predicted = evaluation["reg_predicted"]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=actual,
            y=predicted,
            mode="markers",
            marker={"color": COLORS["teal"], "size": 10, "opacity": 0.72},
            name="Predictions",
        )
    )
    lower = min(actual + predicted)
    upper = max(actual + predicted)
    fig.add_trace(
        go.Scatter(
            x=[lower, upper],
            y=[lower, upper],
            mode="lines",
            line={"color": COLORS["rose"], "dash": "dash", "width": 2},
            name="Perfect Fit",
        )
    )
    fig.update_layout(
        title="Actual vs Predicted Change (%)",
        xaxis_title="Actual Change (%)",
        yaxis_title="Predicted Change (%)",
    )
    return style_figure(fig)


def build_residual_chart(model_bundle: dict) -> go.Figure:
    evaluation = model_bundle["evaluation"]
    actual = np.array(evaluation["reg_actual"])
    predicted = np.array(evaluation["reg_predicted"])
    residuals = actual - predicted
    fig = px.histogram(
        x=residuals,
        nbins=24,
        title="Residual Distribution",
        color_discrete_sequence=[COLORS["indigo"]],
        labels={"x": "Residual (Actual - Predicted)"},
    )
    fig.add_vline(x=0, line_dash="dash", line_color=COLORS["rose"])
    return style_figure(fig)


def build_class_balance_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return empty_figure("Impact Class Balance", "No class balance is available for the current filters.")

    counts = df["Impact"].value_counts().reindex(IMPACT_ORDER, fill_value=0).reset_index()
    counts.columns = ["Impact", "Count"]
    fig = px.bar(
        counts,
        x="Impact",
        y="Count",
        title="Impact Class Balance",
        color="Impact",
        color_discrete_map={
            "High": COLORS["rose"],
            "Medium": COLORS["amber"],
            "Low": COLORS["lime"],
        },
    )
    fig.update_layout(showlegend=False)
    return style_figure(fig)


def get_filter_options(df: pd.DataFrame) -> dict:
    return {
        "companies": ["All"] + sorted(df["Company"].unique().tolist()),
        "sectors": ["All"] + sorted(df["Sector"].unique().tolist()),
        "locations": ["All"] + sorted(df["Location"].unique().tolist()),
        "disaster_categories": ["Natural"],
        "event_types": ["All"] + sorted(df["Type"].unique().tolist()),
        "date_range": {
            "start": format_date(df["Disaster_Date"].min()),
            "end": format_date(df["Disaster_Date"].max()),
        },
    }


def dataframe_records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    records = df[DISPLAY_COLUMNS].copy()
    records["Disaster_Date"] = records["Disaster_Date"].dt.strftime("%Y-%m-%d")
    for column in [
        "Before_Price",
        "After_Price",
        "Change (%)",
        "Sector_Impact_Score",
        "Sector_Resilience_Score",
    ]:
        records[column] = records[column].round(2)
    return records.to_dict(orient="records")


def build_power_bi_payload(filters: dict) -> dict:
    selected_filters = {
        "Company": filters["company"],
        "Sector": filters["sector"],
        "Disaster Category": filters["disaster_category"],
        "Location": filters["location"],
        "Event Type": filters["event_type"],
        "Range": f"{filters['start_date'] or 'Start'} to {filters['end_date'] or 'End'}",
    }
    if not POWER_BI_EMBED_URL:
        return {
            "enabled": False,
            "embed_url": "",
            "selected_filters": selected_filters,
        }

    query = {
        "filterPaneEnabled": "true",
        "navContentPaneEnabled": "true",
    }
    for key, value in selected_filters.items():
        if value and value not in {"All", "Both", "Start to End"}:
            query[f"ui_{key.lower().replace(' ', '_')}"] = value

    separator = "&" if "?" in POWER_BI_EMBED_URL else "?"
    embed_url = f"{POWER_BI_EMBED_URL}{separator}{urlencode(query)}"
    return {
        "enabled": True,
        "embed_url": embed_url,
        "selected_filters": selected_filters,
    }


def compute_kpis(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "avg_change": 0.0,
            "max_drop": 0.0,
            "recovery_days": 0.0,
            "volatility": 0.0,
            "sector_impact_score": 0.0,
            "sector_resilience_score": 0.0,
            "disaster_frequency": 0,
            "records": 0,
            "companies": 0,
            "date_start": None,
            "date_end": None,
        }

    return {
        "avg_change": round(float(df["Change (%)"].mean()), 2),
        "max_drop": round(float(df["Change (%)"].min()), 2),
        "recovery_days": round(float(df["Recovery_Days"].mean()), 1),
        "volatility": round(float(df["Change (%)"].std(ddof=0)), 2),
        "sector_impact_score": round(float(df["Sector_Impact_Score"].mean()), 2),
        "sector_resilience_score": round(float(df["Sector_Resilience_Score"].mean()), 2),
        "disaster_frequency": int(df["Disaster"].nunique()),
        "records": int(len(df)),
        "companies": int(df["Company"].nunique()),
        "date_start": format_date(df["Disaster_Date"].min()),
        "date_end": format_date(df["Disaster_Date"].max()),
    }


def build_ripple_effects(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []

    ripple_map = []
    sector_type = df.groupby(["Type", "Sector"], as_index=False)["Change (%)"].mean()
    type_order = (
        sector_type.groupby("Type")["Change (%)"].mean().sort_values().index.tolist()
    )

    for disaster_type in type_order[:3]:
        subset = sector_type[sector_type["Type"] == disaster_type].sort_values("Change (%)")
        down_sectors = [
            f"{row['Sector']} ↓"
            for _, row in subset[subset["Change (%)"] < -0.25].head(2).iterrows()
        ]
        up_sectors = [
            f"{row['Sector']} ↑"
            for _, row in subset[subset["Change (%)"] > 0.25]
            .sort_values("Change (%)", ascending=False)
            .head(1)
            .iterrows()
        ]
        steps = [disaster_type.title(), *down_sectors, *up_sectors]
        if len(steps) > 1:
            ripple_map.append(
                {
                    "type": disaster_type.title(),
                    "chain": " -> ".join(steps),
                }
            )
    return ripple_map


def build_auto_insights(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    if df.empty:
        return (
            [
                {
                    "title": "No matching records",
                    "description": "Adjust the filters to unlock insights for another company, sector, or date range.",
                    "severity": "low",
                }
            ],
            [],
        )

    sector_summary = build_sector_summary(df)
    top_drop = df.loc[df["Change (%)"].idxmin()]
    top_gain = df.loc[df["Change (%)"].idxmax()]
    resilient_sector = sector_summary.sort_values("resilience_score", ascending=False).iloc[0]
    volatile_sector = sector_summary.sort_values("volatility", ascending=False).iloc[0]
    frequent_type = df["Type"].value_counts(normalize=True).reset_index()
    frequent_type.columns = ["Type", "Share"]
    dominant = frequent_type.iloc[0]

    insights = [
        {
            "title": "Largest downside move",
            "description": (
                f"{top_drop['Disaster']} caused a {abs(top_drop['Change (%)']):.2f}% drop "
                f"in {top_drop['Company']} within the {top_drop['Sector']} sector."
            ),
            "severity": "high",
        },
        {
            "title": "Best rebound",
            "description": (
                f"{top_gain['Company']} posted a {top_gain['Change (%)']:.2f}% gain after "
                f"{top_gain['Disaster']}."
            ),
            "severity": "low",
        },
        {
            "title": "Sector resilience",
            "description": (
                f"{resilient_sector['Sector']} showed the strongest resilience with a score of "
                f"{resilient_sector['resilience_score']:.1f}."
            ),
            "severity": "low",
        },
        {
            "title": "Volatility hotspot",
            "description": (
                f"{volatile_sector['Sector']} had the highest volatility at "
                f"{volatile_sector['volatility']:.2f}% across the selected events."
            ),
            "severity": "medium",
        },
        {
            "title": "Most common trigger",
            "description": (
                f"{dominant['Type'].title()} events account for {dominant['Share'] * 100:.1f}% "
                f"of the filtered disasters."
            ),
            "severity": "medium",
        },
    ]
    return insights, build_ripple_effects(df)


def page_config(page_name: str, title: str, show_filters: bool) -> dict:
    return {
        "page_name": page_name,
        "page_title": title,
        "show_filters": show_filters,
        "frontend_config": {"powerBiBaseUrl": POWER_BI_EMBED_URL},
    }


def build_descriptive_stats(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    stats = (
        df[["Before_Price", "After_Price", "Change (%)", "Recovery_Days"]]
        .describe()
        .round(2)
        .reset_index()
        .rename(columns={"index": "stat"})
    )
    return stats.to_dict(orient="records")


@app.route("/")
def home_page() -> str:
    return render_template("home.html", **page_config("home", "Home", False))


@app.route("/about")
def about_page() -> str:
    return render_template("about.html", **page_config("about", "About", False))


@app.route("/dashboard")
@app.route("/analyze")
def dashboard_page() -> str:
    return render_template("dashboard.html", **page_config("dashboard", "Dashboard", True))


@app.route("/eda")
def eda_page() -> str:
    return render_template("eda.html", **page_config("eda", "EDA", True))


@app.route("/model")
def model_page() -> str:
    return render_template("model.html", **page_config("model", "Model", True))


@app.route("/prediction")
def prediction_page() -> str:
    return render_template("prediction.html", **page_config("prediction", "Future Prediction", True))


@app.route("/get-data", methods=["GET", "POST"])
def get_data():
    df = load_dataset().copy()
    filters = parse_filters()
    filtered = apply_filters(df, filters)

    response = {
        "filters": filters,
        "options": get_filter_options(df),
        "summary": {
            "records": int(len(filtered)),
            "companies": int(filtered["Company"].nunique()),
            "sectors": int(filtered["Sector"].nunique()),
            "disasters": int(filtered["Disaster"].nunique()),
            "date_range": {
                "start": format_date(filtered["Disaster_Date"].min()) if not filtered.empty else None,
                "end": format_date(filtered["Disaster_Date"].max()) if not filtered.empty else None,
            },
        },
        "rows": dataframe_records(filtered),
    }
    return jsonify(response)


@app.route("/analysis", methods=["GET", "POST"])
def analysis():
    df = load_dataset().copy()
    filters = parse_filters()
    filtered = apply_filters(df, filters)

    response = {
        "filters": filters,
        "kpis": compute_kpis(filtered),
        "figures": {
            "line": serialize_figure(build_line_chart(filtered)),
            "bar": serialize_figure(build_bar_chart(filtered)),
            "sector": serialize_figure(build_sector_chart(filtered)),
            "frequency": serialize_figure(build_frequency_chart(filtered)),
            "location": serialize_figure(build_location_chart(filtered)),
        },
        "sector_summary": build_sector_summary(filtered).to_dict(orient="records"),
        "power_bi": build_power_bi_payload(filters),
    }
    return jsonify(response)


@app.route("/eda-data", methods=["GET", "POST"])
def eda_data():
    df = load_dataset().copy()
    filters = parse_filters()
    filtered = apply_filters(df, filters)
    normality = compute_normality_test(filtered)
    hypothesis = compute_hypothesis_test(filtered)
    response = {
        "filters": filters,
        "kpis": compute_kpis(filtered),
        "figures": {
            "histogram": serialize_figure(build_histogram_chart(filtered)),
            "impact_pie": serialize_figure(build_impact_pie_chart(filtered)),
            "box_plot": serialize_figure(build_box_plot(filtered)),
            "sector_bar": serialize_figure(build_sector_avg_bar_chart(filtered)),
            "type_bar": serialize_figure(build_disaster_type_bar_chart(filtered)),
            "correlation": serialize_figure(build_heatmap(filtered)),
            "year_heatmap": serialize_figure(build_year_type_heatmap(filtered)),
            "sector_bubble": serialize_figure(build_sector_bubble_chart(filtered)),
            "multivariate_scatter": serialize_figure(build_multivariate_scatter_chart(filtered)),
            "price_scatter": serialize_figure(build_price_scatter_chart(filtered)),
            "outlier_scatter": serialize_figure(build_outlier_scatter_chart(filtered)),
            "hypothesis_compare": serialize_figure(build_hypothesis_comparison_chart(hypothesis)),
        },
        "summary_stats": build_descriptive_stats(filtered),
        "sector_summary": build_sector_summary(filtered).to_dict(orient="records"),
        "normality_test": normality,
        "hypothesis_test": hypothesis,
        "sample_rows": dataframe_records(filtered)[:15],
    }
    return jsonify(response)


@app.route("/model-data", methods=["GET", "POST"])
def model_data():
    base_df = load_dataset().copy()
    filters = parse_filters()
    filtered = apply_filters(base_df, filters)
    model_bundle = train_models()

    response = {
        "filters": filters,
        "metrics": {
            "classifier_accuracy": model_bundle["classification"]["accuracy"],
            "regression_rmse": model_bundle["regression"]["rmse"],
            "regression_mae": model_bundle["regression"]["mae"],
            "regression_r2": model_bundle["regression"]["r2"],
            "training_records": int(len(base_df)),
            "filtered_records": int(len(filtered)),
        },
        "figures": {
            "confusion_matrix": serialize_figure(build_confusion_matrix_chart(model_bundle)),
            "classifier_importance": serialize_figure(build_feature_importance_chart(model_bundle)),
            "regressor_importance": serialize_figure(build_regression_importance_chart(model_bundle)),
            "actual_vs_predicted": serialize_figure(build_actual_vs_predicted_chart(model_bundle)),
            "residuals": serialize_figure(build_residual_chart(model_bundle)),
            "class_balance": serialize_figure(build_class_balance_chart(filtered if not filtered.empty else base_df)),
        },
        "top_classifier_features": model_bundle["classification"]["feature_importance"][:12],
        "top_regressor_features": model_bundle["regression"]["feature_importance"][:12],
    }
    return jsonify(response)


@app.route("/insights", methods=["GET", "POST"])
def insights():
    df = load_dataset().copy()
    filters = parse_filters()
    filtered = apply_filters(df, filters)
    insight_cards, ripple_effects = build_auto_insights(filtered)
    return jsonify(
        {
            "filters": filters,
            "insights": insight_cards,
            "ripple_effects": ripple_effects,
        }
    )


@app.route("/predict", methods=["POST"])
def predict():
    payload = request.get_json(silent=True) or {}
    try:
        before_price = float(payload.get("before_price") or 0)
        year = int(payload.get("year") or load_dataset()["Year"].max())
    except (TypeError, ValueError):
        return jsonify({"error": "year and before_price must be numeric."}), 400

    if before_price <= 0:
        return jsonify({"error": "before_price must be a positive number."}), 400

    base_df = load_dataset().copy()
    model_bundle = train_models()

    sector = str(payload.get("sector") or base_df["Sector"].mode().iat[0])
    disaster_type = str(payload.get("type") or payload.get("event_type") or base_df["Type"].mode().iat[0]).lower()
    company = str(payload.get("company") or base_df["Company"].mode().iat[0])
    location = str(payload.get("location") or "India")
    disaster_category = str(payload.get("disaster_category") or infer_disaster_category(disaster_type, disaster_type))

    input_row = pd.DataFrame(
        [
            {
                "Company": company,
                "Sector": sector,
                "Type": disaster_type,
                "Disaster_Category": disaster_category,
                "Location": location,
                "Year": year,
                "Before_Price": before_price,
            }
        ]
    )

    predicted_impact = model_bundle["classifier"].predict(input_row)[0]
    predicted_change = float(model_bundle["regressor"].predict(input_row)[0])
    predicted_after_price = round(before_price * (1 + predicted_change / 100), 2)

    probabilities = model_bundle["classifier"].predict_proba(input_row)[0]
    classes = model_bundle["classifier"].named_steps["model"].classes_
    probability_payload = [
        {"label": label, "value": round(float(prob) * 100, 2)}
        for label, prob in zip(classes, probabilities)
    ]

    sector_slice = base_df[base_df["Sector"] == sector]
    type_slice = base_df[base_df["Type"] == disaster_type]
    impact_score = (
        float(sector_slice["Sector_Impact_Score"].mean())
        if not sector_slice.empty
        else float(base_df["Sector_Impact_Score"].mean())
    )
    resilience_score = (
        float(sector_slice["Sector_Resilience_Score"].mean())
        if not sector_slice.empty
        else float(base_df["Sector_Resilience_Score"].mean())
    )
    type_volatility = (
        float(type_slice["Change (%)"].std(ddof=0))
        if len(type_slice) > 1
        else float(base_df["Change (%)"].std(ddof=0))
    )
    recovery_days = estimate_recovery_days(
        predicted_change,
        impact_score,
        resilience_score,
        type_volatility,
    )

    return jsonify(
        {
            "prediction": {
                "impact": predicted_impact,
                "change_pct": round(predicted_change, 2),
                "after_price": predicted_after_price,
                "price_difference": round(predicted_after_price - before_price, 2),
                "recovery_days": recovery_days,
            },
            "probabilities": probability_payload,
            "model_metrics": {
                "classifier_accuracy": model_bundle["classification"]["accuracy"],
                "regression_rmse": model_bundle["regression"]["rmse"],
                "regression_mae": model_bundle["regression"]["mae"],
                "regression_r2": model_bundle["regression"]["r2"],
            },
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
