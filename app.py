import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

st.set_page_config(page_title="Gestión de Recogidas y Vaciados", layout="wide")

# Conexión a Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Cargar datos (ttl=0 para actualizaciones en tiempo real)
df = conn.read(worksheet="Hoja 1", ttl=0)

# Asegurar valores por defecto
if "Estatus" not in df.columns:
    df["Estatus"] = "Activo"
df["Estatus"] = df["Estatus"].fillna("Activo")
df["Valoracion"] = pd.to_numeric(df["Valoracion"], errors="coerce").fillna(0)

# Lista de estados permitidos
ESTADOS = ["Activo", "Realización", "Inactivo", "Cancelado"]

st.title("🚚 Control de Recogidas y Vaciados")

# Pestañas de navegación
tab_admin, tab_workers = st.tabs(["🦅 Vista Dirección (Eagle View)", "👷 Panel Operarios"])

# ==========================================
# PESTAÑA 1: VISTA DIRECCIÓN (EAGLE VIEW)
# ==========================================
with tab_admin:
    st.subheader("Resumen Diario por Estatus")
    
    # Filtro por Fecha
    fechas_disponibles = sorted(df["Fecha"].dropna().unique().tolist(), reverse=True)
    fecha_sel = st.selectbox("Seleccionar Fecha:", ["Todas"] + fechas_disponibles)
    
    df_view = df if fecha_sel == "Todas" else df[df["Fecha"] == fecha_sel]

    # KPIs superiores (6 columnas para incluir todos los estados)
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Trabajos", len(df_view))
    col2.metric("🟡 Activos", len(df_view[df_view["Estatus"] == "Activo"]))
    col3.metric("🔵 Realización", len(df_view[df_view["Estatus"] == "Realización"]))
    col4.metric("⚪ Inactivos", len(df_view[df_view["Estatus"] == "Inactivo"]))
    col5.metric("🔴 Cancelados", len(df_view[df_view["Estatus"] == "Cancelado"]))
    col6.metric("💶 Valoración", f"{df_view['Valoracion'].sum():,.2f} €")

    st.divider()

    # Desglose y Tabla
    col_chart, col_table = st.columns([1, 2])
    with col_chart:
        st.markdown("**Trabajos por Servicio y Estatus**")
        resumen = pd.crosstab(df_view["Servicio"], df_view["Estatus"])
        st.dataframe(resumen, use_container_width=True)

    with col_table:
        st.markdown("**Detalle de Operaciones**")
        st.dataframe(
            df_view[["Fecha", "Cliente", "CP", "Servicio", "Estatus", "Valoracion", "Notas"]],
            use_container_width=True,
            hide_index=True
        )

# ==========================================
# PESTAÑA 2: PANEL OPERARIOS
# ==========================================
with tab_workers:
    st.subheader("Actualizar Estatus y Valoración")
    
    # Filtro para operarios por defecto viendo Activos y en Realización
    filtro_estatus = st.multiselect(
        "Filtrar por estatus:",
        options=ESTADOS,
        default=["Activo", "Realización"]
    )
    
    trabajos = df[df["Estatus"].isin(filtro_estatus)]

    for idx, row in trabajos.iterrows():
        with st.expander(f"[{row['Estatus'].upper()}] {row['Cliente']} — CP: {row['CP']} ({row['Servicio']})"):
            st.write(f"**📍 Dirección:** {row['Direccion']} (CP: {row['CP']})")
            st.write(f"**📞 Teléfono:** {row['Telefono']}")
            st.write(f"**🪑 Muebles / Notas:** {row['Notas']}")
            
            c1, c2, c3 = st.columns([2, 2, 1])
            
            # Obtener índice seguro para el selectbox
            current_status = row["Estatus"]
            status_idx = ESTADOS.index(current_status) if current_status in ESTADOS else 0
            
            nuevo_estatus = c1.selectbox(
                "Cambiar Estatus",
                ESTADOS,
                index=status_idx,
                key=f"status_{idx}"
            )
            nueva_val = c2.number_input(
                "Valoración (€)",
                value=float(row["Valoracion"]),
                step=10.0,
                key=f"val_{idx}"
            )
            if c3.button("Guardar", key=f"btn_{idx}", type="primary"):
                df.at[idx, "Estatus"] = nuevo_estatus
                df.at[idx, "Valoracion"] = nueva_val
                conn.update(worksheet="Hoja 1", data=df)
                st.success("¡Actualizado en Google Sheets!")
                st.rerun()
