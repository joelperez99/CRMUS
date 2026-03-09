import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="CRM Personalizado", layout="wide")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

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
    "Activo",
]

RENAME_MAP = {
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

@st.cache_resource
def connect_gsheet():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    return client

def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=RENAME_MAP)

    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[EXPECTED_COLUMNS].copy()

    text_cols = [
        "ID",
        "Nombre",
        "Apellido",
        "Email",
        "Telefono",
        "Direccion",
        "Pass1",
        "Pass2",
        "Usuario",
        "Notas",
        "Estado",
        "Grupos",
    ]

    for col in text_cols:
        df[col] = df[col].fillna("").astype(str)

    df["FechaNacimiento"] = pd.to_datetime(df["FechaNacimiento"], errors="coerce")
    df["NombreCompleto"] = (
        df["Nombre"].str.strip() + " " + df["Apellido"].str.strip()
    ).str.strip()

    return df

@st.cache_data(ttl=60)
def load_contacts():
    client = connect_gsheet()

    spreadsheet_id = st.secrets["sheets"]["spreadsheet_id"]
    worksheet_name = st.secrets["sheets"]["worksheet_name"]

    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(worksheet_name)

    records = ws.get_all_records()
    df = pd.DataFrame(records)

    return normalize_dataframe(df)

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
            | out["Grupos"].str.lower().str.contains(s, na=False)
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
        st.info("No hay grupos disponibles todavía. Agrega una columna 'Grupos' en tu Google Sheet.")
        return

    selected_group = st.selectbox("Selecciona un grupo", options=["Todos"] + groups)

    if selected_group == "Todos":
        filtered = df.copy()
    else:
        filtered = filter_by_group(df, [selected_group])

    st.caption(f"Mostrando {len(filtered)} contacto(s)")

    st.dataframe(
        filtered[["Nombre", "Apellido", "Email", "Telefono", "Grupos"]].rename(
            columns={"Telefono": "Teléfono"}
        ),
        use_container_width=True,
        hide_index=True,
    )

def render_group_summary(df):
    st.subheader("Resumen por grupo")
    groups = extract_groups(df)

    if not groups:
        st.info("No se encontraron grupos. Crea una columna llamada 'Grupos' en Google Sheets.")
        return

    summary = []
    for g in groups:
        count = filter_by_group(df, [g]).shape[0]
        summary.append({
            "Grupo": g,
            "Contactos": count
        })

    summary_df = pd.DataFrame(summary).sort_values("Contactos", ascending=False)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

def show_connection_info():
    with st.expander("Configuración actual", expanded=False):
        st.write("La app usa Google Sheets API con credenciales desde Streamlit secrets.")
        st.write("Asegúrate de haber compartido el spreadsheet con el client_email de la Service Account.")
        st.code(
            f"Spreadsheet ID: {st.secrets['sheets']['spreadsheet_id']}\n"
            f"Worksheet name: {st.secrets['sheets']['worksheet_name']}"
        )

def main():
    st.title("CRM Personalizado")
    st.caption("Conectado a Google Sheets por API")

    try:
        df = load_contacts()
    except Exception as e:
        st.error(f"No se pudo conectar al Google Sheet: {e}")
        st.stop()

    show_connection_info()

    st.sidebar.header("Filtros")
    search_text = st.sidebar.text_input(
        "Buscar contacto",
        placeholder="Nombre, email, teléfono..."
    )
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
