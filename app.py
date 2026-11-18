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

# Asegurar valores por defecto para Estatus y Valoración
if "Estatus" not in df.columns:
    df["Estatus"] = "Activo"
df["Estatus"] = df["Estatus"].fillna("Activo")

if "Valoración" not in df.columns:
    df["Valoración"] = 0
df["Valoración"] = pd.to_numeric(df["Valoración"], errors="coerce").fillna(0)

# Procesar Marca Temporal (formato: 28/08/2026 11:44:32)
if "Marca Temporal" in df.columns:
    df["_dt"] = pd.to_datetime(df["Marca Temporal"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    df["Fecha_Filtro"] = df["_dt"].dt.strftime("%d/%m/%Y").fillna(df["Marca Temporal"].astype(str))
else:
    df["Fecha_Filtro"] = "Sin fecha"

ESTADOS = ["Activo", "Valoración", "Realización", "Inactivo", "Cancelado"]

st.title("🚚 Control de Recogidas y Vaciados")

# Botón de refresco manual
if st.button("🔄 Actualizar datos ahora"):
    st.cache_data.clear()
    st.rerun()

tab_admin, tab_workers = st.tabs(["🦅 Vista Dirección (Eagle View)", "👷 Panel Operarios"])

# ==========================================
# PESTAÑA 1: VISTA DIRECCIÓN (EAGLE VIEW)
# ==========================================
with tab_admin:
    st.subheader("Resumen Diario por Estatus")
    
    fechas_disponibles = sorted(df["Fecha_Filtro"].dropna().unique().tolist(), reverse=True)
    fecha_sel = st.selectbox("Seleccionar Fecha (Marca Temporal):", ["Todas"] + fechas_disponibles)
    
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
        st.markdown("**Trabajos por Servicio y Estatus**")
        if "Servicio" in df_view.columns:
            resumen = pd.crosstab(df_view["Servicio"], df_view["Estatus"])
            st.dataframe(resumen, use_container_width=True)

    with col_table:
        st.markdown("**Detalle de Operaciones**")
        columnas_deseadas = ["Marca Temporal", "Nombre", "CP", "Servicio", "Estatus", "Valoración", "Notas"]
        columnas_mostrar = [c for c in columnas_deseadas if c in df_view.columns]
        st.dataframe(df_view[columnas_mostrar], use_container_width=True, hide_index=True)

# ==========================================
# PESTAÑA 2: PANEL OPERARIOS
# ==========================================
with tab_workers:
    st.subheader("Actualizar Estatus y Valoración")
    
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
            timestamp = row.get("Marca Temporal", "")
            
            with st.expander(f"[{row['Estatus'].upper()}] {nombre_cliente} — CP: {cp_val} ({servicio_val}) | 🕒 {timestamp}"):
                st.write(f"**📍 Dirección:** {row.get('Direccion', '')} (CP: {cp_val})")
                st.write(f"**📞 Teléfono:** {row.get('Teléfono', '')}")
                st.write(f"**🪑 Muebles / Notas:** {row.get('Notas', '')}")
                
                c1, c2, c3 = st.columns([2, 2, 1])
                current_status = row["Estatus"]
                status_idx = ESTADOS.index(current_status) if current_status in ESTADOS else 0
                
                nuevo_estatus = c1.selectbox("Cambiar Estatus", ESTADOS, index=status_idx, key=f"status_{idx}")
                nueva_val = c2.number_input("Valoración (€)", value=float(row["Valoración"]), step=10.0, key=f"val_{idx}")
                
                if c3.button("Guardar", key=f"btn_{idx}", type="primary"):
                    payload = {
                        "row_index": int(idx),
                        "estatus": nuevo_estatus,
                        "valoracion": nueva_val
                    }
                    res = requests.post(SCRIPT_URL, json=payload)
                    if res.status_code == 200:
                        st.success("¡Guardado correctamente en Google Sheets!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Error al guardar. Revisa la URL del Apps Script.")
