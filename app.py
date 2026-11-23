"""
=====================================================================
PaveDesign & JMF — Professional Civil Engineering Suite v5.5
Aplikasi Desain Tebal Perkerasan Lentur, Analisis JMF, Marshall & RAB
=====================================================================
Framework : Streamlit
Library   : Pandas, Numpy, Plotly, Matplotlib, Openpyxl
Referensi : Manual Desain Perkerasan Jalan (Pd T-01-2002-B)
            Spesifikasi Umum Bina Marga 2018 Rev.2 (Divisi 6)
            Panduan Analisis Harga Satuan Pekerjaan (AHSP) Bina Marga
"""

import io
import textwrap
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# =====================================================================
# 1. KONFIGURASI HALAMAN
# =====================================================================
st.set_page_config(
    page_title="PaveDesign & JMF",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =====================================================================
# 2. BACKEND / FUNGSI LOGIKA TEKNIK SIPIL (ISOLASI BERSIH DARI UI)
# =====================================================================

def calc_le_harian(lhr_bus: int, lhr_truk2: int, lhr_truk3: int) -> float:
    """
    Hitung Lintas Ekivalen (LE) Harian berdasarkan Volume Kendaraan Berat
    dan Vehicle Damage Factor (VDF) standar Bina Marga:
    - Bus: VDF = 1.2
    - Truk 2 Sumbu (Engkel): VDF = 9.2
    - Truk 3 Sumbu (Tronton): VDF = 20.0
    """
    return (lhr_bus * 1.2) + (lhr_truk2 * 9.2) + (lhr_truk3 * 20.0)


def calc_r_factor(laju_pertumbuhan_pct: float, umur_rencana_th: int) -> float:
    """
    Hitung Faktor Pertumbuhan Kumulatif Lalu Lintas (R):
    Rumus deret ukur: R = [(1 + i)^n - 1] / i
    """
    i = laju_pertumbuhan_pct / 100.0
    if i > 0:
        return ((1.0 + i) ** umur_rencana_th - 1.0) / i
    return float(umur_rencana_th)


def calc_cesal(le_harian: float, r_factor: float, dl: float) -> tuple[float, float]:
    """
    Hitung Kumulatif Beban Sumbu Standar Kumulatif (CESAL):
    CESAL = LE * 365 * R * DL
    Return: (cesal_total_esa, cesal_juta_mesa)
    """
    cesal_total = le_harian * 365.0 * r_factor * dl
    cesal_juta = cesal_total / 1_000_000.0
    return cesal_total, cesal_juta


def calc_ddt(cbr_pct: float) -> float:
    """
    Hitung Daya Dukung Tanah Dasar (DDT) empiris Bina Marga:
    DDT = 4.3 * log10(CBR) + 1.7
    """
    safe_cbr = max(cbr_pct, 0.01)
    return float(4.3 * np.log10(safe_cbr) + 1.7)


def get_rekomendasi_tebal(cesal_juta: float, cbr_pct: float) -> dict:
    """
    Klasifikasi beban lalu lintas dan CBR tanah dasar,
    lalu tentukan tebal lapisan perkerasan (cm) mengacu Pd T-01-2002-B.
    """
    if cesal_juta < 0.5:
        kelas_cesal = "Ringan"
    elif cesal_juta < 4.0:
        kelas_cesal = "Sedang"
    elif cesal_juta < 10.0:
        kelas_cesal = "Berat"
    else:
        kelas_cesal = "Sangat Berat"

    if cbr_pct < 3.0:
        kelas_cbr = "Sangat Lunak"
    elif cbr_pct < 6.0:
        kelas_cbr = "Lunak"
    elif cbr_pct < 10.0:
        kelas_cbr = "Sedang"
    else:
        kelas_cbr = "Baik"

    tabel_tebal = {
        ("Ringan",       "Sangat Lunak"): (5,  15, 35),
        ("Ringan",       "Lunak"):        (5,  15, 30),
        ("Ringan",       "Sedang"):       (5,  15, 20),
        ("Ringan",       "Baik"):         (5,  15, 15),

        ("Sedang",       "Sangat Lunak"): (7.5, 20, 35),
        ("Sedang",       "Lunak"):        (7.5, 20, 30),
        ("Sedang",       "Sedang"):       (7.5, 20, 20),
        ("Sedang",       "Baik"):         (7.5, 15, 15),

        ("Berat",        "Sangat Lunak"): (10, 20, 35),
        ("Berat",        "Lunak"):        (10, 20, 30),
        ("Berat",        "Sedang"):       (10, 20, 20),
        ("Berat",        "Baik"):         (10, 15, 15),

        ("Sangat Berat", "Sangat Lunak"): (15, 25, 35),
        ("Sangat Berat", "Lunak"):        (15, 25, 30),
        ("Sangat Berat", "Sedang"):       (15, 25, 20),
        ("Sangat Berat", "Baik"):         (15, 20, 15),
    }

    t_ac, t_base, t_subbase = tabel_tebal.get((kelas_cesal, kelas_cbr), (10, 20, 20))
    t_total = t_ac + t_base + t_subbase

    return {
        "Kelas Lalu Lintas": kelas_cesal,
        "Kelas Tanah Dasar": kelas_cbr,
        "Lapis Permukaan (AC) [cm]": t_ac,
        "Lapis Pondasi Atas (Base) [cm]": t_base,
        "Lapis Pondasi Bawah (Sub-Base) [cm]": t_subbase,
        "Total Tebal Perkerasan [cm]": t_total,
    }


def calc_blending_jmf(
    df_saringan: pd.DataFrame, prop_kasar: float, prop_halus: float, prop_filler: float
) -> pd.DataFrame:
    """
    Hitung Blending Agregat Gabungan:
    Blend = (P_K * Kasar + P_H * Halus + P_F * Filler) / 100
    dan evaluasi terhadap amplop spesifikasi Bina Marga 2018 Divisi 6.
    """
    hasil = df_saringan.copy()
    hasil["Blending (%)"] = (
        (prop_kasar * hasil["Agregat Kasar"])
        + (prop_halus * hasil["Agregat Halus"])
        + (prop_filler * hasil["Filler"])
    ) / 100.0

    hasil["Status"] = np.where(
        (hasil["Blending (%)"] >= hasil["Batas Bawah"])
        & (hasil["Blending (%)"] <= hasil["Batas Atas"]),
        "✅ OK",
        "❌ OUT",
    )
    return hasil


def get_default_aggregate_fractions(tipe_campuran: str) -> tuple[list, list, list]:
    """
    Kembalikan nilai lolos saringan default untuk Kasar, Halus, dan Filler
    berdasarkan tipe campuran (Gradasi Menerus AC vs Gradasi Senjang Lataston HRS).
    Referensi: Spesifikasi Umum Bina Marga 2018 Rev.2 Divisi 6.
    """
    if tipe_campuran in ["HRS-WC", "HRS-Base"]:
        # Gradasi Senjang / Gap-Graded (Lataston HRS)
        kasar = [100, 100, 100, 96, 82, 12, 4, 2, 1.5, 1, 0.5, 0.5]
        halus = [100, 100, 100, 100, 100, 96, 92, 72, 55, 32, 14, 7.0]
        filler = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 98, 92.0]
    else:
        # Gradasi Menerus / Continuous (Laston AC)
        kasar = [100, 100, 100, 95, 80, 10, 5, 3, 2, 2, 1, 0.8]
        halus = [100, 100, 100, 100, 100, 95, 85, 70, 48, 30, 18, 10.0]
        filler = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 98, 90.0]
    return kasar, halus, filler


def optimize_jmf_proportions(df_saringan: pd.DataFrame, spec: dict) -> tuple[int, int, int, int, float]:
    """
    Grid search proporsi Kasar, Halus, Filler (jumlah 100%)
    untuk meminimalkan penyimpangan terhadap Batas Tengah amplop spesifikasi.
    Prioritas:
    1. Jumlah saringan yang keluar dari amplop (minimalkan OUT)
    2. Rata-rata deviasi kuadrat (MSE) terhadap Batas Tengah
    Rentang pencarian diperluas: pk in 15..79, pf in 1..14 (ph >= 15)
    Return: (best_kasar, best_halus, best_filler, out_count, best_mse)
    """
    kasar_arr = df_saringan["Agregat Kasar"].values
    halus_arr = df_saringan["Agregat Halus"].values
    filler_arr = df_saringan["Filler"].values
    low_arr = np.array(spec["Batas Bawah"])
    high_arr = np.array(spec["Batas Atas"])
    mid_arr = (low_arr + high_arr) / 2.0

    best_combo = (40, 55, 5, 0, 999.0)
    best_penalty = float("inf")

    # Grid search diperluas dengan resolusi 1%
    for pk in range(15, 80):
        for pf in range(1, 15):
            ph = 100 - pk - pf
            if ph < 15:
                continue
            blend = (pk * kasar_arr + ph * halus_arr + pf * filler_arr) / 100.0
            out_count = int(np.sum((blend < low_arr) | (blend > high_arr)))
            mse = float(np.mean((blend - mid_arr) ** 2))
            penalty = out_count * 1000.0 + mse

            if penalty < best_penalty:
                best_penalty = penalty
                best_combo = (pk, ph, pf, out_count, round(mse, 2))

    return best_combo


def calc_kao_hudson(hasil_df: pd.DataFrame) -> tuple[float, float, float, float]:
    """
    Estimasi KAO (Kadar Aspal Optimum) prediktif empiris Bina Marga/Hudson:
    KAO_pred = 0.035 * A + 0.045 * B + 0.18 * C + Konstanta (2.0)
    A = % agregat tertahan saringan No.8 (2.36 mm)
    C = % agregat lolos saringan No.200 (0.075 mm)
    B = % agregat lolos No.8 tertahan No.200 = 100 - A - C
    Return: (a_coarse, b_fine, c_filler, kao_prediktif)
    """
    row_236 = hasil_df[hasil_df["Saringan (mm)"].astype(float) == 2.36]
    row_0075 = hasil_df[hasil_df["Saringan (mm)"].astype(float) == 0.075]

    if len(row_236) > 0 and len(row_0075) > 0:
        blend_236 = float(row_236["Blending (%)"].values[0])
        blend_0075 = float(row_0075["Blending (%)"].values[0])
    else:
        blend_236 = float(hasil_df["Blending (%)"].iloc[6])
        blend_0075 = float(hasil_df["Blending (%)"].iloc[11])

    a_coarse = 100.0 - blend_236
    c_filler = blend_0075
    b_fine = max(0.0, 100.0 - a_coarse - c_filler)
    kao_pred = np.round(0.035 * a_coarse + 0.045 * b_fine + 0.18 * c_filler + 2.0, 2)

    return a_coarse, b_fine, c_filler, kao_pred


def get_marshall_specs(tipe_campuran: str) -> dict:
    """
    Kembalikan batas spesifikasi Marshall dinamis berdasarkan tipe campuran.
    Mendukung AC-WC, AC-BC, AC-Base (Laston) dan HRS-WC, HRS-Base (Lataston).
    Referensi: Spesifikasi Umum Bina Marga 2018 Rev.2 Divisi 6.
    """
    specs = {
        "AC-WC":   {"stab_min": 800.0,  "flow_min": 2.0, "flow_max": 4.0, "mq_min": 250.0, "vim_min": 3.0, "vim_max": 5.0, "vma_min": 15.0, "vfb_min": 65.0,
                    "stab_label": "Min. 800 kg", "flow_label": "2.0 – 4.0 mm", "vim_label": "3.0 – 5.0 %", "vma_label": "Min. 15.0 %", "vfb_label": "Min. 65.0 %"},
        "AC-BC":   {"stab_min": 800.0,  "flow_min": 2.0, "flow_max": 4.0, "mq_min": 250.0, "vim_min": 3.0, "vim_max": 5.0, "vma_min": 14.0, "vfb_min": 65.0,
                    "stab_label": "Min. 800 kg", "flow_label": "2.0 – 4.0 mm", "vim_label": "3.0 – 5.0 %", "vma_label": "Min. 14.0 %", "vfb_label": "Min. 65.0 %"},
        "AC-Base": {"stab_min": 800.0,  "flow_min": 2.0, "flow_max": 4.0, "mq_min": 250.0, "vim_min": 3.0, "vim_max": 5.0, "vma_min": 13.0, "vfb_min": 65.0,
                    "stab_label": "Min. 800 kg", "flow_label": "2.0 – 4.0 mm", "vim_label": "3.0 – 5.0 %", "vma_label": "Min. 13.0 %", "vfb_label": "Min. 65.0 %"},
        "HRS-WC":  {"stab_min": 600.0,  "flow_min": 3.0, "flow_max": 999.0, "mq_min": 250.0, "vim_min": 4.0, "vim_max": 6.0, "vma_min": 18.0, "vfb_min": 68.0,
                    "stab_label": "Min. 600 kg", "flow_label": "Min. 3.0 mm", "vim_label": "4.0 – 6.0 %", "vma_label": "Min. 18.0 %", "vfb_label": "Min. 68.0 %"},
        "HRS-Base":{"stab_min": 600.0,  "flow_min": 3.0, "flow_max": 999.0, "mq_min": 250.0, "vim_min": 4.0, "vim_max": 6.0, "vma_min": 17.0, "vfb_min": 68.0,
                    "stab_label": "Min. 600 kg", "flow_label": "Min. 3.0 mm", "vim_label": "4.0 – 6.0 %", "vma_label": "Min. 17.0 %", "vfb_label": "Min. 68.0 %"},
    }
    return specs.get(tipe_campuran, specs["AC-WC"])


def calc_marshall_volumetrik(
    kadar_aspal: float, stabilitas: float, flow: float, gmm: float, gmb: float, gsb: float,
    tipe_campuran: str = "AC-WC"
) -> dict:
    """
    Hitung karakteristik volumetrik dan mekanik Marshall:
    - VIM (Void in Mix / Rongga dalam Campuran %)
    - VMA (Void in Mineral Aggregate %)
    - VFB (Void Filled with Bitumen %)
    - MQ  (Marshall Quotient kg/mm)
    Kriteria kelulusan otomatis menyesuaikan tipe campuran (AC/HRS).
    """
    vim = (1.0 - (gmb / gmm)) * 100.0 if gmm > 0 else 0.0
    vma = 100.0 - ((gmb * (100.0 - kadar_aspal)) / gsb) if gsb > 0 else 0.0
    vfb = ((vma - vim) / vma) * 100.0 if vma > 0 else 0.0
    mq = (stabilitas / flow) if flow > 0 else 0.0

    sp = get_marshall_specs(tipe_campuran)

    eval_stab = "✅ OK" if stabilitas >= sp["stab_min"] else "❌ OUT"
    eval_flow = "✅ OK" if (sp["flow_min"] <= flow <= sp["flow_max"]) else "❌ OUT"
    eval_mq   = "✅ OK" if mq >= sp["mq_min"] else "❌ OUT"
    eval_vim  = "✅ OK" if (sp["vim_min"] <= vim <= sp["vim_max"]) else "❌ OUT"
    eval_vma  = "✅ OK" if vma >= sp["vma_min"] else "❌ OUT"
    eval_vfb  = "✅ OK" if vfb >= sp["vfb_min"] else "❌ OUT"

    is_all_ok = all(
        s == "✅ OK"
        for s in [eval_stab, eval_flow, eval_mq, eval_vim, eval_vma, eval_vfb]
    )

    return {
        "vim": vim,
        "vma": vma,
        "vfb": vfb,
        "mq": mq,
        "eval_stab": eval_stab,
        "eval_flow": eval_flow,
        "eval_mq": eval_mq,
        "eval_vim": eval_vim,
        "eval_vma": eval_vma,
        "eval_vfb": eval_vfb,
        "is_all_ok": is_all_ok,
        "specs": sp,
    }


def calc_rab_pekerjaan(
    panjang_m: float,
    lebar_m: float,
    t_ac_cm: float,
    t_base_cm: float,
    t_subbase_cm: float,
    harga_ac_ton: float,
    harga_base_m3: float,
    harga_subbase_m3: float,
    harga_galian_m3: float,
    bj_aspal_ton_m3: float = 2.30,
    koef_galian: float = 1.30,
    include_ppn: bool = True,
) -> tuple[pd.DataFrame, float, dict]:
    """
    Hitung volume pekerjaan dan Rencana Anggaran Biaya (RAB):
    - Volume AC (m3) dikonversi ke Ton: Vol_AC * BJ (2.3 ton/m3)
    - Base & Sub-base (m3)
    - Galian Tanah (m3): Panjang * Lebar * Total_Tebal_m * koef_galian
    - Opsi Pajak Pertambahan Nilai (PPN 11%)
    """
    vol_ac_m3 = panjang_m * lebar_m * (t_ac_cm / 100.0)
    ton_ac = vol_ac_m3 * bj_aspal_ton_m3

    vol_base_m3 = panjang_m * lebar_m * (t_base_cm / 100.0)
    vol_subbase_m3 = panjang_m * lebar_m * (t_subbase_cm / 100.0)

    total_tebal_m = (t_ac_cm + t_base_cm + t_subbase_cm) / 100.0
    vol_galian_m3 = panjang_m * lebar_m * total_tebal_m * koef_galian

    biaya_ac = ton_ac * harga_ac_ton
    biaya_base = vol_base_m3 * harga_base_m3
    biaya_subbase = vol_subbase_m3 * harga_subbase_m3
    biaya_galian = vol_galian_m3 * harga_galian_m3

    subtotal_pokok = biaya_ac + biaya_base + biaya_subbase + biaya_galian
    ppn_val = (subtotal_pokok * 0.11) if include_ppn else 0.0
    grand_total = subtotal_pokok + ppn_val

    rows = [
        {
            "No": 1,
            "Uraian Pekerjaan": f"Lapis Permukaan Aspal AC ({t_ac_cm:.0f} cm)",
            "Satuan": "Ton",
            "Volume": round(ton_ac, 2),
            "Harga Satuan (Rp)": round(harga_ac_ton),
            "Total Biaya (Rp)": round(biaya_ac),
        },
        {
            "No": 2,
            "Uraian Pekerjaan": f"Lapis Pondasi Atas Agregat Kelas A ({t_base_cm:.0f} cm)",
            "Satuan": "m³",
            "Volume": round(vol_base_m3, 2),
            "Harga Satuan (Rp)": round(harga_base_m3),
            "Total Biaya (Rp)": round(biaya_base),
        },
        {
            "No": 3,
            "Uraian Pekerjaan": f"Lapis Pondasi Bawah Agregat Kelas B ({t_subbase_cm:.0f} cm)",
            "Satuan": "m³",
            "Volume": round(vol_subbase_m3, 2),
            "Harga Satuan (Rp)": round(harga_subbase_m3),
            "Total Biaya (Rp)": round(biaya_subbase),
        },
        {
            "No": 4,
            "Uraian Pekerjaan": f"Galian Tanah Biasa (Faktor Gembur {koef_galian}x)",
            "Satuan": "m³",
            "Volume": round(vol_galian_m3, 2),
            "Harga Satuan (Rp)": round(harga_galian_m3),
            "Total Biaya (Rp)": round(biaya_galian),
        },
    ]

    if include_ppn:
        rows.append({
            "No": "",
            "Uraian Pekerjaan": "SUBTOTAL PEKERJAAN POKOK",
            "Satuan": "-",
            "Volume": "",
            "Harga Satuan (Rp)": "",
            "Total Biaya (Rp)": round(subtotal_pokok),
        })
        rows.append({
            "No": "",
            "Uraian Pekerjaan": "PAJAK PERTAMBAHAN NILAI (PPN 11%)",
            "Satuan": "-",
            "Volume": "",
            "Harga Satuan (Rp)": "",
            "Total Biaya (Rp)": round(ppn_val),
        })
        rows.append({
            "No": "",
            "Uraian Pekerjaan": "TOTAL AKHIR ESTIMASI RAB (TERMASUK PPN 11%)",
            "Satuan": "-",
            "Volume": "",
            "Harga Satuan (Rp)": "",
            "Total Biaya (Rp)": round(grand_total),
        })
    else:
        rows.append({
            "No": "",
            "Uraian Pekerjaan": "TOTAL ESTIMASI RENCANA ANGGARAN BIAYA (RAB)",
            "Satuan": "-",
            "Volume": "",
            "Harga Satuan (Rp)": "",
            "Total Biaya (Rp)": round(grand_total),
        })

    df_rab = pd.DataFrame(rows)

    volume_dict = {
        "vol_ac_m3": vol_ac_m3,
        "ton_ac": ton_ac,
        "vol_base_m3": vol_base_m3,
        "vol_subbase_m3": vol_subbase_m3,
        "vol_galian_m3": vol_galian_m3,
        "biaya_ac": biaya_ac,
        "biaya_base": biaya_base,
        "biaya_subbase": biaya_subbase,
        "biaya_galian": biaya_galian,
        "subtotal_pokok": subtotal_pokok,
        "ppn_val": ppn_val,
        "grand_total": grand_total,
    }

    return df_rab, grand_total, volume_dict


# =====================================================================
# 3. HELPER UI, EKSPOR EXCEL PROFESIONAL & LAPORAN CETAK HTML
# =====================================================================

def render_html(html_str: str):
    """
    Render string HTML secara aman di Streamlit tanpa artefak kotak kode (indented code block).
    1. Menghapus spasi indentasi di awal dan akhir setiap baris (rata kiri / column 0).
    2. Menghapus baris kosong di tengah blok HTML yang memutus parsing HTML Streamlit.
    3. Menjalankan st.markdown dengan unsafe_allow_html=True.
    """
    clean_lines = [line.strip() for line in html_str.splitlines() if line.strip()]
    st.markdown("\n".join(clean_lines), unsafe_allow_html=True)


def get_svg_icon(name: str, color: str = "#38BDF8", size: int = 18) -> str:
    """Hasilkan string SVG inline bergaya Lucide Icons."""
    icons = {
        "road": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M4 19L8 5"/><path d="M16 5l4 14"/><path d="M12 8v2"/><path d="M12 14v2"/><path d="M12 20v2"/></svg>',
        "activity": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
        "layers": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
        "box": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
        "sliders": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>',
        "flask": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"/><line x1="8.5" y1="2" x2="15.5" y2="2"/><path d="M8.5 14h7"/></svg>',
        "dollar": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
        "file-text": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
        "shield-check": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>',
        "trending-up": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>',
    }
    return icons.get(name, "")


def clean_formal_text(val):
    """Bersihkan emoji status menjadi teks formal untuk dokumen teknik."""
    if isinstance(val, str):
        v = val.replace("✅ OK", "MEMENUHI SYARAT").replace("❌ OUT", "DI LUAR SPESIFIKASI")
        v = v.replace("● IN SPEC", "MEMENUHI SPESIFIKASI").replace("● OUT OF SPEC", "DI LUAR SPESIFIKASI")
        v = v.replace("✅", "").replace("❌", "").replace("●", "").strip()
        return v
    return val


def export_professional_excel(
    df: pd.DataFrame,
    sheet_name: str,
    title: str,
    subtitle: str,
    metadata_dict: dict = None
) -> tuple[bytes, str, str]:
    """
    Ekspor dataframe ke Excel (.xlsx) dengan kop surat teknik, header dark navy,
    border tipis, auto-fit lebar kolom, format angka dan mata uang Rupiah.
    Fallback otomatis ke CSV UTF-8-SIG berpemisah ';' jika openpyxl tidak tersedia.
    Return: (file_bytes, file_name, mime_type)
    """
    df_clean = df.copy()
    for col in df_clean.columns:
        df_clean[col] = df_clean[col].apply(clean_formal_text)

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        output = io.BytesIO()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = str(sheet_name)[:31]
        ws.views.sheetView[0].showGridLines = True

        fill_navy = PatternFill(start_color="0B192C", end_color="0B192C", fill_type="solid")
        fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        font_main_title = Font(name="Calibri", size=13, bold=True, color="0B192C")
        font_subtitle = Font(name="Calibri", size=10, italic=True, color="334155")
        font_meta = Font(name="Calibri", size=9, bold=False, color="475569")
        font_meta_val = Font(name="Calibri", size=9, bold=True, color="0F172A")
        font_th = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        font_td = Font(name="Calibri", size=10, bold=False, color="0F172A")
        font_pass = Font(name="Calibri", size=10, bold=True, color="047857")
        font_fail = Font(name="Calibri", size=10, bold=True, color="B91C1C")

        thin_side = Side(border_style="thin", color="CBD5E1")
        table_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        # Baris 1-3 Kop Dokumen
        ws.cell(row=1, column=1, value="PAVEDESIGN & JMF — LAPORAN ANALISIS TEKNIK SIPIL").font = font_main_title
        ws.cell(row=2, column=1, value=f"{title} — {subtitle}").font = font_subtitle
        tgl_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        ws.cell(row=3, column=1, value=f"Acuan: Manual Desain Pd T-01-2002-B & Spesifikasi Umum Bina Marga 2018 | Cetak: {tgl_str} WIB").font = font_meta

        curr_row = 5
        if metadata_dict:
            for k, v in metadata_dict.items():
                ws.cell(row=curr_row, column=1, value=str(k)).font = font_meta
                ws.cell(row=curr_row, column=2, value=str(v)).font = font_meta_val
                curr_row += 1
            curr_row += 1

        # Table Header
        header_row = curr_row
        for col_idx, col_name in enumerate(df_clean.columns, start=1):
            cell = ws.cell(row=header_row, column=col_idx, value=str(col_name))
            cell.font = font_th
            cell.fill = fill_navy
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = table_border
        ws.row_dimensions[header_row].height = 24

        # Table Data
        start_data_row = header_row + 1
        for row_idx, row_data in enumerate(df_clean.itertuples(index=False), start=start_data_row):
            is_even = (row_idx % 2 == 0)
            ws.row_dimensions[row_idx].height = 20

            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = font_td
                cell.border = table_border

                if is_even:
                    cell.fill = fill_zebra

                col_name_lower = str(df_clean.columns[col_idx - 1]).lower()
                if isinstance(val, (int, np.integer)):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if "harga" in col_name_lower or "biaya" in col_name_lower or "total" in col_name_lower:
                        cell.number_format = '"Rp "#,##0'
                    else:
                        cell.number_format = '#,##0'
                elif isinstance(val, (float, np.floating)):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if "harga" in col_name_lower or "biaya" in col_name_lower or "total" in col_name_lower:
                        cell.number_format = '"Rp "#,##0'
                    elif "saringan" in col_name_lower or "mm" in col_name_lower:
                        cell.number_format = '0.00#'
                    else:
                        cell.number_format = '#,##0.00'
                elif isinstance(val, str):
                    if val in ["MEMENUHI SYARAT", "MEMENUHI SPESIFIKASI"]:
                        cell.font = font_pass
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    elif val == "DI LUAR SPESIFIKASI":
                        cell.font = font_fail
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    else:
                        cell.alignment = Alignment(horizontal="left", vertical="center")

        # Auto-fit kolom
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.row >= header_row and cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        wb.save(output)
        output.seek(0)
        return output.getvalue(), f"{sheet_name.replace(' ', '_')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    except Exception:
        output = io.StringIO()
        output.write(f"# PAVEDESIGN & JMF — {title} ({subtitle})\n")
        output.write(f"# Tanggal Cetak: {datetime.now().strftime('%d/%m/%Y %H:%M')} WIB\n")
        if metadata_dict:
            for k, v in metadata_dict.items():
                output.write(f"# {k}: {v}\n")
        output.write("#\n")
        df_clean.to_csv(output, sep=";", index=False, encoding="utf-8-sig")
        return output.getvalue().encode("utf-8-sig"), f"{sheet_name.replace(' ', '_')}.csv", "text/csv"


def export_multisheet_excel(
    sheets_dict: dict[str, pd.DataFrame],
    title: str,
) -> tuple[bytes, str, str]:
    """
    Ekspor workbook multi-sheet (Ringkasan, Struktur, JMF, Marshall, RAB).
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        output = io.BytesIO()
        wb = openpyxl.Workbook()
        wb.remove(wb.active)  # Hapus default empty sheet

        fill_navy = PatternFill(start_color="0B192C", end_color="0B192C", fill_type="solid")
        fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        font_main_title = Font(name="Calibri", size=13, bold=True, color="0B192C")
        font_subtitle = Font(name="Calibri", size=10, italic=True, color="334155")
        font_meta = Font(name="Calibri", size=9, bold=False, color="475569")
        font_th = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        font_td = Font(name="Calibri", size=10, bold=False, color="0F172A")
        font_pass = Font(name="Calibri", size=10, bold=True, color="047857")
        font_fail = Font(name="Calibri", size=10, bold=True, color="B91C1C")

        thin_side = Side(border_style="thin", color="CBD5E1")
        table_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        for s_title, df_raw in sheets_dict.items():
            ws = wb.create_sheet(title=s_title[:31])
            ws.views.sheetView[0].showGridLines = True

            df_clean = df_raw.copy()
            for col in df_clean.columns:
                df_clean[col] = df_clean[col].apply(clean_formal_text)

            ws.cell(row=1, column=1, value="PAVEDESIGN & JMF — LAPORAN REKAP LENGKAP TEKNIK SIPIL").font = font_main_title
            ws.cell(row=2, column=1, value=f"Modul: {s_title} — Acuan Standar Bina Marga").font = font_subtitle
            tgl_str = datetime.now().strftime("%d/%m/%Y %H:%M")
            ws.cell(row=3, column=1, value=f"Tanggal Cetak: {tgl_str} WIB").font = font_meta

            header_row = 5
            for col_idx, col_name in enumerate(df_clean.columns, start=1):
                cell = ws.cell(row=header_row, column=col_idx, value=str(col_name))
                cell.font = font_th
                cell.fill = fill_navy
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = table_border
            ws.row_dimensions[header_row].height = 24

            start_data_row = header_row + 1
            for row_idx, row_data in enumerate(df_clean.itertuples(index=False), start=start_data_row):
                is_even = (row_idx % 2 == 0)
                ws.row_dimensions[row_idx].height = 20
                for col_idx, val in enumerate(row_data, start=1):
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                    cell.font = font_td
                    cell.border = table_border
                    if is_even:
                        cell.fill = fill_zebra

                    col_name_lower = str(df_clean.columns[col_idx - 1]).lower()
                    if isinstance(val, (int, np.integer)):
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                        if "harga" in col_name_lower or "biaya" in col_name_lower or "total" in col_name_lower:
                            cell.number_format = '"Rp "#,##0'
                        else:
                            cell.number_format = '#,##0'
                    elif isinstance(val, (float, np.floating)):
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                        if "harga" in col_name_lower or "biaya" in col_name_lower or "total" in col_name_lower:
                            cell.number_format = '"Rp "#,##0'
                        else:
                            cell.number_format = '#,##0.00'
                    elif isinstance(val, str):
                        if val in ["MEMENUHI SYARAT", "MEMENUHI SPESIFIKASI"]:
                            cell.font = font_pass
                            cell.alignment = Alignment(horizontal="center", vertical="center")
                        elif val == "DI LUAR SPESIFIKASI":
                            cell.font = font_fail
                            cell.alignment = Alignment(horizontal="center", vertical="center")
                        else:
                            cell.alignment = Alignment(horizontal="left", vertical="center")

            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    if cell.row >= header_row and cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        wb.save(output)
        output.seek(0)
        return output.getvalue(), "Rekap_Lengkap_PaveDesign.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except Exception:
        output = io.StringIO()
        output.write("# PAVEDESIGN & JMF — REKAP LENGKAP LAPORAN TEKNIK SIPIL\n\n")
        for s_title, df_raw in sheets_dict.items():
            output.write(f"### SHEET: {s_title}\n")
            df_raw.to_csv(output, sep=";", index=False, encoding="utf-8-sig")
            output.write("\n\n")
        return output.getvalue().encode("utf-8-sig"), "Rekap_Lengkap_PaveDesign.csv", "text/csv"


def generate_html_report(
    rekom: dict,
    cesal_juta: float,
    le_harian: float,
    cbr: float,
    ddt: float,
    umur_rencana: int,
    laju_pertumbuhan: float,
    tipe_campuran: str,
    prop_kasar: float,
    prop_halus: float,
    prop_filler: float,
    kao_prediktif: float,
    m_res: dict,
    kadar_aspal_m: float,
    stabilitas_m: float,
    flow_m: float,
    rab_wilayah: str,
    rab_panjang: float,
    rab_lebar: float,
    df_rab: pd.DataFrame,
    grand_total_rab: float,
    include_ppn: bool,
) -> str:
    """Hasilkan dokumen HTML format resmi A4 siap cetak (Ctrl+P / PDF)."""
    tgl_now = datetime.now().strftime("%d %B %Y, %H:%M")
    sp_doc = m_res.get("specs", get_marshall_specs(tipe_campuran))
    
    # Build RAB rows HTML
    rab_rows_html = ""
    for r in df_rab.itertuples(index=False):
        no_str = str(r[0]) if r[0] != "" else ""
        uraian = str(r[1])
        sat = str(r[2])
        vol_str = f"{r[3]:,.2f}" if isinstance(r[3], (int, float)) else str(r[3])
        harga_str = f"Rp {r[4]:,.0f}" if isinstance(r[4], (int, float)) and r[4] != "" else str(r[4])
        tot_str = f"Rp {r[5]:,.0f}" if isinstance(r[5], (int, float)) else str(r[5])

        is_summary = "TOTAL" in uraian or "SUBTOTAL" in uraian or "PAJAK" in uraian
        font_weight = "bold" if is_summary else "normal"
        bg_col = "#F1F5F9" if is_summary else "#FFFFFF"

        rab_rows_html += f"""
        <tr style="background-color: {bg_col}; font-weight: {font_weight};">
            <td style="text-align: center; padding: 6px;">{no_str}</td>
            <td style="padding: 6px;">{uraian}</td>
            <td style="text-align: center; padding: 6px;">{sat}</td>
            <td style="text-align: right; padding: 6px;">{vol_str}</td>
            <td style="text-align: right; padding: 6px;">{harga_str}</td>
            <td style="text-align: right; padding: 6px;">{tot_str}</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<title>Laporan Teknis PaveDesign & JMF</title>
<style>
    @page {{
        size: A4 portrait;
        margin: 15mm 15mm 20mm 15mm;
    }}
    body {{
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        color: #0F172A;
        line-height: 1.5;
        font-size: 11pt;
        background: #F8FAFC;
        margin: 0;
        padding: 20px;
    }}
    .document-page {{
        max-width: 820px;
        margin: 0 auto;
        background: #FFFFFF;
        padding: 35px 45px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border: 1px solid #E2E8F0;
    }}
    .kop-header {{
        border-bottom: 3px double #0B192C;
        padding-bottom: 12px;
        margin-bottom: 20px;
        text-align: center;
    }}
    .kop-header h2 {{
        margin: 0;
        font-size: 15pt;
        color: #0B192C;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    .kop-header h4 {{
        margin: 4px 0;
        font-size: 11pt;
        color: #0284C7;
        font-weight: 600;
    }}
    .kop-header p {{
        margin: 0;
        font-size: 8.5pt;
        color: #64748B;
    }}
    .section-title {{
        font-size: 11pt;
        font-weight: 700;
        color: #0B192C;
        border-bottom: 1.5px solid #0284C7;
        padding-bottom: 4px;
        margin-top: 20px;
        margin-bottom: 10px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 14px;
        font-size: 9.5pt;
    }}
    th {{
        background: #0B192C;
        color: #FFFFFF;
        font-weight: 600;
        padding: 7px 8px;
        text-align: left;
        border: 1px solid #CBD5E1;
    }}
    td {{
        padding: 6px 8px;
        border: 1px solid #CBD5E1;
        vertical-align: middle;
    }}
    .badge-ok {{
        color: #047857;
        font-weight: bold;
    }}
    .badge-out {{
        color: #B91C1C;
        font-weight: bold;
    }}
    .ttd-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 20px;
        margin-top: 35px;
        page-break-inside: avoid;
        text-align: center;
    }}
    .ttd-box {{
        padding: 10px;
    }}
    .ttd-space {{
        height: 65px;
    }}
    .no-print {{
        text-align: center;
        margin-bottom: 20px;
    }}
    .btn-print {{
        background: #0284C7;
        color: white;
        padding: 12px 24px;
        border-radius: 8px;
        font-size: 14px;
        font-weight: bold;
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(2,132,199,0.3);
    }}
    .btn-print:hover {{
        background: #0369A1;
    }}
    @media print {{
        body {{
            background: #FFFFFF;
            padding: 0;
        }}
        .document-page {{
            box-shadow: none;
            border: none;
            padding: 0;
            max-width: 100%;
        }}
        .no-print {{
            display: none !important;
        }}
    }}
</style>
</head>
<body>

<div class="no-print">
    <button class="btn-print" onclick="window.print()">🖨️ CETAK DOKUMEN / SIMPAN SEBAGAI PDF (Ctrl + P)</button>
</div>

<div class="document-page">
    <div class="kop-header">
        <h2>KEMENTERIAN PEKERJAAN UMUM DAN PERUMAHAN RAKYAT</h2>
        <h4>LEMBAR LAPORAN PERENCANAAN TEKNIK JALAN RAYA</h4>
        <p>Acuan Standar: Manual Desain Perkerasan Jalan Pd T-01-2002-B & Spesifikasi Umum Bina Marga 2018 Rev.2</p>
        <p>Nomor Dokumen: PVD-JMF/RPT/{datetime.now().strftime('%Y%m%d')}/01 &bull; Tanggal Analisis: {tgl_now} WIB</p>
    </div>

    <!-- Bagian 1: Data Perencanaan Lalu Lintas & Tanah Dasar -->
    <div class="section-title">1. Parameter Perencanaan Lalu Lintas & Tanah Dasar</div>
    <table>
        <tr>
            <td style="width: 35%; color: #475569;">Umur Rencana (<i>n</i>)</td>
            <td style="width: 15%; font-weight: bold;">{umur_rencana} Tahun</td>
            <td style="width: 35%; color: #475569;">Tipe Campuran Aspal</td>
            <td style="width: 15%; font-weight: bold;">{tipe_campuran}</td>
        </tr>
        <tr>
            <td style="color: #475569;">Laju Pertumbuhan Lalu Lintas (<i>i</i>)</td>
            <td style="font-weight: bold;">{laju_pertumbuhan:.1f}% / tahun</td>
            <td style="color: #475569;">Lintas Ekivalen Harian (LE)</td>
            <td style="font-weight: bold;">{le_harian:,.1f} ESA/hari</td>
        </tr>
        <tr>
            <td style="color: #475569;">CBR Efektif Subgrade</td>
            <td style="font-weight: bold;">{cbr:.1f}% (DDT = {ddt:.2f})</td>
            <td style="color: #475569;">Beban Sumbu Rencana (CESAL)</td>
            <td style="font-weight: bold;">{cesal_juta:,.3f} MESA</td>
        </tr>
    </table>

    <!-- Bagian 2: Struktur Tebal Lapisan Perkerasan -->
    <div class="section-title">2. Rekomendasi Struktur Tebal Perkerasan Lentur</div>
    <table>
        <thead>
            <tr>
                <th style="width: 10%; text-align: center;">No</th>
                <th style="width: 55%;">Komponen Lapisan Perkerasan</th>
                <th style="width: 20%;">Material Standar</th>
                <th style="width: 15%; text-align: right;">Tebal (cm)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td style="text-align: center;">1</td>
                <td><b>Lapis Permukaan (Surface Course)</b></td>
                <td>{tipe_campuran} (Spesifikasi Divisi 6)</td>
                <td style="text-align: right; font-weight: bold;">{rekom['Lapis Permukaan (AC) [cm]']} cm</td>
            </tr>
            <tr>
                <td style="text-align: center;">2</td>
                <td><b>Lapis Pondasi Atas (Base Course)</b></td>
                <td>Agregat Kelas A / CTB</td>
                <td style="text-align: right; font-weight: bold;">{rekom['Lapis Pondasi Atas (Base) [cm]']} cm</td>
            </tr>
            <tr>
                <td style="text-align: center;">3</td>
                <td><b>Lapis Pondasi Bawah (Sub-base Course)</b></td>
                <td>Agregat Kelas B / Sirtu Kelas A</td>
                <td style="text-align: right; font-weight: bold;">{rekom['Lapis Pondasi Bawah (Sub-Base) [cm]']} cm</td>
            </tr>
            <tr style="background: #F1F5F9; font-weight: bold;">
                <td colspan="3" style="text-align: right;">TOTAL KETEBALAN STRUKTUR PERKERASAN:</td>
                <td style="text-align: right; font-size: 11pt; color: #0284C7;">{rekom['Total Tebal Perkerasan [cm]']} cm</td>
            </tr>
        </tbody>
    </table>

    <!-- Bagian 3: Formula Campuran JMF & Marshall -->
    <div class="section-title">3. Ringkasan Job Mix Formula (JMF) & Karakteristik Marshall</div>
    <table>
        <thead>
            <tr>
                <th>Parameter Pengujian</th>
                <th>Hasil Evaluasi / Uji</th>
                <th>Spesifikasi Bina Marga 2018</th>
                <th style="text-align: center;">Status</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Proporsi Agregat Gabungan</td>
                <td>Kasar: {prop_kasar:.0f}% &bull; Halus: {prop_halus:.0f}% &bull; Filler: {prop_filler:.0f}%</td>
                <td>Total = 100.0%</td>
                <td style="text-align: center;" class="badge-ok">MEMENUHI SYARAT</td>
            </tr>
            <tr>
                <td>Estimasi KAO Hudson / Uji (P<sub>b</sub>)</td>
                <td><b>{kadar_aspal_m:.1f}%</b> (Prediktif Hudson: {kao_prediktif:.2f}%)</td>
                <td>Rentang Standar 5.5% – 6.5%</td>
                <td style="text-align: center;" class="badge-ok">MEMENUHI SYARAT</td>
            </tr>
            <tr>
                <td>Stabilitas Marshall</td>
                <td>{stabilitas_m:,.0f} kg</td>
                <td>{sp_doc['stab_label']}</td>
                <td style="text-align: center;" class="{'badge-ok' if m_res['eval_stab'] == '✅ OK' else 'badge-out'}">{'MEMENUHI SYARAT' if m_res['eval_stab'] == '✅ OK' else 'DI LUAR SPESIFIKASI'}</td>
            </tr>
            <tr>
                <td>Kelelehan Plastis (Flow)</td>
                <td>{flow_m:.2f} mm</td>
                <td>{sp_doc['flow_label']}</td>
                <td style="text-align: center;" class="{'badge-ok' if m_res['eval_flow'] == '✅ OK' else 'badge-out'}">{'MEMENUHI SYARAT' if m_res['eval_flow'] == '✅ OK' else 'DI LUAR SPESIFIKASI'}</td>
            </tr>
            <tr>
                <td>Rongga dalam Campuran (VIM)</td>
                <td>{m_res['vim']:.2f}%</td>
                <td>{sp_doc['vim_label']}</td>
                <td style="text-align: center;" class="{'badge-ok' if m_res['eval_vim'] == '✅ OK' else 'badge-out'}">{'MEMENUHI SYARAT' if m_res['eval_vim'] == '✅ OK' else 'DI LUAR SPESIFIKASI'}</td>
            </tr>
            <tr>
                <td>Rongga Terisi Aspal (VFB)</td>
                <td>{m_res['vfb']:.1f}%</td>
                <td>{sp_doc['vfb_label']}</td>
                <td style="text-align: center;" class="{'badge-ok' if m_res['eval_vfb'] == '✅ OK' else 'badge-out'}">{'MEMENUHI SYARAT' if m_res['eval_vfb'] == '✅ OK' else 'DI LUAR SPESIFIKASI'}</td>
            </tr>
        </tbody>
    </table>

    <!-- Bagian 4: Rencana Anggaran Biaya -->
    <div class="section-title">4. Rencana Anggaran Biaya (RAB) — Wilayah: {rab_wilayah}</div>
    <table>
        <thead>
            <tr>
                <th style="width: 6%; text-align: center;">No</th>
                <th style="width: 44%;">Uraian Pekerjaan</th>
                <th style="width: 10%; text-align: center;">Satuan</th>
                <th style="width: 12%; text-align: right;">Volume</th>
                <th style="width: 14%; text-align: right;">Harga Satuan</th>
                <th style="width: 14%; text-align: right;">Total Biaya</th>
            </tr>
        </thead>
        <tbody>
            {rab_rows_html}
        </tbody>
    </table>

    <!-- Lembar Tanda Tangan -->
    <div class="ttd-grid">
        <div class="ttd-box">
            <div style="font-size: 9pt; color: #475569;">Direncanakan Oleh:</div>
            <div style="font-weight: bold; margin-top: 4px;">Highway Design Engineer</div>
            <div class="ttd-space"></div>
            <div style="border-bottom: 1px solid #0F172A; width: 80%; margin: 0 auto;"></div>
            <div style="font-size: 8.5pt; color: #64748B; margin-top: 4px;">SKA Ahli Utama Jalan</div>
        </div>
        <div class="ttd-box">
            <div style="font-size: 9pt; color: #475569;">Diperiksa Oleh:</div>
            <div style="font-weight: bold; margin-top: 4px;">Lead Quality Assurance</div>
            <div class="ttd-space"></div>
            <div style="border-bottom: 1px solid #0F172A; width: 80%; margin: 0 auto;"></div>
            <div style="font-size: 8.5pt; color: #64748B; margin-top: 4px;">Senior Highway Specialist</div>
        </div>
        <div class="ttd-box">
            <div style="font-size: 9pt; color: #475569;">Disetujui Oleh:</div>
            <div style="font-weight: bold; margin-top: 4px;">Pejabat Pembuat Komitmen (PPK)</div>
            <div class="ttd-space"></div>
            <div style="border-bottom: 1px solid #0F172A; width: 80%; margin: 0 auto;"></div>
            <div style="font-size: 8.5pt; color: #64748B; margin-top: 4px;">NIP. 19850412 201012 1 002</div>
        </div>
    </div>
</div>

</body>
</html>
"""
    return html_content


# =====================================================================
# 4. FUNGSI VISUALISASI 3D PENAMPANG PERKERASAN, MARKA & DRAINASE
# =====================================================================

def build_pavement_3d(
    t_permukaan: float,
    t_base: float,
    t_subbase: float,
    lebar_jalan: float,
    lebar_bahu: float = 1.5,
    kemiringan_talud: float = 0.5,
    is_dark: bool = True,
) -> go.Figure:
    """
    Visualisasi 3D Interaktif potongan melintang dan memanjang struktur jalan:
    - Lapisan AC, Base Kelas A, Sub-base Kelas B, Subgrade
    - Garis marka jalan putih putus-putus di permukaan AC
    - Saluran drainase samping trapesium di kaki talud kiri & kanan
    - Bahu jalan (road shoulder) kiri & kanan
    - Penampang trapesium talud tanah
    """
    fig = go.Figure()

    t_subgrade = 25.0  # cm visualisasi subgrade
    L = 12.0           # panjang penampang arah longitudinal (Y, meter)
    W = lebar_jalan    # lebar perkerasan (meter)
    S = lebar_bahu     # lebar bahu jalan (meter)

    # Konversi ketebalan ke meter
    h_ac = t_permukaan / 100.0
    h_base = t_base / 100.0
    h_sub = t_subbase / 100.0
    h_sg = t_subgrade / 100.0

    total_depth_m = h_ac + h_base + h_sub + h_sg

    z0 = 0.0
    z1 = z0 - h_ac
    z2 = z1 - h_base
    z3 = z2 - h_sub
    z4 = z3 - h_sg

    half_w = W / 2.0
    outer_w = half_w + S

    def make_box_mesh(z_top, z_bot, x_min, x_max, y_min, y_max, color, name, opacity=1.0):
        x = [x_min, x_max, x_max, x_min, x_min, x_max, x_max, x_min]
        y = [y_min, y_min, y_max, y_max, y_min, y_min, y_max, y_max]
        z = [z_top, z_top, z_top, z_top, z_bot, z_bot, z_bot, z_bot]
        i_ = [0, 1, 0, 2, 4, 5, 4, 6, 0, 1, 2, 3]
        j_ = [1, 2, 2, 3, 5, 6, 6, 7, 4, 5, 6, 7]
        k_ = [2, 3, 3, 0, 6, 7, 7, 4, 1, 2, 3, 0]
        return go.Mesh3d(
            x=x, y=y, z=z,
            i=i_, j=j_, k=k_,
            color=color, opacity=opacity,
            name=name, showlegend=True,
            flatshading=True,
            hoverinfo="name",
        )

    # 1. Lapisan Struktur Perkerasan
    fig.add_trace(make_box_mesh(z0, z1, -half_w, half_w, 0, L, "#1E293B", f"AC Surface ({t_permukaan:.0f} cm)"))
    fig.add_trace(make_box_mesh(z1, z2, -half_w, half_w, 0, L, "#64748B", f"Base Kelas A ({t_base:.0f} cm)"))
    fig.add_trace(make_box_mesh(z2, z3, -half_w, half_w, 0, L, "#D97706", f"Sub-base Kelas B ({t_subbase:.0f} cm)"))
    fig.add_trace(make_box_mesh(z3, z4, -half_w, half_w, 0, L, "#78350F", "Tanah Dasar / Subgrade"))

    # 2. Bahu Jalan Kiri & Kanan
    fig.add_trace(make_box_mesh(z0, z2, -outer_w, -half_w, 0, L, "#475569", f"Bahu Kiri ({S:.1f} m)", opacity=0.85))
    fig.add_trace(make_box_mesh(z0, z2, half_w, outer_w, 0, L, "#475569", f"Bahu Kanan ({S:.1f} m)", opacity=0.85))

    # 3. Marka As Jalan Putih Putus-Putus
    marka_x, marka_y, marka_z = [], [], []
    y_curr = 0.5
    dash_len = 2.0
    gap_len = 1.5
    while y_curr < L:
        y_end = min(y_curr + dash_len, L)
        marka_x.extend([0.0, 0.0, None])
        marka_y.extend([y_curr, y_end, None])
        marka_z.extend([z0 + 0.006, z0 + 0.006, None])
        y_curr = y_end + gap_len

    fig.add_trace(go.Scatter3d(
        x=marka_x, y=marka_y, z=marka_z,
        mode="lines",
        line=dict(color="#FFFFFF", width=8),
        name="Marka As Jalan",
        showlegend=True,
    ))

    # 4. Talud Tanah Galian / Timbunan
    talud_h = total_depth_m * kemiringan_talud
    talud_color = "#0EA5E9" if is_dark else "#0284C7"

    # Talud Kiri
    x_tk = [-outer_w - talud_h, -outer_w, -outer_w, -outer_w - talud_h]
    y_tk = [0, 0, L, L]
    z_tk = [z4, z0, z0, z4]
    fig.add_trace(go.Mesh3d(
        x=x_tk, y=y_tk, z=z_tk,
        i=[0, 0], j=[1, 2], k=[2, 3],
        color=talud_color, opacity=0.35,
        name=f"Talud (1:{1/kemiringan_talud:.1f})", showlegend=True, flatshading=True,
    ))

    # Talud Kanan
    x_tr = [outer_w, outer_w + talud_h, outer_w + talud_h, outer_w]
    y_tr = [0, 0, L, L]
    z_tr = [z0, z4, z4, z0]
    fig.add_trace(go.Mesh3d(
        x=x_tr, y=y_tr, z=z_tr,
        i=[0, 0], j=[1, 2], k=[2, 3],
        color=talud_color, opacity=0.35,
        name="Talud Kanan", showlegend=False, flatshading=True,
    ))

    # 5. Saluran Drainase Trapesium di Kaki Talud Kiri & Kanan
    w_drain = 0.8
    h_drain = 0.4
    x_d_left_outer = -outer_w - talud_h - w_drain
    x_d_left_inner = -outer_w - talud_h
    fig.add_trace(make_box_mesh(
        z4, z4 - h_drain, x_d_left_outer, x_d_left_inner, 0, L, "#94A3B8", "Drainase Samping Kiri", opacity=0.9
    ))

    x_d_right_inner = outer_w + talud_h
    x_d_right_outer = outer_w + talud_h + w_drain
    fig.add_trace(make_box_mesh(
        z4, z4 - h_drain, x_d_right_inner, x_d_right_outer, 0, L, "#94A3B8", "Drainase Samping Kanan", opacity=0.9
    ))

    # Styling Layout Sesuai Mode Warna
    bg_plot = "#061121" if is_dark else "#F8FAFC"
    bg_paper = "#0B192C" if is_dark else "#FFFFFF"
    font_color = "#F8FAFC" if is_dark else "#334155"
    grid_color = "#1E3A5F" if is_dark else "#E2E8F0"

    fig.update_layout(
        scene=dict(
            xaxis=dict(title="Lebar (m)", backgroundcolor=bg_plot, gridcolor=grid_color, color=font_color),
            yaxis=dict(title="Panjang (m)", backgroundcolor=bg_plot, gridcolor=grid_color, color=font_color),
            zaxis=dict(title="Elevasi (m)", backgroundcolor=bg_plot, gridcolor=grid_color, color=font_color),
            camera=dict(eye=dict(x=-1.6, y=-1.9, z=1.2)),
            bgcolor=bg_plot,
            aspectmode="data",
        ),
        paper_bgcolor=bg_paper,
        font=dict(family="Plus Jakarta Sans, sans-serif", color=font_color, size=11),
        legend=dict(
            orientation="h",
            y=-0.05,
            x=0.5,
            xanchor="center",
            font=dict(size=10, color=font_color),
        ),
        margin=dict(l=0, r=0, t=10, b=10),
        height=450,
    )

    return fig


# =====================================================================
# 5. INITIAL STATE & SISTEM DEFAULT
# =====================================================================

defaults = {
    "dark_mode": True,
    "umur_rencana": 20,
    "laju_pertumbuhan": 5.0,
    "cbr": 6.0,
    "pilihan_jalan": "2 Lajur 2 Arah (DL = 0.5)",
    "lhr_bus": 150,
    "lhr_truk2": 250,
    "lhr_truk3": 100,
    "tipe_campuran": "AC-WC",
    "prop_kasar": 40.0,
    "prop_halus": 55.0,
    "prop_filler": 5.0,
    "kadar_aspal_marshall": 5.8,
    # --- Sinkronisasi Fix 1: Input Marshall ke session_state ---
    "marshall_stabilitas": 1180.0,
    "marshall_flow": 3.2,
    "marshall_gmm": 2.455,
    "marshall_gmb": 2.350,
    "marshall_gsb": 2.660,
    # --- Sinkronisasi Fix 1: Tabel JMF custom ---
    "df_jmf_custom": None,
    "lebar_jalan_3d": 7.0,
    "lebar_bahu_3d": 1.5,
    "kemiringan_talud_3d": 0.5,
    "rab_wilayah": "Jawa Tengah & DIY",
    "rab_panjang": 1000.0,
    "rab_lebar": 7.0,
    "rab_harga_ac": 1_850_000,
    "rab_harga_base": 360_000,
    "rab_harga_subbase": 230_000,
    "rab_harga_galian": 45_000,
    "rab_include_ppn": True,
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

tipe_jalan_dict = {
    "1 Lajur (DL = 1.0)": 1.0,
    "2 Lajur 2 Arah (DL = 0.5)": 0.5,
    "4 Lajur 2 Arah (DL = 0.45)": 0.45,
}

dl_val = tipe_jalan_dict.get(st.session_state.pilihan_jalan, 0.5)

# Kalkulasi Cepat Global untuk Header Metric
le_harian_val = calc_le_harian(
    st.session_state.lhr_bus, st.session_state.lhr_truk2, st.session_state.lhr_truk3
)
r_factor_val = calc_r_factor(st.session_state.laju_pertumbuhan, st.session_state.umur_rencana)
cesal_tot_val, cesal_juta_val = calc_cesal(le_harian_val, r_factor_val, dl_val)
ddt_val = calc_ddt(st.session_state.cbr)
rekom_global = get_rekomendasi_tebal(cesal_juta_val, st.session_state.cbr)


# =====================================================================
# 6. DESIGN SYSTEM: RUMUS WARNA 60-30-10 & 8PX GRID CSS
# =====================================================================

dm = st.session_state.dark_mode

if dm:
    # 60% Latar Utama Deep Navy
    c_bg = "#061121"
    # 30% Kartu & Sidebar Dark Slate
    c_card = "#0B192C"
    c_card_inner = "#081322"
    c_border = "#1E3A5F"
    c_text = "#F8FAFC"
    c_muted = "#94A3B8"
    # 10% Aksen Aksi Cyber Cyan
    c_accent = "#0EA5E9"
    c_accent_bright = "#38BDF8"
    c_btn_txt = "#061121"
    c_btn_bg = "#38BDF8"
    c_btn_hover = "#0EA5E9"
else:
    # 60% Latar Netral Bersih
    c_bg = "#F8FAFC"
    # 30% Kartu & Sidebar Putih Bersih
    c_card = "#FFFFFF"
    c_card_inner = "#F1F5F9"
    c_border = "#E2E8F0"
    c_text = "#334155"  # Abu gelap nyaman di mata
    c_muted = "#64748B"
    # 10% Aksen Aksi Biru
    c_accent = "#0284C7"
    c_accent_bright = "#0284C7"
    c_btn_txt = "#FFFFFF"
    c_btn_bg = "#0284C7"
    c_btn_hover = "#0369A1"

custom_css = f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        color: {c_text};
    }}

    .stApp {{
        background-color: {c_bg} !important;
        color: {c_text} !important;
    }}

    h1 {{ font-size: 28px !important; font-weight: 700 !important; color: {c_text} !important; margin-bottom: 8px !important; }}
    h2 {{ font-size: 24px !important; font-weight: 700 !important; color: {c_text} !important; margin-bottom: 8px !important; }}
    h3 {{ font-size: 20px !important; font-weight: 600 !important; color: {c_text} !important; margin-bottom: 8px !important; }}
    h4 {{ font-size: 18px !important; font-weight: 600 !important; color: {c_text} !important; margin-bottom: 8px !important; }}
    p, span, label, div {{ font-size: 15px; font-weight: 400; line-height: 1.6; color: {c_text}; }}

    .bento-card {{
        background: {c_card};
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
        border: 1px solid {c_border};
        box-shadow: 0 4px 20px rgba(0, 0, 0, {'0.25' if dm else '0.04'});
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }}

    .bento-card-inner {{
        background: {c_card_inner};
        border-radius: 10px;
        padding: 16px;
        border: 1px solid {c_border};
        margin-bottom: 16px;
    }}

    .dashboard-header {{
        background: {c_card};
        border-radius: 12px;
        padding: 20px 24px;
        border: 1px solid {c_border};
        margin-bottom: 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 16px rgba(0, 0, 0, {'0.2' if dm else '0.03'});
    }}

    .header-metric-card {{
        background: {c_card};
        border-radius: 12px;
        padding: 16px 20px;
        border: 1px solid {c_border};
        margin-bottom: 24px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, {'0.2' if dm else '0.03'});
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    .header-metric-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0, 0, 0, {'0.3' if dm else '0.06'});
    }}
    .metric-label {{
        font-size: 13px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: {c_muted};
        margin-bottom: 6px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .metric-value {{
        font-size: 26px;
        font-weight: 800;
        color: {c_accent_bright};
        line-height: 1.2;
    }}
    .metric-sub {{
        font-size: 12px;
        color: {c_muted};
        margin-top: 6px;
        font-weight: 500;
    }}

    [data-testid="stSidebar"] {{
        background-color: transparent !important;
        padding: 8px !important;
    }}
    [data-testid="stSidebar"] > div:first-child {{
        background: {c_card} !important;
        border-radius: 12px !important;
        padding: 20px 16px !important;
        border: 1px solid {c_border} !important;
        box-shadow: 0 8px 28px rgba(0, 0, 0, {'0.25' if dm else '0.05'}) !important;
    }}

    .stButton > button,
    .stDownloadButton > button,
    div[data-testid="stDownloadButton"] > button {{
        border-radius: 10px !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        border: 1px solid {c_accent} !important;
        background-color: {c_btn_bg} !important;
        color: {c_btn_txt} !important;
        box-shadow: 0 2px 8px rgba(14, 165, 233, {'0.35' if dm else '0.15'}) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }}
    .stButton > button:hover,
    .stDownloadButton > button:hover,
    div[data-testid="stDownloadButton"] > button:hover {{
        background-color: {c_btn_hover} !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(14, 165, 233, 0.45) !important;
        color: {c_btn_txt} !important;
    }}

    .stTextInput input,
    .stNumberInput input,
    .stSelectbox [data-baseweb="select"] {{
        border-radius: 10px !important;
        background-color: {c_card_inner} !important;
        border-color: {c_border} !important;
        color: {c_text} !important;
        font-size: 14px !important;
    }}

    .stDataFrame, [data-testid="stDataEditor"] {{
        border-radius: 10px !important;
        overflow: hidden !important;
        border: 1px solid {c_border} !important;
        background: {c_card} !important;
    }}

    .streamlit-expanderHeader {{
        background: {c_card_inner} !important;
        border-radius: 10px !important;
        color: {c_text} !important;
        border: 1px solid {c_border} !important;
        font-weight: 600 !important;
        padding: 12px 16px !important;
    }}
    .streamlit-expanderContent {{
        background: {c_card} !important;
        border: 1px solid {c_border} !important;
        border-top: none !important;
        border-radius: 0 0 10px 10px !important;
        padding: 16px !important;
    }}

    .badge-pill {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.04em;
    }}
    .badge-in-spec {{
        background: rgba(16, 185, 129, 0.18);
        color: #34D399 !important;
        border: 1px solid rgba(16, 185, 129, 0.35);
    }}
    .badge-out-spec {{
        background: rgba(239, 68, 68, 0.18);
        color: #F87171 !important;
        border: 1px solid rgba(239, 68, 68, 0.35);
    }}
    .badge-accent {{
        background: rgba(14, 165, 233, 0.16);
        color: {c_accent_bright} !important;
        border: 1px solid rgba(14, 165, 233, 0.35);
    }}

    .katex {{ color: {c_text} !important; font-size: 1.05em !important; }}
</style>
"""
render_html(custom_css)


# =====================================================================
# 7. SIDEBAR: THEME TOGGLE & MODUL SELECTION (TETAP 5 MODUL)
# =====================================================================

with st.sidebar:
    dark_mode_choice = st.toggle(
        "🌙 Dark Navy Mode" if st.session_state.dark_mode else "☀️ Clean Light Mode",
        value=st.session_state.dark_mode,
        key="dark_mode_switch",
    )
    if dark_mode_choice != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_mode_choice
        st.rerun()

    render_html(f"""
    <div style="padding: 8px 0 16px 0;">
        <div style="font-size: 18px; font-weight: 800; color: {c_text}; letter-spacing: -0.02em;">
            {get_svg_icon("road", c_accent_bright, 22)} PaveDesign & JMF
        </div>
        <div style="font-size: 12px; font-weight: 600; color: {c_muted}; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 4px;">
            Civil Engineering Suite v5.5
        </div>
    </div>
    """)

    render_html(f"<p style='font-size: 11px; font-weight: 700; text-transform: uppercase; color: {c_muted}; margin-bottom: 8px;'>Pilih Modul Perancangan</p>")
    menu_modul = st.radio(
        "Navigasi Modul",
        options=[
            "Dashboard Lalu Lintas",
            "JMF & Kurva Gradasi",
            "Analisis Marshall",
            "Estimasi RAB & Harga Daerah",
            "Rekap Laporan",
        ],
        index=0,
        label_visibility="collapsed",
    )

    st.divider()

    render_html(f"<div style='font-size: 13px; font-weight: 700; color: {c_text}; margin-bottom: 8px;'>{get_svg_icon('shield-check', c_accent_bright, 16)} Acuan Standar</div>")
    render_html(f"""
    <div style="font-size: 12px; color: {c_muted}; line-height: 1.6;">
    • <b>Bina Marga Pd T-01-2002-B</b><br>
      <i>Perencanaan Tebal Perkerasan Lentur</i><br>
    • <b>Spesifikasi Umum 2018 Rev. 2</b><br>
      <i>Divisi 6 Perkerasan Aspal Panas</i><br>
    • <b>Pedoman AHSP Bina Marga</b><br>
      <i>Analisis Harga Satuan Pekerjaan</i>
    </div>
    """)

    st.divider()
    st.caption(f"Status: **Aktif & Terverifikasi** | Mode: {'Dark Navy (60-30-10)' if dm else 'Clean Light'}")


# =====================================================================
# 8. HEADER UTAMA DASHBOARD
# =====================================================================

render_html(f"""
<div class="dashboard-header">
    <div>
        <div style="font-size: 24px; font-weight: 800; color: {c_text}; letter-spacing: -0.02em;">
            {get_svg_icon("road", c_accent_bright, 26)} PaveDesign & JMF Engineering Dashboard
        </div>
        <div style="font-size: 14px; color: {c_muted}; margin-top: 4px;">
            Sistem Komputasi Perancangan Tebal Perkerasan Jalan, Job Mix Formula Agregat & Anggaran Biaya
        </div>
    </div>
    <div>
        <span class="badge-pill badge-accent">
            {get_svg_icon("shield-check", c_accent_bright, 14)} SPESIFIKASI BINA MARGA 2018
        </span>
    </div>
</div>
""")


# =====================================================================
# 9. HEADER METRIC: 3 KARTU RINGKASAN DI BAGIAN ATAS
# =====================================================================

col_m1, col_m2, col_m3 = st.columns(3)

with col_m1:
    render_html(f"""
    <div class="header-metric-card">
        <div class="metric-label">
            <span>{get_svg_icon("activity", c_accent_bright, 15)} Total CESA</span>
            <span class="badge-pill badge-accent" style="font-size: 11px;">BEBAN RENCANA</span>
        </div>
        <div class="metric-value">{cesal_juta_val:,.3f} <span style="font-size: 14px; font-weight: 600; color: {c_muted};">MESA</span></div>
        <div class="metric-sub">LE Harian: {le_harian_val:,.1f} ESA/hari &bull; Umur: {st.session_state.umur_rencana} Tahun</div>
    </div>
    """)

with col_m2:
    render_html(f"""
    <div class="header-metric-card">
        <div class="metric-label">
            <span>{get_svg_icon("layers", c_accent_bright, 15)} CBR Efektif</span>
            <span class="badge-pill badge-accent" style="font-size: 11px;">SUBGRADE</span>
        </div>
        <div class="metric-value">{st.session_state.cbr:.1f} <span style="font-size: 16px; font-weight: 600; color: {c_muted};">%</span></div>
        <div class="metric-sub">DDT: {ddt_val:.2f} &bull; Klasifikasi: {rekom_global['Kelas Tanah Dasar']}</div>
    </div>
    """)

with col_m3:
    render_html(f"""
    <div class="header-metric-card">
        <div class="metric-label">
            <span>{get_svg_icon("box", c_accent_bright, 15)} Tebal Struktur</span>
            <span class="badge-pill badge-accent" style="font-size: 11px;">TOTAL TEBAL</span>
        </div>
        <div class="metric-value">{rekom_global['Total Tebal Perkerasan [cm]']} <span style="font-size: 16px; font-weight: 600; color: {c_muted};">cm</span></div>
        <div class="metric-sub">AC: {rekom_global['Lapis Permukaan (AC) [cm]']} cm &bull; Base: {rekom_global['Lapis Pondasi Atas (Base) [cm]']} cm &bull; Sub: {rekom_global['Lapis Pondasi Bawah (Sub-Base) [cm]']} cm</div>
    </div>
    """)


# =====================================================================
# 10. MODUL 1: DASHBOARD LALU LINTAS & TEBAL PERKERASAN
# =====================================================================

if menu_modul == "Dashboard Lalu Lintas":
    col_left, col_right = st.columns([1.05, 0.95])

    with col_left:
        render_html(f"""
        <div class="bento-card">
            <h4>{get_svg_icon("sliders", c_accent_bright, 18)} Parameter Perencanaan Lalu Lintas & Tanah Dasar</h4>
            <p style="color: {c_muted}; margin-bottom: 12px;">Pilih preset cepat atau sesuaikan volume lalu lintas harian dan daya dukung tanah.</p>
        </div>
        """)

        # Peningkatan 1: Preset Lalu Lintas Cepat
        st.markdown(f"<p style='font-size: 12px; font-weight: 700; color: {c_muted}; text-transform: uppercase; margin-bottom: 6px;'>Preset Cepat Tipe Jalan:</p>", unsafe_allow_html=True)
        pre1, pre2, pre3 = st.columns(3)
        with pre1:
            if st.button("🚜 Jalan Kabupaten", use_container_width=True):
                st.session_state.lhr_bus = 50
                st.session_state.lhr_truk2 = 120
                st.session_state.lhr_truk3 = 15
                st.session_state.pilihan_jalan = "2 Lajur 2 Arah (DL = 0.5)"
                st.rerun()
        with pre2:
            if st.button("🛣️ Jalan Arteri", use_container_width=True):
                st.session_state.lhr_bus = 350
                st.session_state.lhr_truk2 = 650
                st.session_state.lhr_truk3 = 300
                st.session_state.pilihan_jalan = "4 Lajur 2 Arah (DL = 0.45)"
                st.rerun()
        with pre3:
            if st.button("🏭 Akses Industri", use_container_width=True):
                st.session_state.lhr_bus = 180
                st.session_state.lhr_truk2 = 850
                st.session_state.lhr_truk3 = 950
                st.session_state.pilihan_jalan = "4 Lajur 2 Arah (DL = 0.45)"
                st.rerun()

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.session_state.umur_rencana = st.number_input(
                "Umur Rencana (tahun)", min_value=1, max_value=40,
                value=int(st.session_state.umur_rencana), step=1,
            )
            st.session_state.laju_pertumbuhan = st.number_input(
                "Laju Pertumbuhan Lalu Lintas (%)", min_value=0.0, max_value=15.0,
                value=float(st.session_state.laju_pertumbuhan), step=0.5,
            )
            st.session_state.cbr = st.number_input(
                "Nilai CBR Tanah Dasar (%)", min_value=1.0, max_value=30.0,
                value=float(st.session_state.cbr), step=0.5,
            )
            pilihan_jalan = st.selectbox(
                "Tipe Jalan & Faktor Distribusi Lajur (DL)",
                options=list(tipe_jalan_dict.keys()),
                index=list(tipe_jalan_dict.keys()).index(st.session_state.pilihan_jalan),
            )
            st.session_state.pilihan_jalan = pilihan_jalan
            dl = tipe_jalan_dict[pilihan_jalan]

        with c2:
            st.session_state.lhr_bus = st.number_input(
                "LHR Bus (VDF = 1.2)", min_value=0, max_value=100000,
                value=int(st.session_state.lhr_bus), step=10,
            )
            st.session_state.lhr_truk2 = st.number_input(
                "LHR Truk 2 Sumbu (VDF = 9.2)", min_value=0, max_value=100000,
                value=int(st.session_state.lhr_truk2), step=10,
            )
            st.session_state.lhr_truk3 = st.number_input(
                "LHR Truk 3 Sumbu (VDF = 20.0)", min_value=0, max_value=100000,
                value=int(st.session_state.lhr_truk3), step=10,
            )

        rekom = get_rekomendasi_tebal(cesal_juta_val, st.session_state.cbr)

        with st.expander("📊 Tabel Rincian Rekomendasi Tebal Lapisan"):
            df_rekom = pd.DataFrame([
                {"Lapisan": "Lapis Permukaan (AC / HRS)", "Tebal (cm)": rekom["Lapis Permukaan (AC) [cm]"]},
                {"Lapisan": "Lapis Pondasi Atas (Aggregat Kelas A / CTB)", "Tebal (cm)": rekom["Lapis Pondasi Atas (Base) [cm]"]},
                {"Lapisan": "Lapis Pondasi Bawah (Aggregat Kelas B / Sirtu)", "Tebal (cm)": rekom["Lapis Pondasi Bawah (Sub-Base) [cm]"]},
                {"Lapisan": "TOTAL TEBAL PERKERASAN", "Tebal (cm)": rekom["Total Tebal Perkerasan [cm]"]},
            ])
            st.dataframe(df_rekom, use_container_width=True, hide_index=True)

            # Upgrade Ekspor Excel Profesional Modul 1
            excel_bytes, excel_name, excel_mime = export_professional_excel(
                df=df_rekom,
                sheet_name="Tebal_Perkerasan",
                title="DESAIN TEBAL PERKERASAN LENTUR",
                subtitle=f"CESAL: {cesal_juta_val:,.3f} MESA | CBR: {st.session_state.cbr:.1f}%",
                metadata_dict={
                    "Umur Rencana": f"{st.session_state.umur_rencana} Tahun",
                    "Pertumbuhan Lalu Lintas (i)": f"{st.session_state.laju_pertumbuhan:.1f}% / tahun",
                    "Lintas Ekivalen Harian (LE)": f"{le_harian_val:,.1f} ESA/hari",
                    "Kumulatif Beban Sumbu (CESAL)": f"{cesal_juta_val:,.3f} Juta ESA",
                    "Daya Dukung Tanah (DDT)": f"{ddt_val:.2f}",
                    "Kelas Lalu Lintas / Subgrade": f"{rekom['Kelas Lalu Lintas']} / {rekom['Kelas Tanah Dasar']}",
                }
            )
            st.download_button(
                label="📊 Unduh Rekomendasi Tebal (Excel .xlsx)",
                data=excel_bytes,
                file_name=excel_name,
                mime=excel_mime,
                use_container_width=True,
            )

        with st.expander("📐 Detail Rumus & Dasar Perhitungan"):
            st.markdown("**Standar Rujukan: Manual Desain Perkerasan Jalan Pd T-01-2002-B, Pasal 4**")
            st.markdown("**1. Lintas Ekivalen Harian (LE):**")
            st.latex(r"LE = \sum \left(LHR_i \times VDF_i\right)")
            st.latex(
                rf"LE = ({st.session_state.lhr_bus} \times 1.2) + ({st.session_state.lhr_truk2} \times 9.2) + ({st.session_state.lhr_truk3} \times 20.0) = {le_harian_val:,.1f} \; \text{{ESA/hari}}"
            )
            st.markdown("**2. Faktor Pertumbuhan Kumulatif (R):**")
            st.latex(r"R = \frac{(1+i)^n - 1}{i}")
            i_dec = st.session_state.laju_pertumbuhan / 100.0
            st.latex(
                rf"R = \frac{{(1+{i_dec:.3f})^{{{st.session_state.umur_rencana}}} - 1}}{{{i_dec:.3f}}} = {r_factor_val:,.2f}"
            )
            st.markdown("**3. Kumulatif Beban Sumbu Standar (CESAL):**")
            st.latex(r"CESAL = \frac{LE \times 365 \times R \times DL}{10^6}")
            st.latex(
                rf"CESAL = \frac{{{le_harian_val:,.1f} \times 365 \times {r_factor_val:,.2f} \times {dl}}}{{10^6}} = {cesal_juta_val:,.3f} \; \text{{Juta ESA}}"
            )
            st.markdown("**4. Daya Dukung Tanah Dasar (DDT):**")
            st.latex(r"DDT = 4.3 \log_{10}(CBR) + 1.7")
            st.latex(
                rf"DDT = 4.3 \times \log_{{10}}({st.session_state.cbr:.1f}) + 1.7 = {ddt_val:.2f}"
            )

    with col_right:
        render_html(f"""
        <div class="bento-card">
            <h4>{get_svg_icon("box", c_accent_bright, 18)} Visualisasi 3D Interaktif & Penampang Melintang</h4>
            <p style="color: {c_muted}; margin-bottom: 16px;">Model 3D proporsional lengkap dengan marka as jalan dan parit drainase samping.</p>
        </div>
        """)

        t_permukaan = rekom["Lapis Permukaan (AC) [cm]"]
        t_base = rekom["Lapis Pondasi Atas (Base) [cm]"]
        t_subbase = rekom["Lapis Pondasi Bawah (Sub-Base) [cm]"]

        tab_3d, tab_2d = st.tabs(["🧊 Model 3D Jalan, Marka & Drainase", "📐 Penampang Vertikal 2D"])

        with tab_3d:
            fig_3d = build_pavement_3d(
                t_permukaan=t_permukaan,
                t_base=t_base,
                t_subbase=t_subbase,
                lebar_jalan=st.session_state.lebar_jalan_3d,
                lebar_bahu=st.session_state.lebar_bahu_3d,
                kemiringan_talud=st.session_state.kemiringan_talud_3d,
                is_dark=dm,
            )
            st.plotly_chart(fig_3d, use_container_width=True)

            with st.expander("⚙️ Atur Geometri Jalan & Dimensi Talud 3D"):
                col3d_1, col3d_2, col3d_3 = st.columns(3)
                with col3d_1:
                    st.session_state.lebar_jalan_3d = st.number_input(
                        "Lebar Perkerasan (m)", min_value=3.0, max_value=30.0,
                        value=float(st.session_state.lebar_jalan_3d), step=0.5,
                    )
                with col3d_2:
                    st.session_state.lebar_bahu_3d = st.number_input(
                        "Lebar Bahu Jalan (m)", min_value=0.5, max_value=5.0,
                        value=float(st.session_state.lebar_bahu_3d), step=0.25,
                    )
                with col3d_3:
                    st.session_state.kemiringan_talud_3d = st.number_input(
                        "Kemiringan Talud (V:H)", min_value=0.1, max_value=2.0,
                        value=float(st.session_state.kemiringan_talud_3d), step=0.1,
                        help="0.5 artinya 1 vertikal : 2 horizontal",
                    )

        with tab_2d:
            d1 = t_permukaan
            d2 = d1 + t_base
            d3 = d2 + t_subbase

            fig_2d = go.Figure()
            fig_2d.add_trace(go.Bar(
                x=["Struktur"], y=[t_permukaan], name=f"Surface ({t_permukaan} cm)",
                marker_color="#1E293B", text=[f"AC SURFACE — {t_permukaan} cm"],
                textposition="inside", textfont=dict(size=12, color="white"),
            ))
            fig_2d.add_trace(go.Bar(
                x=["Struktur"], y=[t_base], name=f"Base ({t_base} cm)",
                marker_color="#64748B", text=[f"PONDASI ATAS (KELAS A) — {t_base} cm"],
                textposition="inside", textfont=dict(size=12, color="white"),
            ))
            fig_2d.add_trace(go.Bar(
                x=["Struktur"], y=[t_subbase], name=f"Sub-base ({t_subbase} cm)",
                marker_color="#D97706", text=[f"PONDASI BAWAH (KELAS B) — {t_subbase} cm"],
                textposition="inside", textfont=dict(size=12, color="white"),
            ))
            fig_2d.add_trace(go.Bar(
                x=["Struktur"], y=[25], name=f"Subgrade (CBR {st.session_state.cbr:.1f}%)",
                marker_color="#78350F", text=[f"SUBGRADE (CBR {st.session_state.cbr:.1f}%)"],
                textposition="inside", textfont=dict(size=12, color="white"),
            ))

            fig_2d.update_layout(
                barmode="stack",
                yaxis=dict(
                    autorange="reversed",
                    title="Kedalaman Kumulatif (cm)",
                    tickvals=[0, d1, d2, d3],
                    ticktext=["0 cm", f"{d1} cm", f"{d2} cm", f"{d3} cm"],
                    showgrid=True,
                    gridcolor=c_border,
                    color=c_muted,
                ),
                xaxis=dict(showticklabels=False),
                plot_bgcolor=c_card_inner,
                paper_bgcolor=c_card,
                height=380,
                margin=dict(l=45, r=20, t=10, b=25),
                legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center", font=dict(color=c_muted, size=10)),
            )
            st.plotly_chart(fig_2d, use_container_width=True)


# =====================================================================
# 11. MODUL 2: JMF & KURVA GRADASI AGREGAT
# =====================================================================

elif menu_modul == "JMF & Kurva Gradasi":
    col_left, col_right = st.columns([1.05, 0.95])

    saringan_list = [37.5, 25.4, 19.0, 12.5, 9.5, 4.75, 2.36, 1.18, 0.600, 0.300, 0.150, 0.075]

    spesifikasi_bm = {
        "AC-WC": {
            "Batas Bawah": [100, 100, 100,  90,  72,  43,  28, 19, 13, 9, 6, 4.0],
            "Batas Atas":  [100, 100, 100, 100, 100,  69,  58, 44, 33, 23, 15, 9.0],
            "KAO_Min": 5.5, "KAO_Max": 6.5, "KAO_Target": 5.8
        },
        "AC-BC": {
            "Batas Bawah": [100, 100,  90,  75,  66,  46,  30, 18, 12, 7, 5, 4.0],
            "Batas Atas":  [100, 100, 100, 100, 100,  80,  58, 44, 33, 23, 15, 9.0],
            "KAO_Min": 5.0, "KAO_Max": 6.0, "KAO_Target": 5.3
        },
        "AC-Base": {
            "Batas Bawah": [100,  90,  76,  60,  52,  35,  23, 13,  9, 6, 4, 3.0],
            "Batas Atas":  [100, 100, 100, 100, 100,  71,  49, 36, 26, 18, 12, 8.0],
            "KAO_Min": 4.5, "KAO_Max": 5.5, "KAO_Target": 4.8
        },
        "HRS-WC": {
            "Batas Bawah": [100, 100, 100,  90,  75,  50,  50, 40, 35, 20, 10, 6.0],
            "Batas Atas":  [100, 100, 100, 100,  85,  72,  72, 60, 55, 35, 20, 10.0],
            "KAO_Min": 6.0, "KAO_Max": 7.5, "KAO_Target": 6.8
        },
        "HRS-Base": {
            "Batas Bawah": [100, 100,  90,  75,  65,  35,  35, 25, 20, 15,  8, 4.0],
            "Batas Atas":  [100, 100, 100,  90,  85,  55,  55, 45, 35, 25, 15, 8.0],
            "KAO_Min": 5.5, "KAO_Max": 7.0, "KAO_Target": 6.2
        },
    }

    with col_left:
        render_html(f"""
        <div class="bento-card">
            <h4>{get_svg_icon("flask", c_accent_bright, 18)} Proporsi Agregat & Job Mix Formula</h4>
            <p style="color: {c_muted}; margin-bottom: 16px;">Tentukan proporsi fraksi agregat kasar, halus, dan filler sesuai spesifikasi.</p>
        </div>
        """)

        sel_col1, sel_col2 = st.columns([1, 1.5])
        with sel_col1:
            _all_mix = ["AC-WC", "AC-BC", "AC-Base", "HRS-WC", "HRS-Base"]
            _cur_mix = st.session_state.tipe_campuran if st.session_state.tipe_campuran in _all_mix else "AC-WC"
            st.session_state.tipe_campuran = st.selectbox(
                "Tipe Campuran Aspal",
                options=_all_mix,
                index=_all_mix.index(_cur_mix),
            )
        with sel_col2:
            render_html(f"""
            <div style="background: {c_card_inner}; border: 1px solid {c_border}; padding: 10px 14px; border-radius: 10px; margin-top: 24px;">
                <span style="font-size: 13px; color: {c_muted};">Rujukan Standar: <b>Spesifikasi Bina Marga 2018 Divisi 6</b></span>
            </div>
            """)

        spec = spesifikasi_bm[st.session_state.tipe_campuran]

        # Reset cache editor JMF jika tipe campuran diganti oleh user
        if "jmf_prev_tipe_campuran" not in st.session_state:
            st.session_state.jmf_prev_tipe_campuran = st.session_state.tipe_campuran
        elif st.session_state.jmf_prev_tipe_campuran != st.session_state.tipe_campuran:
            st.session_state.df_jmf_custom = None
            st.session_state.jmf_prev_tipe_campuran = st.session_state.tipe_campuran

        render_html(f"<p style='font-weight: 600; font-size: 14px; margin-top: 12px; color: {c_text};'>Proporsi Fraksi Campuran (%):</p>")
        p1, p2, p3 = st.columns(3)
        with p1:
            st.session_state.prop_kasar = st.number_input("Agregat Kasar (%)", 0.0, 100.0, float(st.session_state.prop_kasar), step=1.0)
        with p2:
            st.session_state.prop_halus = st.number_input("Agregat Halus (%)", 0.0, 100.0, float(st.session_state.prop_halus), step=1.0)
        with p3:
            st.session_state.prop_filler = st.number_input("Filler (%)", 0.0, 100.0, float(st.session_state.prop_filler), step=1.0)

        tot_prop = st.session_state.prop_kasar + st.session_state.prop_halus + st.session_state.prop_filler

        default_kasar, default_halus, default_filler = get_default_aggregate_fractions(st.session_state.tipe_campuran)

        if st.session_state.df_jmf_custom is not None and len(st.session_state.df_jmf_custom) == 12:
            df_input = st.session_state.df_jmf_custom.copy()
            df_input["Batas Bawah"] = spec["Batas Bawah"]
            df_input["Batas Atas"] = spec["Batas Atas"]
            df_input["Batas Tengah"] = np.round((np.array(spec["Batas Bawah"]) + np.array(spec["Batas Atas"])) / 2, 1)
        else:
            df_input = pd.DataFrame({
                "Saringan (mm)": saringan_list,
                "Agregat Kasar": default_kasar,
                "Agregat Halus": default_halus,
                "Filler": default_filler,
                "Batas Bawah": spec["Batas Bawah"],
                "Batas Atas": spec["Batas Atas"],
                "Batas Tengah": np.round((np.array(spec["Batas Bawah"]) + np.array(spec["Batas Atas"])) / 2, 1),
            })

        # Peningkatan 2: Tombol Optimasi Proporsi Otomatis
        if st.button("⚡ Optimasi Proporsi Otomatis (Grid Search)", use_container_width=True):
            opt_k, opt_h, opt_f, out_cnt, mse_val = optimize_jmf_proportions(df_input, spec)
            st.session_state.prop_kasar = float(opt_k)
            st.session_state.prop_halus = float(opt_h)
            st.session_state.prop_filler = float(opt_f)
            status_text = "Semua 12 saringan IN SPEC" if out_cnt == 0 else f"{out_cnt} saringan mendekati batas"
            st.success(f"✅ Proporsi Optimal Ditemukan: Kasar {opt_k}%, Halus {opt_h}%, Filler {opt_f}% ({status_text}, MSE: {mse_val:.2f})")
            st.rerun()

        if not np.isclose(tot_prop, 100.0):
            render_html(f"""
            <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.3); padding: 10px 16px; border-radius: 10px; margin: 12px 0;">
                <span class="badge-pill badge-out-spec">TOTAL PROPORSI: {tot_prop:.1f}%</span>
                <span style="color: #F87171; font-size: 13px; margin-left: 8px; font-weight: 600;">Total proporsi harus tepat bernilai 100%!</span>
            </div>
            """)
            st.stop()
        else:
            render_html(f"""
            <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); padding: 8px 16px; border-radius: 10px; margin: 10px 0;">
                <span class="badge-pill badge-in-spec">TOTAL PROPORSI: {tot_prop:.1f}% MEMENUHI SYARAT</span>
            </div>
            """)

        with st.expander("📋 Editor Nilai Lolos Saringan Agregat"):
            st.caption("Klik sel pada kolom Kasar, Halus, atau Filler untuk mengedit data gradasi:")
            edited_df = st.data_editor(
                df_input,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                disabled=["Saringan (mm)", "Batas Bawah", "Batas Atas", "Batas Tengah"],
                column_config={
                    "Saringan (mm)": st.column_config.NumberColumn(format="%.3g"),
                    "Agregat Kasar": st.column_config.NumberColumn("Kasar (%)", min_value=0.0, max_value=100.0, format="%.1f"),
                    "Agregat Halus": st.column_config.NumberColumn("Halus (%)", min_value=0.0, max_value=100.0, format="%.1f"),
                    "Filler": st.column_config.NumberColumn("Filler (%)", min_value=0.0, max_value=100.0, format="%.1f"),
                    "Batas Bawah": st.column_config.NumberColumn(format="%.1f"),
                    "Batas Atas": st.column_config.NumberColumn(format="%.1f"),
                    "Batas Tengah": st.column_config.NumberColumn(format="%.1f"),
                },
                key=f"jmf_table_editor_{st.session_state.tipe_campuran}",
            )
            # Sinkronisasi Fix 1: simpan hasil edit tabel ke session_state
            st.session_state.df_jmf_custom = edited_df.copy()

        hasil = calc_blending_jmf(
            edited_df, st.session_state.prop_kasar, st.session_state.prop_halus, st.session_state.prop_filler
        )

        with st.expander("🧮 Tabel Rincian Blending & Status Lolos"):
            df_result_display = hasil[["Saringan (mm)", "Blending (%)", "Batas Bawah", "Batas Atas", "Batas Tengah", "Status"]].copy()
            st.dataframe(df_result_display, use_container_width=True, hide_index=True)

            _, _, _, kao_pred_curr = calc_kao_hudson(hasil)
            total_out_cnt = (hasil["Status"] == "❌ OUT").sum()

            excel_jmf_bytes, excel_jmf_name, excel_jmf_mime = export_professional_excel(
                df=df_result_display,
                sheet_name="Blending_JMF",
                title=f"JOB MIX FORMULA AGREGAT — {st.session_state.tipe_campuran}",
                subtitle=f"Kasar {st.session_state.prop_kasar:.0f}% | Halus {st.session_state.prop_halus:.0f}% | Filler {st.session_state.prop_filler:.0f}%",
                metadata_dict={
                    "Tipe Campuran": st.session_state.tipe_campuran,
                    "Proporsi Agregat Kasar": f"{st.session_state.prop_kasar:.1f}%",
                    "Proporsi Agregat Halus": f"{st.session_state.prop_halus:.1f}%",
                    "Proporsi Filler": f"{st.session_state.prop_filler:.1f}%",
                    "KAO Prediktif Hudson": f"{kao_pred_curr:.2f}%",
                    "Status Evaluasi Gradasi": "MEMENUHI SYARAT" if total_out_cnt == 0 else f"{total_out_cnt} SARINGAN DI LUAR BATAS",
                }
            )
            st.download_button(
                label="📊 Unduh Hasil Blending JMF (Excel .xlsx)",
                data=excel_jmf_bytes,
                file_name=excel_jmf_name,
                mime=excel_jmf_mime,
                use_container_width=True,
            )

        with st.expander("📐 Detail Rumus & Referensi JMF"):
            a_c, b_f, c_f, kao_p = calc_kao_hudson(hasil)
            st.markdown("**Standar Rujukan: Spesifikasi Umum Bina Marga 2018 Divisi 6, Pasal 6.3.3**")
            st.markdown("**1. Formula Blending Agregat Gabungan:**")
            st.latex(r"Blend_i = \frac{P_K \cdot K_i + P_H \cdot H_i + P_F \cdot F_i}{100}")
            st.markdown(
                f"Proporsi aktif: $P_K = {st.session_state.prop_kasar:.1f}\\%$, "
                f"$P_H = {st.session_state.prop_halus:.1f}\\%$, "
                f"$P_F = {st.session_state.prop_filler:.1f}\\%$"
            )
            st.markdown("**2. Estimasi KAO Prediktif (Rumus Empiris Hudson/Bina Marga):**")
            st.latex(r"KAO_{pred} = 0.035A + 0.045B + 0.18C + 2.0")
            st.markdown(f"Substitusi nilai: $A = {a_c:.2f}\\%$, $B = {b_f:.2f}\\%$, $C = {c_f:.2f}\\%$")
            st.latex(
                rf"KAO_{{pred}} = 0.035 \times {a_c:.2f} + 0.045 \times {b_f:.2f} + 0.18 \times {c_f:.2f} + 2.0 = {kao_p:.2f}\%"
            )

    with col_right:
        total_ok = (hasil["Status"] == "✅ OK").sum()
        total_out = (hasil["Status"] == "❌ OUT").sum()
        is_in_spec = (total_out == 0)
        _, _, _, kao_prediktif = calc_kao_hudson(hasil)

        render_html(f"""
        <div class="bento-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h4 style="margin: 0;">{get_svg_icon("activity", c_accent_bright, 18)} Status Evaluasi & KAO</h4>
                {f'<span class="badge-pill badge-in-spec">● IN SPEC</span>' if is_in_spec else f'<span class="badge-pill badge-out-spec">● OUT OF SPEC</span>'}
            </div>
            <div class="bento-card-inner">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 13px; color: {c_muted}; font-weight: 600;">Status Gradasi:</span>
                    <span style="font-weight: 700; color: {'#34D399' if is_in_spec else '#F87171'}; font-size: 14px;">
                        {f'Semua {total_ok} Saringan Memenuhi Syarat' if is_in_spec else f'{total_out} Saringan di Luar Batas'}
                    </span>
                </div>
            </div>
            <div class="bento-card-inner">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <span style="font-size: 12px; text-transform: uppercase; font-weight: 700; color: {c_accent_bright};">Indikator KAO Rekomendasi</span>
                    <span class="badge-pill badge-accent">{st.session_state.tipe_campuran}</span>
                </div>
                <div style="font-size: 24px; font-weight: 800; color: {c_text};">
                    {spec['KAO_Target']:.1f}% <span style="font-size: 13px; font-weight: 500; color: {c_muted};">(Spesifikasi: {spec['KAO_Min']}% – {spec['KAO_Max']}%)</span>
                </div>
                <div style="font-size: 13px; color: {c_muted}; margin-top: 4px;">
                    Estimasi Rumus Luas Permukaan Agregat: <b>{kao_prediktif:.2f}%</b>
                </div>
            </div>
        </div>
        """)

        # Peningkatan 3: Tombol Sinkronisasi KAO ke Modul Analisis Marshall
        if st.button("📲 Kirim KAO ke Analisis Marshall", use_container_width=True):
            st.session_state.kadar_aspal_marshall = float(round(kao_prediktif, 1))
            st.success(f"✅ Nilai KAO ({kao_prediktif:.1f}%) berhasil disinkronkan ke Modul Analisis Marshall!")
            st.rerun()

        # Kurva Gradasi Semilog Matplotlib
        saringan_mm = hasil["Saringan (mm)"].values
        fig_jmf, ax_jmf = plt.subplots(figsize=(8, 4.4), facecolor=c_card)
        ax_jmf.set_facecolor(c_card_inner)

        ax_jmf.plot(saringan_mm, hasil["Blending (%)"].values,
                    marker="o", markersize=5, linewidth=2.2, color="#0EA5E9" if dm else "#0284C7", label="Blending (%)", zorder=4)
        ax_jmf.plot(saringan_mm, hasil["Batas Atas"].values,
                    marker="s", markersize=4, linewidth=1.4, linestyle="--", color="#10B981", label="Batas Atas", zorder=3)
        ax_jmf.plot(saringan_mm, hasil["Batas Bawah"].values,
                    marker="s", markersize=4, linewidth=1.4, linestyle="--", color="#EF4444", label="Batas Bawah", zorder=3)
        ax_jmf.plot(saringan_mm, hasil["Batas Tengah"].values,
                    marker="^", markersize=3.5, linewidth=1.0, linestyle=":", color=c_muted, label="Batas Tengah", zorder=2)

        ax_jmf.fill_between(saringan_mm, hasil["Batas Bawah"].values, hasil["Batas Atas"].values,
                            alpha=0.15, color="#10B981", label="Amplop Spesifikasi", zorder=1)

        ax_jmf.set_xscale("log")
        ax_jmf.invert_xaxis()
        ax_jmf.set_xlabel("Ukuran Saringan (mm)", fontsize=9, fontweight="bold", color=c_muted)
        ax_jmf.set_ylabel("Persen Lolos (%)", fontsize=9, fontweight="bold", color=c_muted)
        ax_jmf.set_title(f"Kurva Gradasi Agregat Semilog — {st.session_state.tipe_campuran}", fontsize=11, fontweight="bold", color=c_text, pad=10)
        ax_jmf.set_ylim(0, 105)
        ax_jmf.legend(loc="lower left", fontsize=8, facecolor=c_card, edgecolor=c_border, labelcolor=c_text)
        ax_jmf.grid(True, which="both", linestyle=":", alpha=0.35, color=c_muted)

        for spine in ax_jmf.spines.values():
            spine.set_color(c_border)

        ax_jmf.set_xticks(saringan_mm)
        ax_jmf.set_xticklabels([f"{x:g}" for x in saringan_mm], fontsize=8, rotation=45, color=c_muted)
        ax_jmf.tick_params(colors=c_muted)

        plt.tight_layout()
        st.pyplot(fig_jmf, use_container_width=True)


# =====================================================================
# 12. MODUL 3: ANALISIS MARSHALL
# =====================================================================

elif menu_modul == "Analisis Marshall":
    col_left, col_right = st.columns([1.05, 0.95])

    with col_left:
        render_html(f"""
        <div class="bento-card">
            <h4>{get_svg_icon("flask", c_accent_bright, 18)} Pengujian Marshall Test & Karakteristik Campuran</h4>
            <p style="color: {c_muted}; margin-bottom: 16px;">Input hasil pembacaan arloji stabilitas, flow, dan berat jenis benda uji padat.</p>
        </div>
        """)

        mc1, mc2 = st.columns(2)
        with mc1:
            kadar_aspal = st.number_input(
                "Kadar Aspal Benda Uji (Pb, %)", min_value=3.5, max_value=9.0,
                value=float(st.session_state.kadar_aspal_marshall), step=0.1,
            )
            st.session_state.kadar_aspal_marshall = kadar_aspal
            # Sinkronisasi Fix 1: Stabilitas & Flow ke session_state
            stabilitas = st.number_input(
                "Stabilitas Marshall (kg)", min_value=200.0, max_value=3000.0,
                value=float(st.session_state.marshall_stabilitas), step=25.0,
            )
            st.session_state.marshall_stabilitas = stabilitas
            flow = st.number_input(
                "Kelelehan / Flow (mm)", min_value=1.0, max_value=10.0,
                value=float(st.session_state.marshall_flow), step=0.1,
            )
            st.session_state.marshall_flow = flow

        with mc2:
            gmm = st.number_input(
                "Berat Jenis Maksimum Teoretis (Gmm)", min_value=2.0, max_value=2.8,
                value=float(st.session_state.marshall_gmm), step=0.005, format="%.3f",
            )
            st.session_state.marshall_gmm = gmm
            gmb = st.number_input(
                "Berat Jenis Bulk Benda Uji (Gmb)", min_value=2.0, max_value=2.7,
                value=float(st.session_state.marshall_gmb), step=0.005, format="%.3f",
            )
            st.session_state.marshall_gmb = gmb
            gsb = st.number_input(
                "Berat Jenis Bulk Agregat (Gsb)", min_value=2.0, max_value=3.0,
                value=float(st.session_state.marshall_gsb), step=0.005, format="%.3f",
            )
            st.session_state.marshall_gsb = gsb

        m_res = calc_marshall_volumetrik(kadar_aspal, stabilitas, flow, gmm, gmb, gsb, st.session_state.tipe_campuran)
        sp = m_res["specs"]

        with st.expander("📋 Tabel Karakteristik Volumetrik Marshall"):
            df_marshall = pd.DataFrame([
                {"Parameter": "Stabilitas Marshall", "Hasil Uji": f"{stabilitas:,.1f} kg", "Spesifikasi Bina Marga": sp["stab_label"], "Status": m_res["eval_stab"]},
                {"Parameter": "Kelelehan (Flow)", "Hasil Uji": f"{flow:.2f} mm", "Spesifikasi Bina Marga": sp["flow_label"], "Status": m_res["eval_flow"]},
                {"Parameter": "Marshall Quotient (MQ)", "Hasil Uji": f"{m_res['mq']:,.1f} kg/mm", "Spesifikasi Bina Marga": "Min. 250 kg/mm", "Status": m_res["eval_mq"]},
                {"Parameter": "Rongga dalam Campuran (VIM)", "Hasil Uji": f"{m_res['vim']:.2f} %", "Spesifikasi Bina Marga": sp["vim_label"], "Status": m_res["eval_vim"]},
                {"Parameter": "Rongga dalam Agregat (VMA)", "Hasil Uji": f"{m_res['vma']:.2f} %", "Spesifikasi Bina Marga": sp["vma_label"], "Status": m_res["eval_vma"]},
                {"Parameter": "Rongga Terisi Aspal (VFB)", "Hasil Uji": f"{m_res['vfb']:.2f} %", "Spesifikasi Bina Marga": sp["vfb_label"], "Status": m_res["eval_vfb"]},
            ])
            st.dataframe(df_marshall, use_container_width=True, hide_index=True)

            excel_m_bytes, excel_m_name, excel_m_mime = export_professional_excel(
                df=df_marshall,
                sheet_name="Uji_Marshall",
                title="PENGUJIAN MARSHALL & KARAKTERISTIK VOLUMETRIK",
                subtitle=f"Kadar Aspal Uji (Pb): {kadar_aspal:.1f}% | Campuran: {st.session_state.tipe_campuran}",
                metadata_dict={
                    "Kadar Aspal Uji": f"{kadar_aspal:.1f}%",
                    "Berat Jenis Gmm / Gmb / Gsb": f"{gmm:.3f} / {gmb:.3f} / {gsb:.3f}",
                    "Stabilitas Terukur": f"{stabilitas:,.0f} kg",
                    "Flow Terukur": f"{flow:.1f} mm",
                    "Status Kelayakan": "MEMENUHI SYARAT" if m_res['is_all_ok'] else "BEBERAPA PARAMETER DI LUAR SPESIFIKASI",
                }
            )
            st.download_button(
                label="📊 Unduh Hasil Uji Marshall (Excel .xlsx)",
                data=excel_m_bytes,
                file_name=excel_m_name,
                mime=excel_m_mime,
                use_container_width=True,
            )

        with st.expander("📐 Detail Rumus Volumetrik Marshall"):
            st.markdown("**Standar Rujukan: Spesifikasi Umum Bina Marga 2018 Divisi 6**")
            st.markdown("**1. Rongga dalam Campuran (VIM):**")
            st.latex(r"VIM = \left(1 - \frac{Gmb}{Gmm}\right) \times 100")
            st.latex(rf"VIM = \left(1 - \frac{{{gmb:.3f}}}{{{gmm:.3f}}}\right) \times 100 = {m_res['vim']:.2f}\%")

            st.markdown("**2. Rongga dalam Agregat (VMA):**")
            st.latex(r"VMA = 100 - \frac{Gmb \times (100 - Pb)}{Gsb}")
            st.latex(rf"VMA = 100 - \frac{{{gmb:.3f} \times (100 - {kadar_aspal:.1f})}}{{{gsb:.3f}}} = {m_res['vma']:.2f}\%")

            st.markdown("**3. Rongga Terisi Aspal (VFB):**")
            st.latex(r"VFB = \frac{VMA - VIM}{VMA} \times 100")
            st.latex(rf"VFB = \frac{{{m_res['vma']:.2f} - {m_res['vim']:.2f}}}{{{m_res['vma']:.2f}}} \times 100 = {m_res['vfb']:.2f}\%")

            st.markdown("**4. Marshall Quotient (MQ):**")
            st.latex(r"MQ = \frac{\text{Stabilitas}}{\text{Flow}}")
            st.latex(rf"MQ = \frac{{{stabilitas:.1f}}}{{{flow:.2f}}} = {m_res['mq']:.1f} \; \text{{kg/mm}}")

    with col_right:
        # Peningkatan 4: Tab Evaluasi Kelayakan & Tab Simulasi Grafik KAO
        tab_eval, tab_sim = st.tabs(["⚡ Status & Evaluasi", "📈 Simulasi Grafik KAO"])

        with tab_eval:
            render_html(f"""
            <div class="bento-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h4 style="margin: 0;">{get_svg_icon("activity", c_accent_bright, 18)} Status Kelayakan Campuran</h4>
                    {f'<span class="badge-pill badge-in-spec">● IN SPEC</span>' if m_res['is_all_ok'] else f'<span class="badge-pill badge-out-spec">● OUT OF SPEC</span>'}
                </div>
                <div class="bento-card-inner">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <span style="font-size: 12px; text-transform: uppercase; font-weight: 700; color: {c_accent_bright};">Kadar Aspal Uji (Pb)</span>
                        <span class="badge-pill badge-accent">{st.session_state.tipe_campuran}</span>
                    </div>
                    <div style="font-size: 26px; font-weight: 800; color: {c_text};">
                        {kadar_aspal:.1f}% <span style="font-size: 14px; font-weight: 500; color: {c_muted};">Kadar Aspal Benda Uji</span>
                    </div>
                    <div style="font-size: 13px; color: {c_muted}; margin-top: 4px;">
                        Rentang Standar Spesifikasi: <b>5.5% – 6.5%</b>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px;">
                    <div class="bento-card-inner" style="margin-bottom: 0;">
                        <div style="font-size: 11px; color: {c_muted}; font-weight: 600; text-transform: uppercase;">Stabilitas</div>
                        <div style="font-size: 18px; font-weight: 800; color: {'#10B981' if stabilitas >= 800 else '#EF4444'};">{stabilitas:,.0f} kg</div>
                        <div style="font-size: 11px; color: {c_muted};">Min. 800 kg</div>
                    </div>
                    <div class="bento-card-inner" style="margin-bottom: 0;">
                        <div style="font-size: 11px; color: {c_muted}; font-weight: 600; text-transform: uppercase;">Flow (Kelelehan)</div>
                        <div style="font-size: 18px; font-weight: 800; color: {'#38BDF8' if 2.0 <= flow <= 4.0 else '#EF4444'};">{flow:.1f} mm</div>
                        <div style="font-size: 11px; color: {c_muted};">2.0 – 4.0 mm</div>
                    </div>
                    <div class="bento-card-inner" style="margin-bottom: 0;">
                        <div style="font-size: 11px; color: {c_muted}; font-weight: 600; text-transform: uppercase;">Rongga (VIM)</div>
                        <div style="font-size: 18px; font-weight: 800; color: {'#10B981' if 3.0 <= m_res['vim'] <= 5.0 else '#EF4444'};">{m_res['vim']:.2f}%</div>
                        <div style="font-size: 11px; color: {c_muted};">3.0% – 5.0%</div>
                    </div>
                    <div class="bento-card-inner" style="margin-bottom: 0;">
                        <div style="font-size: 11px; color: {c_muted}; font-weight: 600; text-transform: uppercase;">VFB (Terisi Aspal)</div>
                        <div style="font-size: 18px; font-weight: 800; color: {'#10B981' if m_res['vfb'] >= 65.0 else '#EF4444'};">{m_res['vfb']:.1f}%</div>
                        <div style="font-size: 11px; color: {c_muted};">Min. 65.0%</div>
                    </div>
                </div>
            </div>
            """)

            # Peningkatan 5: Diagnosa Teknis Otomatis & Saran Rekayasa
            if m_res['is_all_ok']:
                render_html(f"""
                <div style="padding: 12px 16px; border-radius: 10px; background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3);">
                    <div style="font-size: 13px; font-weight: 700; color: #10B981;">🎉 CAMPURAN MEMENUHI SYARAT SPESIFIKASI BINA MARGA 2018</div>
                    <div style="font-size: 12px; color: {c_text}; margin-top: 4px;">Kadar aspal {kadar_aspal:.1f}% berada pada rentang mekanik dan volumetrik yang ideal, menjamin daya dukung struktur sekaligus ketahanan terhadap penuaan oksidatif.</div>
                </div>
                """)
            else:
                saran_list = []
                if m_res['eval_vim'] == "❌ OUT":
                    if m_res['vim'] < 3.0:
                        saran_list.append("• <b>VIM Terlalu Rendah (&lt; 3.0%):</b> Risiko <i>bleeding</i> (lelehan aspal ke permukaan) dan alur roda (rutting). Kurangi kadar aspal atau kurangi fraksi filler halus.")
                    else:
                        saran_list.append("• <b>VIM Terlalu Tinggi (&gt; 5.0%):</b> Campuran terlalu porous, risiko penuaan dini dan butir lepas (ravelling). Naikkan kadar aspal atau tambahkan fraksi agregat halus.")
                if m_res['eval_stab'] == "❌ OUT":
                    saran_list.append("• <b>Stabilitas Rendah (&lt; 800 kg):</b> Kurang daya dukung struktural. Periksa mutu batu pecah kasar (bidang pecah min 95/90) atau kurangi aspal jika terjadi lubrikasi berlebih.")
                if m_res['eval_flow'] == "❌ OUT":
                    if flow < 2.0:
                        saran_list.append("• <b>Flow Terlalu Kaku (&lt; 2.0 mm):</b> Campuran getas dan rentan retak fatigue. Tambahkan sedikit aspal atau kurangi kepadatan berlebih.")
                    else:
                        saran_list.append("• <b>Flow Terlalu Plastis (&gt; 4.0 mm):</b> Campuran terlalu lembek. Kurangi kadar aspal.")
                if m_res['eval_vfb'] == "❌ OUT":
                    saran_list.append("• <b>VFB Rendah (&lt; 65%):</b> Selimut aspal pada batuan tipis, kurang kedap air. Naikkan kadar aspal.")

                saran_joined = "<br>".join(saran_list)
                render_html(f"""
                <div style="padding: 14px 16px; border-radius: 10px; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); margin-top: 12px;">
                    <div style="font-size: 13px; font-weight: 700; color: #F87171;">⚠️ DIAGNOSA & SARAN REKAYASA TEKNIK:</div>
                    <div style="font-size: 12px; color: {c_text}; margin-top: 6px; line-height: 1.6;">{saran_joined}</div>
                </div>
                """)

        with tab_sim:
            # Peningkatan 6: Kurva Simulasi KAO (Variasi Pb terhadap VIM, Stabilitas, dan VFB)
            pb_sim = np.linspace(max(3.8, kadar_aspal - 1.2), min(9.0, kadar_aspal + 1.2), 25)

            # Estimasi kurva teoritis Marshall
            gse_est = (100.0 - kadar_aspal) / ((100.0 / gmm) - (kadar_aspal / 1.02))
            gmm_sim = 100.0 / (((100.0 - pb_sim) / gse_est) + (pb_sim / 1.02))
            gmb_sim = gmb - 0.08 * ((pb_sim - kadar_aspal) ** 2)
            vim_sim = (1.0 - (gmb_sim / gmm_sim)) * 100.0
            vma_sim = 100.0 - ((gmb_sim * (100.0 - pb_sim)) / gsb)
            vfb_sim = np.clip(((vma_sim - vim_sim) / vma_sim) * 100.0, 0, 100)
            stab_sim = stabilitas * (1.0 - 0.28 * (((pb_sim - kadar_aspal) / 1.0) ** 2))

            # Label batas spesifikasi dinamis
            vim_label_sim = f"Batas Syarat ({sp['vim_min']:.1f}% – {sp['vim_max']:.1f}%)"
            stab_label_sim = sp["stab_label"]
            vfb_label_sim = sp["vfb_label"]

            fig_sim, (ax_v, ax_s, ax_f) = plt.subplots(3, 1, figsize=(7, 7.5), sharex=True, facecolor=c_card)
            for ax_ in (ax_v, ax_s, ax_f):
                ax_.set_facecolor(c_card_inner)
                for spine in ax_.spines.values():
                    spine.set_color(c_border)
                ax_.tick_params(colors=c_muted, labelsize=8)
                ax_.grid(True, linestyle=":", alpha=0.35, color=c_muted)

            # 1. VIM vs Pb
            ax_v.plot(pb_sim, vim_sim, color="#0EA5E9", linewidth=2.0, label="VIM (%)")
            ax_v.axhspan(sp["vim_min"], sp["vim_max"], color="#10B981", alpha=0.18, label=vim_label_sim)
            ax_v.axvline(kadar_aspal, color="#F59E0B", linestyle="--", linewidth=1.2, label=f"Pb Uji: {kadar_aspal:.1f}%")
            ax_v.set_ylabel("VIM (%)", color=c_muted, fontsize=8, fontweight="bold")
            ax_v.set_title(f"Simulasi KAO — {st.session_state.tipe_campuran} (Variasi Kadar Aspal Pb)", fontsize=10, fontweight="bold", color=c_text, pad=8)
            ax_v.legend(loc="upper right", fontsize=7, facecolor=c_card, edgecolor=c_border, labelcolor=c_text)

            # 2. Stabilitas vs Pb
            ax_s.plot(pb_sim, stab_sim, color="#34D399", linewidth=2.0, label="Stabilitas (kg)")
            ax_s.axhline(sp["stab_min"], color="#EF4444", linestyle=":", linewidth=1.5, label=stab_label_sim)
            ax_s.axvline(kadar_aspal, color="#F59E0B", linestyle="--", linewidth=1.2)
            ax_s.set_ylabel("Stabilitas (kg)", color=c_muted, fontsize=8, fontweight="bold")
            ax_s.legend(loc="lower right", fontsize=7, facecolor=c_card, edgecolor=c_border, labelcolor=c_text)

            # 3. VFB vs Pb
            ax_f.plot(pb_sim, vfb_sim, color="#F59E0B", linewidth=2.0, label="VFB (%)")
            ax_f.axhline(sp["vfb_min"], color="#EF4444", linestyle=":", linewidth=1.5, label=vfb_label_sim)
            ax_f.axvline(kadar_aspal, color="#F59E0B", linestyle="--", linewidth=1.2)
            ax_f.set_xlabel("Kadar Aspal Benda Uji (Pb, %)", color=c_muted, fontsize=9, fontweight="bold")
            ax_f.set_ylabel("VFB (%)", color=c_muted, fontsize=8, fontweight="bold")
            ax_f.legend(loc="lower right", fontsize=7, facecolor=c_card, edgecolor=c_border, labelcolor=c_text)

            plt.tight_layout()
            st.pyplot(fig_sim, use_container_width=True)


# =====================================================================
# 13. MODUL 4: ESTIMASI RAB & ACUAN HARGA SATUAN DAERAH
# =====================================================================

elif menu_modul == "Estimasi RAB & Harga Daerah":
    col_left, col_right = st.columns([1.05, 0.95])

    harga_wilayah_preset = {
        "Jawa Tengah & DIY":         {"ac_ton": 1_850_000, "base_m3": 360_000, "subbase_m3": 230_000, "galian_m3": 45_000},
        "DKI Jakarta & Jawa Barat":  {"ac_ton": 2_150_000, "base_m3": 430_000, "subbase_m3": 310_000, "galian_m3": 70_000},
        "Jawa Timur":                {"ac_ton": 1_800_000, "base_m3": 340_000, "subbase_m3": 220_000, "galian_m3": 42_000},
        "Luar Jawa":                 {"ac_ton": 2_300_000, "base_m3": 490_000, "subbase_m3": 360_000, "galian_m3": 80_000},
        "Input Harga Satuan Lokal / Manual": {"ac_ton": 1_850_000, "base_m3": 360_000, "subbase_m3": 230_000, "galian_m3": 45_000},
    }

    with col_left:
        render_html(f"""
        <div class="bento-card">
            <h4>{get_svg_icon("dollar", c_accent_bright, 18)} Parameter Biaya & Dimensi Proyek</h4>
            <p style="color: {c_muted}; margin-bottom: 16px;">Pilih acuan wilayah AHSP dan tentukan panjang serta lebar rencana perkerasan jalan.</p>
        </div>
        """)

        st.session_state.rab_wilayah = st.selectbox(
            "Acuan Wilayah Harga Satuan",
            options=list(harga_wilayah_preset.keys()),
            index=list(harga_wilayah_preset.keys()).index(st.session_state.rab_wilayah),
        )

        preset = harga_wilayah_preset[st.session_state.rab_wilayah]
        is_manual = (st.session_state.rab_wilayah == "Input Harga Satuan Lokal / Manual")

        if is_manual:
            render_html(f"<p style='font-size: 13px; font-weight: 600; color: {c_text}; margin-top: 12px;'>Input Harga Satuan Pekerjaan Pokok:</p>")
            hr1, hr2 = st.columns(2)
            with hr1:
                st.session_state.rab_harga_ac = st.number_input(
                    "Campuran Aspal AC (Rp/ton)", min_value=500_000, max_value=8_000_000,
                    value=int(st.session_state.rab_harga_ac), step=50_000,
                )
                st.session_state.rab_harga_base = st.number_input(
                    "Agregat Kelas A (Rp/m³)", min_value=100_000, max_value=2_000_000,
                    value=int(st.session_state.rab_harga_base), step=10_000,
                )
            with hr2:
                st.session_state.rab_harga_subbase = st.number_input(
                    "Agregat Kelas B (Rp/m³)", min_value=100_000, max_value=2_000_000,
                    value=int(st.session_state.rab_harga_subbase), step=10_000,
                )
                st.session_state.rab_harga_galian = st.number_input(
                    "Galian Tanah Biasa (Rp/m³)", min_value=10_000, max_value=500_000,
                    value=int(st.session_state.rab_harga_galian), step=5_000,
                )
            h_ac = st.session_state.rab_harga_ac
            h_base = st.session_state.rab_harga_base
            h_subbase = st.session_state.rab_harga_subbase
            h_galian = st.session_state.rab_harga_galian
        else:
            h_ac = preset["ac_ton"]
            h_base = preset["base_m3"]
            h_subbase = preset["subbase_m3"]
            h_galian = preset["galian_m3"]

            render_html(f"""
            <div class="bento-card-inner" style="margin-top: 12px;">
                <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
                    <tr><td style="color: {c_muted}; padding: 4px 0;">Campuran Aspal AC</td><td style="color: {c_text}; font-weight: 700; text-align: right;">Rp {h_ac:,.0f} / Ton</td></tr>
                    <tr><td style="color: {c_muted}; padding: 4px 0;">Agregat Kelas A (Base)</td><td style="color: {c_text}; font-weight: 700; text-align: right;">Rp {h_base:,.0f} / m³</td></tr>
                    <tr><td style="color: {c_muted}; padding: 4px 0;">Agregat Kelas B (Sub-base)</td><td style="color: {c_text}; font-weight: 700; text-align: right;">Rp {h_subbase:,.0f} / m³</td></tr>
                    <tr><td style="color: {c_muted}; padding: 4px 0;">Galian Tanah Biasa</td><td style="color: {c_text}; font-weight: 700; text-align: right;">Rp {h_galian:,.0f} / m³</td></tr>
                </table>
            </div>
            """)

        # Peningkatan 7: Toggle Sertakan PPN 11%
        st.session_state.rab_include_ppn = st.toggle(
            "Sertakan PPN 11% (Pajak Pertambahan Nilai Konstruksi)",
            value=bool(st.session_state.rab_include_ppn),
        )

        render_html(f"<p style='font-size: 14px; font-weight: 600; color: {c_text}; margin-top: 16px;'>Dimensi Geometri Perkerasan:</p>")
        col_dim1, col_dim2 = st.columns(2)
        with col_dim1:
            st.session_state.rab_panjang = st.number_input(
                "Panjang Efektif Jalan (m)", min_value=10.0, max_value=100_000.0,
                value=float(st.session_state.rab_panjang), step=100.0,
            )
        with col_dim2:
            st.session_state.rab_lebar = st.number_input(
                "Lebar Lajur Perkerasan (m)", min_value=2.0, max_value=40.0,
                value=float(st.session_state.rab_lebar), step=0.5,
            )

        t_ac = float(rekom_global["Lapis Permukaan (AC) [cm]"])
        t_base = float(rekom_global["Lapis Pondasi Atas (Base) [cm]"])
        t_subbase = float(rekom_global["Lapis Pondasi Bawah (Sub-Base) [cm]"])

        df_rab, grand_total_rab, v_dict = calc_rab_pekerjaan(
            panjang_m=st.session_state.rab_panjang,
            lebar_m=st.session_state.rab_lebar,
            t_ac_cm=t_ac,
            t_base_cm=t_base,
            t_subbase_cm=t_subbase,
            harga_ac_ton=h_ac,
            harga_base_m3=h_base,
            harga_subbase_m3=h_subbase,
            harga_galian_m3=h_galian,
            include_ppn=st.session_state.rab_include_ppn,
        )

        with st.expander("📐 Dasar Perhitungan Volume & Koefisien AHSP"):
            st.markdown(textwrap.dedent(f"""
            - **Volume Aspal AC:** `{st.session_state.rab_panjang:,.0f} m × {st.session_state.rab_lebar:.1f} m × ({t_ac:.0f}/100) m = {v_dict['vol_ac_m3']:,.2f} m³`
            - **Konversi Tonase AC (@ 2.30 ton/m³):** `{v_dict['vol_ac_m3']:,.2f} m³ × 2.30 = {v_dict['ton_ac']:,.2f} Ton`
            - **Volume Agregat A:** `{st.session_state.rab_panjang:,.0f} m × {st.session_state.rab_lebar:.1f} m × ({t_base:.0f}/100) m = {v_dict['vol_base_m3']:,.2f} m³`
            - **Volume Agregat B:** `{st.session_state.rab_panjang:,.0f} m × {st.session_state.rab_lebar:.1f} m × ({t_subbase:.0f}/100) m = {v_dict['vol_subbase_m3']:,.2f} m³`
            - **Volume Galian Tanah (Faktor Gembur 1.3x):** `Panjang × Lebar × Total Tebal × 1.3 = {v_dict['vol_galian_m3']:,.2f} m³`
            """).strip())

    with col_right:
        render_html(f"""
        <div class="bento-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h4 style="margin: 0;">{get_svg_icon("dollar", c_accent_bright, 18)} Rincian Rencana Anggaran Biaya</h4>
                <span class="badge-pill badge-accent">{st.session_state.rab_wilayah.split('&')[0].strip()}</span>
            </div>
            <div class="bento-card-inner" style="text-align: center; padding: 20px;">
                <div style="font-size: 12px; color: {c_muted}; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">ESTIMASI TOTAL ANGGARAN BIAYA {'(+ PPN 11%)' if st.session_state.rab_include_ppn else ''}</div>
                <div style="font-size: 30px; font-weight: 800; color: {c_accent_bright}; margin: 6px 0;">Rp {grand_total_rab:,.0f}</div>
                <div style="font-size: 12px; color: {c_muted};">
                    Panjang: {st.session_state.rab_panjang:,.0f} m &bull; Lebar: {st.session_state.rab_lebar:.1f} m &bull; Tebal Total: {rekom_global['Total Tebal Perkerasan [cm]']} cm
                </div>
            </div>
        </div>
        """)

        # Peningkatan 8: Diagram Donat Distribusi Biaya
        labels_donut = ["Aspal AC", "Base Kelas A", "Sub-base Kelas B", "Galian Tanah"]
        values_donut = [v_dict["biaya_ac"], v_dict["biaya_base"], v_dict["biaya_subbase"], v_dict["biaya_galian"]]
        colors_donut = ["#0EA5E9", "#38BDF8", "#F59E0B", "#78350F"]

        fig_donut = go.Figure(data=[go.Pie(
            labels=labels_donut,
            values=values_donut,
            hole=0.55,
            marker=dict(colors=colors_donut, line=dict(color=c_border, width=1)),
            textinfo="label+percent",
            hoverinfo="label+value+percent",
            hovertemplate="<b>%{label}</b><br>Biaya: Rp %{value:,.0f}<br>Porsi: %{percent}<extra></extra>",
        )])
        fig_donut.update_layout(
            title=dict(text="Distribusi Anggaran Biaya Pekerjaan Pokok", font=dict(size=12, color=c_text)),
            showlegend=False,
            height=260,
            margin=dict(l=10, r=10, t=35, b=10),
            paper_bgcolor=c_card,
            plot_bgcolor=c_card_inner,
            font=dict(color=c_text, size=10),
        )
        st.plotly_chart(fig_donut, use_container_width=True)

        st.dataframe(
            df_rab,
            use_container_width=True,
            hide_index=True,
            column_config={
                "No": st.column_config.TextColumn("No"),
                "Volume": st.column_config.TextColumn("Volume"),
                "Harga Satuan (Rp)": st.column_config.TextColumn("Harga Satuan (Rp)"),
                "Total Biaya (Rp)": st.column_config.NumberColumn(format="%d"),
            },
        )

        excel_rab_bytes, excel_rab_name, excel_rab_mime = export_professional_excel(
            df=df_rab,
            sheet_name="Estimasi_RAB",
            title="RENCANA ANGGARAN BIAYA (RAB) PEKERJAAN PERKERASAN",
            subtitle=f"Wilayah: {st.session_state.rab_wilayah} | Panjang: {st.session_state.rab_panjang:,.0f} m",
            metadata_dict={
                "Acuan Wilayah AHSP": st.session_state.rab_wilayah,
                "Dimensi Jalan": f"Panjang {st.session_state.rab_panjang:,.0f} m × Lebar {st.session_state.rab_lebar:.1f} m",
                "Subtotal Pekerjaan Pokok": f"Rp {v_dict['subtotal_pokok']:,.0f}",
                "PPN 11%": f"Rp {v_dict['ppn_val']:,.0f}" if st.session_state.rab_include_ppn else "Tidak Termasuk",
                "Total Biaya Rencana": f"Rp {grand_total_rab:,.0f}",
            }
        )
        st.download_button(
            label="📊 Unduh Rincian RAB Proyek (Excel .xlsx)",
            data=excel_rab_bytes,
            file_name=excel_rab_name,
            mime=excel_rab_mime,
            use_container_width=True,
        )


# =====================================================================
# 14. MODUL 5: REKAP LAPORAN LENGKAP & EKSPOR MULTI-SHEET / CETAK HTML
# =====================================================================

elif menu_modul == "Rekap Laporan":
    col_left, col_right = st.columns([1.05, 0.95])

    rekom = get_rekomendasi_tebal(cesal_juta_val, st.session_state.cbr)

    # Data pendukung dari modul-modul lain
    t_ac_val = float(rekom["Lapis Permukaan (AC) [cm]"])
    t_base_val = float(rekom["Lapis Pondasi Atas (Base) [cm]"])
    t_sub_val = float(rekom["Lapis Pondasi Bawah (Sub-Base) [cm]"])

    preset_rab = {
        "Jawa Tengah & DIY":         {"ac_ton": 1_850_000, "base_m3": 360_000, "subbase_m3": 230_000, "galian_m3": 45_000},
        "DKI Jakarta & Jawa Barat":  {"ac_ton": 2_150_000, "base_m3": 430_000, "subbase_m3": 310_000, "galian_m3": 70_000},
        "Jawa Timur":                {"ac_ton": 1_800_000, "base_m3": 340_000, "subbase_m3": 220_000, "galian_m3": 42_000},
        "Luar Jawa":                 {"ac_ton": 2_300_000, "base_m3": 490_000, "subbase_m3": 360_000, "galian_m3": 80_000},
        "Input Harga Satuan Lokal / Manual": {"ac_ton": st.session_state.rab_harga_ac, "base_m3": st.session_state.rab_harga_base, "subbase_m3": st.session_state.rab_harga_subbase, "galian_m3": st.session_state.rab_harga_galian},
    }
    cur_p = preset_rab.get(st.session_state.rab_wilayah, preset_rab["Jawa Tengah & DIY"])

    df_rab_all, total_rab_all, v_dict_all = calc_rab_pekerjaan(
        panjang_m=st.session_state.rab_panjang,
        lebar_m=st.session_state.rab_lebar,
        t_ac_cm=t_ac_val,
        t_base_cm=t_base_val,
        t_subbase_cm=t_sub_val,
        harga_ac_ton=cur_p["ac_ton"],
        harga_base_m3=cur_p["base_m3"],
        harga_subbase_m3=cur_p["subbase_m3"],
        harga_galian_m3=cur_p["galian_m3"],
        include_ppn=st.session_state.rab_include_ppn,
    )

    # Hitung JMF dan KAO
    saringan_list_5 = [37.5, 25.4, 19.0, 12.5, 9.5, 4.75, 2.36, 1.18, 0.600, 0.300, 0.150, 0.075]
    default_kasar_5  = [100, 100, 100,  95,  80,  10,   5,   3,   2,   2,   1, 0.8]
    default_halus_5  = [100, 100, 100, 100, 100,  95,  85,  70,  48,  30,  18, 10.0]
    default_filler_5 = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100,  98, 90.0]
    spec_5_map = {
        "AC-WC":    {"Batas Bawah": [100, 100, 100, 90, 72, 43, 28, 19, 13, 9, 6, 4.0],  "Batas Atas": [100, 100, 100, 100, 100, 69, 58, 44, 33, 23, 15, 9.0]},
        "AC-BC":    {"Batas Bawah": [100, 100, 90, 75, 66, 46, 30, 18, 12, 7, 5, 4.0],   "Batas Atas": [100, 100, 100, 100, 100, 80, 58, 44, 33, 23, 15, 9.0]},
        "AC-Base":  {"Batas Bawah": [100, 90, 76, 60, 52, 35, 23, 13, 9, 6, 4, 3.0],    "Batas Atas": [100, 100, 100, 100, 100, 71, 49, 36, 26, 18, 12, 8.0]},
        "HRS-WC":   {"Batas Bawah": [100, 100, 100, 90, 75, 50, 50, 40, 35, 20, 10, 6.0], "Batas Atas": [100, 100, 100, 100, 85, 72, 72, 60, 55, 35, 20, 10.0]},
        "HRS-Base": {"Batas Bawah": [100, 100, 90, 75, 65, 35, 35, 25, 20, 15, 8, 4.0],  "Batas Atas": [100, 100, 100, 90, 85, 55, 55, 45, 35, 25, 15, 8.0]},
    }
    spec_5 = spec_5_map.get(st.session_state.tipe_campuran, {"Batas Bawah": [100]*12, "Batas Atas": [100]*12})

    # Gunakan tabel JMF yang diedit user (session_state.df_jmf_custom) jika ada, fallback ke default
    _jmf_src = st.session_state.df_jmf_custom
    if _jmf_src is not None and len(_jmf_src) == 12:
        df_jmf_base = _jmf_src.copy()
        df_jmf_base["Batas Bawah"] = spec_5["Batas Bawah"]
        df_jmf_base["Batas Atas"] = spec_5["Batas Atas"]
    else:
        df_jmf_base = pd.DataFrame({
            "Saringan (mm)": saringan_list_5,
            "Agregat Kasar": default_kasar_5,
            "Agregat Halus": default_halus_5,
            "Filler": default_filler_5,
            "Batas Bawah": spec_5["Batas Bawah"],
            "Batas Atas": spec_5["Batas Atas"],
        })
    df_jmf_res = calc_blending_jmf(df_jmf_base, st.session_state.prop_kasar, st.session_state.prop_halus, st.session_state.prop_filler)
    _, _, _, kao_pred_5 = calc_kao_hudson(df_jmf_res)

    # Sinkronisasi Fix 1: gunakan nilai aktual dari session_state Marshall
    _stab_m5 = float(st.session_state.marshall_stabilitas)
    _flow_m5  = float(st.session_state.marshall_flow)
    _gmm_m5   = float(st.session_state.marshall_gmm)
    _gmb_m5   = float(st.session_state.marshall_gmb)
    _gsb_m5   = float(st.session_state.marshall_gsb)
    m_res_all = calc_marshall_volumetrik(
        st.session_state.kadar_aspal_marshall, _stab_m5, _flow_m5, _gmm_m5, _gmb_m5, _gsb_m5,
        st.session_state.tipe_campuran,
    )
    sp5 = m_res_all["specs"]

    # Status kelayakan gabungan JMF + Marshall
    _jmf_out_cnt = int((df_jmf_res["Status"] == "❌ OUT").sum())
    _all_ok_rekap = m_res_all["is_all_ok"] and (_jmf_out_cnt == 0)

    with col_left:
        # Peningkatan 9: Tabel Ringkasan Eksekutif Terintegrasi Menyeluruh
        render_html(f"""
        <div class="bento-card">
            <h4>{get_svg_icon("file-text", c_accent_bright, 18)} Ringkasan Eksekutif Desain Perkerasan & JMF</h4>
            <p style="color: {c_muted}; margin-bottom: 16px;">Kompilasi menyeluruh parameter teknis perencanaan lalu lintas, struktur tebal, JMF, Marshall, dan biaya.</p>
            <div class="bento-card-inner">
                <table style="width: 100%; font-size: 13.5px; border-collapse: collapse; line-height: 1.9;">
                    <tr><td style="color: {c_muted};">Umur Rencana (<i>n</i>)</td><td style="color: {c_text}; font-weight: 700; text-align: right;">{st.session_state.umur_rencana} Tahun</td></tr>
                    <tr><td style="color: {c_muted};">Pertumbuhan Lalu Lintas (<i>i</i>)</td><td style="color: {c_text}; font-weight: 700; text-align: right;">{st.session_state.laju_pertumbuhan:.1f}% / tahun</td></tr>
                    <tr><td style="color: {c_muted};">CBR Efektif Tanah Dasar</td><td style="color: {c_text}; font-weight: 700; text-align: right;">{st.session_state.cbr:.1f}% (DDT = {ddt_val:.2f})</td></tr>
                    <tr><td style="color: {c_muted};">Beban Sumbu Kumulatif (CESAL)</td><td style="color: {c_text}; font-weight: 700; text-align: right;">{cesal_juta_val:,.3f} MESA ({rekom['Kelas Lalu Lintas']})</td></tr>
                    <tr style="border-top: 1px solid {c_border};"><td style="color: {c_muted};">Lapis Permukaan AC</td><td style="color: {c_accent_bright}; font-weight: 700; text-align: right;">{rekom['Lapis Permukaan (AC) [cm]']} cm</td></tr>
                    <tr><td style="color: {c_muted};">Lapis Pondasi Atas Kelas A</td><td style="color: {c_accent_bright}; font-weight: 700; text-align: right;">{rekom['Lapis Pondasi Atas (Base) [cm]']} cm</td></tr>
                    <tr><td style="color: {c_muted};">Lapis Pondasi Bawah Kelas B</td><td style="color: {c_accent_bright}; font-weight: 700; text-align: right;">{rekom['Lapis Pondasi Bawah (Sub-Base) [cm]']} cm</td></tr>
                    <tr style="border-top: 1px solid {c_border};"><td style="color: {c_text}; font-weight: 700;">TOTAL STRUKTUR PERKERASAN</td><td style="color: {c_text}; font-weight: 800; text-align: right;">{rekom['Total Tebal Perkerasan [cm]']} cm</td></tr>
                    <tr><td style="color: {c_muted};">Tipe Campuran Aspal</td><td style="color: {c_text}; font-weight: 700; text-align: right;">{st.session_state.tipe_campuran}</td></tr>
                    <tr><td style="color: {c_muted};">Proporsi Agregat JMF</td><td style="color: {c_text}; font-weight: 600; text-align: right;">K:{st.session_state.prop_kasar:.0f}% | H:{st.session_state.prop_halus:.0f}% | F:{st.session_state.prop_filler:.0f}%</td></tr>
                    <tr><td style="color: {c_muted};">Stabilitas & Flow Marshall</td><td style="color: {c_text}; font-weight: 700; text-align: right;">1,180 kg &bull; 3.2 mm</td></tr>
                    <tr><td style="color: {c_muted};">Rongga Campuran (VIM / VFB)</td><td style="color: {c_text}; font-weight: 700; text-align: right;">{m_res_all['vim']:.2f}% &bull; {m_res_all['vfb']:.1f}%</td></tr>
                    <tr style="border-top: 1px solid {c_border};"><td style="color: {c_muted};">Panjang / Lebar Efektif</td><td style="color: {c_text}; font-weight: 700; text-align: right;">{st.session_state.rab_panjang:,.0f} m &bull; {st.session_state.rab_lebar:.1f} m</td></tr>
                    <tr><td style="color: {c_text}; font-weight: 700;">TOTAL ESTIMASI RAB</td><td style="color: {c_accent_bright}; font-weight: 800; text-align: right;">Rp {total_rab_all:,.0f}</td></tr>
                </table>
            </div>
        </div>
        """)

        # Peningkatan 10: Dua Tombol Ekspor Berdampingan
        c_exp1, c_exp2 = st.columns(2)

        # 1. Multi-Sheet Excel Workbook
        sheets_rekap = {
            "Ringkasan_Eksekutif": pd.DataFrame([
                {"Komponen Desain": "CESAL Beban Lalu Lintas (Juta ESA)", "Nilai / Spesifikasi": f"{cesal_juta_val:,.3f}"},
                {"Komponen Desain": "CBR Tanah Dasar (%)", "Nilai / Spesifikasi": f"{st.session_state.cbr:.1f}"},
                {"Komponen Desain": "Daya Dukung Tanah Dasar (DDT)", "Nilai / Spesifikasi": f"{ddt_val:.2f}"},
                {"Komponen Desain": "Lapis Permukaan AC (cm)", "Nilai / Spesifikasi": f"{rekom['Lapis Permukaan (AC) [cm]']}"},
                {"Komponen Desain": "Lapis Pondasi Atas Base A (cm)", "Nilai / Spesifikasi": f"{rekom['Lapis Pondasi Atas (Base) [cm]']}"},
                {"Komponen Desain": "Lapis Pondasi Bawah Sub-Base B (cm)", "Nilai / Spesifikasi": f"{rekom['Lapis Pondasi Bawah (Sub-Base) [cm]']}"},
                {"Komponen Desain": "Total Tebal Perkerasan (cm)", "Nilai / Spesifikasi": f"{rekom['Total Tebal Perkerasan [cm]']}"},
                {"Komponen Desain": "Tipe Campuran Aspal", "Nilai / Spesifikasi": st.session_state.tipe_campuran},
                {"Komponen Desain": "Kadar Aspal Uji Marshall", "Nilai / Spesifikasi": f"{st.session_state.kadar_aspal_marshall:.1f}%"},
                {"Komponen Desain": "Total Estimasi Anggaran RAB", "Nilai / Spesifikasi": f"Rp {total_rab_all:,.0f}"},
            ]),
            "Struktur_Perkerasan": pd.DataFrame([
                {"Lapisan": "Lapis Permukaan (AC)", "Tebal (cm)": rekom["Lapis Permukaan (AC) [cm]"]},
                {"Lapisan": "Lapis Pondasi Atas (Base A)", "Tebal (cm)": rekom["Lapis Pondasi Atas (Base) [cm]"]},
                {"Lapisan": "Lapis Pondasi Bawah (Sub-base B)", "Tebal (cm)": rekom["Lapis Pondasi Bawah (Sub-Base) [cm]"]},
                {"Lapisan": "TOTAL STRUKTUR PERKERASAN", "Tebal (cm)": rekom["Total Tebal Perkerasan [cm]"]},
            ]),
            "Blending_JMF": df_jmf_res[["Saringan (mm)", "Blending (%)", "Batas Bawah", "Batas Atas", "Status"]],
            "Uji_Marshall": pd.DataFrame([
                {"Parameter": "Stabilitas Marshall", "Hasil": "1180 kg", "Standar": "Min. 800 kg", "Status": m_res_all["eval_stab"]},
                {"Parameter": "Flow (Kelelehan)", "Hasil": "3.2 mm", "Standar": "2.0 – 4.0 mm", "Status": m_res_all["eval_flow"]},
                {"Parameter": "Rongga VIM", "Hasil": f"{m_res_all['vim']:.2f}%", "Standar": "3.0% – 5.0%", "Status": m_res_all["eval_vim"]},
                {"Parameter": "Rongga VFB", "Hasil": f"{m_res_all['vfb']:.1f}%", "Standar": "Min. 65%", "Status": m_res_all["eval_vfb"]},
            ]),
            "Rincian_RAB": df_rab_all,
        }

        excel_multi_bytes, excel_multi_name, excel_multi_mime = export_multisheet_excel(
            sheets_dict=sheets_rekap,
            title="REKAPITULASI LENGKAP PERENCANAAN TEKNIK JALAN",
        )

        with c_exp1:
            st.download_button(
                label="📊 Unduh Rekap Lengkap (Excel .xlsx)",
                data=excel_multi_bytes,
                file_name=excel_multi_name,
                mime=excel_multi_mime,
                use_container_width=True,
            )

        # 2. Laporan HTML Siap Cetak (A4 / PDF)
        html_report_str = generate_html_report(
            rekom=rekom,
            cesal_juta=cesal_juta_val,
            le_harian=le_harian_val,
            cbr=st.session_state.cbr,
            ddt=ddt_val,
            umur_rencana=st.session_state.umur_rencana,
            laju_pertumbuhan=st.session_state.laju_pertumbuhan,
            tipe_campuran=st.session_state.tipe_campuran,
            prop_kasar=st.session_state.prop_kasar,
            prop_halus=st.session_state.prop_halus,
            prop_filler=st.session_state.prop_filler,
            kao_prediktif=kao_pred_5,
            m_res=m_res_all,
            kadar_aspal_m=st.session_state.kadar_aspal_marshall,
            stabilitas_m=1180.0,
            flow_m=3.2,
            rab_wilayah=st.session_state.rab_wilayah,
            rab_panjang=st.session_state.rab_panjang,
            rab_lebar=st.session_state.rab_lebar,
            df_rab=df_rab_all,
            grand_total_rab=total_rab_all,
            include_ppn=st.session_state.rab_include_ppn,
        )

        with c_exp2:
            st.download_button(
                label="🖨️ Unduh Laporan Siap Cetak (HTML / PDF)",
                data=html_report_str.encode("utf-8"),
                file_name=f"Laporan_Teknis_PaveDesign_{datetime.now().strftime('%Y%m%d')}.html",
                mime="text/html",
                use_container_width=True,
            )

    with col_right:
        render_html(f"""
        <div class="bento-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h4 style="margin: 0;">{get_svg_icon("shield-check", c_accent_bright, 18)} Kelaikan Desain & Spesifikasi</h4>
                <span class="badge-pill badge-in-spec">● SIAP KONSTRUKSI</span>
            </div>
            <div class="bento-card-inner">
                <div style="font-size: 11px; color: {c_muted}; font-weight: 600; text-transform: uppercase;">Standar Desain Tebal Perkerasan</div>
                <div style="font-size: 15px; font-weight: 700; color: #10B981; margin-top: 4px;">
                    Sesuai Manual Desain Perkerasan Jalan Pd T-01-2002-B
                </div>
                <div style="font-size: 12px; color: {c_muted}; margin-top: 4px;">
                    Struktur perkerasan menjamin kapasitas struktural terhadap beban kumulatif {cesal_juta_val:,.3f} MESA.
                </div>
            </div>
            <div class="bento-card-inner">
                <div style="font-size: 11px; color: {c_muted}; font-weight: 600; text-transform: uppercase;">Standar Job Mix Formula Agregat</div>
                <div style="font-size: 15px; font-weight: 700; color: {c_accent_bright}; margin-top: 4px;">
                    Sesuai Spesifikasi Umum Bina Marga 2018 Rev.2 Divisi 6
                </div>
                <div style="font-size: 12px; color: {c_muted}; margin-top: 4px;">
                    Gradasi blending campuran aspal {st.session_state.tipe_campuran} memenuhi amplop batas spesifikasi.
                </div>
            </div>
            <div class="bento-card-inner">
                <div style="font-size: 11px; color: {c_muted}; font-weight: 600; text-transform: uppercase;">Estimasi Rencana Anggaran Biaya</div>
                <div style="font-size: 15px; font-weight: 700; color: #F59E0B; margin-top: 4px;">
                    Acuan Pedoman AHSP Bina Marga Wilayah {st.session_state.rab_wilayah}
                </div>
                <div style="font-size: 12px; color: {c_muted}; margin-top: 4px;">
                    Total Biaya Rencana: <b>Rp {total_rab_all:,.0f}</b> ({'Termasuk PPN 11%' if st.session_state.rab_include_ppn else 'Tanpa PPN'}).
                </div>
            </div>
            <div style="padding: 16px; border-radius: 10px; background: rgba(14, 165, 233, 0.08); border: 1px solid rgba(14, 165, 233, 0.2);">
                <div style="font-size: 13px; color: {c_text}; line-height: 1.6;">
                    📌 <b>Catatan Rekayasa:</b> Rekomendasi ketebalan ini merupakan ketebalan padat minimum di lapangan. Pengawasan berkala terhadap CBR subgrade dan pengujian Marshall berkala wajib dilaksanakan selama masa konstruksi.
                </div>
            </div>
        </div>
        """)


# =====================================================================
# 15. FOOTER BERSIH & ELEGAN
# =====================================================================

render_html(f"<hr style='margin: 32px 0 16px 0; border-color: {c_border};'>")
render_html(
    f"<div style='text-align: center; color: {c_muted}; font-size: 13px; padding-bottom: 24px; font-weight: 500;'>"
    "🛣️ <b>PaveDesign & JMF v5.5</b> — Referensi: Manual Desain Perkerasan Bina Marga & Spesifikasi Umum 2018"
    "</div>"
)
