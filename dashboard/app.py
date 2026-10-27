"""Painel local de prospecção agro (Streamlit), lendo a gold do DuckDB.

    make dash   ->  http://localhost:8501
"""

import os
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("CNPJ_DATA_DIR", ROOT / "data")) / "warehouse.duckdb"

st.set_page_config(page_title="Prospecção Agro", page_icon="🌱", layout="wide")

# Paleta categórica validada (claro/escuro): slot 1 azul, 2 laranja, 3 verde-água
DARK = getattr(getattr(st, "context", None), "theme", None) is not None and st.context.theme.type == "dark"
SERIES = ["#3987e5", "#d95926", "#199e70"] if DARK else ["#2a78d6", "#eb6834", "#1baf7a"]
INK = "#c3c2b7" if DARK else "#52514e"
GRID = "#383835" if DARK else "#e8e7e3"
TIPO_CORES = {"Principal": SERIES[0], "Secundário": SERIES[1]}


# ---------------------------------------------------------------- dados
def _query(sql: str, params: list | None = None) -> pd.DataFrame:
    # conexão curta e read-only: não bloqueia o `make dbt` enquanto o painel está aberto
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute(sql, params or []).df()


@st.cache_data(show_spinner="Carregando leads…")
def load_leads() -> tuple[pd.DataFrame, dict[str, str]]:
    df = _query("select * from gold.leads_agro")
    rotulos = dict(_query("select cnae, rotulo from ref.cnaes_alvo").itertuples(index=False))
    df["tipo"] = df["match_tipo"].map({"principal": "Principal", "secundario": "Secundário"})
    df["cnaes_alvo"] = df["cnaes_alvo"].apply(list)
    df["ano_abertura"] = pd.to_datetime(df["data_inicio_atividade"]).dt.year
    df["municipio_uf"] = df["municipio"].str.title() + " - " + df["uf"]
    df["tem_email"] = df["email"].notna()
    df["tem_telefone"] = df["telefone_1"].notna() | df["telefone_2"].notna()
    return df, rotulos


@st.cache_data
def load_socios(cnpj_basico: str) -> pd.DataFrame:
    return _query(
        "select nome_socio, qualificacao, tipo_socio, faixa_etaria, data_entrada_sociedade "
        "from gold.leads_socios where cnpj_basico = ? order by data_entrada_sociedade",
        [cnpj_basico],
    )


def fmt_cnpj(c: str) -> str:
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if c and len(c) == 14 else c


def fmt_tel(t: str | None) -> str:
    if not t or pd.isna(t):
        return ""
    return f"({t[:2]}) {t[2:]}" if len(t) > 2 else t


def fmt_data(d) -> str:
    return pd.Timestamp(d).strftime("%d/%m/%Y") if pd.notna(d) else "—"


def fmt_int(n: float) -> str:
    return f"{int(n):,}".replace(",", ".")


def style(fig, height: int = 380):
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=0),
        bargap=0.3,
        barcornerradius=4,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None),
        hoverlabel=dict(font_size=13),
        separators=",.",
    )
    fig.update_xaxes(title=None, gridcolor=GRID, zeroline=False)
    fig.update_yaxes(title=None, gridcolor=GRID, zeroline=False, automargin=True, showticklabels=True,
                     ticks="outside", ticklen=4, tickcolor="rgba(0,0,0,0)")
    fig.update_xaxes(automargin=True)
    fig.update_traces(marker_line_width=2, marker_line_color="rgba(0,0,0,0)", selector=dict(type="bar"))
    return fig


def chart(fig, height: int = 380):
    st.plotly_chart(style(fig, height), width="stretch", theme=None,
                    config={"displaylogo": False, "modeBarButtonsToRemove": ["select2d", "lasso2d"]})


# ---------------------------------------------------------------- filtros
if not DB_PATH.exists():
    st.error(f"Banco não encontrado em `{DB_PATH}`. Rode `make ingest` e `make dbt` antes.")
    st.stop()

leads, ROTULOS = load_leads()

with st.sidebar:
    st.header("Filtros")
    situacoes = st.multiselect("Situação cadastral", sorted(leads["situacao_cadastral"].dropna().unique()),
                               default=["ATIVA"])
    tipos = st.multiselect("CNAE alvo como", ["Principal", "Secundário"], default=["Principal", "Secundário"],
                           help="Principal = atividade principal da empresa. Secundário = só declarado como "
                                "atividade secundária (lista maior, porém menos qualificada).")
    cnaes = st.multiselect("CNAEs alvo", list(ROTULOS), default=list(ROTULOS), format_func=ROTULOS.get)
    ufs = st.multiselect("UF", sorted(leads["uf"].dropna().unique()), placeholder="Todas")
    mun_opcoes = leads[leads["uf"].isin(ufs)] if ufs else leads
    municipios = st.multiselect("Município", sorted(mun_opcoes["municipio_uf"].dropna().unique()),
                                placeholder="Todos")
    portes = st.multiselect("Porte", sorted(leads["porte"].dropna().unique()), placeholder="Todos")
    matriz_filial = st.multiselect("Matriz / filial", ["MATRIZ", "FILIAL"], placeholder="Ambas")
    simples = st.radio("Simples Nacional", ["Todos", "Optante", "Não optante"], horizontal=True)
    contato = st.multiselect("Exigir contato", ["E-mail", "Telefone"], placeholder="Não exigir")
    anos = leads["ano_abertura"].dropna()
    ano_min, ano_max = st.slider("Ano de abertura", int(anos.min()), int(anos.max()),
                                 (int(anos.min()), int(anos.max())))

f = leads[
    leads["situacao_cadastral"].isin(situacoes)
    & leads["tipo"].isin(tipos)
    & leads["cnaes_alvo"].apply(lambda xs: any(c in cnaes for c in xs))
    & leads["ano_abertura"].between(ano_min, ano_max)
]
if ufs:
    f = f[f["uf"].isin(ufs)]
if municipios:
    f = f[f["municipio_uf"].isin(municipios)]
if portes:
    f = f[f["porte"].isin(portes)]
if matriz_filial:
    f = f[f["matriz_filial"].isin(matriz_filial)]
if simples != "Todos":
    f = f[f["opcao_simples"] == (simples == "Optante")]
if "E-mail" in contato:
    f = f[f["tem_email"]]
if "Telefone" in contato:
    f = f[f["tem_telefone"]]

# ---------------------------------------------------------------- cabeçalho + KPIs
ref_month = leads["ref_month"].iloc[0] if len(leads) else "-"
st.title("Prospecção agro")
st.caption(f"Base CNPJ da Receita Federal · snapshot {ref_month} · "
           f"{fmt_int(len(f))} de {fmt_int(len(leads))} estabelecimentos no filtro")

if f.empty:
    st.info("Nenhum estabelecimento com esses filtros.")
    st.stop()

hoje = pd.Timestamp(date.today())
novas = (pd.to_datetime(f["data_inicio_atividade"]) >= hoje - pd.DateOffset(months=12)).sum()
k = st.columns(5)
k[0].metric("Estabelecimentos", fmt_int(len(f)))
k[1].metric("Empresas (CNPJ raiz)", fmt_int(f["cnpj_basico"].nunique()))
k[2].metric("Com e-mail", f"{f['tem_email'].mean():.0%}")
k[3].metric("Com telefone", f"{f['tem_telefone'].mean():.0%}")
k[4].metric("Abertas nos últimos 12 meses", fmt_int(novas))

tab_mercado, tab_lista = st.tabs(["Mercado", "Lista de leads"])

# ---------------------------------------------------------------- aba Mercado
with tab_mercado:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Onde estão — por UF")
        por_uf = f.groupby(["uf", "tipo"]).size().rename("leads").reset_index()
        ordem = por_uf.groupby("uf")["leads"].sum().sort_values().index.tolist()
        fig = px.bar(por_uf, x="leads", y="uf", color="tipo", orientation="h",
                     color_discrete_map=TIPO_CORES, category_orders={"uf": ordem[::-1]},
                     labels={"leads": "Estabelecimentos", "uf": "UF", "tipo": "CNAE alvo como"})
        chart(fig, height=max(320, 22 * len(ordem)))
    with c2:
        st.subheader("Top 15 municípios")
        top = f["municipio_uf"].value_counts().head(15).rename_axis("municipio").reset_index(name="leads")
        fig = px.bar(top, x="leads", y="municipio", orientation="h", text="leads",
                     color_discrete_sequence=[SERIES[0]],
                     category_orders={"municipio": top["municipio"].tolist()},
                     labels={"leads": "Estabelecimentos", "municipio": "Município"})
        fig.update_traces(textposition="outside", cliponaxis=False, texttemplate="%{x:,d}")
        fig.update_xaxes(range=[0, fig.data[0].x.max() * 1.15])
        chart(fig, height=max(320, 22 * len(ordem)) if len(ordem) > 15 else 380)

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Por CNAE alvo")
        ex = f[["cnaes_alvo", "cnae_principal"]].explode("cnaes_alvo")
        ex = ex[ex["cnaes_alvo"].isin(cnaes)]
        ex["tipo"] = (ex["cnaes_alvo"] == ex["cnae_principal"]).map({True: "Principal", False: "Secundário"})
        ex = ex[ex["tipo"].isin(tipos)]
        por_cnae = ex.groupby(["cnaes_alvo", "tipo"]).size().rename("leads").reset_index()
        por_cnae["cnae"] = por_cnae["cnaes_alvo"].map(ROTULOS)
        fig = px.bar(por_cnae, x="leads", y="cnae", color="tipo", orientation="h", barmode="group",
                     color_discrete_map=TIPO_CORES,
                     labels={"leads": "Estabelecimentos", "cnae": "CNAE", "tipo": "CNAE alvo como"})
        chart(fig, height=300)
        st.caption("Um estabelecimento pode ter mais de um CNAE alvo, por isso a soma pode passar do total.")
    with c4:
        st.subheader("Porte da empresa")
        por_porte = f["porte"].fillna("NAO INFORMADO").value_counts().rename_axis("porte").reset_index(name="leads")
        fig = px.bar(por_porte, x="leads", y="porte", orientation="h", text="leads",
                     color_discrete_sequence=[SERIES[0]],
                     category_orders={"porte": por_porte["porte"].tolist()},
                     labels={"leads": "Estabelecimentos", "porte": "Porte"})
        fig.update_traces(textposition="outside", cliponaxis=False, texttemplate="%{x:,d}")
        fig.update_xaxes(range=[0, fig.data[0].x.max() * 1.15])
        chart(fig, height=300)

    st.subheader("Aberturas por ano")
    por_ano = f.dropna(subset=["ano_abertura"]).groupby("ano_abertura").size().rename("leads").reset_index()
    fig = px.line(por_ano, x="ano_abertura", y="leads", markers=True, color_discrete_sequence=[SERIES[0]],
                  labels={"ano_abertura": "Ano de abertura", "leads": "Estabelecimentos abertos"})
    fig.update_traces(line_width=2, marker_size=8)
    fig.update_layout(hovermode="x unified")
    chart(fig, height=300)
    st.caption(f"{date.today().year} é parcial (ano em curso). "
               "Conta só estabelecimentos que existem na base hoje, com a situação filtrada ao lado. "
               "Com o filtro padrão (ATIVA), é \"quantas das ativas de hoje abriram em cada ano\".")

# ---------------------------------------------------------------- aba Lista
with tab_lista:
    busca_col, dl_col = st.columns([4, 1], vertical_alignment="bottom")
    busca = busca_col.text_input("Buscar por razão social, nome fantasia ou CNPJ", placeholder="ex.: agro, 12345678")
    lista = f
    if busca:
        b = busca.strip()
        digitos = "".join(ch for ch in b if ch.isdigit())
        mask = lista["razao_social"].str.contains(b, case=False, na=False, regex=False) | \
            lista["nome_fantasia"].str.contains(b, case=False, na=False, regex=False)
        if digitos:
            mask |= lista["cnpj"].str.contains(digitos, na=False, regex=False)
        lista = lista[mask]

    tabela = pd.DataFrame({
        "CNPJ": lista["cnpj"].map(fmt_cnpj),
        "Razão social": lista["razao_social"],
        "Nome fantasia": lista["nome_fantasia"],
        "CNAE alvo como": lista["tipo"],
        "CNAEs alvo": lista["cnaes_alvo"].map(lambda xs: ", ".join(ROTULOS.get(x, x).split(" ")[0] for x in xs)),
        "Porte": lista["porte"],
        "Município": lista["municipio_uf"],
        "Telefone": lista["telefone_1"].map(fmt_tel),
        "E-mail": lista["email"],
        "Abertura": lista["data_inicio_atividade"],
        "Capital social": lista["capital_social"].astype(float),
        "Situação": lista["situacao_cadastral"],
    })
    # CNAE alvo como atividade principal primeiro (lead mais qualificado), depois maior capital
    tabela = tabela.sort_values(["CNAE alvo como", "Capital social"], ascending=[True, False])
    texto = ["Razão social", "Nome fantasia", "Porte", "Município", "E-mail"]
    tabela[texto] = tabela[texto].fillna("")

    dl_col.download_button(
        "Baixar CSV", tabela.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name=f"leads_agro_{ref_month}.csv", mime="text/csv", width="stretch",
    )
    st.caption(f"{fmt_int(len(tabela))} estabelecimentos · CNAE alvo como principal primeiro, "
               "depois por capital social · clique numa linha para abrir a ficha")

    sel = st.dataframe(
        tabela, hide_index=True, width="stretch", height=420,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "Capital social": st.column_config.NumberColumn(format="R$ %.2f"),
            "Abertura": st.column_config.DateColumn(format="DD/MM/YYYY"),
        },
    )

    rows = sel.selection.rows if sel and sel.selection else []
    if rows:
        lead = lista.loc[tabela.index[rows[0]]]
        st.divider()
        st.subheader(lead["razao_social"] or fmt_cnpj(lead["cnpj"]))
        a, b, c = st.columns(3)
        with a:
            st.markdown(f"**CNPJ** {fmt_cnpj(lead['cnpj'])} · {lead['matriz_filial'] or ''}")
            st.markdown(f"**Nome fantasia** {lead['nome_fantasia'] or '—'}")
            st.markdown(f"**Situação** {lead['situacao_cadastral']} desde {fmt_data(lead['data_situacao_cadastral'])}")
            st.markdown(f"**Abertura** {fmt_data(lead['data_inicio_atividade'])}")
            st.markdown(f"**Natureza jurídica** {lead['natureza_juridica'] or '—'}")
        with b:
            st.markdown(f"**Porte** {lead['porte'] or '—'}")
            cap = lead["capital_social"]
            st.markdown(f"**Capital social** {'R$ ' + fmt_int(cap) if pd.notna(cap) else '—'}")
            st.markdown(f"**Simples** {'sim' if lead['opcao_simples'] else 'não'} · "
                        f"**MEI** {'sim' if lead['opcao_mei'] else 'não'}")
            st.markdown(f"**CNAE principal** {lead['cnae_principal']} — {lead['cnae_principal_descricao']}")
            st.markdown("**CNAEs alvo** " + ", ".join(ROTULOS.get(x, x) for x in lead["cnaes_alvo"]))
        with c:
            end = ", ".join(str(x) for x in [lead["logradouro"], lead["numero"], lead["complemento"],
                                              lead["bairro"]] if x and pd.notna(x))
            st.markdown(f"**Endereço** {end}")
            st.markdown(f"**Município** {lead['municipio_uf']} · CEP {lead['cep'] or '—'}")
            tels = " · ".join(t for t in [fmt_tel(lead["telefone_1"]), fmt_tel(lead["telefone_2"])] if t)
            st.markdown(f"**Telefone** {tels or '—'}")
            st.markdown(f"**E-mail** {lead['email'] or '—'}")

        s_col, e_col = st.columns(2)
        with s_col:
            st.markdown("**Quadro societário**")
            socios = load_socios(lead["cnpj_basico"])
            if socios.empty:
                st.caption("Sem sócios informados (comum em empresário individual / MEI).")
            else:
                st.dataframe(socios.rename(columns={
                    "nome_socio": "Nome", "qualificacao": "Qualificação", "tipo_socio": "Tipo",
                    "faixa_etaria": "Faixa etária", "data_entrada_sociedade": "Entrada"}),
                    hide_index=True, width="stretch")
        with e_col:
            outros = leads[(leads["cnpj_basico"] == lead["cnpj_basico"]) & (leads["cnpj"] != lead["cnpj"])]
            st.markdown(f"**Outros estabelecimentos da empresa na base** ({len(outros)})")
            if not outros.empty:
                st.dataframe(pd.DataFrame({
                    "CNPJ": outros["cnpj"].map(fmt_cnpj), "Tipo": outros["matriz_filial"],
                    "Município": outros["municipio_uf"], "Situação": outros["situacao_cadastral"],
                }), hide_index=True, width="stretch")
