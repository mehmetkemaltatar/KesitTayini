from flask import Flask, jsonify, request, render_template
import math
import threading
import sys
import os
import database as db

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    app = Flask(__name__, template_folder=os.path.join(sys._MEIPASS, 'templates'))
else:
    BASE_DIR = os.path.dirname(__file__)
    app = Flask(__name__)

db.DB_PATH = os.path.join(BASE_DIR, 'kesit_tayini.db')

# Tüm ayarlar veritabanından alınır (config objesi üzerinden)

CABLE_CAPACITY_TABLE = [
    {"section": "4x6", "capacity": 56},
    {"section": "4x10", "capacity": 75},
    {"section": "4x16", "capacity": 98},
    {"section": "3x25/16", "capacity": 128},
    {"section": "3x35/16", "capacity": 157},
    {"section": "3x50/25", "capacity": 185},
    {"section": "3x70/35", "capacity": 228},
    {"section": "3x95/50", "capacity": 275},
    {"section": "3x120/70", "capacity": 313},
    {"section": "3x150/70", "capacity": 353},
    {"section": "3x185/95", "capacity": 399},
    {"section": "3x240/120", "capacity": 464}
]

def safe_float(val, default=0):
    if val is None or val == "": return default
    try: return float(val)
    except: return default

def safe_int(val, default=1):
    if val is None or val == "": return default
    try: return int(float(val))
    except: return default

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/calculate", methods=["POST"])
def calculate():
    data = request.get_json()
    config = db.get_config()

    talep_gucu = safe_float(data.get("talep_gucu"))
    mesafe = safe_float(data.get("mesafe"))
    hat_tipi = data.get("hat_tipi", "yeralti")

    if talep_gucu <= 0:
        return jsonify({"error": "Talep Gücü sıfırdan büyük olmalıdır."}), 400

    gamma = config.get("CONDUCTIVITY_COPPER", 56)
    voltage = config.get("VOLTAGE", 380)
    cos_phi = config.get("COS_PHI", 0.8)
    derating = 0.85 if hat_tipi == "havai" else 1.0

    current = (talep_gucu * 1000) / (math.sqrt(3) * voltage * cos_phi)

    selected_cable = None
    final_e = 0
    final_n = 1

    for n in range(1, 5):
        for cable in CABLE_CAPACITY_TABLE:
            s_val = float(cable["section"].split('x')[-1].split('/')[0])
            total_capacity = cable["capacity"] * n * derating
            effective_s = s_val * n

            if mesafe > 0 and effective_s > 0:
                e_val = (100 * mesafe * (talep_gucu * 1000)) / (gamma * effective_s * (voltage ** 2))
            else:
                e_val = 0

            if current <= total_capacity and e_val <= config["VOLTAGE_DROP_LIMIT"]:
                selected_cable = cable
                final_e = e_val
                final_n = n
                break
        if selected_cable:
            break

    if not selected_cable:
        max_n = 4
        max_cable = CABLE_CAPACITY_TABLE[-1]
        s_max = float(max_cable["section"].split('x')[-1].split('/')[0]) * max_n
        if mesafe > 0 and s_max > 0:
            e_max = (100 * mesafe * (talep_gucu * 1000)) / (gamma * s_max * (voltage ** 2))
        else:
            e_max = 0
        return jsonify({
            "error": f"Tablodaki en büyük kesitten {max_n} adet ({max_n} x {max_cable['section']}) bile yeterli değil! "
                     f"Hesaplanan akım: {round(current, 2)} A (Maks kapasite: {round(max_cable['capacity'] * max_n * derating, 2)} A), "
                     f"Gerilim düşümü: %{round(e_max, 2)} (Sınır: %{config['VOLTAGE_DROP_LIMIT']}). Lütfen değerleri kontrol edin."
        }), 400

    display_cable = selected_cable["section"]
    if final_n > 1:
        display_cable = f"{final_n}x {selected_cable['section']}"

    db.add_history_entry(
        p=round(talep_gucu, 2),
        l=round(mesafe, 2),
        cable=display_cable,
        e=round(final_e, 2),
        i=round(current, 2)
    )

    return jsonify({
        "current": round(current, 2),
        "selected_cable": display_cable,
        "voltage_drop": round(final_e, 2),
        "limit": config["VOLTAGE_DROP_LIMIT"],
        "cable_quantity": final_n,
        "hat_tipi": hat_tipi,
        "guc": round(talep_gucu, 2),
        "mesafe": round(mesafe, 2)
    })

def simultaneity_coeff(n):
    if n <= 0: return 0
    if n <= 4: return 1.0
    if n <= 9: return 0.78
    if n <= 14: return 0.63
    if n <= 19: return 0.53
    if n <= 24: return 0.49
    if n <= 29: return 0.46
    if n <= 34: return 0.44
    if n <= 39: return 0.42
    return 0.41

def get_cable_info(section_mm2):
    best = None
    for cable in CABLE_CAPACITY_TABLE:
        s_val = float(cable["section"].split('x')[-1].split('/')[0])
        if abs(s_val - section_mm2) < 0.1:
            return {"section": cable["section"], "capacity": cable["capacity"], "section_val": s_val}
        if s_val <= section_mm2:
            best = cable
    if best:
        s_val = float(best["section"].split('x')[-1].split('/')[0])
        return {"section": best["section"], "capacity": best["capacity"], "section_val": s_val}
    return None

def calc_vd_simple(section, length, current, gamma, voltage, cos_phi, system_type="three_phase"):
    if section <= 0 or length <= 0: return 0
    if system_type == "three_phase":
        return (100 * math.sqrt(3) * length * current * cos_phi) / (gamma * section * voltage)
    else:
        return (200 * length * current * cos_phi) / (gamma * section * voltage)

def suggest_cables(req_current, derating, limit_vd, length, gamma, voltage, cos_phi=0.8, other_vd=0):
    suggestions = []
    for n in range(1, 5):
        for cable in CABLE_CAPACITY_TABLE:
            s_val = float(cable["section"].split('x')[-1].split('/')[0])
            total_capacity = cable["capacity"] * n * derating
            if req_current <= total_capacity:
                effective_s = s_val * n
                vd = calc_vd_simple(effective_s, length, req_current, gamma, voltage, cos_phi) if length > 0 else 0
                if vd + other_vd <= limit_vd:
                    suggestions.append({
                        "quantity": n,
                        "section": cable["section"],
                        "section_val": s_val,
                        "total_section": effective_s,
                        "capacity": total_capacity,
                        "vd": round(vd, 2)
                    })
                    break
        if suggestions:
            break
    return suggestions

@app.route("/api/network_calc", methods=["POST"])
def network_calc():
    data = request.get_json()
    config = db.get_config()

    l_tp = safe_float(data.get("l_tp"))
    l_tsdk = safe_float(data.get("l_tsdk"))
    s_tp = safe_float(data.get("s_tp"))
    s_tsdk = safe_float(data.get("s_tsdk"))
    n_tp = max(1, safe_int(data.get("n_tp", 1)))
    n_tsdk = max(1, safe_int(data.get("n_tsdk", 1)))
    hat_tipi = data.get("hat_tipi", "yeralti")
    material = data.get("material", "copper")
    input_mode = data.get("input_mode", "abone")

    gamma = config.get("CONDUCTIVITY_COPPER", 56) if material == "copper" else config.get("CONDUCTIVITY_ALUMINUM", 35)
    voltage = config.get("VOLTAGE", 380)
    cos_phi = config.get("COS_PHI", 0.8)
    p_mesken = config.get("MESKEN_UNIT_KW", 2.0)
    p_ticaret = config.get("TICARET_UNIT_KW", 5.0)
    limit = config.get("VOLTAGE_DROP_LIMIT", 5.0)

    derating = 0.85 if hat_tipi == "havai" else 1.0

    if input_mode == "guc":
        p_mevcut = safe_float(data.get("p_mevcut"))
        p_yeni = safe_float(data.get("p_yeni"))
        p_kurulu_toplam = p_mevcut + p_yeni
        p_mesken_kurulu = 0
        p_ticaret_kurulu = 0
        n_toplam = 0
        n_mesken_mevcut = 0; n_ticaret_mevcut = 0
        n_mesken_yeni = 0; n_ticaret_yeni = 0
    else:
        n_mesken_mevcut = safe_int(data.get("n_mesken_mevcut"))
        n_ticaret_mevcut = safe_int(data.get("n_ticaret_mevcut"))
        n_mesken_yeni = safe_int(data.get("n_mesken_yeni"))
        n_ticaret_yeni = safe_int(data.get("n_ticaret_yeni"))
        n_toplam = n_mesken_mevcut + n_ticaret_mevcut + n_mesken_yeni + n_ticaret_yeni
        p_mesken_kurulu = (n_mesken_mevcut + n_mesken_yeni) * p_mesken
        p_ticaret_kurulu = (n_ticaret_mevcut + n_ticaret_yeni) * p_ticaret
        p_kurulu_toplam = p_mesken_kurulu + p_ticaret_kurulu
        p_mevcut = (n_mesken_mevcut * p_mesken) + (n_ticaret_mevcut * p_ticaret)
        p_yeni = (n_mesken_yeni * p_mesken) + (n_ticaret_yeni * p_ticaret)

    if p_kurulu_toplam <= 0:
        return jsonify({"error": "Toplam güç sıfırdan büyük olmalıdır."}), 400

    current = (p_kurulu_toplam * 1000) / (math.sqrt(3) * voltage * cos_phi)
    current_yeni = (p_yeni * 1000) / (math.sqrt(3) * voltage * cos_phi) if p_yeni > 0 else 0

    tp_cable = get_cable_info(s_tp) if s_tp > 0 else None
    tsdk_cable = get_cable_info(s_tsdk) if s_tsdk > 0 else None

    tp_capacity_ok = False
    tsdk_capacity_ok = False
    tp_vd = 0
    tsdk_vd = 0
    tp_capacity_available = 0
    tsdk_capacity_available = 0

    tp_adet = n_tp
    tsdk_adet = n_tsdk

    if tp_cable:
        tp_capacity_available = tp_cable["capacity"] * tp_adet * derating
        tp_capacity_ok = current <= tp_capacity_available
        tp_vd = calc_vd_simple(s_tp * tp_adet, l_tp, current, gamma, voltage, cos_phi)

    if tsdk_cable:
        tsdk_capacity_available = tsdk_cable["capacity"] * tsdk_adet * derating
        tsdk_capacity_ok = current_yeni <= tsdk_capacity_available
        tsdk_vd = calc_vd_simple(s_tsdk * tsdk_adet, l_tsdk, current_yeni, gamma, voltage, cos_phi)

    vd_total = tp_vd + tsdk_vd
    vd_ok = vd_total <= limit

    tp_suggestions = []
    tsdk_suggestions = suggest_cables(current_yeni, derating, limit, l_tsdk, gamma, voltage, cos_phi, other_vd=tp_vd)

    rec_cable = None
    rec_n = 0
    rec_e = 0
    if tsdk_suggestions:
        rec_cable = tsdk_suggestions[0]["section"]
        rec_n = tsdk_suggestions[0]["quantity"]
        rec_e = tsdk_suggestions[0]["vd"]
    recommended_cable_display = rec_cable
    if rec_n > 1 and rec_cable:
        recommended_cable_display = f"{rec_n}x {rec_cable}"

    # Step-by-step calculation details
    details = {
        "adim1_gucler": {
            "mesken_kurulu_toplam": round(p_mesken_kurulu, 2),
            "ticaret_kurulu_toplam": round(p_ticaret_kurulu, 2),
            "kurulu_toplam": round(p_kurulu_toplam, 2),
            "abone_sayisi_toplam": n_toplam,
            "mevcut_guc": round(p_mevcut, 2),
            "yeni_guc": round(p_yeni, 2)
        },
        "adim2_akim": {
            "formul": "I = P / (√3 × V × cosφ)",
            "toplam_akim": round(current, 2),
            "yeni_akim": round(current_yeni, 2),
            "gerilim": voltage,
            "cos_phi": cos_phi
        },
        "adim3_tp_kablo": {
            "mevcut_kesit": f"{tp_adet}x {s_tp}" if tp_adet > 1 and s_tp > 0 else (str(s_tp) if s_tp > 0 else "-"),
            "kapasite": round(tp_capacity_available, 2) if tp_cable else 0,
            "yeterli_mi": tp_capacity_ok,
            "gerilim_dusumu_yuzde": round(tp_vd, 2)
        },
        "adim4_tsdk_kablo": {
            "mevcut_kesit": f"{tsdk_adet}x {s_tsdk}" if tsdk_adet > 1 and s_tsdk > 0 else (str(s_tsdk) if s_tsdk > 0 else "-"),
            "kapasite": round(tsdk_capacity_available, 2) if tsdk_cable else 0,
            "yeterli_mi": tsdk_capacity_ok,
            "gerilim_dusumu_yuzde": round(tsdk_vd, 2)
        },
        "adim5_toplam_gd": {
            "tp_vd": round(tp_vd, 2),
            "tsdk_vd": round(tsdk_vd, 2),
            "toplam_vd": round(vd_total, 2),
            "sinir": limit,
            "yeterli_mi": vd_ok
        }
    }

    return jsonify({
        "success": True,
        "inputs": {
            "l_tp": l_tp, "l_tsdk": l_tsdk,
            "s_tp": s_tp, "s_tsdk": s_tsdk,
            "n_tp": tp_adet, "n_tsdk": tsdk_adet,
            "hat_tipi": hat_tipi,
            "material": material,
            "input_mode": input_mode
        },
        "results": {
            "p_kurulu": round(p_kurulu_toplam, 2),
            "p_mesken_kurulu": round(p_mesken_kurulu, 2),
            "p_ticaret_kurulu": round(p_ticaret_kurulu, 2),
            "p_mevcut": round(p_mevcut, 2),
            "p_yeni": round(p_yeni, 2),
            "n_toplam": n_toplam,
            "current": round(current, 2),
            "current_yeni": round(current_yeni, 2),
            "tp_capacity_ok": tp_capacity_ok,
            "tp_capacity_available": round(tp_capacity_available, 2) if tp_cable else 0,
            "tsdk_capacity_ok": tsdk_capacity_ok,
            "tsdk_capacity_available": round(tsdk_capacity_available, 2) if tsdk_cable else 0,
            "tp_vd": round(tp_vd, 2),
            "tsdk_vd": round(tsdk_vd, 2),
            "vd_total": round(vd_total, 2),
            "vd_ok": vd_ok,
            "vd_limit": limit,
            "tp_suggestions": tp_suggestions,
            "tsdk_suggestions": tsdk_suggestions,
            "tp_cable_exists": tp_cable is not None,
            "tsdk_cable_exists": tsdk_cable is not None,
            "derating": derating,
            "recommended_cable": recommended_cable_display,
            "recommended_n": rec_n,
            "recommended_vd": round(rec_e, 2)
        },
        "details": details
    })

@app.route("/api/voltage_drop", methods=["POST"])
def voltage_drop():
    data = request.get_json()
    config = db.get_config()

    section = safe_float(data.get("section"))
    length = safe_float(data.get("length"))
    current = safe_float(data.get("current"))
    power = safe_float(data.get("power"))
    voltage = safe_float(data.get("voltage"), config.get("VOLTAGE", 380))
    cos_phi = safe_float(data.get("cos_phi"), config.get("COS_PHI", 0.8))
    material = data.get("material", "copper")
    system_type = data.get("system_type", "three_phase")
    num_parallel = safe_int(data.get("num_parallel"), 1)
    use_reactance = data.get("use_reactance", False)
    cable_x = safe_float(data.get("cable_x"), 0.08)

    if section <= 0:
        return jsonify({"error": "Kesit alanı sıfırdan büyük olmalıdır."}), 400
    if length <= 0:
        return jsonify({"error": "Uzunluk sıfırdan büyük olmalıdır."}), 400

    gamma = config.get("CONDUCTIVITY_COPPER", 56) if material == "copper" else config.get("CONDUCTIVITY_ALUMINUM", 35)

    if power > 0 and current <= 0:
        if system_type == "three_phase":
            current = (power * 1000) / (math.sqrt(3) * voltage * cos_phi)
        else:
            current = (power * 1000) / (voltage * cos_phi)

    effective_section = section * num_parallel

    if use_reactance:
        R = length / (gamma * effective_section)
        X = cable_x * length / 1000
        sin_phi = math.sin(math.acos(cos_phi))
        if system_type == "three_phase":
            delta_u = math.sqrt(3) * current * (R * cos_phi + X * sin_phi)
        else:
            delta_u = 2 * current * (R * cos_phi + X * sin_phi)
        delta_u_percent = (delta_u / voltage) * 100
    else:
        if system_type == "three_phase":
            if power > 0:
                delta_u_percent = (100 * length * power * 1000) / (gamma * effective_section * (voltage ** 2))
            else:
                delta_u_percent = (100 * math.sqrt(3) * length * current * cos_phi) / (gamma * effective_section * voltage)
        else:
            delta_u_percent = (200 * length * current * cos_phi) / (gamma * effective_section * voltage)

    limit = config.get("VOLTAGE_DROP_LIMIT", 5)

    return jsonify({
        "voltage_drop_percent": round(delta_u_percent, 2),
        "voltage_drop_volts": round(delta_u_percent * voltage / 100, 2),
        "current": round(current, 2),
        "is_acceptable": delta_u_percent <= limit,
        "limit": limit,
        "effective_section": effective_section,
        "resistance_per_km": round(1000 / (gamma * section), 4) if section > 0 else 0
    })

@app.route("/api/config", methods=["GET"])
def get_config_route():
    return jsonify(db.get_config())

@app.route("/api/config", methods=["POST"])
def update_config_route():
    data = request.get_json()
    updated = db.update_config(data)
    return jsonify(updated)

@app.route("/api/history", methods=["GET"])
def get_history_route():
    return jsonify(db.get_history())

@app.route("/api/history", methods=["DELETE"])
def clear_history_route():
    conn = db.get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM history')
    conn.commit()
    return jsonify({"success": True})

@app.route("/api/trafo_capacity", methods=["POST"])
def trafo_capacity():
    data = request.get_json()
    config = db.get_config()

    trafo_kapasitesi_kva = safe_float(data.get("trafo_kapasitesi_kva"))
    abone_sayisi = safe_int(data.get("abone_sayisi"))
    birim_guc = safe_float(data.get("birim_guc"), 1.5)
    cos_phi = safe_float(data.get("cos_phi"), config.get("COS_PHI", 0.8))

    if trafo_kapasitesi_kva <= 0:
        return jsonify({"error": "Trafo kapasitesi sıfırdan büyük olmalıdır."}), 400
    if abone_sayisi <= 0:
        return jsonify({"error": "Abone/tesisat sayısı sıfırdan büyük olmalıdır."}), 400
    if birim_guc <= 0:
        return jsonify({"error": "Tesisat başına güç sıfırdan büyük olmalıdır."}), 400
    if cos_phi <= 0 or cos_phi > 1:
        return jsonify({"error": "Güç faktörü 0-1 arasında olmalıdır."}), 400

    p_kurulu = abone_sayisi * birim_guc
    s_toplam = p_kurulu / cos_phi
    trafo_yuku_yuzde = (s_toplam / trafo_kapasitesi_kva) * 100
    yeterli_mi = trafo_yuku_yuzde <= 100
    asilma_miktari = max(0, round(trafo_yuku_yuzde - 100, 2))

    db.add_history_entry(
        p=round(p_kurulu, 2),
        l=0,
        cable=f"Trafo: {round(trafo_kapasitesi_kva, 0)} kVA",
        e=round(trafo_yuku_yuzde, 2),
        i=round(s_toplam, 2)
    )

    return jsonify({
        "p_kurulu": round(p_kurulu, 2),
        "s_toplam": round(s_toplam, 2),
        "trafo_yuku_yuzde": round(trafo_yuku_yuzde, 2),
        "yeterli_mi": yeterli_mi,
        "asilma_miktari": asilma_miktari,
        "trafo_kapasitesi_kva": round(trafo_kapasitesi_kva, 1),
        "abone_sayisi": abone_sayisi,
        "birim_guc": birim_guc,
        "cos_phi": cos_phi
    })

def start_flask(data_dir=None):
    """Android (Chaquopy) tarafından çağrılır. Hemen döner, Flask arka planda çalışır."""
    if data_dir:
        db.USE_MEMORY = True
        app.template_folder = os.path.join(os.path.dirname(__file__), 'templates')
    db.init_db()
    t = threading.Thread(target=lambda: app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False), daemon=True)
    t.start()

if __name__ == "__main__":
    db.init_db()

    def run_flask():
        app.run(host="127.0.0.1", port=5001, debug=False)

    import webview
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    webview.create_window(
        title="Kesit Tayini",
        url="http://127.0.0.1:5001",
        width=1100,
        height=750,
        resizable=True,
        min_size=(800, 600)
    )
    webview.start()
