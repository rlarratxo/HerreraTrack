import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Gestión de Recogidas y Vaciados", layout="wide")

# Obtener URLs desde Secrets de Streamlit
SHEET_URL = st.secrets["SHEET_URL"]
SCRIPT_URL = st.secrets["SCRIPT_URL"]

# Convertir URL normal de Google Sheets en enlace directo de descarga CSV para "Respuestas de formulario 1"
sheet_id = SHEET_URL.split("/d/")[1].split("/")[0]
CSV_URL = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=Respuestas%20de%20formulario%201"

# Cargar datos en tiempo real desde la hoja pública
@st.cache_data(ttl=5)
def cargar_datos():
    df = pd.read_csv(CSV_URL)
    df.columns = df.columns.str.strip()
    return df

df = cargar_datos()

# Asegurar valores por defecto para Estatus, Valoración, Notas operario y Servicio
if "Estatus" not in df.columns:
    df["Estatus"] = "Activo"
df["Estatus"] = df["Estatus"].fillna("Activo").astype(str).str.strip()

if "Valoración" not in df.columns:
    df["Valoración"] = 0
df["Valoración"] = pd.to_numeric(df["Valoración"], errors="coerce").fillna(0)

if "Notas operario" not in df.columns:
    df["Notas operario"] = ""
df["Notas operario"] = df["Notas operario"].fillna("").astype(str)

if "Servicio" in df.columns:
    df["Servicio"] = df["Servicio"].fillna("Sin servicio").astype(str).str.strip()
    df.loc[df["Servicio"] == "", "Servicio"] = "Sin servicio"

# Procesar Marca Temporal -> Entrada (fecha y hora de entrada del trabajo)
if "Marca Temporal" in df.columns:
    df["Entrada"] = df["Marca Temporal"].fillna("Sin fecha").astype(str).str.strip()
    df["_dt"] = pd.to_datetime(df["Entrada"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    mask_na = df["_dt"].isna()
    if mask_na.any():
        df.loc[mask_na, "_dt"] = pd.to_datetime(df.loc[mask_na, "Entrada"], dayfirst=True, errors="coerce")
    df["Fecha_Filtro"] = df["_dt"].dt.strftime("%d/%m/%Y").fillna(df["Entrada"])
else:
    df["Entrada"] = "Sin fecha"
    df["Fecha_Filtro"] = "Sin fecha"

ESTADOS = ["Activo", "Valoración", "Realización", "Inactivo", "Cancelado"]

st.title("🚚 Control de Recogidas y Vaciados")

# Botón de refresco manual
if st.button("🔄 Actualizar datos ahora"):
    st.cache_data.clear()
    st.rerun()

# Orden invertido: primero Panel Operarios, luego Vista Dirección (Eagle View)
tab_workers, tab_admin = st.tabs(["👷 Panel Operarios", "🦅 Vista Dirección (Eagle View)"])

# ==========================================
# PESTAÑA 1: PANEL OPERARIOS
# ==========================================
with tab_workers:
    st.subheader("Actualizar Estatus, Valoración y Notas operario")

    filtro_estatus = st.multiselect(
        "Filtrar por estatus:",
        options=ESTADOS,
        default=["Activo", "Valoración", "Realización"]
    )

    trabajos = df[df["Estatus"].isin(filtro_estatus)]

    if trabajos.empty:
        st.info("No hay trabajos con los estatus seleccionados.")
    else:
        for idx, row in trabajos.iterrows():
            nombre_cliente = row.get("Nombre", "Sin nombre")
            cp_val = row.get("CP", "")
            servicio_val = row.get("Servicio", "")
            entrada_val = row.get("Entrada", "Sin fecha")

            with st.expander(f"[{row['Estatus'].upper()}] {nombre_cliente} — CP: {cp_val} ({servicio_val}) | 🕒 Entrada: {entrada_val}"):
                # Entrada (fecha y hora) siempre antes de Dirección para ver la frescura del trabajo
                st.write(f"**🕒 Entrada:** {entrada_val}")
                st.write(f"**📍 Dirección:** {row.get('Direccion', '')} (CP: {cp_val})")
                st.write(f"**📞 Teléfono:** {row.get('Teléfono', '')}")
                st.write(f"**🪑 Muebles / Notas:** {row.get('Notas', '')}")

                c1, c2 = st.columns([2, 2])
                current_status = row["Estado"]
                status_idx = ESTADOS.index(current_status) if current_status in ESTADOS else 0

                nuevo_estatus = c1.selectbox("Cambiar Estado", ESTADOS, index=status_idx, key=f"estado_{idx}")
                nueva_val = c2.number_input("Valoración (€)", value=float(row["Valoración"]), step=10.0, key=f"val_{idx}")

                nuevas_notas_op = st.text_area(
                    "Notas operario",
                    value=row["Notas operario"],
                    placeholder="Añade observaciones de campo, acceso, incidencias o estado del trabajo...",
                    key=f"notas_op_{idx}"
                )

                if st.button("Guardar", key=f"btn_{idx}", type="primary"):
                    payload = {
                        "row_index": int(idx),
                        "estatus": nuevo_estatus,
                        "valoracion": nueva_val,
                        "notas_operario": nuevas_notas_op,
                    }
                    try:
                        res = requests.post(SCRIPT_URL, json=payload, timeout=15)
                        if res.status_code == 200 and '"status":"ok"' in res.text.replace(" ", ""):
                            st.success("¡Guardado correctamente en Google Sheets!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.warning(f"Respuesta inesperada ({res.status_code}): {res.text[:250]}")
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

# ==========================================
# PESTAÑA 2: VISTA DIRECCIÓN (EAGLE VIEW)
# ==========================================
with tab_admin:
    st.subheader("Resumen Diario por Estado")

    fechas_disponibles = sorted(df["Fecha_Filtro"].dropna().unique().tolist(), reverse=True)
    fecha_sel = st.selectbox("Seleccionar Fecha (Entrada):", ["Todas"] + fechas_disponibles)

    df_view = df if fecha_sel == "Todas" else df[df["Fecha_Filtro"] == fecha_sel]

    # KPIs superiores - Fila 1
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Trabajos", len(df_view))
    c2.metric("🟡 Activos", len(df_view[df_view["Estatus"] == "Activo"]))
    c3.metric("🔍 Valoración", len(df_view[df_view["Estatus"] == "Valoración"]))
    c4.metric("🔵 Realización", len(df_view[df_view["Estatus"] == "Realización"]))

    # KPIs superiores - Fila 2
    c5, c6, c7 = st.columns(3)
    c5.metric("⚪ Inactivos", len(df_view[df_view["Estatus"] == "Inactivo"]))
    c6.metric("🔴 Cancelados", len(df_view[df_view["Estatus"] == "Cancelado"]))
    c7.metric("💶 Importe Total (€)", f"{df_view['Valoración'].sum():,.2f} €")

    st.divider()

    col_chart, col_table = st.columns([1, 2])
    with col_chart:
        st.markdown("**Trabajos por Servicio y Estado**")
        if "Servicio" in df_view.columns and not df_view.empty:
            resumen = df_view.groupby(["Servicio", "Estatus"]).size().unstack(fill_value=0)
            for est in ESTADOS:
                if est not in resumen.columns:
                    resumen[est] = 0
            resumen = resumen[ESTADOS]
            resumen["Total"] = resumen.sum(axis=1)
            st.dataframe(resumen, use_container_width=True)
        else:
            st.info("No hay datos de trabajos para mostrar.")

    with col_table:
        st.markdown("**Detalle de Operaciones**")
        columnas_deseadas = ["Entrada", "Nombre", "CP", "Servicio", "Estatus", "Valoración", "Notas", "Notas operario"]
        columnas_mostrar = [c for c in columnas_deseadas if c in df_view.columns]
        st.dataframe(df_view[columnas_mostrar], use_container_width=True, hide_index=True)
