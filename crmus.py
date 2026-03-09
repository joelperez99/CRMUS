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
    "Fecha de nacimiento": "FechaNacimiento",
    "FechaNacimiento": "FechaNacimiento",
    "Dirección": "Direccion",
    "Direccion": "Direccion",
    "Teléfono": "Telefono",
    "Telefono": "Telefono",
    "Pass 1": "Pass1",
    "Pass 2": "Pass2",
    "Grupo": "Grupos",
    "Grupos": "Grupos",
    "Usuario": "Usuario",
    "Activo": "Activo",
    "Nombre": "Nombre",
    "Apellido": "Apellido",
    "Email": "Email",
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
        "Activo",
    ]

    for col in text_cols:
        df[col] = df[col].fillna("").astype(str).str.strip()

    df["FechaNacimiento"] = pd.to_datetime(df["FechaNacimiento"], errors="coerce")
    df["NombreCompleto"] = (
        df["Nombre"].fillna("").astype(str).str.strip() + " " +
        df["Apellido"].fillna("").astype(str).str.strip()
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

def normalize_active_value(value: str) -> str:
    v = str(value).strip().lower()
    if v in ["sí", "si", "yes", "true", "1", "activo", "active"]:
        return "Sí"
    if v in ["no", "false", "0", "inactivo", "inactive"]:
        return "No"
    return str(value).strip()

def extract_active_options(df: pd.DataFrame):
    options = set()
    for value in df["Activo"].fillna(""):
        v = normalize_active_value(value)
        if v:
            options.add(v)

    ordered = []
    if "Sí" in options:
        ordered.append("Sí")
    if "No" in options:
        ordered.append("No")
    ordered.extend(sorted([x for x in options if x not in ["Sí", "No"]]))
    return ordered

def filter_by_group(df: pd.DataFrame, selected_groups):
    if not selected_groups:
        return df

    def row_has_group(value: str):
        row_groups = [x.strip().lower() for x in str(value).split(",") if x.strip()]
        return any(g.lower() in row_groups for g in selected_groups)

    return df[df["Grupos"].apply(row_has_group)].copy()

def filter_by_active(df: pd.DataFrame, selected_active):
    if not selected_active or selected_active == "Todos":
        return df.copy()

    normalized = df["Activo"].apply(normalize_active_value)
    return df[normalized == selected_active].copy()

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
            | out["Usuario"].str.lower().str.contains(s, na=False)
            | out["Grupos"].str.lower().str.contains(s, na=False)
            | out["Activo"].str.lower().str.contains(s, na=False)
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

def prepare_display_table(df):
    display = df.copy()
    display["FechaNacimiento"] = display["FechaNacimiento"].dt.strftime("%d/%m/%Y")
    display["FechaNacimiento"] = display["FechaNacimiento"].fillna("")
    display["Activo"] = display["Activo"].apply(normalize_active_value)

    display = display.rename(columns={
        "FechaNacimiento": "DOB",
        "Pass1": "Pass 1",
        "Pass2": "Pass 2",
        "Grupos": "Grupo",
        "Telefono": "Telefono",
    })

    cols = [
        "Email",
        "DOB",
        "Pass 1",
        "Pass 2",
        "Nombre",
        "Apellido",
        "Telefono",
        "Usuario",
        "Grupo",
        "Activo",
    ]

    existing = [c for c in cols if c in display.columns]
    return display[existing]

def render_main_table(df):
    st.subheader("Contactos")
    st.dataframe(
        prepare_display_table(df),
        use_container_width=True,
        hide_index=True
    )

def render_card_selector(title, options, key):
    st.markdown(f"### {title}")

    if key not in st.session_state:
        st.session_state[key] = options[0]

    selected = st.radio(
        label="",
        options=options,
        key=key,
        horizontal=True,
        label_visibility="collapsed"
    )

    return selected

def render_contacts_by_group(df):
    st.subheader("Ver contactos por grupo")
    groups = extract_groups(df)

    if not groups:
        st.info("No hay grupos disponibles todavía. Agrega una columna 'Grupos' en tu Google Sheet.")
        return

    selected_group = render_card_selector(
        "Selecciona un grupo",
        ["Todos"] + groups,
        "selected_group_button"
    )

    st.markdown(f"**Grupo seleccionado:** {selected_group}")

    if selected_group == "Todos":
        filtered = df.copy()
    else:
        filtered = filter_by_group(df, [selected_group])

    st.caption(f"Mostrando {len(filtered)} contacto(s)")

    st.dataframe(
        prepare_display_table(filtered),
        use_container_width=True,
        hide_index=True,
    )

def render_contacts_by_active(df):
    st.subheader("Ver contactos por activo")

    active_options = extract_active_options(df)

    if not active_options:
        st.info("No hay valores en la columna 'Activo' todavía.")
        return

    selected_active = render_card_selector(
        "Selecciona una opción",
        ["Todos"] + active_options,
        "selected_active_button"
    )

    st.markdown(f"**Activo seleccionado:** {selected_active}")

    filtered = filter_by_active(df, selected_active)

    st.caption(f"Mostrando {len(filtered)} contacto(s)")

    st.dataframe(
        prepare_display_table(filtered),
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
    st.markdown("""
    <style>
        .block-container {
            padding-top: 0.8rem !important;
            padding-bottom: 1rem !important;
        }

        [data-testid="stHeader"] {
            height: 0rem;
        }

        [data-testid="stToolbar"] {
            top: 0.5rem;
            right: 0.5rem;
        }

        div[role="radiogroup"] {
            display: flex;
            gap: 18px;
            flex-wrap: wrap;
            margin-bottom: 8px;
        }

        div[role="radiogroup"] > label {
            background: white;
            border: 1px solid #d9d9d9;
            border-radius: 18px;
            padding: 24px 28px;
            min-width: 220px;
            min-height: 92px;
            display: flex !important;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 18px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        div[role="radiogroup"] > label:hover {
            border-color: #999;
            box-shadow: 0 2px 10px rgba(0,0,0,0.06);
        }

        div[role="radiogroup"] input[type="radio"] {
            display: none;
        }

        div[role="radiogroup"] input[type="radio"]:checked + div {
            color: #111827 !important;
            font-weight: 700 !important;
        }

        div[role="radiogroup"] > label:has(input[type="radio"]:checked) {
            background: #e8f0fe;
            border: 2px solid #4f8dfd;
            box-shadow: 0 0 0 1px #4f8dfd inset;
        }
    </style>
    """, unsafe_allow_html=True)

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
        placeholder="Nombre, email, teléfono, usuario..."
    )
    selected_groups = st.sidebar.multiselect("Grupos", extract_groups(df))
    start_date = st.sidebar.date_input("Fecha de nacimiento desde", value=None)
    end_date = st.sidebar.date_input("Fecha de nacimiento hasta", value=None)

    if st.sidebar.button("Recargar datos"):
        st.cache_data.clear()
        st.rerun()

    filtered_df = apply_filters(df, search_text, selected_groups, start_date, end_date)

    metrics_cards(filtered_df)

    tab1, tab2, tab3, tab4 = st.tabs(["Vista general", "Por grupos", "Activos", "Resumen"])

    with tab1:
        render_main_table(filtered_df)

    with tab2:
        render_contacts_by_group(filtered_df)

    with tab3:
        render_contacts_by_active(filtered_df)

    with tab4:
        render_group_summary(filtered_df)

if __name__ == "__main__":
    main()
