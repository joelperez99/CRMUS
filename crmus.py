import streamlit as st
import pandas as pd

st.set_page_config(page_title="CRM Personalizado", layout="wide")

EXPECTED_COLUMNS = [
    "ID",
    "Nombre",
    "Apellido",
    "Email",
    "Telefono",
    "FechaNacimiento",
    "Direccion",
    "Usuario",
    "Notas",
    "Estado",
    "Grupos",
]

@st.cache_data(ttl=120)
def load_contacts(csv_url: str) -> pd.DataFrame:
    if not csv_url:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    df = pd.read_csv(csv_url)

    rename_map = {
        "Teléfono": "Telefono",
        "Fecha de nacimiento": "FechaNacimiento",
        "Fecha de Nacimiento": "FechaNacimiento",
        "Dirección": "Direccion",
        "Dirección completa": "Direccion",
        "Grupo": "Grupos",
        "Grupo o grupos asignados": "Grupos",
    }
    df = df.rename(columns=rename_map)

    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[EXPECTED_COLUMNS].copy()

    df["Grupos"] = df["Grupos"].fillna("").astype(str)
    df["Nombre"] = df["Nombre"].fillna("").astype(str)
    df["Apellido"] = df["Apellido"].fillna("").astype(str)
    df["Email"] = df["Email"].fillna("").astype(str)
    df["Telefono"] = df["Telefono"].fillna("").astype(str)
    df["Estado"] = df["Estado"].fillna("").astype(str)
    df["Direccion"] = df["Direccion"].fillna("").astype(str)
    df["Usuario"] = df["Usuario"].fillna("").astype(str)
    df["Notas"] = df["Notas"].fillna("").astype(str)

    df["FechaNacimiento"] = pd.to_datetime(df["FechaNacimiento"], errors="coerce")
    df["NombreCompleto"] = (df["Nombre"].str.strip() + " " + df["Apellido"].str.strip()).str.strip()

    return df

def extract_groups(df: pd.DataFrame):
    groups = set()
    for value in df["Grupos"].fillna(""):
        for g in str(value).split(","):
            g = g.strip()
            if g:
                groups.add(g)
    return sorted(groups)

def filter_by_group(df: pd.DataFrame, selected_groups):
    if not selected_groups:
        return df

    def row_has_group(value: str):
        row_groups = [x.strip().lower() for x in str(value).split(",") if x.strip()]
        return any(g.lower() in row_groups for g in selected_groups)

    return df[df["Grupos"].apply(row_has_group)].copy()

def apply_filters(df, search_text, selected_groups, selected_status, start_date, end_date):
    out = df.copy()

    if search_text:
        s = search_text.lower().strip()
        mask = (
            out["NombreCompleto"].str.lower().str.contains(s, na=False)
            | out["Email"].str.lower().str.contains(s, na=False)
            | out["Telefono"].str.lower().str.contains(s, na=False)
            | out["Direccion"].str.lower().str.contains(s, na=False)
            | out["Usuario"].str.lower().str.contains(s, na=False)
            | out["Notas"].str.lower().str.contains(s, na=False)
            | out["Grupos"].str.lower().str.contains(s, na=False)
        )
        out = out[mask]

    out = filter_by_group(out, selected_groups)

    if selected_status:
        out = out[out["Estado"].isin(selected_status)]

    if start_date:
        out = out[out["FechaNacimiento"].dt.date >= start_date]
    if end_date:
        out = out[out["FechaNacimiento"].dt.date <= end_date]

    return out

def metrics_cards(df):
    total = len(df)
    unique_groups = len(extract_groups(df))
    with_phone = int(df["Telefono"].astype(str).str.strip().ne("").sum())
    with_email = int(df["Email"].astype(str).str.strip().ne("").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de contactos", total)
    c2.metric("Grupos detectados", unique_groups)
    c3.metric("Con teléfono", with_phone)
    c4.metric("Con email", with_email)

def render_group_summary(df):
    st.subheader("Resumen por grupo")
    groups = extract_groups(df)

    if not groups:
        st.info("No se encontraron grupos en la hoja.")
        return

    summary = []
    for g in groups:
        count = filter_by_group(df, [g]).shape[0]
        summary.append({"Grupo": g, "Contactos": count})

    summary_df = pd.DataFrame(summary).sort_values("Contactos", ascending=False)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

def render_main_table(df):
    st.subheader("Contactos")

    display = df.copy()
    display["FechaNacimiento"] = display["FechaNacimiento"].dt.strftime("%d/%m/%Y")
    display = display.rename(columns={
        "FechaNacimiento": "Fecha de Nacimiento",
        "Telefono": "Teléfono",
        "Direccion": "Dirección",
        "Usuario": "Usuario/Alias",
    })

    cols = [
        "ID",
        "Nombre",
        "Apellido",
        "Email",
        "Teléfono",
        "Fecha de Nacimiento",
        "Dirección",
        "Usuario/Alias",
        "Estado",
        "Grupos",
        "Notas",
    ]
    st.dataframe(display[cols], use_container_width=True, hide_index=True)

def render_contacts_by_group(df):
    st.subheader("Ver contactos por grupo")
    groups = extract_groups(df)

    if not groups:
        st.info("No hay grupos disponibles.")
        return

    selected_group = st.selectbox("Selecciona un grupo", options=["Todos"] + groups)

    if selected_group == "Todos":
        filtered = df.copy()
    else:
        filtered = filter_by_group(df, [selected_group])

    st.caption(f"Mostrando {len(filtered)} contacto(s)")

    display = filtered[["Nombre", "Apellido", "Email", "Telefono", "Estado", "Grupos"]].copy()
    display = display.rename(columns={"Telefono": "Teléfono"})
    st.dataframe(display, use_container_width=True, hide_index=True)

def main():
    st.title("CRM Personalizado")
    st.caption("Visualiza todos tus contactos y también por grupos, usando Google Sheets como base de datos.")

    csv_url = st.text_input(
        "URL CSV de Google Sheets",
        placeholder="https://docs.google.com/spreadsheets/d/.../gviz/tq?tqx=out:csv&sheet=Contactos"
    )

    df = load_contacts(csv_url)

    if df.empty:
        st.warning("Pega la URL CSV de Google Sheets para cargar los contactos.")
        st.code(
            "ID, Nombre, Apellido, Email, Telefono, FechaNacimiento, Direccion, Usuario, Notas, Estado, Grupos"
        )
        return

    st.sidebar.header("Filtros")
    search_text = st.sidebar.text_input("Buscar contacto", placeholder="Nombre, email, teléfono...")
    selected_groups = st.sidebar.multiselect("Grupos", extract_groups(df))
    statuses = sorted([x for x in df["Estado"].dropna().astype(str).unique().tolist() if x.strip()])
    selected_status = st.sidebar.multiselect("Estado", statuses)
    start_date = st.sidebar.date_input("Fecha de nacimiento desde", value=None)
    end_date = st.sidebar.date_input("Fecha de nacimiento hasta", value=None)

    if st.sidebar.button("Recargar datos"):
        st.cache_data.clear()
        st.rerun()

    filtered_df = apply_filters(df, search_text, selected_groups, selected_status, start_date, end_date)

    metrics_cards(filtered_df)

    tab1, tab2, tab3 = st.tabs(["Vista general", "Por grupos", "Resumen"])

    with tab1:
        render_main_table(filtered_df)

    with tab2:
        render_contacts_by_group(filtered_df)

    with tab3:
        render_group_summary(filtered_df)

if __name__ == "__main__":
    main()
