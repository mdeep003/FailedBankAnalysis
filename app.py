import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import matplotlib.pyplot as plt

st.set_page_config(page_title="Failed Banks Analysis", layout="wide")
st.title("Failed Banks Analysis (2000–Present)")
st.caption("Interactive exploration of FDIC failed bank data")

@st.cache_data
def load_csv(file_or_path):
    df = pd.read_csv(file_or_path, dtype=str)
    # clean headers - remove special characters and normalize
    df.columns = (df.columns.str.strip()
                  .str.replace("†", "")  # Remove dagger symbols
                  .str.lower()
                  .str.replace(" ", "_"))
    # normalize common variants
    if "closingdate" in df.columns and "closing_date" not in df.columns:
        df = df.rename(columns={"closingdate": "closing_date"})
    if "acquiringinstitution" in df.columns and "acquiring_institution" not in df.columns:
        df = df.rename(columns={"acquiringinstitution": "acquiring_institution"})
    # parse date (flexible)
    if "closing_date" in df.columns:
        df["closing_date"] = pd.to_datetime(df["closing_date"], errors="coerce")
    # tidy strings
    for c in ["bank_name","city","state","acquiring_institution","fund"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
    if "state" in df.columns:
        df["state"] = df["state"].str.upper()
    return df

uploaded = st.sidebar.file_uploader("Upload your FDIC Failed Banks CSV", type=["csv"])
default_path = "failed_banks.csv"  # change if your file is named differently
try:
    if uploaded is not None:
        df = load_csv(uploaded)
    else:
        df = load_csv(default_path)
except FileNotFoundError:
    st.warning(f"Could not find '{default_path}'. Upload a CSV in the sidebar to continue.")
    st.stop()

years = sorted(df["closing_date"].dropna().dt.year.unique()) if "closing_date" in df.columns else []
states = sorted(df["state"].dropna().unique()) if "state" in df.columns else []
c1, c2 = st.sidebar.columns(2)
year_min = c1.selectbox("Start Year", options=years, index=0) if years else None
year_max = c2.selectbox("End Year", options=years, index=len(years)-1) if years else None
state_sel = st.sidebar.multiselect("States", options=states, default=[])

df_f = df.copy()
if years:
    df_f = df_f[(df_f["closing_date"].dt.year >= year_min) & (df_f["closing_date"].dt.year <= year_max)]
if state_sel:
    df_f = df_f[df_f["state"].isin(state_sel)]

k1, k2, k3 = st.columns(3)
with k1:
    st.metric("Total Failures", f"{len(df_f):,}")
with k2:
    if "closing_date" in df_f.columns and df_f["closing_date"].notna().any():
        yvc = df_f["closing_date"].dt.year.value_counts().sort_index()
        st.metric("Peak Year", int(yvc.idxmax()) if not yvc.empty else "—")
    else:
        st.metric("Peak Year", "—")
with k3:
    if "state" in df_f.columns and df_f["state"].notna().any():
        st.metric("Top State", df_f["state"].value_counts().idxmax())
    else:
        st.metric("Top State", "—")

st.divider()

st.subheader("Failures per Year")
if "closing_date" in df_f.columns and df_f["closing_date"].notna().any():
    failures_per_year = df_f["closing_date"].dt.year.value_counts().sort_index().reset_index()
    failures_per_year.columns = ["year","failures"]
    fig_year = px.bar(failures_per_year, x="year", y="failures", title="Bank Failures per Year")
    st.plotly_chart(fig_year, use_container_width=True)
else:
    st.info("No valid dates to plot.")

st.subheader("Geographic Hotspots (USA)")
if "state" in df_f.columns and df_f["state"].notna().any():
    valid_states = {
        "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY",
        "LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND",
        "OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"
    }
    state_counts = (df_f.assign(state=df_f["state"].str.upper())
                      .loc[lambda d: d["state"].isin(valid_states)]
                      .groupby("state").size().reset_index(name="failures"))
    if not state_counts.empty:
        fig_map = px.choropleth(
            state_counts,
            locations="state",
            locationmode="USA-states",   # note: lowercase 'states'
            color="failures",
            scope="usa",
            title="Failed Banks by State"
        )
        st.plotly_chart(fig_map, use_container_width=True)
    else:
        st.info("No state data to display.")
else:
    st.info("State column not found.")

st.subheader("Consolidation: Who Absorbed Failures?")
if "acquiring_institution" in df_f.columns:
    acq_counts = (df_f.assign(acq=df_f["acquiring_institution"].fillna("Unknown").str.strip())
                    .groupby("acq").size().reset_index(name="count")
                    .sort_values("count", ascending=False))
    if not acq_counts.empty:
        fig_treemap = px.treemap(acq_counts, path=["acq"], values="count",
                                 title="Acquirers of Failed Banks (Treemap)")
        st.plotly_chart(fig_treemap, use_container_width=True)

        # Pareto (cumulative share)
        counts = acq_counts["count"].to_numpy()
        total = counts.sum()
        if total > 0:
            cum = np.cumsum(counts) / total
            top_50 = int(np.searchsorted(cum, 0.5)) + 1
            top_80 = int(np.searchsorted(cum, 0.8)) + 1
            st.caption(f"Top **{top_50}** acquirers ≈ 50% of resolutions; Top **{top_80}** ≈ 80%.")
    else:
        st.info("No acquisition data to display.")
else:
    st.info("Acquiring institution column not found.")

st.subheader("Consolidation Over Time (HHI)")
if "closing_date" in df_f.columns and df_f["closing_date"].notna().any() and "acquiring_institution" in df_f.columns:
    year_acq = (df_f.assign(year=df_f["closing_date"].dt.year,
                            acq=df_f["acquiring_institution"].fillna("Unknown").str.strip())
                  .dropna(subset=["year"])
                  .groupby(["year","acq"]).size().reset_index(name="count"))
    if not year_acq.empty:
        hhi = (year_acq.groupby("year")["count"]
               .apply(lambda x: ((x / x.sum())**2).sum())
               .reset_index(name="HHI"))
        fig_hhi = px.line(hhi, x="year", y="HHI", markers=True, title="HHI of Acquirers by Year")
        st.plotly_chart(fig_hhi, use_container_width=True)
    else:
        st.info("No yearly acquisition data available.")
else:
    st.info("Need valid dates and acquiring institutions to compute HHI.")

st.divider()
st.caption("Tip: Upload a CSV in the sidebar to replace the default file. Data cleaning (headers/dates) happens automatically.")
