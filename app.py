"""
PerformanceRun — Streamlit Dashboard
Skill aplicada: running-dashboard
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta

# ── Configuração ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="PerformanceRun 🏃", page_icon="🏃",
                   layout="wide", initial_sidebar_state="expanded")

# ══════════════════════════════════════════════════════════════════════════════
#  SISTEMA DE CORES (skill: running-dashboard §2)
# ══════════════════════════════════════════════════════════════════════════════
INTENSITY_COLORS = {
    "Leve":           "#2ECC71",
    "Moderado":       "#3498DB",
    "Moderado Firme": "#F39C12",
    "Forte":          "#E67E22",
    "Muito Forte":    "#E74C3C",
    "Skate":          "#95A5A6",
}
INTENSITY_ORDER = ["Leve","Moderado","Moderado Firme","Forte","Muito Forte","Skate"]

ZONA_COLORS = {
    "Sem FC":            "#BDC3C7",
    "Z1 - Regenerativo": "#2ECC71",
    "Z2 - Aeróbico":     "#3498DB",
    "Z3 - Tempo":        "#F39C12",
    "Z4 - Limiar":       "#E67E22",
    "Z5 - VO2max":       "#E74C3C",
}
ZONA_ORDER = ["Sem FC","Z1 - Regenerativo","Z2 - Aeróbico",
              "Z3 - Tempo","Z4 - Limiar","Z5 - VO2max"]

GREEN, BLUE, AMBER, RED, PURPLE, GRAY = \
    "#2ECC71","#3498DB","#F39C12","#E74C3C","#9B59B6","#95A5A6"

# Tradução de meses e dias para PT-BR
MESES_PT = {"Jan":"jan","Feb":"fev","Mar":"mar","Apr":"abr","May":"mai",
             "Jun":"jun","Jul":"jul","Aug":"ago","Sep":"set","Oct":"out",
             "Nov":"nov","Dec":"dez"}
DIAS_PT   = {"Monday":"Seg","Tuesday":"Ter","Wednesday":"Qua",
             "Thursday":"Qui","Friday":"Sex","Saturday":"Sáb","Sunday":"Dom"}
DIAS_ORDER_PT = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]

def mesano_pt(dt_series):
    """Converte datetime para 'jan 2025', 'fev 2025' etc. (PT-BR)."""
    return dt_series.dt.strftime("%b %Y").apply(
        lambda x: f"{MESES_PT.get(x[:3], x[:3])} {x[4:]}")

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS (skill: running-dashboard §1, §7)
# ══════════════════════════════════════════════════════════════════════════════
def normalize_dt(col):
    """Remove timezone de qualquer coluna de data (UTC-aware ou tz-naive)."""
    return pd.to_datetime(col, dayfirst=True, errors="coerce", utc=True).dt.tz_convert(None)

def fmt_pace(sec):
    """Formata segundos/km em mm:ss usando floor (trunca, não arredonda).
    3:39.8 → 3:39  (nunca 3:40). Correto para exibição de pace."""
    if pd.isna(sec) or sec <= 0: return "—"
    s = int(sec)          # floor — preserva o segundo exato
    return f"{s // 60}:{s % 60:02d}"

def set_pace_yaxis(fig, pace_sec_series, step_sec=30):
    """Formata o eixo Y de pace em mm:ss (ex: 4:30, 5:00, 5:30)."""
    mn = max(0, int(pace_sec_series.min()) - step_sec)
    mx = int(pace_sec_series.max()) + step_sec
    vals  = list(range(mn - mn % step_sec, mx + step_sec, step_sec))
    fig.update_yaxes(
        autorange="reversed",
        tickvals=[v / 60 for v in vals],
        ticktext=[fmt_pace(v) for v in vals],
        title="Pace (min/km)",
    )
    return fig

def zona_fc(hr):
    if pd.isna(hr): return "Sem FC"
    if hr < 137:    return "Z1 - Regenerativo"
    if hr < 165:    return "Z2 - Aeróbico"
    if hr < 175:    return "Z3 - Tempo"
    if hr < 185:    return "Z4 - Limiar"
    return "Z5 - VO2max"

# ── Palavras-chave para classificação por nome (1ª prioridade) ───────────────
# Ordem importa: mais específico primeiro
KEYWORDS_INTENSIDADE = {
    "Muito Forte": ["intervalad","tiro","interval","vo2","muito forte",
                    "repetição","repeticao","série","serie","prova","teste"],
    "Forte":       ["fartlek","forte","threshold","limiar"],
    "Moderado Firme": ["progressiv","ritmado","moderado firme","tempo run"],
    "Moderado":    ["longo","moderado","moder","base","contínuo","continuo",
                    "aeróbic","aerobic"],
    "Leve":        ["regenerat","fácil","facil","easy","recovery",
                    "leve","caminhad","walk","solto"],
}

def _classify_by_name(name):
    """Retorna intensidade baseada em palavras-chave no nome. None se não encontrar."""
    if not name or pd.isna(name):
        return None
    n = str(name).lower()
    for intensity, keywords in KEYWORDS_INTENSIDADE.items():
        if any(kw in n for kw in keywords):
            return intensity
    return None

def calc_intensidade_fc(laps_df, act_names=None):
    """
    Classificação em duas etapas:

    1ª — Nome da atividade (palavras-chave): se o nome der uma pista clara,
         usa ela diretamente. Resolve o caso de FC naturalmente alta em treinos fáceis.

    2ª — Zonas de FC RELATIVAS ao FCmax do próprio atleta (fallback):
         usa % da FC máxima registrada nos dados, adaptando-se a qualquer
         nível de condicionamento sem depender de thresholds absolutos.

         Zonas relativas:
           Z1 < 65% FCmax  |  Z2 < 78%  |  Z3 < 85%  |  Z4 < 92%  |  Z5 ≥ 92%

    Remoção inteligente de aquecimento/desaquecimento:
    Remove 1º/último lap somente se estiver em zona fácil (Z1/Z2/Sem FC).
    Se o atleta começar forte desde o 1º lap, ele é mantido.
    """
    if laps_df.empty or "average_heartrate" not in laps_df.columns:
        return pd.Series(dtype=str)

    # FCmax do atleta baseado nos dados (mínimo de 150 para evitar outliers)
    hr_max = laps_df["average_heartrate"].dropna().max()
    hr_max = hr_max if (not pd.isna(hr_max) and hr_max > 150) else 195

    # Zona relativa baseada em % do FCmax
    def zona_rel(hr):
        if pd.isna(hr): return "Sem FC"
        p = hr / hr_max
        if p < 0.65: return "Z1"
        if p < 0.78: return "Z2"
        if p < 0.85: return "Z3"
        if p < 0.92: return "Z4"
        return "Z5"

    laps_df = laps_df.copy()
    laps_df["Zona_Rel"] = laps_df["average_heartrate"].apply(zona_rel)
    ZONAS_FACEIS_REL = {"Z1", "Z2", "Sem FC"}

    results = {}

    for aid, grp in laps_df.groupby("activity_id"):

        # ── 1ª prioridade: nome da atividade ─────────────────────────────────
        if act_names is not None and aid in act_names.index:
            by_name = _classify_by_name(act_names.get(aid))
            if by_name:
                results[aid] = by_name
                continue

        # ── 2ª prioridade: zonas relativas de FC ─────────────────────────────
        grp = grp.sort_values("lap_index").copy()

        # Remove aquecimento/desaquecimento (só se forem laps fáceis)
        if len(grp) > 3:
            if grp.iloc[0]["Zona_Rel"] in ZONAS_FACEIS_REL:
                grp = grp.iloc[1:]
            if len(grp) > 1 and grp.iloc[-1]["Zona_Rel"] in ZONAS_FACEIS_REL:
                grp = grp.iloc[:-1]

        total = grp["moving_time_sec"].sum()
        if total == 0:
            continue

        sem_fc = grp[grp["Zona_Rel"] == "Sem FC"]["moving_time_sec"].sum()
        if sem_fc / total > 0.5:
            continue

        def pct(z):
            return grp[grp["Zona_Rel"] == z]["moving_time_sec"].sum() / total

        z1, z2, z3 = pct("Z1"), pct("Z2"), pct("Z3")
        z4, z5     = pct("Z4"), pct("Z5")
        pct_z45    = z4 + z5
        pct_z12    = z1 + z2

        if z5 >= 0.20 or pct_z45 >= 0.50:
            intensity = "Muito Forte"
        elif pct_z45 >= 0.30:
            intensity = "Forte"
        elif pct_z45 >= 0.15 or z3 >= 0.25:
            intensity = "Moderado Firme"
        elif pct_z12 >= 0.75:
            intensity = "Leve"
        else:
            intensity = "Moderado"

        results[aid] = intensity

    return pd.Series(results, name="Intensidade_FC")

def cat_intensity(df):
    """Aplica Categorical ordenado para plots consistentes."""
    if "Intensidade" not in df.columns: return df
    df = df.copy()
    df["Intensidade"] = pd.Categorical(df["Intensidade"],
                                        categories=INTENSITY_ORDER, ordered=True)
    return df

# ══════════════════════════════════════════════════════════════════════════════
#  DADOS (skill: running-dashboard §1 — cache + normalize)
# ══════════════════════════════════════════════════════════════════════════════
BASE = "data/processed"
# BASE = "data/namorada/processed"   # ← Thais

@st.cache_data(ttl=300)
def load_all(base):
    import os

    def read(name):
        p = f"{base}/{name}"
        return pd.read_csv(p, sep=";", encoding="utf-8-sig") \
               if os.path.exists(p) else pd.DataFrame()

    # Activities
    act = read("activities_consolidated.csv")
    if not act.empty:
        act["start_date"] = normalize_dt(act["start_date"])
        act["MesAno"]     = mesano_pt(act["start_date"])
        act["MesAnoOrd"]  = act["start_date"].dt.to_period("M").apply(lambda x: x.ordinal)
        act["Semana"]     = act["start_date"].dt.to_period("W").apply(lambda x: x.ordinal)
        act["SemanaStr"]  = act["start_date"].dt.strftime("Sem %V/%Y")
        act["DiaSemana"]  = act["start_date"].dt.day_name().map(DIAS_PT)
        rename_map = {c: "Intensidade" for c in act.columns if c.lower() == "intensidade"}
        act = act.rename(columns=rename_map)
        if "Intensidade" in act.columns:
            # Coluna pode ser float (tudo NaN) se o atleta não classificou manualmente
            if act["Intensidade"].dropna().empty:
                act = act.drop(columns=["Intensidade"])   # sem dados — descarta
            else:
                act["Intensidade"] = act["Intensidade"].astype(str).str.strip().str.title()
                act["Intensidade"] = act["Intensidade"].replace("Nan", None)

    # Laps
    laps = read("activity_laps_consolidated.csv")
    if not laps.empty:
        laps["start_date"] = normalize_dt(laps["start_date"])
        laps["MesAno"]     = mesano_pt(laps["start_date"])
        laps["MesAnoOrd"]  = laps["start_date"].dt.to_period("M").apply(lambda x: x.ordinal)
        laps["Zona FC"]    = laps["average_heartrate"].apply(zona_fc)

    # Best Efforts
    be = read("activity_best_efforts_consolidated.csv")
    if not be.empty:
        be["start_date"] = normalize_dt(be["start_date"])
        be["MesAno"]     = mesano_pt(be["start_date"])
        be["MesAnoOrd"]  = be["start_date"].dt.to_period("M").apply(lambda x: x.ordinal)

    # Calcula Intensidade_FC e junta nas atividades
    if not laps.empty and not act.empty:
        # Passa nomes das atividades para classificação por palavra-chave
        act_names = act.set_index("id")["name"] if "name" in act.columns else None
        intensidade_fc = calc_intensidade_fc(laps, act_names=act_names)
        if not intensidade_fc.empty:
            fc_df = intensidade_fc.reset_index()
            fc_df.columns = ["id", "Intensidade_FC"]
            act = act.merge(fc_df, on="id", how="left")

    return act, laps, be

df_raw, laps_raw, be_raw = load_all(BASE)

# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR — FILTROS (skill: running-dashboard §6)
# ══════════════════════════════════════════════════════════════════════════════
st.sidebar.title("🎛️ Filtros")
min_d = df_raw["start_date"].min().date()
max_d = df_raw["start_date"].max().date()
date_range = st.sidebar.date_input("Período", value=(min_d, max_d),
                                    min_value=min_d, max_value=max_d)
sports_all      = sorted(df_raw["sport_type"].dropna().unique())
# Default só inclui modalidades que existem nos dados do atleta
_default_sports = [s for s in ["Run","TrailRun"] if s in sports_all]
if not _default_sports:                  # se nenhuma corrida, seleciona tudo
    _default_sports = sports_all
selected_sports = st.sidebar.multiselect("Modalidade", sports_all,
                                          default=_default_sports)
# Toggle: classificação automática (FC) ou manual
has_fc_class = ("Intensidade_FC" in df_raw.columns
                and df_raw["Intensidade_FC"].notna().any())
if has_fc_class:
    int_mode = st.sidebar.radio(
        "Classificação de Intensidade",
        ["Automática (FC)", "Manual"],
        help="Automática: % tempo em zona de FC por atividade (exclui aquecimento/desaquecimento). "
             "Manual: sua coluna Intensidade preenchida à mão.")
else:
    int_mode = "Manual"

int_col  = "Intensidade_FC" if int_mode == "Automática (FC)" else "Intensidade"
int_opts = [i for i in INTENSITY_ORDER
            if int_col in df_raw.columns
            and i in df_raw[int_col].dropna().unique()]
sel_int  = st.sidebar.multiselect("Filtrar Intensidade", int_opts, default=int_opts)

s_dt = pd.Timestamp(date_range[0]) if len(date_range) >= 1 else pd.Timestamp(min_d)
e_dt = pd.Timestamp(date_range[1]) if len(date_range) == 2 else pd.Timestamp(max_d)

def filt_act(d):
    mask = ((d["start_date"] >= s_dt) & (d["start_date"] <= e_dt)
            & d["sport_type"].isin(selected_sports))
    if sel_int and int_col in d.columns:
        mask &= d[int_col].isin(sel_int)
    return d[mask].copy()

def filt_laps(d):
    if d.empty: return d
    return d[(d["start_date"] >= s_dt) & (d["start_date"] <= e_dt)
             & d["activity_sport_type"].isin(selected_sports)].copy()

def filt_be(d):
    if d.empty: return d
    return d[(d["start_date"] >= s_dt) & (d["start_date"] <= e_dt)
             & d["activity_sport_type"].isin(selected_sports)].copy()

df      = filt_act(df_raw)
laps    = filt_laps(laps_raw)
be      = filt_be(be_raw)
df_run  = df[df["sport_type"].isin(["Run","TrailRun"])].copy()
lps_run = laps[laps["activity_sport_type"].isin(["Run","TrailRun"])].copy() \
          if not laps.empty else laps

# Coluna unificada "Intensidade" — todos os gráficos usam essa, sem precisar mudar nada
# Se Automática (FC) selecionada, sobrescreve com Intensidade_FC; senão usa Manual
for _df in [df, df_run]:
    if int_col in _df.columns:
        _df["Intensidade"] = _df[int_col]
    elif "Intensidade" not in _df.columns:
        _df["Intensidade"] = None

# Helpers de best efforts — usam dados NÃO filtrados (records são all-time)
def melhor_be(nome):
    if be_raw.empty: return "—"
    s = be_raw[be_raw["name"].str.lower() == nome.lower()]
    return fmt_pace(s["pace_sec_km"].min()) if not s.empty else "—"

def melhor_3km():
    # Usa laps não filtrados para garantir melhor all-time
    lps_all = laps_raw[laps_raw["activity_sport_type"].isin(["Run","TrailRun"])].copy() \
              if not laps_raw.empty else laps_raw
    if lps_all.empty: return "—"
    best = None
    for _, grp in lps_all.groupby("activity_id"):
        km = grp[(grp["distance_m"] >= 900) & (grp["distance_m"] <= 1100)]
        if len(km) >= 3:
            t = km.nsmallest(3,"lap_index")["moving_time_sec"].sum()
            if best is None or t < best: best = t
    return fmt_pace(best / 3) if best else "—"

# ══════════════════════════════════════════════════════════════════════════════
#  ABAS
# ══════════════════════════════════════════════════════════════════════════════
tab_geral, tab_perf, tab_fc, tab_intel, tab_elev, tab_clima, tab_metas, tab_vol, tab_coach = st.tabs([
    "📊 Visão Geral","⚡ Performance e Pace","❤️ Frequência Cardíaca",
    "🧠 Inteligência de Treino","⛰️ Elevação","🌤️ Clima",
    "🎯 Metas e Benchmarks","📈 Volume e Evolução","🧑‍🏫 Visão Treinador",
])


# ══════════════════════════════════════════════════════════════════════════════
#  1 · VISÃO GERAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_geral:
    st.title("📊 Visão Geral")

    # KPIs — 3+3 layout (skill §5)
    c1,c2,c3 = st.columns(3)
    c1.metric("🏃 Atividades",  f"{len(df):,}")
    c2.metric("📏 Distância",   f"{df['distance_km'].sum():,.0f} km")
    c3.metric("⏱️ Tempo Total", f"{df['moving_time_sec'].sum()/3600:,.1f} h")

    c4,c5,c6 = st.columns(3)
    c4.metric("⚡ Pace Médio",  fmt_pace(df_run["pace_sec_km"].mean()))
    fc_med = df_run["average_heartrate"].mean()
    c5.metric("❤️ FC Média",   f"{fc_med:.0f} bpm" if not pd.isna(fc_med) else "—")
    cal = df["calories"].sum()
    c6.metric("🔥 Calorias",   f"{cal:,.0f} kcal" if df["calories"].notna().any() else "—")

    st.markdown("---")
    col_a, col_b = st.columns(2)

    # Distância por mês
    with col_a:
        df_m = (df.groupby(["MesAnoOrd","MesAno"])
                  .agg(KM=("distance_km","sum")).reset_index()
                  .sort_values("MesAnoOrd"))
        fig = px.bar(df_m, x="MesAno", y="KM",
                     title="📏 Distância por Mês (km)",
                     color_discrete_sequence=[BLUE],
                     labels={"KM":"km","MesAno":""}, text_auto=".0f")
        fig.update_traces(textposition="outside")
        fig.update_layout(xaxis_tickangle=-45, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # Mix de intensidade — donut com cores corretas
    with col_b:
        if "Intensidade" in df.columns and df["Intensidade"].notna().any():
            df_i = cat_intensity(df)["Intensidade"].value_counts().reset_index()
            df_i.columns = ["Intensidade","Qtd"]
            df_i = df_i[df_i["Intensidade"].isin(INTENSITY_ORDER)]
            fig = px.pie(df_i, names="Intensidade", values="Qtd",
                         title="🎯 Mix de Intensidade", hole=0.42,
                         color="Intensidade", color_discrete_map=INTENSITY_COLORS,
                         category_orders={"Intensidade": INTENSITY_ORDER})
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)

            # Critérios discretos — só aparece quando o usuário abre
            label = "🤖 Automática (FC)" if int_mode == "Automática (FC)" else "✍️ Manual"
            with st.expander(f"Como cada categoria é definida? — {label}"):
                if int_mode == "Automática (FC)":
                    st.markdown(
                        "A classificação usa **duas etapas em sequência**:\n\n"
                        "**1ª — Nome da atividade:** se o nome contiver palavras-chave "
                        "(ex: *regenerativo*, *intervalado*, *progressivo*), "
                        "essa informação tem prioridade — resolve casos onde a FC "
                        "naturalmente fica alta mesmo em treinos fáceis.\n\n"
                        "**2ª — Zonas de FC relativas ao seu FCmax** (quando o nome "
                        "não dá pista): usa % da sua FC máxima registrada nos dados, "
                        "adaptando-se automaticamente a qualquer nível de condicionamento."
                    )
                    st.markdown("**Critérios por zona relativa:**")
                    criterios = {
                        "🟢 Leve":           "Z1+Z2 ≥ 75%  *(< 78% FCmax)*",
                        "🔵 Moderado":       "Demais casos",
                        "🟡 Moderado Firme": "Z4+Z5 ≥ 15% **ou** Z3 ≥ 25%  *(78–92% FCmax)*",
                        "🟠 Forte":          "Z4+Z5 ≥ 30%",
                        "🔴 Muito Forte":    "Z5 ≥ 20% **ou** Z4+Z5 ≥ 50%  *(> 92% FCmax)*",
                    }
                    for cat, criterio in criterios.items():
                        st.markdown(f"**{cat}** → {criterio}")
                    st.caption(
                        "Palavras-chave reconhecidas: regenerativo, fácil, easy, longo, "
                        "moderado, progressivo, ritmado, fartlek, forte, intervalado, "
                        "tiro, prova, teste, entre outras."
                    )
                else:
                    st.markdown(
                        "Modo **Manual** — usando a coluna `Intensidade` "
                        "que você preencheu com base na sua percepção de cada treino.\n\n"
                        "Para usar classificação automática baseada em FC, "
                        "selecione **Automática (FC)** na sidebar."
                    )

    # Pace mensal com rolling 3M (skill §4)
    df_p = (df_run[df_run["pace_sec_km"].notna()]
            .groupby(["MesAnoOrd","MesAno"])
            .agg(Pace=("pace_sec_km","mean")).reset_index()
            .sort_values("MesAnoOrd"))
    df_p["Pace_fmt"] = df_p["Pace"].apply(fmt_pace)
    df_p["Pace_min"] = df_p["Pace"] / 60
    df_p["Roll3M"]   = df_p["Pace_min"].rolling(3, min_periods=1).mean()

    fig = go.Figure()
    fig.add_bar(x=df_p["MesAno"], y=df_p["Pace_min"],
                name="Pace mensal", marker_color=BLUE, opacity=0.5,
                customdata=df_p["Pace_fmt"],
                hovertemplate="%{x}<br>Pace: %{customdata}/km<extra></extra>")
    fig.add_scatter(x=df_p["MesAno"], y=df_p["Roll3M"], name="Média 3M",
                    mode="lines+markers", line=dict(color=RED, width=2, dash="dash"))
    set_pace_yaxis(fig, df_p["Pace"] )
    fig.update_layout(title="⚡ Evolução do Pace Médio + Média Móvel 3M",
                      xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("📖 **Como ler:** barras = pace médio do mês. Linha tracejada = média dos últimos 3 meses. "
               "Eixo Y invertido: quanto mais alto no gráfico, mais rápido.")

    # Insight de pace (skill §9)
    if len(df_p) >= 2:
        last_pace = df_p["Pace_min"].iloc[-1]
        avg_pace  = df_p["Pace_min"].mean()
        if last_pace < avg_pace:
            st.success(f"📈 Pace do último mês ({df_p['Pace_fmt'].iloc[-1]}/km) "
                       f"abaixo da média histórica ({fmt_pace(avg_pace*60)}/km) — evolução positiva!")
        else:
            st.info(f"ℹ️ Pace do último mês ({df_p['Pace_fmt'].iloc[-1]}/km) "
                    f"acima da média ({fmt_pace(avg_pace*60)}/km).")

    # Atividades por dia da semana (já em PT-BR após load_all)
    df_dia = (df["DiaSemana"].value_counts()
              .reindex(DIAS_ORDER_PT).fillna(0)
              .reset_index().rename(columns={"DiaSemana":"Dia","count":"Qtd"}))
    fig = px.bar(df_dia, x="Dia", y="Qtd",
                 title="📅 Atividades por Dia da Semana",
                 color_discrete_sequence=[PURPLE], text_auto=True)
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  2 · PERFORMANCE E PACE
# ══════════════════════════════════════════════════════════════════════════════
with tab_perf:
    st.title("⚡ Performance e Pace")

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("🥇 Melhor 3km",   melhor_3km())
    c2.metric("🥇 Melhor 5K",    melhor_be("5k"))
    c3.metric("🥇 Melhor 10K",   melhor_be("10k"))
    c4.metric("🥇 Melhor HM",    melhor_be("half-marathon"))
    c5.metric("🏅 PRs Totais",   f"{int(df_run['pr_count'].sum()):,}"
                                  if df_run["pr_count"].notna().any() else "—")

    st.markdown("---")

    # Evolução best efforts (5K e 10K numa mesma figura) (skill §4)
    if not be.empty:
        be_sel = be[be["name"].str.lower().isin(["5k","10k"])].copy()
        if not be_sel.empty:
            be_best = (be_sel.groupby(["MesAnoOrd","MesAno","name"])
                             .agg(Pace=("pace_sec_km","min")).reset_index()
                             .sort_values("MesAnoOrd"))
            be_best["Pace_fmt"] = be_best["Pace"].apply(fmt_pace)
            be_best["Pace_min"] = be_best["Pace"] / 60

            # custom_data no px.line garante que cada ponto usa seu próprio Pace_fmt
            fig = px.line(be_best, x="MesAno", y="Pace_min", color="name",
                          markers=True,
                          custom_data=["Pace_fmt"],       # ← correto: por ponto, não por traço
                          title="📈 Evolução Melhor Pace — 5K e 10K",
                          color_discrete_map={"5k": RED, "10k": BLUE, "5K": RED, "10K": BLUE},
                          labels={"Pace_min":"Pace (min/km)","MesAno":"","name":"Distância"})
            # hovertemplate usa customdata[0] = Pace_fmt do ponto correto
            fig.update_traces(
                hovertemplate="<b>%{x}</b><br>Melhor pace: %{customdata[0]}/km<extra></extra>")
            set_pace_yaxis(fig, be_best["Pace"])
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    col_a, col_b = st.columns(2)

    # Pace por intensidade — barra (média) com barra de erro (desvio padrão)
    with col_a:
        if "Intensidade" in df_run.columns:
            df_b = cat_intensity(df_run[df_run["pace_sec_km"].notna()].copy())
            df_agg = (df_b.groupby("Intensidade", observed=True)["pace_sec_km"]
                         .agg(Media="mean", DP="std").reset_index().dropna())
            df_agg["Media_min"] = df_agg["Media"] / 60
            df_agg["DP_min"]    = df_agg["DP"] / 60
            df_agg["Label"]     = df_agg["Media"].apply(fmt_pace)
            df_agg["Cor"]       = df_agg["Intensidade"].map(INTENSITY_COLORS)
            fig = go.Figure()
            for _, row in df_agg.iterrows():
                fig.add_bar(
                    x=[row["Intensidade"]], y=[row["Media_min"]],
                    error_y=dict(type="data", array=[row["DP_min"]], visible=True),
                    marker_color=row["Cor"], name=row["Intensidade"],
                    text=row["Label"], textposition="outside",
                )
            set_pace_yaxis(fig, df_agg["Media"])
            fig.update_layout(title="🎯 Pace Médio por Intensidade",
                              showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("📖 Barra = pace médio de cada tipo de treino. "
                       "Traço vertical = variação típica (desvio padrão). "
                       "Quanto mais alto, mais lento. Treinos leves devem ter pace mais alto que os fortes.")

    # Scatter pace × distância com LOWESS (skill §4)
    with col_b:
        df_s = df_run[df_run["pace_sec_km"].notna() & df_run["distance_km"].notna()].copy()
        df_s["Pace_min"] = df_s["pace_sec_km"] / 60
        fig = px.scatter(df_s, x="distance_km", y="Pace_min",
                         title="📍 Pace vs Distância (tendência LOWESS)",
                         color="Intensidade" if "Intensidade" in df_s.columns else None,
                         color_discrete_map=INTENSITY_COLORS,
                         category_orders={"Intensidade": INTENSITY_ORDER},
                         trendline="lowess", trendline_color_override=RED,
                         opacity=0.65,
                         labels={"distance_km":"Distância (km)","Pace_min":"Pace (min/km)"})
        set_pace_yaxis(fig, df_s["pace_sec_km"])
        st.plotly_chart(fig, use_container_width=True)

    # Eficiência mensal
    df_ef = (df_run[df_run["efficiency_index"].notna()]
             .groupby(["MesAnoOrd","MesAno"])
             .agg(Ef=("efficiency_index","mean")).reset_index()
             .sort_values("MesAnoOrd"))
    if not df_ef.empty:
        fig = px.line(df_ef, x="MesAno", y="Ef", markers=True,
                      title="🧠 Índice de Eficiência Mensal (pace ÷ FC — maior = melhor)",
                      color_discrete_sequence=[GREEN],
                      labels={"Ef":"Eficiência","MesAno":""})
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  3 · FREQUÊNCIA CARDÍACA
# ══════════════════════════════════════════════════════════════════════════════
with tab_fc:
    st.title("❤️ Frequência Cardíaca")

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("❤️ FC Média",    f"{df_run['average_heartrate'].mean():.0f} bpm"
                                 if df_run["average_heartrate"].notna().any() else "—")
    c2.metric("🔴 FC Máx Reg.", f"{df_run['max_heartrate'].max():.0f} bpm"
                                 if df_run["max_heartrate"].notna().any() else "—")

    if "weather_temp" in df_run.columns:
        fc_calor = df_run[df_run["weather_temp"] > 24]["average_heartrate"].mean()
        fc_frio  = df_run[df_run["weather_temp"] < 18]["average_heartrate"].mean()
        c3.metric("🌡️ FC no Calor (>24°C)", f"{fc_calor:.0f} bpm" if not pd.isna(fc_calor) else "—")
        c4.metric("❄️ FC no Frio (<18°C)",  f"{fc_frio:.0f} bpm"  if not pd.isna(fc_frio)  else "—")

    st.markdown("---")

    if lps_run.empty:
        st.info("Dados de laps não disponíveis para este período.")
    else:
        col_a, col_b = st.columns(2)

        # % Tempo em Zona FC — barras verticais (skill §4)
        with col_a:
            lps_run["tempo_min"] = lps_run["moving_time_sec"] / 60
            df_zona = (lps_run.groupby("Zona FC")
                               .agg(Tempo=("tempo_min","sum")).reset_index())
            df_zona["Zona FC"] = pd.Categorical(df_zona["Zona FC"],
                                                 categories=ZONA_ORDER, ordered=True)
            df_zona = df_zona.sort_values("Zona FC")
            total_t = df_zona["Tempo"].sum()
            df_zona["Pct"] = df_zona["Tempo"] / total_t * 100
            fig = px.bar(df_zona, x="Zona FC", y="Pct",
                         title="⏱️ % Tempo em Zona FC",
                         color="Zona FC", color_discrete_map=ZONA_COLORS,
                         text=df_zona["Pct"].apply(lambda x: f"{x:.1f}%"),
                         labels={"Pct":"% Tempo","Zona FC":""})
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("📖 **Zonas de FC:** Z1 = regenerativo (caminhada leve) → Z5 = esforço máximo (tiros). "
                       "O ideal para corredores de base é passar mais de 70% do tempo nas zonas Z1 e Z2.")

        # Deriva cardíaca por mês (skill §4)
        with col_b:
            lps_s = lps_run.sort_values(["activity_id","lap_index"])
            first_fc = lps_s.groupby("activity_id")["average_heartrate"].first()
            last_fc  = lps_s.groupby("activity_id")["average_heartrate"].last()
            deriv = (last_fc - first_fc).reset_index()
            deriv.columns = ["activity_id","drift"]
            deriv = deriv.merge(
                df_run[["id","MesAno","MesAnoOrd"]].rename(columns={"id":"activity_id"}),
                on="activity_id", how="left")
            df_deriv_m = (deriv.groupby(["MesAnoOrd","MesAno"])
                               .agg(Deriva=("drift","mean")).reset_index()
                               .sort_values("MesAnoOrd"))
            fig = px.line(df_deriv_m, x="MesAno", y="Deriva", markers=True,
                          title="📈 Deriva Cardíaca Média (bpm — menor = melhor)",
                          color_discrete_sequence=[RED],
                          labels={"Deriva":"Δ bpm","MesAno":""})
            fig.add_hline(y=0,  line_dash="dash", line_color=GRAY)
            fig.add_hline(y=10, line_dash="dot",  line_color=AMBER,
                          annotation_text="+10 bpm — atenção")
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

            # Insight (skill §9)
            if not df_deriv_m.empty:
                last_drift = df_deriv_m["Deriva"].iloc[-1]
                if last_drift > 10:
                    st.warning("⚠️ Deriva cardíaca alta no último mês — sinal de fadiga ou desidratação.")
                elif last_drift < 5:
                    st.success("✅ Deriva cardíaca baixa — boa estabilidade cardiovascular.")

        # FC média por mês
        df_fc_m = (df_run[df_run["average_heartrate"].notna()]
                   .groupby(["MesAnoOrd","MesAno"])
                   .agg(FC=("average_heartrate","mean")).reset_index()
                   .sort_values("MesAnoOrd"))
        fig = px.line(df_fc_m, x="MesAno", y="FC", markers=True,
                      title="❤️ FC Média por Mês",
                      color_discrete_sequence=[RED],
                      labels={"FC":"bpm","MesAno":""})
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  4 · INTELIGÊNCIA DE TREINO (LAPS)
# ══════════════════════════════════════════════════════════════════════════════
with tab_intel:
    st.title("🧠 Inteligência de Treino")

    if lps_run.empty:
        st.info("Dados de laps não disponíveis.")
    else:
        # CV% por atividade (skill §7 — metrics.md)
        def cv_pace(grp):
            p = grp["pace_sec_km"].dropna()
            return (p.std() / p.mean() * 100) if len(p) > 1 and p.mean() > 0 else None

        cv_df = lps_run.groupby("activity_id").apply(cv_pace).dropna().reset_index()
        cv_df.columns = ["activity_id","CV_Pace"]
        cv_medio = cv_df["CV_Pace"].mean()

        c1,c2,c3,c4 = st.columns(4)
        c1.metric("🎯 Consistência (CV%)", f"{cv_medio:.1f}%"
                  if not pd.isna(cv_medio) else "—",
                  help="< 10% = ritmo controlado | > 25% = intervalado")
        c2.metric("📊 Laps / Atividade",
                  f"{lps_run.groupby('activity_id').size().mean():.1f}")
        elev = lps_run["total_elevation_gain"].mean()
        c3.metric("⛰️ Elev. Média / Lap",
                  f"{elev:.1f} m" if not pd.isna(elev) else "—")
        c4.metric("💓 FC Média nos Laps",
                  f"{lps_run['average_heartrate'].mean():.0f} bpm"
                  if lps_run["average_heartrate"].notna().any() else "—")

        st.markdown("---")
        col_a, col_b = st.columns(2)

        # Pace médio + desvio nos 10 treinos mais recentes (substituiu boxplot)
        with col_a:
            recent_ids = (lps_run.sort_values("start_date", ascending=False)
                          ["activity_id"].unique()[:10])
            df_box = lps_run[lps_run["activity_id"].isin(recent_ids)].copy()
            df_box["Data"] = df_box["start_date"].dt.strftime("%d/%m")
            df_agg2 = (df_box.groupby("Data")["pace_sec_km"]
                             .agg(Media="mean", DP="std").reset_index().dropna())
            df_agg2["Media_min"] = df_agg2["Media"] / 60
            df_agg2["DP_min"]    = df_agg2["DP"] / 60
            df_agg2["Label"]     = df_agg2["Media"].apply(fmt_pace)
            fig = go.Figure(go.Bar(
                x=df_agg2["Data"], y=df_agg2["Media_min"],
                error_y=dict(type="data", array=df_agg2["DP_min"].tolist(), visible=True),
                marker_color=BLUE, text=df_agg2["Label"], textposition="outside",
            ))
            set_pace_yaxis(fig, df_agg2["Media"])
            fig.update_layout(title="📅 Pace Médio — 10 Treinos Mais Recentes")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("📖 Barra = pace médio dos km rodados naquele treino. "
                       "Traço = variação entre os km (alta variação = treino intervalado ou com subidas).")

        # Histograma de pace nos laps
        with col_b:
            df_hist = lps_run[lps_run["pace_sec_km"].notna()].copy()
            df_hist["Pace_min"] = df_hist["pace_sec_km"] / 60
            fig = px.histogram(df_hist, x="Pace_min", nbins=40,
                               title="📊 Distribuição de Pace — Todos os Laps",
                               color_discrete_sequence=[PURPLE],
                               labels={"Pace_min":"Pace (min/km)"})
            fig.update_yaxes(title="Nº de Laps")
            st.plotly_chart(fig, use_container_width=True)

        # CV% por mês com linhas de referência (skill §4 + §9)
        lps_cv = lps_run.merge(cv_df, on="activity_id")
        df_cv_m = (lps_cv.groupby(["MesAnoOrd","MesAno"])
                         .agg(CV=("CV_Pace","mean")).reset_index()
                         .sort_values("MesAnoOrd"))
        fig = px.line(df_cv_m, x="MesAno", y="CV", markers=True,
                      title="🎯 Consistência de Pace por Mês (CV%)",
                      color_discrete_sequence=[AMBER],
                      labels={"CV":"CV (%)","MesAno":""})
        fig.add_hline(y=10, line_dash="dash", line_color=GREEN,
                      annotation_text="< 10% — ritmo controlado")
        fig.add_hline(y=25, line_dash="dash", line_color=RED,
                      annotation_text="> 25% — treino intervalado")
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("📖 **CV% (Coeficiente de Variação):** mede o quanto o seu ritmo variou dentro dos treinos do mês. "
                   "Abaixo de 10% = você correu num pace uniforme. Acima de 25% = treino com variações fortes (intervalado, subidas).")


# ══════════════════════════════════════════════════════════════════════════════
#  5 · ELEVAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
with tab_elev:
    st.title("⛰️ Elevação")

    df_e = df_run[df_run["elevation_gain"].notna() & (df_run["elevation_gain"] > 0)].copy()

    if df_e.empty:
        st.info("Nenhum dado de elevação disponível para o período selecionado.")
    else:
        df_e["elev_km"] = df_e["elevation_gain"] / df_e["distance_km"]

        # KPIs
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("⛰️ Elevação Total",       f"{df_e['elevation_gain'].sum():,.0f} m")
        c2.metric("📈 Maior Subida",          f"{df_e['elevation_gain'].max():.0f} m",
                  help="Maior ganho de elevação em uma única atividade")
        c3.metric("📏 Elevação Média/Run",    f"{df_e['elevation_gain'].mean():.0f} m")
        c4.metric("📐 Gradiente Médio",       f"{df_e['elev_km'].mean():.1f} m/km",
                  help="Elevação média por km rodado — indica o perfil dos treinos")
        runs_montanha = len(df_e[df_e["elevation_gain"] >= 300])
        c5.metric("🏔️ Runs c/ >300m",        f"{runs_montanha}")

        st.markdown("---")
        col_a, col_b = st.columns(2)

        # Elevação por mês
        with col_a:
            df_em = (df_e.groupby(["MesAnoOrd","MesAno"])
                         .agg(Elev=("elevation_gain","sum")).reset_index()
                         .sort_values("MesAnoOrd"))
            fig = px.bar(df_em, x="MesAno", y="Elev",
                         title="📅 Elevação Total por Mês (m)",
                         color_discrete_sequence=[AMBER],
                         labels={"Elev":"metros","MesAno":""}, text_auto=".0f")
            fig.update_traces(textposition="outside")
            fig.update_layout(xaxis_tickangle=-45, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        # Histograma de elevação por atividade
        with col_b:
            fig = px.histogram(df_e, x="elevation_gain", nbins=30,
                               title="📊 Distribuição de Elevação por Atividade",
                               color_discrete_sequence=[AMBER],
                               labels={"elevation_gain":"Elevação (m)"})
            fig.update_yaxes(title="Nº de Atividades")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("📖 Mostra quantos treinos tiveram cada faixa de ganho de elevação. "
                       "Uma distribuição concentrada à esquerda indica a maioria dos treinos em terreno plano.")

        col_a, col_b = st.columns(2)

        # Pace vs elevação — impacto da subida no ritmo
        with col_a:
            df_pe = df_e[df_e["pace_sec_km"].notna()].copy()
            df_pe["Pace_min"] = df_pe["pace_sec_km"] / 60
            df_pe["Pace_fmt"] = df_pe["pace_sec_km"].apply(fmt_pace)
            fig = px.scatter(df_pe, x="elevation_gain", y="Pace_min",
                             title="📍 Pace vs Elevação (impacto da subida no ritmo)",
                             trendline="lowess", trendline_color_override=RED,
                             opacity=0.65,
                             color="Intensidade" if "Intensidade" in df_pe.columns else None,
                             color_discrete_map=INTENSITY_COLORS,
                             category_orders={"Intensidade": INTENSITY_ORDER},
                             labels={"elevation_gain":"Elevação (m)",
                                     "Pace_min":"Pace (min/km)"})
            set_pace_yaxis(fig, df_pe["pace_sec_km"])
            st.plotly_chart(fig, use_container_width=True)
            st.caption("📖 Linha vermelha = tendência. Se inclina para cima = mais elevação → pace mais lento.")

        # FC média vs elevação
        with col_b:
            df_fe = df_e[df_e["average_heartrate"].notna()].copy()
            fig = px.scatter(df_fe, x="elevation_gain", y="average_heartrate",
                             title="❤️ FC Média vs Elevação",
                             trendline="lowess", trendline_color_override=RED,
                             opacity=0.65,
                             color="Intensidade" if "Intensidade" in df_fe.columns else None,
                             color_discrete_map=INTENSITY_COLORS,
                             category_orders={"Intensidade": INTENSITY_ORDER},
                             labels={"elevation_gain":"Elevação (m)",
                                     "average_heartrate":"FC Média (bpm)"})
            st.plotly_chart(fig, use_container_width=True)
            st.caption("📖 Mais elevação geralmente = FC mais alta pelo esforço de subida.")

        # Top 10 atividades com maior elevação
        top10 = (df_e.nlargest(10, "elevation_gain")
                     [["start_date","name","distance_km","elevation_gain","elev_km","pace_sec_km"]]
                     .copy())
        top10["Data"]       = top10["start_date"].dt.strftime("%d/%m/%Y")
        top10["Pace"]       = top10["pace_sec_km"].apply(fmt_pace)
        top10["Elev/km"]    = top10["elev_km"].apply(lambda x: f"{x:.1f} m/km")
        top10["Distância"]  = top10["distance_km"].apply(lambda x: f"{x:.1f} km")
        top10["Elevação"]   = top10["elevation_gain"].apply(lambda x: f"{x:.0f} m")
        st.markdown("### 🏔️ Top 10 Atividades com Maior Elevação")
        st.dataframe(
            top10[["Data","name","Distância","Elevação","Elev/km","Pace"]]
                 .rename(columns={"name":"Atividade"}),
            hide_index=True, use_container_width=True
        )

        # Elevação por intensidade — contexto de onde está o volume vertical
        if "Intensidade" in df_e.columns:
            df_ei = (cat_intensity(df_e)
                     .groupby("Intensidade", observed=True)
                     .agg(ElevTotal=("elevation_gain","sum"),
                          ElevMedia=("elevation_gain","mean"),
                          Qtd=("id","count"))
                     .reset_index())
            col_a, col_b = st.columns(2)
            with col_a:
                fig = px.bar(df_ei, x="Intensidade", y="ElevTotal",
                             title="⛰️ Elevação Total por Tipo de Treino (m)",
                             color="Intensidade", color_discrete_map=INTENSITY_COLORS,
                             category_orders={"Intensidade": INTENSITY_ORDER},
                             text=df_ei["ElevTotal"].apply(lambda x: f"{x:.0f}m"),
                             labels={"ElevTotal":"metros","Intensidade":""})
                fig.update_traces(textposition="outside")
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            with col_b:
                fig = px.bar(df_ei, x="Intensidade", y="ElevMedia",
                             title="📐 Elevação Média por Atividade e Tipo (m)",
                             color="Intensidade", color_discrete_map=INTENSITY_COLORS,
                             category_orders={"Intensidade": INTENSITY_ORDER},
                             text=df_ei["ElevMedia"].apply(lambda x: f"{x:.0f}m"),
                             labels={"ElevMedia":"metros","Intensidade":""})
                fig.update_traces(textposition="outside")
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

        # Evolução do gradiente por mês
        df_grad = (df_e.groupby(["MesAnoOrd","MesAno"])
                       .agg(Grad=("elev_km","mean")).reset_index()
                       .sort_values("MesAnoOrd"))
        fig = px.line(df_grad, x="MesAno", y="Grad", markers=True,
                      title="📈 Gradiente Médio por Mês (m/km) — perfil de dificuldade",
                      color_discrete_sequence=[AMBER],
                      labels={"Grad":"m/km","MesAno":""})
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("📖 **Gradiente (m/km):** metros de subida por km rodado. "
                   "Indica o quanto seus treinos têm sido verticalmente exigentes. "
                   "Treinos de morro aumentam força, economia de corrida e VO2max.")


# ══════════════════════════════════════════════════════════════════════════════
#  6 · CLIMA
# ══════════════════════════════════════════════════════════════════════════════
with tab_clima:
    st.title("🌤️ Clima e Condições")

    df_w = df_run[df_run["weather_temp"].notna()].copy() \
           if "weather_temp" in df_run.columns else pd.DataFrame()

    if df_w.empty:
        st.warning("Dados de clima não disponíveis para o período selecionado.")
    else:
        n_chuva   = int((df_w["weather_rain"] > 0).sum()) if "weather_rain" in df_w.columns else 0
        pct_chuva = n_chuva / len(df_w) * 100
        n_ideal   = len(df_w[(df_w["weather_temp"] >= 18) & (df_w["weather_temp"] <= 24)])
        pct_ideal = n_ideal / len(df_w) * 100

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("🌡️ Temp Média",        f"{df_w['weather_temp'].mean():.1f} °C")
        c2.metric("🌧️ Treinos c/ Chuva",  f"{n_chuva} ({pct_chuva:.0f}%)")
        c3.metric("✅ Temp Ideal 18–24°C", f"{pct_ideal:.0f}%")
        c4.metric("💧 Umidade Média",      f"{df_w['weather_humidity'].mean():.0f}%"
                  if "weather_humidity" in df_w.columns else "—")
        c5.metric("💨 Vento Médio",        f"{df_w['weather_wind_speed'].mean():.1f} km/h"
                  if "weather_wind_speed" in df_w.columns else "—")

        st.markdown("---")
        col_a, col_b = st.columns(2)

        # Scatter pace × temperatura com LOWESS (skill §4 — chart mais importante aqui)
        with col_a:
            df_w["Pace_min"] = df_w["pace_sec_km"] / 60
            df_w["Pace_fmt"] = df_w["pace_sec_km"].apply(fmt_pace)
            fig = px.scatter(df_w, x="weather_temp", y="Pace_min",
                             title="🌡️ Pace vs Temperatura (LOWESS)",
                             trendline="lowess", trendline_color_override=RED,
                             opacity=0.6,
                             color="Intensidade" if "Intensidade" in df_w.columns else None,
                             color_discrete_map=INTENSITY_COLORS,
                             category_orders={"Intensidade": INTENSITY_ORDER},
                             labels={"weather_temp":"Temperatura (°C)",
                                     "Pace_min":"Pace (min/km)"})
            fig.update_yaxes(autorange="reversed")
            fig.add_vrect(x0=18, x1=24, fillcolor=GREEN, opacity=0.07,
                          annotation_text="Zona Ideal")
            st.plotly_chart(fig, use_container_width=True)

        # Pace por faixa de temperatura — barras com label mm:ss (skill §4)
        with col_b:
            bins   = [0,15,18,22,26,50]
            labels = ["<15°C","15–18°C","18–22°C","22–26°C",">26°C"]
            df_w["Faixa"] = pd.cut(df_w["weather_temp"], bins=bins, labels=labels)
            df_f = (df_w.groupby("Faixa", observed=True)
                        .agg(Pace=("pace_sec_km","mean"), Qtd=("id","count"))
                        .reset_index())
            df_f["Pace_fmt"] = df_f["Pace"].apply(fmt_pace)
            df_f["Pace_min"] = df_f["Pace"] / 60
            fig = px.bar(df_f, x="Faixa", y="Pace_min",
                         title="📊 Pace Médio por Faixa de Temperatura",
                         color="Faixa", text="Pace_fmt",
                         labels={"Faixa":"","Pace_min":"Pace (min/km)"})
            set_pace_yaxis(fig, df_f["Pace"].dropna())
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("📖 Faixa 18–22°C é considerada a temperatura ideal para corrida. "
                       "Quanto mais quente, maior tende a ser o pace (mais lento).")

        # Impacto da chuva (skill §9)
        if "weather_rain" in df_w.columns:
            pace_chuva = df_w[df_w["weather_rain"] > 0]["pace_sec_km"].mean()
            pace_seco  = df_w[df_w["weather_rain"] == 0]["pace_sec_km"].mean()
            c1,c2,c3 = st.columns(3)
            c1.metric("🌧️ Pace na Chuva",  fmt_pace(pace_chuva))
            c2.metric("☀️ Pace Sem Chuva", fmt_pace(pace_seco))
            if not (pd.isna(pace_chuva) or pd.isna(pace_seco)):
                delta = pace_chuva - pace_seco
                c3.metric("Δ Impacto da Chuva",
                          f"+{delta:.0f}s/km" if delta > 0 else f"{delta:.0f}s/km")
                if delta > 15:
                    st.warning("🌧️ A chuva impacta significativamente seu ritmo — "
                               f"+{delta:.0f}s/km em média.")
                elif delta <= 5:
                    st.success("💪 Ótima resiliência na chuva — impacto mínimo no pace.")


# ══════════════════════════════════════════════════════════════════════════════
#  6 · METAS E BENCHMARKS
# ══════════════════════════════════════════════════════════════════════════════
with tab_metas:
    st.title("🎯 Metas e Benchmarks")

    hoje     = pd.Timestamp.now()
    mes_run  = df_run[df_run["start_date"].dt.to_period("M") == hoje.to_period("M")]
    km_mes   = mes_run["distance_km"].sum()
    tr_mes   = len(mes_run)

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("📏 KM este Mês",      f"{km_mes:.0f} km",
              f"{km_mes/150*100:.0f}% meta 150km")
    c2.metric("🏃 Treinos este Mês", f"{tr_mes}",
              f"{tr_mes/16*100:.0f}% meta 16 treinos")
    c3.metric("🥇 Melhor 5K",        melhor_be("5k"))
    c4.metric("🥇 Melhor 10K",       melhor_be("10k"))

    st.markdown("---")

    if not be.empty:
        col_a, col_b = st.columns(2)

        # Evolução best efforts por distância (skill §4)
        with col_a:
            be_ev = be[be["name"].str.lower().isin(["5k","10k","1k"])].copy()
            if not be_ev.empty:
                be_ev_m = (be_ev.groupby(["MesAnoOrd","MesAno","name"])
                                .agg(Pace=("pace_sec_km","min")).reset_index()
                                .sort_values("MesAnoOrd"))
                be_ev_m["Pace_fmt"] = be_ev_m["Pace"].apply(fmt_pace)
                be_ev_m["Pace_min"] = be_ev_m["Pace"] / 60
                fig = px.line(be_ev_m, x="MesAno", y="Pace_min", color="name",
                              markers=True,
                              custom_data=["Pace_fmt"],
                              title="📈 Evolução dos Melhores Esforços",
                              labels={"Pace_min":"Pace (min/km)","MesAno":"",
                                      "name":"Distância"})
                fig.update_traces(
                    hovertemplate="<b>%{x}</b><br>Melhor pace: %{customdata[0]}/km<extra></extra>")
                set_pace_yaxis(fig, be_ev_m["Pace"])
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

        # PRs por distância
        with col_b:
            pr_df = be[be["pr_rank"].notna()]
            if not pr_df.empty:
                pr_count = pr_df["name"].value_counts().reset_index()
                pr_count.columns = ["Distância","PRs"]
                fig = px.bar(pr_count, x="Distância", y="PRs",
                             title="🏅 PRs Conquistados por Distância",
                             color_discrete_sequence=[AMBER], text_auto=True)
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

    # % Metas mensais — últimos 12 meses
    df_meta = (df_run.groupby(["MesAnoOrd","MesAno"])
                     .agg(KM=("distance_km","sum"), Treinos=("id","count"))
                     .reset_index().sort_values("MesAnoOrd").tail(12))
    df_meta["PctKM"]     = (df_meta["KM"] / 150 * 100).clip(upper=120)
    df_meta["PctTreinos"]= (df_meta["Treinos"] / 16 * 100).clip(upper=120)

    fig = go.Figure()
    fig.add_bar(x=df_meta["MesAno"], y=df_meta["PctKM"],
                name="% Meta 150km", marker_color=BLUE,
                text=df_meta["KM"].apply(lambda x: f"{x:.0f}km"),
                textposition="outside")
    fig.add_bar(x=df_meta["MesAno"], y=df_meta["PctTreinos"],
                name="% Meta 16 treinos", marker_color=GREEN,
                text=df_meta["Treinos"], textposition="outside")
    fig.add_hline(y=100, line_dash="dash", line_color=AMBER,
                  annotation_text="Meta 100%")
    fig.update_layout(barmode="group",
                      title="📊 % Metas Mensais — últimos 12 meses",
                      yaxis_title="%", xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  7 · VOLUME E EVOLUÇÃO
# ══════════════════════════════════════════════════════════════════════════════
with tab_vol:
    st.title("📈 Volume e Evolução")

    col_a, col_b = st.columns(2)

    # Distância acumulada — área
    with col_a:
        df_acum = (df_run.sort_values("start_date")
                         .assign(KM_Acum=lambda x: x["distance_km"].cumsum()))
        fig = px.area(df_acum, x="start_date", y="KM_Acum",
                      title="📏 Distância Acumulada",
                      color_discrete_sequence=[BLUE],
                      labels={"start_date":"","KM_Acum":"km"})
        st.plotly_chart(fig, use_container_width=True)

    # Volume semanal — barras
    with col_b:
        df_sem = (df_run.groupby(["Semana","SemanaStr"])
                        .agg(KM=("distance_km","sum")).reset_index()
                        .sort_values("Semana").tail(24))
        fig = px.bar(df_sem, x="SemanaStr", y="KM",
                     title="📅 Volume Semanal — últimas 24 semanas",
                     color_discrete_sequence=[PURPLE], text_auto=".0f",
                     labels={"SemanaStr":"","KM":"km"})
        fig.update_layout(xaxis_tickangle=-45, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # Volume por intensidade — stacked bar (skill §4 — mais útil para treinador)
    if "Intensidade" in df_run.columns:
        df_int_m = cat_intensity(
            df_run.groupby(["MesAnoOrd","MesAno","Intensidade"])
                  .agg(KM=("distance_km","sum")).reset_index()
                  .sort_values("MesAnoOrd"))
        fig = px.bar(df_int_m, x="MesAno", y="KM", color="Intensidade",
                     title="🎯 Volume por Intensidade e Mês (estrutura de treino)",
                     color_discrete_map=INTENSITY_COLORS,
                     category_orders={"Intensidade": INTENSITY_ORDER},
                     labels={"KM":"km","MesAno":"","Intensidade":"Intensidade"})
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    # Crescimento MoM com cor condicional (skill §4)
    df_mom = (df_run.groupby(["MesAnoOrd","MesAno"])
                    .agg(KM=("distance_km","sum")).reset_index()
                    .sort_values("MesAnoOrd"))
    df_mom["Δ%"] = df_mom["KM"].pct_change() * 100
    df_mom["cor"] = df_mom["Δ%"].apply(
        lambda x: RED if not pd.isna(x) and x < -10
        else AMBER if not pd.isna(x) and x > 30
        else GREEN if not pd.isna(x) else GRAY)
    fig = go.Figure(go.Bar(
        x=df_mom["MesAno"], y=df_mom["Δ%"], marker_color=df_mom["cor"],
        text=df_mom["Δ%"].apply(lambda x: f"{x:+.0f}%" if not pd.isna(x) else ""),
        textposition="outside"))
    fig.add_hline(y=0,   line_color=GRAY, line_dash="dash")
    fig.add_hline(y=30,  line_color=AMBER, line_dash="dot",
                  annotation_text="+30% — risco overload")
    fig.add_hline(y=-10, line_color=AMBER, line_dash="dot")
    fig.update_layout(title="📊 Crescimento de Volume MoM (%)",
                      yaxis_title="%", xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  8 · VISÃO TREINADOR
# ══════════════════════════════════════════════════════════════════════════════
with tab_coach:
    st.title("🧑‍🏫 Visão Treinador")

    hoje  = pd.Timestamp.now()
    ult7  = df_run[df_run["start_date"] >= hoje - timedelta(days=7)]
    ult28 = df_run[df_run["start_date"] >= hoje - timedelta(days=28)]

    # ACWR (skill §7 — metrics.md)
    carga_aguda   = ult7["suffer_score"].sum()  if "suffer_score" in df_run.columns else 0
    carga_cronica = ult28["suffer_score"].sum() / 4 if "suffer_score" in df_run.columns else 0
    acwr          = carga_aguda / carga_cronica if carga_cronica > 0 else 0

    if   acwr < 0.8:  zona_r, cor_r = "🟡 Subcarregado",   AMBER
    elif acwr <= 1.3: zona_r, cor_r = "🟢 Zona Segura",    GREEN
    elif acwr <= 1.5: zona_r, cor_r = "🟠 Risco Moderado", "#E67E22"
    else:             zona_r, cor_r = "🔴 Alto Risco",      RED

    if "Intensidade" in df_run.columns:
        leves    = df_run["Intensidade"].isin(["Leve","Moderado"]).sum()
        intensos = df_run["Intensidade"].isin(["Forte","Muito Forte"]).sum()
        ratio_li = f"{leves}:{intensos}"
    else:
        ratio_li = "—"

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("⚡ ACWR",               f"{acwr:.2f}", zona_r)
    c2.metric("🔥 Carga Aguda 7d",     f"{carga_aguda:.0f}")
    c3.metric("📊 Carga Crônica 28d",  f"{carga_cronica:.0f}")
    c4.metric("🎯 Ratio Leve:Intenso", ratio_li, help="Ideal: ~80:20 (polarized)")
    c5.metric("📏 KM última semana",   f"{ult7['distance_km'].sum():.0f} km")

    st.caption("📖 **ACWR (Razão Carga Aguda/Crônica):** compara o esforço dos últimos 7 dias com a média das últimas 4 semanas. "
               "Entre 0,8 e 1,3 = equilíbrio seguro. Acima de 1,5 = risco elevado de lesão por overtraining.")

    # Insight ACWR (skill §9)
    if   acwr > 1.5: st.warning("⚠️ ACWR acima de 1,5 — alto risco de lesão. Reduza o volume esta semana.")
    elif acwr > 1.3: st.warning("🟠 ACWR entre 1,3 e 1,5 — zona de atenção. Monitore sinais de fadiga.")
    elif acwr < 0.8: st.info("📉 ACWR abaixo de 0,8 — carga baixa. Espaço para aumentar volume com segurança.")
    else:            st.success("✅ ACWR dentro da zona segura (0,8–1,3). Continue o plano atual.")

    st.markdown("---")
    col_a, col_b = st.columns(2)

    # ACWR histórico com bandas coloridas (skill §4 — chart mais importante aqui)
    with col_a:
        if df_run["suffer_score"].notna().any():
            weekly = (df_run[df_run["suffer_score"].notna()]
                      .set_index("start_date")["suffer_score"]
                      .resample("W").sum())
            acwr_df = pd.DataFrame({"Carga": weekly}).reset_index()
            acwr_df.columns = ["Semana","Carga"]
            acwr_df["Aguda"]   = acwr_df["Carga"].rolling(1).sum()
            acwr_df["Cronica"] = acwr_df["Carga"].rolling(4).mean()
            acwr_df["ACWR"]    = (acwr_df["Aguda"] / acwr_df["Cronica"]).replace([float("inf")], None)
            acwr_df = acwr_df.dropna(subset=["ACWR"])
            fig = px.line(acwr_df, x="Semana", y="ACWR", markers=True,
                          title="⚡ ACWR Histórico por Semana",
                          color_discrete_sequence=[BLUE],
                          labels={"ACWR":"Ratio","Semana":""})
            fig.add_hrect(y0=0.8, y1=1.3, fillcolor=GREEN, opacity=0.08,
                          annotation_text="Zona Segura (0.8–1.3)")
            fig.add_hline(y=1.5, line_dash="dash", line_color=RED,
                          annotation_text="Risco Alto (1.5)")
            st.plotly_chart(fig, use_container_width=True)

    # Variação de carga semanal (skill §4 — cor condicional)
    with col_b:
        if df_run["suffer_score"].notna().any():
            df_carga = (df_run[df_run["suffer_score"].notna()]
                        .groupby(["Semana","SemanaStr"])
                        .agg(Carga=("suffer_score","sum")).reset_index()
                        .sort_values("Semana").tail(16))
            df_carga["Δ%"] = df_carga["Carga"].pct_change() * 100
            df_carga["cor"] = df_carga["Δ%"].apply(
                lambda x: RED if not pd.isna(x) and abs(x) > 10 else GREEN)
            fig = go.Figure(go.Bar(
                x=df_carga["SemanaStr"], y=df_carga["Δ%"],
                marker_color=df_carga["cor"],
                text=df_carga["Δ%"].apply(lambda x: f"{x:+.0f}%" if not pd.isna(x) else ""),
                textposition="outside"))
            fig.add_hline(y=10,  line_dash="dash", line_color=AMBER,
                          annotation_text="±10% limite seguro")
            fig.add_hline(y=-10, line_dash="dash", line_color=AMBER)
            fig.update_layout(title="📊 Variação de Carga Semanal (%)",
                              xaxis_tickangle=-45, yaxis_title="%")
            st.plotly_chart(fig, use_container_width=True)

    # Tendência FC últimas 8 semanas
    df_fc8 = (df_run[df_run["average_heartrate"].notna()]
              .groupby(["Semana","SemanaStr"])
              .agg(FC=("average_heartrate","mean")).reset_index()
              .sort_values("Semana").tail(8))
    if not df_fc8.empty:
        tend = ("📈 Subindo — possível fadiga acumulada"
                if df_fc8["FC"].iloc[-1] > df_fc8["FC"].iloc[0]
                else "📉 Caindo — boa adaptação cardiovascular"
                if df_fc8["FC"].iloc[-1] < df_fc8["FC"].iloc[0]
                else "➡️ Estável")
        st.info(f"**Tendência FC (últimas 8 semanas):** {tend}")
        fig = px.line(df_fc8, x="SemanaStr", y="FC", markers=True,
                      title="❤️ FC Média — Últimas 8 Semanas",
                      color_discrete_sequence=[RED],
                      labels={"FC":"bpm","SemanaStr":""})
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)