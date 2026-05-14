import streamlit as st
from streamlit_gsheets import GSheetsConnection
from streamlit_option_menu import option_menu
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import plotly.express as px
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import xlsxwriter

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="CLX Group - BI Metas", layout="wide", initial_sidebar_state="expanded")

# Estilos CSS
st.markdown("""
    <style>
    [data-testid="stSidebarCollapseButton"] { visibility: visible !important; color: #1e1e1e !important; }
    [data-testid="stDecoration"] {visibility: hidden !important;}
    .stApp { background-color: white !important; color: #1e1e1e !important; }
    [data-testid="stSidebar"] { background-color: #f8f9fa !important; }
    .stButton>button, .stDownloadButton>button { 
        background-color: #1e1e1e !important; 
        color: white !important; 
        border: none !important;
        padding: 0.6rem 2rem !important;
        font-weight: 700 !important;
        border-radius: 4px !important;
    }
    .stMetric { background-color: #ffffff !important; padding: 20px; border-radius: 8px; border: 1px solid #eeeeee !important; }
    </style>
    """, unsafe_allow_html=True)

LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/1/1a/Logo_CLX_Group.png"

# --- LÓGICA DE BASE DE DATOS (AUTO-CONFIG) ---
def init_db(conn):
    """Crea las tablas en Google Sheets si no existen."""
    required_sheets = {
        "SUCURSALES": ["ID", "Nombre"],
        "METAS": ["Sucursal", "Mes", "Año", "Monto_USD"],
        "TASAS": ["Fecha", "USD", "EUR"],
        "REGISTROS": ["Sucursal", "Fecha", "Facturado_BS", "Tasa_USD", "Facturado_USD", "Meta_Calculada_USD"]
    }
    for sheet, cols in required_sheets.items():
        try:
            conn.read(worksheet=sheet)
        except:
            # Si falla la lectura, creamos la hoja con los headers
            df_empty = pd.DataFrame(columns=cols)
            conn.update(worksheet=sheet, data=df_empty)
            st.toast(f"Tabla {sheet} configurada correctamente")

# --- FUNCIONES SOPORTE ---
def format_bcv(value):
    try: return f"{float(value):.4f}".replace('.', ',')
    except: return "0,0000"

def get_bcv_rates():
    try:
        r = requests.get("https://www.bcv.org.ve/", headers={'User-Agent': 'Mozilla/5.0'}, verify=False, timeout=5)
        s = BeautifulSoup(r.content, 'html.parser')
        u = float(s.find('div', id='dolar').find('strong').text.strip().replace(',', '.'))
        e = float(s.find('div', id='euro').find('strong').text.strip().replace(',', '.'))
        return u, e
    except: return None, None

def init_demo_state():
    if 'mock_SUCURSALES' not in st.session_state:
        st.session_state.mock_SUCURSALES = pd.DataFrame([{"ID": 1, "Nombre": "CLX Valencia"}])
        st.session_state.mock_TASAS = pd.DataFrame([{"Fecha": str(datetime.now().date()), "USD": 36.5, "EUR": 39.2}])
        st.session_state.mock_METAS = pd.DataFrame([{"Sucursal": "CLX Valencia", "Mes": "Mayo", "Año": 2026, "Monto_USD": 50000.0}])
        st.session_state.mock_REGISTROS = pd.DataFrame(columns=["Sucursal", "Fecha", "Facturado_BS", "Tasa_USD", "Facturado_USD", "Meta_Calculada_USD"])

# --- NAVEGACIÓN ---
with st.sidebar:
    st.image(LOGO_URL, use_container_width=True)
    selected = option_menu(menu_title=None, options=["Dashboard", "Estadisticas", "Registro Diario", "Configurar Metas", "Sucursales", "Tasas BCV", "Reportes", "Configuracion"], default_index=0, styles={"nav-link-selected": {"background-color": "#1e1e1e"}})
    st.session_state.demo_mode = st.checkbox("Modo Demo", value=True)
    if st.session_state.demo_mode: init_demo_state()

# --- CONEXIÓN ---
def get_conn():
    if st.session_state.demo_mode: return None
    return st.connection("gsheets", type=GSheetsConnection)

def get_data(ws):
    if st.session_state.demo_mode: return st.session_state[f'mock_{ws}']
    return get_conn().read(worksheet=ws)

def update_data(ws, df):
    if st.session_state.demo_mode: st.session_state[f'mock_{ws}'] = df
    else: get_conn().update(worksheet=ws, data=df)

# --- MÓDULOS ---

if selected == "Dashboard":
    st.title("Dashboard Ejecutivo")
    df_t, df_r = get_data("TASAS"), get_data("REGISTROS")
    if not df_t.empty:
        l = df_t.iloc[-1]
        c1, c2, c3 = st.columns(3)
        c1.metric("USD BCV", f"{format_bcv(l['USD'])} Bs")
        c2.metric("EUR BCV", f"{format_bcv(l['EUR'])} Bs")
        c3.metric("Facturacion Total", f"${df_r['Facturado_USD'].sum() if not df_r.empty else 0:,.2f} USD")

elif selected == "Configuracion":
    st.title("Configuracion de Sistema")
    st.markdown("Conecta tu Google Sheet para empezar a usar la aplicacion en produccion.")
    sheet_url = st.text_input("Google Sheet URL", placeholder="https://docs.google.com/spreadsheets/d/...")
    if st.button("INICIALIZAR BASE DE DATOS"):
        if not st.session_state.demo_mode:
            init_db(get_conn())
            st.success("Tablas creadas y vinculadas con exito.")
        else:
            st.warning("Desactiva el Modo Demo para inicializar una base de datos real.")

elif selected == "Tasas BCV":
    st.title("Tasas")
    df_t = get_data("TASAS")
    c1, c2, c3 = st.columns([6, 2, 2])
    if c2.button("SINCRONIZAR"):
        u, e = get_bcv_rates()
        if u:
            hoy = str(datetime.now().date()); df_t = df_t[df_t['Fecha'] != hoy]
            df_t = pd.concat([df_t, pd.DataFrame([{"Fecha": hoy, "USD": u, "EUR": e}])]).sort_values("Fecha")
            update_data("TASAS", df_t); st.rerun()
    if c3.button("GUARDAR"): update_data("TASAS", st.session_state.ed_tas); st.success("Guardado"); st.rerun()
    st.session_state.ed_tas = st.data_editor(df_t, num_rows="dynamic", use_container_width=True)

elif selected == "Registro Diario":
    st.title("Registro Diario")
    df_r = get_data("REGISTROS")
    c1, c2 = st.columns([8, 2])
    if c2.button("ACTUALIZAR"): update_data("REGISTROS", st.session_state.ed_reg); st.success("Actualizado"); st.rerun()
    st.session_state.ed_reg = st.data_editor(df_r, num_rows="dynamic", use_container_width=True)

elif selected == "Sucursales":
    st.title("Sucursales")
    df_s = get_data("SUCURSALES")
    c1, c2 = st.columns([8, 2])
    if c2.button("GUARDAR"): update_data("SUCURSALES", st.session_state.ed_suc); st.success("Guardado"); st.rerun()
    st.session_state.ed_suc = st.data_editor(df_s, num_rows="dynamic", use_container_width=True)

elif selected == "Configurar Metas":
    st.title("Metas")
    df_m = get_data("METAS")
    c1, c2 = st.columns([8, 2])
    if c2.button("GUARDAR"): update_data("METAS", st.session_state.ed_met); st.success("Guardado"); st.rerun()
    st.session_state.ed_met = st.data_editor(df_m, num_rows="dynamic", use_container_width=True)

st.markdown("---")
st.caption(f"CLX Group | {datetime.now().year}")
