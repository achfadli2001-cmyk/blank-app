
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from io import BytesIO
import openpyxl

# ==================== KONFIGURASI HALAMAN ====================
st.set_page_config(
    page_title="RAB Dinamis Kelapa Sawit - 25 Tahun",
    page_icon="🌴",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CUSTOM CSS (DARK MODE PROFESSIONAL) ====================
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #1e2530;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #2e3a4a;
    }
    .metric-card {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 20px;
        border-radius: 12px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .metric-value {
        font-size: 32px;
        font-weight: bold;
        margin: 10px 0;
    }
    .metric-label {
        font-size: 14px;
        opacity: 0.9;
    }
    h1 {
        color: #4CAF50;
        text-align: center;
        padding: 20px 0;
    }
    .section-header {
        background: linear-gradient(90deg, #2e7d32 0%, #4CAF50 100%);
        padding: 10px 20px;
        border-radius: 8px;
        color: white;
        font-weight: bold;
        margin: 20px 0 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# ==================== FUNGSI HELPER ====================

def get_yield_curve(year, luas_lahan):
    """
    Kurva produksi kelapa sawit berdasarkan umur tanaman
    Return: Ton TBS per tahun
    """
    if year <= 3:
        return 0  # TBM
    elif year == 4:
        return 12 * luas_lahan
    elif year == 5:
        return 15 * luas_lahan
    elif year == 6:
        return 18 * luas_lahan
    elif year == 7:
        return 22 * luas_lahan
    elif 8 <= year <= 15:
        return 26.5 * luas_lahan  # Masa puncak (rata-rata 25-28)
    elif 16 <= year <= 19:
        return 23 * luas_lahan  # Rata-rata 22-24
    elif 20 <= year <= 25:
        return 19 * luas_lahan  # Penurunan (rata-rata 18-20)
    else:
        return 15 * luas_lahan


def format_currency(value):
    """Format angka ke Rupiah"""
    return f"Rp {value:,.0f}".replace(",", ".")

def create_default_capex():
    """Data default CAPEX (Tahun 0) - Update April 2026"""
    return pd.DataFrame({
        'Item': [
            'Land Clearing & Persiapan Lahan',
            'Bibit Kelapa Sawit (Bersertifikat)',
            'Penanaman & Tenaga Kerja',
            'Pupuk Dasar (NPK, Dolomit)',
            'Alat Kerja (Cangkul, Sprayer, dll)',
            'Infrastruktur Dasar (Jalan, Parit)'
        ],
        'Satuan': ['Ha', 'Pokok', 'Ha', 'Ha', 'Set', 'Ha'],
        'Harga Satuan (Rp)': [8500000, 45000, 3500000, 4200000, 2500000, 6000000],
        'Volume': [1, 136, 1, 1, 1, 1],
        'Subtotal (Rp)': [0, 0, 0, 0, 0, 0]
    })

def create_default_opex_tbm():
    """Data default OPEX TBM (Per Tahun) - Update April 2026"""
    return pd.DataFrame({
        'Item': [
            'Pupuk Urea',
            'Pupuk NPK',
            'Pupuk Dolomit',
            'Herbisida (Roundup)',
            'Insektisida',
            'Upah Pemupukan',
            'Upah Penyemprotan',
            'Upah Pemeliharaan Umum'
        ],
        'Satuan': ['Kg', 'Kg', 'Kg', 'Liter', 'Liter', 'HOK', 'HOK', 'HOK'],
        'Harga Satuan (Rp)': [11000, 14500, 8500, 85000, 120000, 100000, 100000, 100000],
        'Volume/Ha': [250, 300, 200, 8, 4, 12, 8, 15],
        'Subtotal (Rp)': [0, 0, 0, 0, 0, 0, 0, 0]
    })

def create_default_opex_tm():
    """Data default OPEX TM (Per Tahun) - Update April 2026"""
    return pd.DataFrame({
        'Item': [
            'Pupuk Urea',
            'Pupuk NPK',
            'Pupuk KCl',
            'Pupuk Dolomit',
            'Herbisida',
            'Upah Panen (per Kg TBS)',
            'Upah Langsir TBS',
            'Transport ke PKS',
            'Pemeliharaan Jalan & Parit',
            'Upah Pemupukan'
        ],
        'Satuan': ['Kg', 'Kg', 'Kg', 'Kg', 'Liter', 'Kg', 'Ton', 'Ton', 'Ha', 'HOK'],
        'Harga Satuan (Rp)': [11000, 14500, 13000, 8500, 85000, 300, 50000, 150000, 500000, 100000],
        'Volume/Ha': [400, 500, 300, 250, 10, 0, 0, 0, 1, 18],
        'Subtotal (Rp)': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    })

# ==================== SIDEBAR INPUT ====================
st.sidebar.image("https://img.icons8.com/color/96/000000/palm-tree.png", width=80)
st.sidebar.title("⚙️ Konfigurasi Global")

luas_lahan = st.sidebar.number_input(
    "🌾 Luas Lahan (Ha)", 
    min_value=1.0, 
    max_value=10000.0, 
    value=10.0, 
    step=1.0
)

pokok_per_ha = st.sidebar.number_input(
    "🌱 Jumlah Pokok per Ha", 
    min_value=100, 
    max_value=200, 
    value=136, 
    step=1
)

durasi_tbm = st.sidebar.number_input(
    "⏳ Durasi TBM (Tahun)", 
    min_value=2, 
    max_value=5, 
    value=3, 
    step=1
)

total_tahun = st.sidebar.number_input(
    "📅 Total Siklus Investasi (Tahun)", 
    min_value=10, 
    max_value=30, 
    value=25, 
    step=1
)

harga_tbs = st.sidebar.number_input(
    "💰 Harga TBS Saat Ini (Rp/Kg)", 
    min_value=1000, 
    max_value=5000, 
    value=2100, 
    step=50
)

st.sidebar.markdown("---")
st.sidebar.info(f"""
**📊 Ringkasan Input:**
- Total Pokok: **{int(luas_lahan * pokok_per_ha):,}** pokok
- Fase TBM: Tahun 0-{durasi_tbm}
- Fase TM: Tahun {durasi_tbm+1}-{total_tahun}
""")

# ==================== HEADER UTAMA ====================
st.markdown("<h1>🌴 SISTEM RAB DINAMIS & PROYEKSI PROFITABILITAS KELAPA SAWIT</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888;'>Analisis Investasi Jangka Panjang (25 Tahun) | Update Data Pasar April 2026</p>", unsafe_allow_html=True)

# ==================== TAB NAVIGATION ====================
tab1, tab2, tab3, tab4 = st.tabs(["📋 RAB CAPEX", "🌱 RAB OPEX TBM", "🌴 RAB OPEX TM", "📈 PROYEKSI & ANALISIS"])

# ==================== TAB 1: CAPEX ====================
with tab1:
    st.markdown("<div class='section-header'>💼 CAPITAL EXPENDITURE (CAPEX) - TAHUN 0</div>", unsafe_allow_html=True)
    
    if 'df_capex' not in st.session_state:
        st.session_state.df_capex = create_default_capex()
    
    # Update volume bibit otomatis
    st.session_state.df_capex.loc[1, 'Volume'] = int(luas_lahan * pokok_per_ha)
    
    # Update volume lainnya
    for idx in [0, 2, 3, 5]:
        st.session_state.df_capex.loc[idx, 'Volume'] = luas_lahan
    
    # Hitung subtotal
    st.session_state.df_capex['Subtotal (Rp)'] = (
        st.session_state.df_capex['Harga Satuan (Rp)'] * 
        st.session_state.df_capex['Volume']
    )
    
    edited_capex = st.data_editor(
        st.session_state.df_capex,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Harga Satuan (Rp)": st.column_config.NumberColumn(
                "Harga Satuan (Rp)",
                format="Rp %.0f"
            ),
            "Subtotal (Rp)": st.column_config.NumberColumn(
                "Subtotal (Rp)",
                format="Rp %.0f",
                disabled=True
            )
        }
    )
    
    st.session_state.df_capex = edited_capex
    total_capex = edited_capex['Subtotal (Rp)'].sum()
    
    col1, col2 = st.columns([3, 1])
    with col2:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>TOTAL CAPEX</div>
            <div class='metric-value'>{format_currency(total_capex)}</div>
        </div>
        """, unsafe_allow_html=True)

# ==================== TAB 2: OPEX TBM ====================
with tab2:
    st.markdown("<div class='section-header'>🌱 OPERATIONAL EXPENDITURE TBM (Per Tahun)</div>", unsafe_allow_html=True)
    st.info(f"💡 Biaya ini akan diulang selama **{durasi_tbm} tahun** fase TBM (Tanaman Belum Menghasilkan)")
    
    if 'df_opex_tbm' not in st.session_state:
        st.session_state.df_opex_tbm = create_default_opex_tbm()
    
    # Hitung subtotal
    st.session_state.df_opex_tbm['Subtotal (Rp)'] = (
        st.session_state.df_opex_tbm['Harga Satuan (Rp)'] * 
        st.session_state.df_opex_tbm['Volume/Ha'] * 
        luas_lahan
    )
    
    edited_opex_tbm = st.data_editor(
        st.session_state.df_opex_tbm,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Harga Satuan (Rp)": st.column_config.NumberColumn(
                "Harga Satuan (Rp)",
                format="Rp %.0f"
            ),
            "Subtotal (Rp)": st.column_config.NumberColumn(
                "Subtotal (Rp)",
                format="Rp %.0f",
                disabled=True
            )
        }
    )
    
    st.session_state.df_opex_tbm = edited_opex_tbm
    total_opex_tbm_per_tahun = edited_opex_tbm['Subtotal (Rp)'].sum()
    total_opex_tbm_all = total_opex_tbm_per_tahun * durasi_tbm
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>OPEX TBM Per Tahun</div>
            <div class='metric-value'>{format_currency(total_opex_tbm_per_tahun)}</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>Total OPEX TBM ({durasi_tbm} Tahun)</div>
            <div class='metric-value'>{format_currency(total_opex_tbm_all)}</div>
        </div>
        """, unsafe_allow_html=True)

# ==================== TAB 3: OPEX TM ====================
with tab3:
    st.markdown("<div class='section-header'>🌴 OPERATIONAL EXPENDITURE TM (Per Tahun)</div>", unsafe_allow_html=True)
    st.info(f"💡 Biaya ini akan diulang selama **{total_tahun - durasi_tbm} tahun** fase TM (Tanaman Menghasilkan)")
    
    if 'df_opex_tm' not in st.session_state:
        st.session_state.df_opex_tm = create_default_opex_tm()
    
    # Hitung subtotal (untuk item non-panen)
    for idx in range(len(st.session_state.df_opex_tm)):
        if st.session_state.df_opex_tm.loc[idx, 'Item'] not in ['Upah Panen (per Kg TBS)', 'Upah Langsir TBS', 'Transport ke PKS']:
            st.session_state.df_opex_tm.loc[idx, 'Subtotal (Rp)'] = (
                st.session_state.df_opex_tm.loc[idx, 'Harga Satuan (Rp)'] * 
                st.session_state.df_opex_tm.loc[idx, 'Volume/Ha'] * 
                luas_lahan
            )
    
    edited_opex_tm = st.data_editor(
        st.session_state.df_opex_tm,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Harga Satuan (Rp)": st.column_config.NumberColumn(
                "Harga Satuan (Rp)",
                format="Rp %.0f"
            ),
            "Subtotal (Rp)": st.column_config.NumberColumn(
                "Subtotal (Rp)",
                format="Rp %.0f",
                disabled=True
            )
        }
    )
    
    st.session_state.df_opex_tm = edited_opex_tm
    
    st.warning("⚠️ Biaya Panen, Langsir, dan Transport akan dihitung otomatis berdasarkan produksi aktual per tahun")

# ==================== TAB 4: PROYEKSI & ANALISIS ====================
with tab4:
    st.markdown("<div class='section-header'>📊 PROYEKSI PROFITABILITAS JANGKA PANJANG</div>", unsafe_allow_html=True)
    
    # Hitung proyeksi per tahun
    proyeksi_data = []
    cumulative_profit = 0
    bep_year = None
    
    for year in range(total_tahun + 1):
        # CAPEX (hanya tahun 0)
        capex = total_capex if year == 0 else 0
        
        # OPEX
        if year <= durasi_tbm:
            opex = total_opex_tbm_per_tahun if year > 0 else 0
            produksi_ton = 0
            pendapatan = 0
        else:
            # OPEX TM (fixed cost)
            opex_fixed = 0
            for idx in range(len(st.session_state.df_opex_tm)):
                if st.session_state.df_opex_tm.loc[idx, 'Item'] not in ['Upah Panen (per Kg TBS)', 'Upah Langsir TBS', 'Transport ke PKS']:
                    opex_fixed += st.session_state.df_opex_tm.loc[idx, 'Subtotal (Rp)']
            
            # Produksi
            produksi_ton = get_yield_curve(year, luas_lahan)
            produksi_kg = produksi_ton * 1000
            
            # OPEX variabel (tergantung produksi)
            upah_panen = produksi_kg * st.session_state.df_opex_tm[st.session_state.df_opex_tm['Item'] == 'Upah Panen (per Kg TBS)']['Harga Satuan (Rp)'].values[0]
            upah_langsir = produksi_ton * st.session_state.df_opex_tm[st.session_state.df_opex_tm['Item'] == 'Upah Langsir TBS']['Harga Satuan (Rp)'].values[0]
            transport = produksi_ton * st.session_state.df_opex_tm[st.session_state.df_opex_tm['Item'] == 'Transport ke PKS']['Harga Satuan (Rp)'].values[0]
            
            opex = opex_fixed + upah_panen + upah_langsir + transport
            pendapatan = produksi_kg * harga_tbs
        
        # Cash Flow
        cash_flow = pendapatan - capex - opex
        cumulative_profit += cash_flow
        
        # Deteksi BEP
        if bep_year is None and cumulative_profit > 0 and year > 0:
            bep_year = year
        
        proyeksi_data.append({
            'Tahun': year,
            'Fase': 'CAPEX' if year == 0 else ('TBM' if year <= durasi_tbm else 'TM'),
            'CAPEX (Rp)': capex,
            'OPEX (Rp)': opex,
            'Produksi (Ton)': produksi_ton,
            'Pendapatan (Rp)': pendapatan,
            'Cash Flow (Rp)': cash_flow,
            'Cumulative Profit (Rp)': cumulative_profit
        })
    
    df_proyeksi = pd.DataFrame(proyeksi_data)
    
    # ==================== METRICS CARDS ====================
    total_investasi = total_capex + total_opex_tbm_all
    total_pendapatan = df_proyeksi['Pendapatan (Rp)'].sum()
    total_profit = df_proyeksi['Cash Flow (Rp)'].sum()
    avg_profit_per_bulan = total_profit / (total_tahun * 12) if total_tahun > 0 else 0
    roi = (total_profit / total_investasi * 100) if total_investasi > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class='metric-card' style='background: linear-gradient(135deg, #d32f2f 0%, #f44336 100%);'>
            <div class='metric-label'>💸 Total Investasi Awal</div>
            <div class='metric-value'>{format_currency(total_investasi)}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class='metric-card' style='background: linear-gradient(135deg, #1976d2 0%, #2196F3 100%);'>
            <div class='metric-label'>📅 Break Even Point</div>
            <div class='metric-value'>Tahun {bep_year if bep_year else 'N/A'}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class='metric-card' style='background: linear-gradient(135deg, #388e3c 0%, #4CAF50 100%);'>
            <div class='metric-label'>💰 Profit per Bulan (Avg)</div>
            <div class='metric-value'>{format_currency(avg_profit_per_bulan)}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class='metric-card' style='background: linear-gradient(135deg, #f57c00 0%, #ff9800 100%);'>
            <div class='metric-label'>📈 ROI ({total_tahun} Tahun)</div>
            <div class='metric-value'>{roi:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # ==================== GRAFIK INTERAKTIF ====================
    fig = go.Figure()
    
    # Area background untuk fase TBM dan TM
    fig.add_vrect(
        x0=0, x1=durasi_tbm,
        fillcolor="rgba(255, 152, 0, 0.1)",
        layer="below", line_width=0,
        annotation_text="Fase TBM", annotation_position="top left"
    )
    
    fig.add_vrect(
        x0=durasi_tbm, x1=total_tahun,
        fillcolor="rgba(76, 175, 80, 0.1)",
        layer="below", line_width=0,
        annotation_text="Fase TM", annotation_position="top left"
    )
    
    # Line Chart: Cash Flow Tahunan
    fig.add_trace(go.Scatter(
        x=df_proyeksi['Tahun'],
        y=df_proyeksi['Cash Flow (Rp)'],
        mode='lines+markers',
        name='Cash Flow Tahunan',
        line=dict(color='#2196F3', width=3),
        marker=dict(size=6),
        hovertemplate='Tahun %{x}<br>Cash Flow: Rp %{y:,.0f}<extra></extra>'
    ))
    
    # Line Chart: Cumulative Profit
    fig.add_trace(go.Scatter(
        x=df_proyeksi['Tahun'],
        y=df_proyeksi['Cumulative Profit (Rp)'],
        mode='lines+markers',
        name='Akumulasi Laba',
        line=dict(color='#4CAF50', width=4),
        marker=dict(size=8),
        fill='tozeroy',
        fillcolor='rgba(76, 175, 80, 0.2)',
        hovertemplate='Tahun %{x}<br>Akumulasi: Rp %{y:,.0f}<extra></extra>'
    ))
    
    # Garis BEP
    if bep_year:
        fig.add_vline(
            x=bep_year, 
            line_dash="dash", 
            line_color="red", 
            line_width=2,
            annotation_text=f"BEP: Tahun {bep_year}",
            annotation_position="top"
        )
    
    # Garis nol
    fig.add_hline(y=0, line_dash="dot", line_color="white", line_width=1)
    
    fig.update_layout(
        title={
            'text': '📈 Proyeksi Profitabilitas Jangka Panjang (25 Tahun)',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 20, 'color': '#4CAF50'}
        },
        xaxis_title='Tahun',
        yaxis_title='Rupiah (Rp)',
        hovermode='x unified',
        template='plotly_dark',
        height=600,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # ==================== TABEL PROYEKSI ====================
    st.markdown("<div class='section-header'>📋 Detail Proyeksi Per Tahun</div>", unsafe_allow_html=True)
    
    # Format tabel untuk display
    df_display = df_proyeksi.copy()
    for col in ['CAPEX (Rp)', 'OPEX (Rp)', 'Pendapatan (Rp)', 'Cash Flow (Rp)', 'Cumulative Profit (Rp)']:
        df_display[col] = df_display[col].apply(lambda x: format_currency(x))
    df_display['Produksi (Ton)'] = df_display['Produksi (Ton)'].apply(lambda x: f"{x:.2f}")
    
    st.dataframe(df_display, use_container_width=True, height=400)
    
    # ==================== EXPORT FEATURE ====================
    st.markdown("<div class='section-header'>💾 Export Data</div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Export CAPEX
        buffer_capex = BytesIO()
        with pd.ExcelWriter(buffer_capex, engine='openpyxl') as writer:
            st.session_state.df_capex.to_excel(writer, index=False, sheet_name='CAPEX')
        
        st.download_button(
            label="📥 Download CAPEX (Excel)",
            data=buffer_capex.getvalue(),
            file_name=f"RAB_CAPEX_{luas_lahan}Ha.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    with col2:
        # Export OPEX
        buffer_opex = BytesIO()
        with pd.ExcelWriter(buffer_opex, engine='openpyxl') as writer:
            st.session_state.df_opex_tbm.to_excel(writer, index=False, sheet_name='OPEX TBM')
            st.session_state.df_opex_tm.to_excel(writer, index=False, sheet_name='OPEX TM')
        
        st.download_button(
            label="📥 Download OPEX (Excel)",
            data=buffer_opex.getvalue(),
            file_name=f"RAB_OPEX_{luas_lahan}Ha.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    with col3:
        # Export Proyeksi
        buffer_proyeksi = BytesIO()
        with pd.ExcelWriter(buffer_proyeksi, engine='openpyxl') as writer:
            df_proyeksi.to_excel(writer, index=False, sheet_name='Proyeksi 25 Tahun')
        
        st.download_button(
            label="📥 Download Proyeksi (Excel)",
            data=buffer_proyeksi.getvalue(),
            file_name=f"Proyeksi_Profitabilitas_{luas_lahan}Ha.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ==================== FOOTER ====================
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p>🌴 <strong>Sistem RAB Dinamis Kelapa Sawit</strong> | Developed by Senior Full-stack Developer & Agribusiness Consultant</p>
    <p>📊 Data Pasar: <strong>April 2026</strong> | Urea: Rp 11.000/kg | NPK: Rp 14.500/kg | Upah Panen: Rp 300/kg</p>
    <p style='font-size: 12px; margin-top: 10px;'>⚠️ Disclaimer: Proyeksi ini bersifat estimasi berdasarkan data pasar terkini dan kurva produksi standar industri. Hasil aktual dapat bervariasi tergantung kondisi lapangan.</p>
</div>
""", unsafe_allow_html=True)
