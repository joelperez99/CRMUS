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

DISPLAY_TO_SOURCE_MAP = {
    "Email": "Email",
    "DOB": "FechaNacimiento",
    "Pass 1": "Pass1",
    "Pass 2": "Pass2",
    "Nombre": "Nombre",
    "Apellido": "Apellido",
    "Telefono": "Telefono",
    "Usuario": "Usuario",
    "Grupo": "Grupos",
    "Activo": "Activo",
}

SOURCE_TO_DISPLAY_MAP = {
    "Email": "Email",
    "FechaNacimiento": "DOB",
    "Pass1": "Pass 1",
    "Pass2": "Pass 2",
    "Nombre": "Nombre",
    "Apellido": "Apellido",
    "Telefono": "Telefono",
    "Usuario": "Usuario",
    "Grupos": "Grupo",
    "Activo": "Activo",
}


@st.cache_resource
def connect_gsheet():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    return client


def get_worksheet():
    client = connect_gsheet()
    spreadsheet_id = st.secrets["sheets"]["spreadsheet_id"]
    worksheet_name = st.secrets["sheets"]["worksheet_name"]
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(worksheet_name)
    return ws


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
    ws = get_worksheet()
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

    display["DOB"] = display["FechaNacimiento"].apply(
        lambda x: x.strftime("%d/%m/%Y") if pd.notnull(x) else ""
    )
    display["Activo"] = display["Activo"].apply(normalize_active_value)
    display["Grupo"] = display["Grupos"]

    cols = [
        "Email",
        "DOB",
        "Pass1",
        "Pass2",
        "Nombre",
        "Apellido",
        "Telefono",
        "Usuario",
        "Grupo",
        "Activo",
    ]

    display = display[cols].rename(columns={
        "Pass1": "Pass 1",
        "Pass2": "Pass 2",
    })

    return display.copy()


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


def parse_display_dob(value):
    value = str(value).strip()
    if not value:
        return ""
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def get_sheet_header_map():
    ws = get_worksheet()
    headers = ws.row_values(1)
    return {header: idx + 1 for idx, header in enumerate(headers)}


def save_edited_rows_to_gsheet(edited_display_df: pd.DataFrame, original_filtered_df: pd.DataFrame):
    ws = get_worksheet()
    header_map = get_sheet_header_map()

    if "ID" not in original_filtered_df.columns:
        st.error("No se encontró la columna ID para guardar cambios.")
        return False

    edited_df = edited_display_df.copy()
    original_df = original_filtered_df.copy()

    original_df = original_df.reset_index(drop=True)
    edited_df = edited_df.reset_index(drop=True)

    # Asegurar misma longitud
    if len(edited_df) != len(original_df):
        st.error("La cantidad de filas editadas no coincide con la tabla original filtrada.")
        return False

    updates = []

    for i in range(len(edited_df)):
        row_id = str(original_df.loc[i, "ID"]).strip()
        if not row_id:
            continue

        sheet_row = i + 2
        if len(load_contacts()) != 0:
            # Buscar fila real en la hoja a partir del DataFrame completo
            full_df = load_contacts().reset_index(drop=True)
            matches = full_df.index[full_df["ID"].astype(str).str.strip() == row_id].tolist()
            if not matches:
                continue
            sheet_row = matches[0] + 2

        for display_col, source_col in DISPLAY_TO_SOURCE_MAP.items():
            if display_col not in edited_df.columns:
                continue

            new_value = edited_df.loc[i, display_col]

            if display_col == "DOB":
                new_value = parse_display_dob(new_value)
                old_raw = original_df.loc[i, "FechaNacimiento"]
                old_value = old_raw.strftime("%Y-%m-%d") if pd.notnull(old_raw) else ""
            elif display_col == "Grupo":
                old_value = str(original_df.loc[i, "Grupos"]).strip()
                new_value = str(new_value).strip()
            elif display_col == "Activo":
                old_value = normalize_active_value(original_df.loc[i, "Activo"])
                new_value = normalize_active_value(new_value)
            else:
                old_value = str(original_df.loc[i, source_col]).strip()
                new_value = str(new_value).strip()

            if str(old_value).strip() != str(new_value).strip():
                sheet_col = header_map.get(source_col)
                if sheet_col:
                    updates.append({
                        "range": gspread.utils.rowcol_to_a1(sheet_row, sheet_col),
                        "values": [[new_value]]
                    })

    if not updates:
        st.info("No hay cambios para guardar.")
        return False

    ws.batch_update(updates, value_input_option="USER_ENTERED")
    st.cache_data.clear()
    return True


def render_editable_table_with_save(df, table_key, save_key, success_key):
    original_filtered_df = df.copy().reset_index(drop=True)
    editable_df = prepare_display_table(original_filtered_df).copy()

    edited_df = st.data_editor(
        editable_df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key=table_key
    )

    if st.button("Guardar cambios", key=save_key):
        try:
            changed = save_edited_rows_to_gsheet(edited_df, original_filtered_df)
            if changed:
                st.session_state[success_key] = "Cambios guardados correctamente en Google Sheets."
                st.rerun()
        except Exception as e:
            st.error(f"No se pudieron guardar los cambios: {e}")

    if st.session_state.get(success_key):
        st.success(st.session_state[success_key])
        del st.session_state[success_key]


def render_main_table(df):
    st.subheader("Contactos")
    render_editable_table_with_save(
        df=df,
        table_key="main_table_editor",
        save_key="save_main_table",
        success_key="save_main_success"
    )


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

    render_editable_table_with_save(
        df=filtered,
        table_key="group_table_editor",
        save_key="save_group_table",
        success_key="save_group_success"
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

    render_editable_table_with_save(
        df=filtered,
        table_key="active_table_editor",
        save_key="save_active_table",
        success_key="save_active_success"
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
