import re
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
    "Pass1",
    "Pass2",
    "Usuario",
    "Notas",
    "Estado",
    "Grupos",
]

def normalize_google_sheet_url(url: str, sheet_name: str = "Hoja1") -> str:
    if not url:
        return url

    if "gviz/tq?tqx=out:csv" in url:
        return url

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if match:
        sheet_id = match.group(1)
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"

    return url

@st.cache_data(ttl=120)
def load_contacts(sheet_url: str, sheet_name: str) -> pd.DataFrame:
    if not sheet_url:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    csv_url = normalize_google_sheet_url(sheet_url, sheet_name)
    df = pd.read_csv(csv_url)

    rename_map = {
        "DOB": "FechaNacimiento",
        "Dirección": "Direccion",
        "Direccion": "Direccion",
        "Teléfono": "Telefono",
        "Telefono": "Telefono",
        "Pass 1": "Pass1",
        "Pass 2": "Pass2",
        "Fecha de nacimiento": "FechaNacimiento",
        "FechaNacimiento": "FechaNacimiento",
        "Grupo": "Grupos",
        "Grupos": "Grupos",
    }

    df = df.rename(columns=rename_map)

    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[EXPECTED_COLUMNS].copy()

    for col in ["Nombre", "Apellido", "Email", "Telefono", "Direccion", "Pass1", "Pass2", "Usuario", "Notas", "Estado", "Grupos"]:
        df[col] = df[col].fillna("").astype(str)

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

def apply_filters(df, search_text, selected_groups, start_date, end_date):
    out = df.copy()

    if search_text:
        s = search_text.lower().strip()
        mask = (
            out["NombreCompleto"].str.lower().str.contains(s, na=False)
            | out["Email"].str.lower().str.contains(s, na=False)
            | out["Telefono"].str.lower().str.contains(s, na=False)
            | out["Direccion"].str.lower().str.contains(s, na=False)
            | out["Pass1"].str.lower().str.contains(s, na=False)
            | out["Pass2"].str.lower().str.contains(s, na=False)
        )
        out = out[mask]

    out = filter_by_group(out, selected_groups)

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

def render_main_table(df):
    st.subheader("Contactos")

    display = df.copy()
    display["FechaNacimiento"] = display["FechaNacimiento"].dt.strftime("%d/%m/%Y")

    display = display.rename(columns={
        "FechaNacimiento": "Fecha de Nacimiento",
        "Telefono": "Teléfono",
        "Direccion": "Dirección",
        "Pass1": "Pass 1",
        "Pass2": "Pass 2",
    })

    cols = [
        "Email",
        "Fecha de Nacimiento",
        "Pass 1",
        "Pass 2",
        "Dirección",
        "Nombre",
        "Apellido",
        "Teléfono",
        "Grupos",
    ]

    existing = [c for c in cols if c in display.columns]
    st.dataframe(display[existing], use_container_width=True, hide_index=True)

def render_contacts_by_group(df):
    st.subheader("Ver contactos por grupo")
    groups = extract_groups(df)

    if not groups:
        st.info("No hay grupos disponibles todavía. Agrega una columna Grupos en tu hoja si quieres usar esta parte.")
        return

    selected_group = st.selectbox("Selecciona un grupo", options=["Todos"] + groups)

    if selected_group == "Todos":
        filtered = df.copy()
    else:
        filtered = filter_by_group(df, [selected_group])

    st.caption(f"Mostrando {len(filtered)} contacto(s)")
    st.dataframe(
        filtered[["Nombre", "Apellido", "Email", "Telefono", "Grupos"]].rename(columns={"Telefono": "Teléfono"}),
        use_container_width=True,
        hide_index=True,
    )

def render_group_summary(df):
    st.subheader("Resumen por grupo")
    groups = extract_groups(df)

    if not groups:
        st.info("No se encontraron grupos. Crea una columna llamada Grupos en Google Sheets.")
        return

    summary = []
    for g in groups:
        count = filter_by_group(df, [g]).shape[0]
        summary.append({"Grupo": g, "Contactos": count})

    summary_df = pd.DataFrame(summary).sort_values("Contactos", ascending=False)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

def main():
    st.title("CRM Personalizado")
    st.caption("Conectado a Google Sheets")

    sheet_url = st.text_input("URL de Google Sheets")
    sheet_name = st.text_input("Nombre de la pestaña", value="Hoja1")

    if not sheet_url:
        st.warning("Pega la URL de tu Google Sheet.")
        return

    try:
        df = load_contacts(sheet_url, sheet_name)
    except Exception as e:
        st.error(f"No se pudo cargar la hoja: {e}")
        st.stop()

    st.sidebar.header("Filtros")
    search_text = st.sidebar.text_input("Buscar contacto", placeholder="Nombre, email, teléfono...")
    selected_groups = st.sidebar.multiselect("Grupos", extract_groups(df))
    start_date = st.sidebar.date_input("Fecha de nacimiento desde", value=None)
    end_date = st.sidebar.date_input("Fecha de nacimiento hasta", value=None)

    if st.sidebar.button("Recargar datos"):
        st.cache_data.clear()
        st.rerun()

    filtered_df = apply_filters(df, search_text, selected_groups, start_date, end_date)

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
