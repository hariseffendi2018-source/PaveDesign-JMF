"""
=====================================================================
PaveDesign & JMF
Aplikasi Desain Perkerasan Lentur & Analisis Job Mix Formula Agregat
=====================================================================
Framework : Streamlit
Library   : Pandas, Numpy, Plotly, Matplotlib
Referensi : Manual Desain Perkerasan Jalan – Bina Marga (Pd T-01-2002-B)
            Spesifikasi Umum Bina Marga 2018 Rev.2

Dibuat untuk keperluan akademik mata kuliah Aplikasi Komputer / Perkerasan Jalan.
"""

import plotly.graph_objects as go
import matplotlib.pyplot as plt
import streamlit as st
import pandas as pd
import numpy as np

# ──────────────────────────────────────────────────────────────────────
# KONFIGURASI HALAMAN
# ──────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PaveDesign & JMF",
    page_icon="🛣️",
    layout="wide",
)

# ──────────────────────────────────────────────────────────────────────
# CUSTOM CSS – tampilan profesional & bersih
# ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Header utama */
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        color: white;
        text-align: center;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.15);
    }
    .main-header h1 { margin: 0; font-size: 2rem; }
    .main-header p  { margin: 0.3rem 0 0 0; font-size: 0.95rem; opacity: 0.85; }

    /* Card sederhana */
    .result-card {
        background: #f8fafc;
        border-left: 4px solid #2d6a9f;
        padding: 1rem 1.2rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
    }

    /* Tabel styling */
    .stDataFrame { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────
# HEADER APLIKASI
# ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>🛣️ PaveDesign & JMF</h1>
    <p>Aplikasi Desain Tebal Perkerasan Lentur & Analisis Job Mix Formula Agregat</p>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# DUA TAB UTAMA
# ══════════════════════════════════════════════════════════════════════
tab1, tab2 = st.tabs([
    "📐 Desain Tebal Perkerasan Lentur",
    "🧪 Analisis Job Mix Formula (JMF)",
])


# ######################################################################
#                          TAB 1 – PERKERASAN LENTUR
# ######################################################################
with tab1:
    st.subheader("Desain Tebal Perkerasan Lentur (Flexible Pavement)")
    st.caption("Metode analisis mengacu pada Manual Desain Perkerasan Jalan – Bina Marga.")

    # ── Panel Input ──────────────────────────────────────────────────
    col_in1, col_in2 = st.columns(2)

    with col_in1:
        umur_rencana = st.number_input(
            "Umur Rencana (tahun)",
            min_value=1, max_value=40, value=20, step=1,
            help="Umur rencana perkerasan, umumnya 20 tahun.",
        )
        laju_pertumbuhan = st.number_input(
            "Laju Pertumbuhan Lalu Lintas (%)",
            min_value=0.0, max_value=15.0, value=5.0, step=0.5,
            help="Laju pertumbuhan lalu lintas rata-rata per tahun.",
        )

    with col_in2:
        lhr = st.number_input(
            "LHR Kendaraan Berat – Sumbu Standar (ESA/hari)",
            min_value=1, max_value=100000, value=500, step=50,
            help="Lintas Harian Rata-rata kendaraan berat dalam ekivalen sumbu standar.",
        )
        cbr = st.number_input(
            "Nilai CBR Tanah Dasar (%)",
            min_value=1.0, max_value=30.0, value=6.0, step=0.5,
            help="Nilai CBR (California Bearing Ratio) tanah dasar.",
        )

    st.divider()

    # ── PERHITUNGAN ──────────────────────────────────────────────────

    # 1) Faktor pertumbuhan majemuk (compound growth factor)
    # -------------------------------------------------------
    # Rumus:  R = [(1 + i)^n - 1] / i
    # Keterangan:
    #   i = laju pertumbuhan (desimal)
    #   n = umur rencana (tahun)
    #   R = faktor pertumbuhan kumulatif
    i = laju_pertumbuhan / 100.0                    # konversi persen → desimal
    if i > 0:
        R = ((1 + i) ** umur_rencana - 1) / i      # rumus deret geometri
    else:
        R = float(umur_rencana)                     # jika pertumbuhan 0 → linear

    # 2) Kumulatif Beban Lalu Lintas (CESAL)
    # -------------------------------------------------------
    # Rumus:  CESAL = LHR × 365 × R
    # Satuan awal: ESA (Equivalent Standard Axle)
    # Konversi ke Juta ESA: CESAL / 1.000.000
    cesal_total = lhr * 365 * R                     # total ESA selama umur rencana
    cesal_juta  = cesal_total / 1_000_000           # konversi ke Juta ESA (MESA)

    # 3) Daya Dukung Tanah (DDT)
    # -------------------------------------------------------
    # Rumus empiris (Bina Marga Pd T-01-2002-B):
    #   DDT = 4.3 × log10(CBR) + 1.7
    ddt = 4.3 * np.log10(cbr) + 1.7                # daya dukung tanah

    # ── Tampilkan Metrik Hasil ───────────────────────────────────────
    st.markdown("### 📊 Hasil Perhitungan")

    m1, m2, m3 = st.columns(3)
    m1.metric("Faktor Pertumbuhan (R)", f"{R:,.2f}")
    m2.metric("CESAL (Juta ESA)", f"{cesal_juta:,.3f}")
    m3.metric("Daya Dukung Tanah (DDT)", f"{ddt:,.2f}")

    st.divider()

    # ── TABEL REKOMENDASI TEBAL LAPISAN ──────────────────────────────
    # Klasifikasi berdasarkan rentang CESAL (Juta ESA) dan CBR.
    # Nilai tebal dalam satuan cm – acuan umum desain Bina Marga.
    # ─────────────────────────────────────────────────────────────────

    def rekomendasi_tebal(cesal_juta: float, cbr: float) -> dict:
        """
        Mengembalikan dict rekomendasi tebal lapisan perkerasan
        berdasarkan klasifikasi CESAL dan CBR.
        Satuan tebal: cm.
        """
        # -----------------------------------------------------------
        # Klasifikasi CESAL (Juta ESA)
        # -----------------------------------------------------------
        if cesal_juta < 0.5:
            kelas_cesal = "Ringan"
        elif cesal_juta < 4.0:
            kelas_cesal = "Sedang"
        elif cesal_juta < 10.0:
            kelas_cesal = "Berat"
        else:
            kelas_cesal = "Sangat Berat"

        # -----------------------------------------------------------
        # Klasifikasi CBR Tanah Dasar
        # -----------------------------------------------------------
        if cbr < 3:
            kelas_cbr = "Sangat Lunak"
        elif cbr < 6:
            kelas_cbr = "Lunak"
        elif cbr < 10:
            kelas_cbr = "Sedang"
        else:
            kelas_cbr = "Baik"

        # -----------------------------------------------------------
        # Tabel rekomendasi tebal lapisan (cm)
        # Lapis Permukaan (AC/HRS), Lapis Pondasi Atas (Base),
        # Lapis Pondasi Bawah (Sub-Base)
        #
        # Logika: CESAL tinggi → lapis permukaan lebih tebal.
        #         CBR rendah  → lapis pondasi bawah lebih tebal.
        # -----------------------------------------------------------
        tabel = {
            # (kelas_cesal, kelas_cbr): (permukaan, base, sub-base)
            ("Ringan",       "Sangat Lunak"): (5,  15, 35),
            ("Ringan",       "Lunak"):        (5,  15, 30),
            ("Ringan",       "Sedang"):       (5,  15, 25),
            ("Ringan",       "Baik"):         (5,  15, 20),

            ("Sedang",       "Sangat Lunak"): (7,  20, 35),
            ("Sedang",       "Lunak"):        (7,  20, 30),
            ("Sedang",       "Sedang"):       (7,  20, 25),
            ("Sedang",       "Baik"):         (7,  20, 20),

            ("Berat",        "Sangat Lunak"): (10, 25, 40),
            ("Berat",        "Lunak"):        (10, 25, 35),
            ("Berat",        "Sedang"):       (10, 25, 30),
            ("Berat",        "Baik"):         (10, 20, 25),

            ("Sangat Berat", "Sangat Lunak"): (15, 30, 45),
            ("Sangat Berat", "Lunak"):        (15, 30, 40),
            ("Sangat Berat", "Sedang"):       (12, 25, 35),
            ("Sangat Berat", "Baik"):         (12, 25, 30),
        }

        permukaan, base, subbase = tabel[(kelas_cesal, kelas_cbr)]

        return {
            "Kelas Lalu Lintas": kelas_cesal,
            "Kelas Tanah Dasar": kelas_cbr,
            "Lapis Permukaan (AC) [cm]": permukaan,
            "Lapis Pondasi Atas (Base) [cm]": base,
            "Lapis Pondasi Bawah (Sub-Base) [cm]": subbase,
            "Total Tebal Perkerasan [cm]": permukaan + base + subbase,
        }

    rekom = rekomendasi_tebal(cesal_juta, cbr)

    st.markdown("### 🧱 Rekomendasi Tebal Lapisan Perkerasan")

    k1, k2 = st.columns(2)
    k1.info(f"**Kelas Lalu Lintas:** {rekom['Kelas Lalu Lintas']}  \n"
            f"**CESAL:** {cesal_juta:,.3f} Juta ESA")
    k2.info(f"**Kelas Tanah Dasar:** {rekom['Kelas Tanah Dasar']}  \n"
            f"**CBR:** {cbr:.1f}%  |  **DDT:** {ddt:.2f}")

    df_rekom = pd.DataFrame([
        {"Lapisan": "Lapis Permukaan (AC / HRS)",
         "Tebal (cm)": rekom["Lapis Permukaan (AC) [cm]"]},
        {"Lapisan": "Lapis Pondasi Atas (Aggregat Kelas A / CTB)",
         "Tebal (cm)": rekom["Lapis Pondasi Atas (Base) [cm]"]},
        {"Lapisan": "Lapis Pondasi Bawah (Aggregat Kelas B / Sirtu)",
         "Tebal (cm)": rekom["Lapis Pondasi Bawah (Sub-Base) [cm]"]},
        {"Lapisan": "TOTAL TEBAL PERKERASAN",
         "Tebal (cm)": rekom["Total Tebal Perkerasan [cm]"]},
    ])

    st.dataframe(df_rekom, use_container_width=True, hide_index=True)

    # ── Visualisasi Penampang Vertikal Perkerasan (Plotly) ──────────
    # Menggunakan stacked bar chart vertikal untuk menggambarkan
    # susunan lapisan perkerasan secara proporsional (vertikal).
    # Urutan penumpukan (bawah → atas):
    #   1. Lapis Pondasi Bawah (Sub-Base) – warna cokelat muda
    #   2. Lapis Pondasi Atas (Base)       – warna abu-abu muda
    #   3. Lapis Permukaan (AC)            – warna hitam/abu-abu gelap
    # ─────────────────────────────────────────────────────────────────

    st.markdown("### 📐 Penampang Vertikal Perkerasan")

    t_permukaan = rekom["Lapis Permukaan (AC) [cm]"]
    t_base      = rekom["Lapis Pondasi Atas (Base) [cm]"]
    t_subbase   = rekom["Lapis Pondasi Bawah (Sub-Base) [cm]"]

    fig_section = go.Figure()

    # Lapisan ditambahkan dari bawah ke atas (stack order)
    fig_section.add_trace(go.Bar(
        x=["Perkerasan"], y=[t_subbase],
        name=f"Pondasi Bawah ({t_subbase} cm)",
        marker_color="#c9a96e",                      # cokelat muda
        text=[f"{t_subbase} cm"], textposition="inside",
        textfont=dict(size=13, color="white"),
    ))
    fig_section.add_trace(go.Bar(
        x=["Perkerasan"], y=[t_base],
        name=f"Pondasi Atas ({t_base} cm)",
        marker_color="#b0b0b0",                      # abu-abu muda
        text=[f"{t_base} cm"], textposition="inside",
        textfont=dict(size=13, color="white"),
    ))
    fig_section.add_trace(go.Bar(
        x=["Perkerasan"], y=[t_permukaan],
        name=f"Lapis Permukaan ({t_permukaan} cm)",
        marker_color="#2d2d2d",                      # hitam/abu-abu gelap
        text=[f"{t_permukaan} cm"], textposition="inside",
        textfont=dict(size=13, color="white"),
    ))

    fig_section.update_layout(
        barmode="stack",
        title=dict(text="Susunan Lapisan Perkerasan (cm)", font=dict(size=16)),
        yaxis_title="Tebal (cm)",
        xaxis=dict(showticklabels=False),
        height=250,
        margin=dict(l=20, r=20, t=50, b=40),
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.45,
            xanchor="center", x=0.5,
        ),
    )

    st.plotly_chart(fig_section, use_container_width=True)

    # ── Ilustrasi ringkas parameter input ────────────────────────────
    with st.expander("📋 Ringkasan Parameter & Rumus Perhitungan"):
        st.markdown(f"""
| Parameter | Nilai |
|---|---|
| Umur Rencana (n) | **{umur_rencana}** tahun |
| Laju Pertumbuhan (i) | **{laju_pertumbuhan}%** |
| LHR Kendaraan Berat | **{lhr:,}** ESA/hari |
| CBR Tanah Dasar | **{cbr:.1f}%** |

**Rumus yang digunakan:**
1. **Faktor Pertumbuhan Majemuk (R):**
   `R = [(1 + i)^n − 1] / i = [(1 + {i})^{umur_rencana} − 1] / {i} = {R:,.2f}`

2. **CESAL (Cumulative Equivalent Standard Axle Load):**
   `CESAL = LHR × 365 × R = {lhr:,} × 365 × {R:,.2f} = {cesal_total:,.0f} ESA = {cesal_juta:,.3f} Juta ESA`

3. **DDT (Daya Dukung Tanah):**
   `DDT = 4.3 × log₁₀(CBR) + 1.7 = 4.3 × log₁₀({cbr}) + 1.7 = {ddt:.2f}`
        """)


# ######################################################################
#                     TAB 2 – JOB MIX FORMULA (JMF)
# ######################################################################
with tab2:
    st.subheader("Analisis Job Mix Formula (JMF) Agregat")
    st.caption("Blending agregat kasar, halus, dan filler berdasarkan Spesifikasi Umum Bina Marga 2018.")

    # ── 1) Dropdown Tipe Campuran Aspal ──────────────────────────────
    tipe_campuran = st.selectbox(
        "Pilih Tipe Campuran Aspal",
        options=["AC-WC", "AC-BC", "AC-Base"],
        index=0,
        help="AC-WC = Wearing Course, AC-BC = Binder Course, AC-Base = Base Course.",
    )

    # ── Input Proporsi ───────────────────────────────────────────────
    st.markdown("#### ⚖️ Proporsi Campuran Agregat")
    p1, p2, p3 = st.columns(3)

    with p1:
        prop_kasar = st.number_input(
            "Agregat Kasar (%)", min_value=0.0, max_value=100.0,
            value=40.0, step=1.0, key="pk",
        )
    with p2:
        prop_halus = st.number_input(
            "Agregat Halus (%)", min_value=0.0, max_value=100.0,
            value=55.0, step=1.0, key="ph",
        )
    with p3:
        prop_filler = st.number_input(
            "Filler (%)", min_value=0.0, max_value=100.0,
            value=5.0, step=1.0, key="pf",
        )

    total_prop = prop_kasar + prop_halus + prop_filler

    # ── Validasi total proporsi = 100% ───────────────────────────────
    if not np.isclose(total_prop, 100.0):
        st.error(
            f"⚠️ **Total proporsi = {total_prop:.1f}%** — "
            f"harus tepat **100%**!  \n"
            f"Silakan koreksi proporsi Agregat Kasar, Halus, dan Filler."
        )
        st.stop()  # hentikan kalkulasi

    st.success(f"✅ Total proporsi: **{total_prop:.1f}%** — Valid!")

    st.divider()

    # ── 2) Database Spesifikasi Dinamis – Bina Marga 2018 ───────────
    # Dictionary berisi Batas Bawah & Batas Atas untuk setiap tipe
    # campuran aspal. Ukuran saringan diperluas dengan 37.5 mm dan
    # 25.4 mm agar kompatibel dengan AC-Base.
    #
    # Referensi: Spesifikasi Umum Bina Marga 2018 Rev.2
    #            Tabel Gradasi AC-WC, AC-BC, AC-Base
    #
    # Catatan: Saringan yang TIDAK digunakan pada tipe tertentu
    #          diberi batas 0–100 (selalu lolos) agar tidak
    #          mengganggu evaluasi status.
    # ─────────────────────────────────────────────────────────────────

    # Daftar lengkap ukuran saringan (mm) – dari terbesar ke terkecil
    saringan_list = [37.5, 25.4, 19.0, 12.5, 9.5, 4.75, 2.36,
                     1.18, 0.600, 0.300, 0.150, 0.075]

    spesifikasi_bm = {
        # ── AC-WC (Wearing Course) ──────────────────────────────────
        # Saringan 37.5 & 25.4 mm tidak digunakan → batas 0–100
        "AC-WC": {
            "Batas Bawah": [100, 100, 100,  90,  72,  43,  28,
                            19,   13,    9,    6,   4.0],
            "Batas Atas":  [100, 100, 100, 100, 100,  69,  58,
                            44,   33,   23,   15,   9.0],
        },
        # ── AC-BC (Binder Course) ───────────────────────────────────
        # Saringan 37.5 mm tidak digunakan → batas 0–100
        "AC-BC": {
            "Batas Bawah": [100, 100, 90,  75,  66,  46,  30,
                            18,   12,    7,    5,   4.0],
            "Batas Atas":  [100, 100, 100, 100, 100,  80,  58,
                            44,   33,   23,   15,   9.0],
        },
        # ── AC-Base (Base Course) ───────────────────────────────────
        "AC-Base": {
            "Batas Bawah": [100,  90,  76,  60,  52,  35,  23,
                             13,    9,    6,    4,   3.0],
            "Batas Atas":  [100, 100, 100, 100, 100,  71,  49,
                             36,   26,   18,   12,   8.0],
        },
    }

    # Ambil batas sesuai tipe campuran terpilih
    spec = spesifikasi_bm[tipe_campuran]

    # ── Data bawaan persen lolos agregat per saringan ────────────────
    # Nilai default realistis untuk agregat kasar, halus, dan filler.
    # Pengguna dapat mengedit langsung di st.data_editor.
    # ─────────────────────────────────────────────────────────────────
    default_kasar  = [100, 100, 100,  95,  80,  10,   5,
                        3,    2,    2,    1,   0.8]
    default_halus  = [100, 100, 100, 100, 100,  95,  85,
                       70,   48,   30,   18,  10.0]
    default_filler = [100, 100, 100, 100, 100, 100, 100,
                      100,  100,  100,   98,  90.0]

    df_input = pd.DataFrame({
        "Saringan (mm)":  saringan_list,
        "Agregat Kasar":  default_kasar,
        "Agregat Halus":  default_halus,
        "Filler":         default_filler,
        "Batas Bawah":    spec["Batas Bawah"],
        "Batas Atas":     spec["Batas Atas"],
        "Batas Tengah":   np.round((np.array(spec["Batas Bawah"]) + np.array(spec["Batas Atas"])) / 2, 1),
    })

    # ── 3) Tabel Input Interaktif (st.data_editor) ───────────────────
    # Kolom Saringan, Batas Bawah, Batas Atas → dikunci (disabled).
    # Kolom Agregat Kasar, Agregat Halus, Filler → dapat diedit user.
    # ─────────────────────────────────────────────────────────────────
    st.markdown(f"#### 📋 Data Gradasi Agregat — **{tipe_campuran}**")
    st.caption("✏️ Klik sel pada kolom **Agregat Kasar**, **Agregat Halus**, atau "
               "**Filler** untuk mengedit nilai persen lolos secara langsung.")

    edited_df = st.data_editor(
        df_input,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=["Saringan (mm)", "Batas Bawah", "Batas Atas"],
        column_config={
            "Saringan (mm)":  st.column_config.NumberColumn(format="%.3g"),
            "Agregat Kasar":  st.column_config.NumberColumn(
                "Agregat Kasar (%)", min_value=0.0, max_value=100.0, format="%.1f"),
            "Agregat Halus":  st.column_config.NumberColumn(
                "Agregat Halus (%)", min_value=0.0, max_value=100.0, format="%.1f"),
            "Filler":         st.column_config.NumberColumn(
                "Filler (%)", min_value=0.0, max_value=100.0, format="%.1f"),
            "Batas Bawah":    st.column_config.NumberColumn(format="%.1f"),
            "Batas Atas":     st.column_config.NumberColumn(format="%.1f"),
        },
        key="gradasi_editor",
    )

    st.divider()

    # ── 4) Kalkulasi Blending dari data yang sudah diedit ────────────
    # Rumus Blending:
    #   Blend_i = (Kasar_i × P_kasar + Halus_i × P_halus + Filler_i × P_filler) / 100
    #
    # Keterangan:
    #   Blend_i   = persen lolos gabungan pada saringan ke-i
    #   Kasar_i   = persen lolos agregat kasar pada saringan ke-i (dari editor)
    #   Halus_i   = persen lolos agregat halus pada saringan ke-i (dari editor)
    #   Filler_i  = persen lolos filler pada saringan ke-i (dari editor)
    #   P_kasar   = proporsi agregat kasar (%)
    #   P_halus   = proporsi agregat halus (%)
    #   P_filler  = proporsi filler (%)
    # ─────────────────────────────────────────────────────────────────

    hasil = edited_df.copy()

    hasil["Blending (%)"] = np.round(
        (hasil["Agregat Kasar"]  * prop_kasar
       + hasil["Agregat Halus"]  * prop_halus
       + hasil["Filler"]         * prop_filler) / 100.0,
        2
    )

    # ── Kolom Status: cek apakah blending dalam rentang spesifikasi ──
    # Jika Batas Bawah ≤ Blending ≤ Batas Atas → "✅ OK"
    # Jika di luar rentang → "❌ OUT"
    hasil["Status"] = np.where(
        (hasil["Blending (%)"] >= hasil["Batas Bawah"])
        & (hasil["Blending (%)"] <= hasil["Batas Atas"]),
        "✅ OK",
        "❌ OUT",
    )

    # ── Tabel Hasil Blending ─────────────────────────────────────────
    st.markdown(f"#### 🧮 Hasil Blending — **{tipe_campuran}**")

    df_result_display = hasil[["Saringan (mm)", "Blending (%)",
                               "Batas Bawah", "Batas Atas", "Batas Tengah", "Status"]].copy()
    df_result_display["Saringan (mm)"] = df_result_display["Saringan (mm)"].apply(
        lambda x: f"{x:g}"
    )

    st.dataframe(df_result_display, use_container_width=True, hide_index=True)

    # Hitung ringkasan status
    total_ok  = (hasil["Status"] == "✅ OK").sum()
    total_out = (hasil["Status"] == "❌ OUT").sum()

    if total_out == 0:
        st.success(f"🎉 Semua {total_ok} saringan memenuhi spesifikasi Bina Marga ({tipe_campuran})!")
    else:
        st.warning(
            f"⚠️ **{total_out}** dari {total_ok + total_out} saringan "
            f"**di luar** rentang spesifikasi {tipe_campuran}. Koreksi proporsi/gradasi."
        )

    st.divider()

    # ── Grafik Semilog: Blending vs Batas Spesifikasi (Matplotlib) ──
    # Sumbu X = ukuran saringan (mm) dalam skala logaritmik, arah
    # dibalik (besar → kecil) sesuai konvensi kurva gradasi agregat.
    # Data langsung dari hasil editor → grafik update otomatis.
    # ─────────────────────────────────────────────────────────────────
    st.markdown(f"#### 📈 Kurva Gradasi – Blending vs Spesifikasi (Skala Semilog) — {tipe_campuran}")

    saringan_mm = hasil["Saringan (mm)"].values

    fig, ax = plt.subplots(figsize=(10, 5))

    # Plot garis Hasil Blending
    ax.plot(saringan_mm, hasil["Blending (%)"].values,
            marker="o", linewidth=2, color="#1f77b4", label="Hasil Blending")

    # Plot garis Batas Atas spesifikasi
    ax.plot(saringan_mm, hasil["Batas Atas"].values,
            marker="s", linewidth=1.5, linestyle="--", color="#2ca02c", label="Batas Atas")

    # Plot garis Batas Bawah spesifikasi
    ax.plot(saringan_mm, hasil["Batas Bawah"].values,
            marker="s", linewidth=1.5, linestyle="--", color="#d62728", label="Batas Bawah")

    # Isi area antara batas atas dan bawah (envelope spesifikasi)
    ax.fill_between(saringan_mm,
                    hasil["Batas Bawah"].values,
                    hasil["Batas Atas"].values,
                    alpha=0.12, color="green", label="Zona Spesifikasi")

    # Sumbu X: skala logaritmik, arah dibalik (besar → kecil)
    ax.set_xscale("log")           # skala logaritmik
    ax.invert_xaxis()              # balik arah: besar di kiri, kecil di kanan

    # Label & grid
    ax.set_xlabel("Ukuran Saringan (mm)", fontsize=11)
    ax.set_ylabel("Persen Lolos (%)", fontsize=11)
    ax.set_title(f"Kurva Gradasi Agregat Gabungan — {tipe_campuran}",
                 fontsize=13, fontweight="bold")
    ax.set_ylim(0, 105)
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(True, which="both", linestyle=":", alpha=0.5)

    # Tick label untuk setiap ukuran saringan
    ax.set_xticks(saringan_mm)
    ax.set_xticklabels([f"{x:g}" for x in saringan_mm], fontsize=9, rotation=45)

    plt.tight_layout()
    st.pyplot(fig)

    st.caption(
        f"Grafik menunjukkan kurva **Blending** (hasil gabungan agregat) "
        f"dibandingkan dengan **Batas Atas** dan **Batas Bawah** "
        f"spesifikasi Bina Marga **{tipe_campuran}**. Idealnya kurva blending "
        f"berada di antara kedua batas tersebut."
    )

    # ── Expander rumus blending ──────────────────────────────────────
    with st.expander("📋 Rumus & Keterangan Blending"):
        st.markdown(f"""
**Tipe Campuran:** `{tipe_campuran}`

**Proporsi yang digunakan:**
| Komponen | Proporsi |
|---|---|
| Agregat Kasar | **{prop_kasar:.1f}%** |
| Agregat Halus | **{prop_halus:.1f}%** |
| Filler | **{prop_filler:.1f}%** |
| **Total** | **{total_prop:.1f}%** |

**Rumus Blending per saringan:**

```
Blend_i = (Kasar_i × P_kasar + Halus_i × P_halus + Filler_i × P_filler) / 100
```

**Keterangan:**
- `Blend_i` = persen lolos gabungan pada saringan ke-i
- `Kasar_i` = persen lolos agregat kasar pada saringan ke-i
- `Halus_i` = persen lolos agregat halus pada saringan ke-i
- `Filler_i` = persen lolos filler pada saringan ke-i
- `P_kasar`, `P_halus`, `P_filler` = proporsi masing-masing agregat (%)
        """)


# ──────────────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<div style='text-align:center; color:gray; font-size:0.85rem;'>"
    "🛣️ <b>PaveDesign & JMF</b> — Dibuat untuk keperluan akademik "
    "| Referensi: Manual Desain Perkerasan Bina Marga & Spesifikasi Umum 2018"
    "</div>",
    unsafe_allow_html=True,
)
