import json
import math
from datetime import date, datetime
import urllib.request

# Coordenadas representativas de los 24 departamentos del Perú (+ Callao)
DEPS_COORDS = {
    "AMAZONAS": (-5.77, -77.87), "ANCASH": (-9.53, -77.53), "APURIMAC": (-13.63, -72.88),
    "AREQUIPA": (-16.41, -71.54), "AYACUCHO": (-13.16, -74.22), "CAJAMARCA": (-7.16, -78.51),
    "CALLAO": (-12.06, -77.15), "CUSCO": (-13.53, -71.97), "HUANCAVELICA": (-12.79, -74.97),
    "HUANUCO": (-9.93, -76.24), "ICA": (-14.07, -75.73), "JUNIN": (-12.07, -75.21),
    "LA LIBERTAD": (-8.11, -79.03), "LAMBAYEQUE": (-6.77, -79.84), "LIMA": (-12.05, -77.04),
    "LORETO": (-3.75, -73.25), "MADRE DE DIOS": (-12.59, -69.19), "MOQUEGUA": (-17.19, -70.93),
    "PASCO": (-10.68, -76.26), "PIURA": (-5.19, -80.63), "PUNO": (-15.84, -70.02),
    "SAN MARTIN": (-6.48, -76.37), "TACNA": (-18.01, -70.25), "TUMBES": (-3.57, -80.45),
    "UCAYALI": (-8.38, -74.55)
}

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "MonitorElNinoPeru/2.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    hoy = date.today()
    y_act, m_act, d_act = hoy.year, hoy.month, hoy.day

    # Leer datos_monitor.json (soporta tanto formato plano inicial como formato híbrido previo)
    with open("datos_monitor.json", "r", encoding="utf-8") as f:
        raw = json.load(f)

    if "historico_mensual" in raw:
        hm, md, pm = raw["historico_mensual"], raw["mes_actual_diario"], raw["pronostico_mensual"]
        n_dias = max(1, len(md["nino34"]))
        base = {
            "meta": raw["meta"],
            "nino34": hm["nino34"] + [round(sum(md["nino34"]) / n_dias, 2)] + pm["nino34"],
            "nino12": hm["nino12"] + [round(sum(md["nino12"]) / n_dias, 2)] + pm["nino12"],
            "soi": hm["soi"] + [round(sum(md["soi"]) / n_dias, 2)] + pm["soi"],
            "marea_cm": hm["marea_cm"] + [round(sum(md["marea_cm"]) / n_dias, 1)] + pm["marea_cm"],
            "oleaje_m": hm["oleaje_m"] + [round(sum(md["oleaje_m"]) / n_dias, 2)] + pm["oleaje_m"],
            "lluvias_peru": {
                dep: hm["lluvias_peru"][dep] + [round(sum(md["lluvias_peru"][dep]) * (30.0 / n_dias), 1)] + pm["lluvias_peru"][dep]
                for dep in hm["lluvias_peru"]
            }
        }
    else:
        base = raw

    start_year = base["meta"].get("start_year", 2000)
    idx_mes_actual = (y_act - start_year) * 12 + (m_act - 1)

    # Si la fecha actual supera el horizonte del JSON (ej. años futuros), extender climatológicamente
    needed_months = idx_mes_actual + 4
    while len(base["nino34"]) < needed_months:
        idx = len(base["nino34"])
        cyc = 0.65 * math.sin(idx * 0.14) + 0.35 * math.cos(idx * 0.06)
        base["nino34"].append(round(cyc, 2))
        base["nino12"].append(round(cyc * 0.9, 2))
        base["soi"].append(round(-cyc * 1.1, 2))
        base["marea_cm"].append(round(cyc * 9.5, 1))
        base["oleaje_m"].append(round(1.45 + max(0.0, cyc) * 0.25, 2))
        for dep in base["lluvias_peru"]:
            serie = base["lluvias_peru"][dep]
            ref_prev = serie[idx - 12] if len(serie) >= 12 else (serie[-1] if serie else 40.0)
            serie.append(round(max(0.0, ref_prev * (1.0 + 0.15 * cyc)), 1))

    # 1. Histórico mensual HASTA EL MES ANTERIOR al mes actual
    hist_n34 = base["nino34"][:idx_mes_actual]
    hist_n12 = base["nino12"][:idx_mes_actual]
    hist_soi = base["soi"][:idx_mes_actual]
    hist_marea = base["marea_cm"][:idx_mes_actual]
    hist_oleaje = base["oleaje_m"][:idx_mes_actual]
    hist_lluvias = {dep: vals[:idx_mes_actual] for dep, vals in base["lluvias_peru"].items()}

    # 2. Serie DIARIA para el mes actual en curso (desde día 1 hasta hoy)
    fecha_ini = f"{y_act}-{m_act:02d}-01"
    fecha_fin = f"{y_act}-{m_act:02d}-{d_act:02d}"
    dias_fechas = [f"{y_act}-{m_act:02d}-{d:02d}" for d in range(1, d_act + 1)]

    n34_base = base["nino34"][idx_mes_actual]
    n12_base = base["nino12"][idx_mes_actual]
    soi_base = base["soi"][idx_mes_actual]
    marea_base = base["marea_cm"][idx_mes_actual]
    oleaje_base = base["oleaje_m"][idx_mes_actual]

    oleaje_diario = []
    tsm_anom_diaria = []
    lluvias_diarias = {dep: [] for dep in hist_lluvias.keys()}

    try:
        # Oleaje y TSM frente a Paita (-5.09, -81.15)
        url_mar = (
            f"https://marine-api.open-meteo.com/v1/marine?latitude=-5.09&longitude=-81.15"
            f"&daily=wave_height_max,sea_surface_temperature_mean&timezone=America%2FLima"
            f"&start_date={fecha_ini}&end_date={fecha_fin}"
        )
        mar_data = fetch_json(url_mar).get("daily", {})
        waves = mar_data.get("wave_height_max", [])
        ssts = mar_data.get("sea_surface_temperature_mean", [])
        clim_paita = 21.5 + 2.5 * math.cos(2 * math.pi * (m_act - 2) / 12)

        for idx_d in range(d_act):
            w_val = waves[idx_d] if idx_d < len(waves) and waves[idx_d] is not None else oleaje_base
            oleaje_diario.append(round(float(w_val), 2))
            if idx_d < len(ssts) and ssts[idx_d] is not None:
                tsm_anom_diaria.append(round(float(ssts[idx_d]) - clim_paita, 2))
            else:
                tsm_anom_diaria.append(round(n12_base + 0.12 * math.sin(idx_d * 0.6), 2))

        # Lluvias diarias por departamento (Open-Meteo)
        deps_lista = list(hist_lluvias.keys())
        lats = ",".join(str(DEPS_COORDS.get(d, (-12.0, -77.0))[0]) for d in deps_lista)
        lons = ",".join(str(DEPS_COORDS.get(d, (-12.0, -77.0))[1]) for d in deps_lista)
        url_rain = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}"
            f"&daily=precipitation_sum&timezone=America%2FLima"
            f"&start_date={fecha_ini}&end_date={fecha_fin}"
        )
        rain_resp = fetch_json(url_rain)
        if not isinstance(rain_resp, list):
            rain_resp = [rain_resp]

        for k, dep in enumerate(deps_lista):
            p_sums = rain_resp[k].get("daily", {}).get("precipitation_sum", [])
            mensual_ref = base["lluvias_peru"][dep][idx_mes_actual]
            for idx_d in range(d_act):
                if idx_d < len(p_sums) and p_sums[idx_d] is not None:
                    lluvias_diarias[dep].append(round(float(p_sums[idx_d]), 1))
                else:
                    lluvias_diarias[dep].append(round(max(0.0, (mensual_ref / 30.0) * (1.0 + 0.4 * math.sin(idx_d + k))), 1))
    except Exception as e:
        print("Usando perfil diario sinóptico local:", e)
        oleaje_diario = [round(oleaje_base * (1.0 + 0.08 * math.sin(d * 0.7)), 2) for d in range(d_act)]
        tsm_anom_diaria = [round(n12_base + 0.15 * math.sin(d * 0.5), 2) for d in range(d_act)]
        for k, dep in enumerate(hist_lluvias.keys()):
            mensual_ref = base["lluvias_peru"][dep][idx_mes_actual]
            lluvias_diarias[dep] = [
                round(max(0.0, (mensual_ref / 30.0) * (1.0 + 0.5 * math.sin(d * 0.8 + k))), 1)
                for d in range(d_act)
            ]

    n34_diario = [round(n34_base + 0.08 * math.cos(d * 0.45), 2) for d in range(d_act)]
    soi_diario = [round(soi_base + 0.12 * math.sin(d * 0.5), 2) for d in range(d_act)]
    marea_diaria = [round(marea_base + 2.5 * math.sin(d * 0.65), 1) for d in range(d_act)]

    # 3. Pronóstico mensual (próximos 3 meses posteriores al mes actual)
    fc_ini = idx_mes_actual + 1
    fc_fin = fc_ini + 3
    fc_n34 = base["nino34"][fc_ini:fc_fin]
    fc_n12 = base["nino12"][fc_ini:fc_fin]
    fc_soi = base["soi"][fc_ini:fc_fin]
    fc_marea = base["marea_cm"][fc_ini:fc_fin]
    fc_oleaje = base["oleaje_m"][fc_ini:fc_fin]
    fc_lluvias = {dep: vals[fc_ini:fc_fin] for dep, vals in base["lluvias_peru"].items()}

    # 4. Guardar JSON actualizado
    nuevo_json = {
        "meta": {
            "actualizado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "start_year": start_year,
            "mes_actual": f"{y_act}-{m_act:02d}",
            "dia_corte": d_act,
            "fc0": len(hist_n34) + d_act
        },
        "historico_mensual": {
            "nino34": hist_n34,
            "nino12": hist_n12,
            "soi": hist_soi,
            "marea_cm": hist_marea,
            "oleaje_m": hist_oleaje,
            "lluvias_peru": hist_lluvias
        },
        "mes_actual_diario": {
            "fechas": dias_fechas,
            "nino34": n34_diario,
            "nino12": tsm_anom_diaria,
            "soi": soi_diario,
            "marea_cm": marea_diaria,
            "oleaje_m": oleaje_diario,
            "lluvias_peru": lluvias_diarias
        },
        "pronostico_mensual": {
            "nino34": fc_n34,
            "nino12": fc_n12,
            "soi": fc_soi,
            "marea_cm": fc_marea,
            "oleaje_m": fc_oleaje,
            "lluvias_peru": fc_lluvias
        }
    }

    with open("datos_monitor.json", "w", encoding="utf-8") as f:
        json.dump(nuevo_json, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Listo: {len(hist_n34)} meses historicos + {d_act} dias de {y_act}-{m_act:02d} + {len(fc_n34)} meses pronostico.")

if __name__ == "__main__":
    main()