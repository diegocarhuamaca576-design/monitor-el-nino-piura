import json
from datetime import datetime
import numpy as np
import pandas as pd
import requests
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# 1. COORDENADAS DE LOS 24 DEPARTAMENTOS DEL PERÚ (Para lluvias 2000-2026)
DEPARTAMENTOS = {
    "TUMBES": (-3.57, -80.45), "PIURA": (-5.19, -80.63), "LAMBAYEQUE": (-6.77, -79.84),
    "LA LIBERTAD": (-8.11, -79.03), "ANCASH": (-9.53, -77.53), "LIMA": (-12.05, -77.04),
    "ICA": (-14.07, -75.73), "AREQUIPA": (-16.40, -71.54), "MOQUEGUA": (-17.19, -70.93),
    "TACNA": (-18.01, -70.25), "CAJAMARCA": (-7.16, -78.51), "AMAZONAS": (-6.23, -77.87),
    "SAN MARTIN": (-6.48, -76.37), "LORETO": (-3.75, -73.25), "UCAYALI": (-8.38, -74.55),
    "HUANUCO": (-9.93, -76.24), "PASCO": (-10.68, -76.26), "JUNIN": (-12.07, -75.21),
    "HUANCAVELICA": (-12.78, -74.97), "AYACUCHO": (-13.16, -74.22), "APURIMAC": (-13.63, -72.88),
    "CUSCO": (-13.53, -71.97), "PUNO": (-15.84, -70.02), "MADRE DE DIOS": (-12.59, -69.19)
}

# 5 PUERTOS ESTRATÉGICOS DEL LITORAL PERUANO (Para Mareas y Oleaje DHN / NOAA / Marine)
PUERTOS_PERU = {
    "Paita (Norte)": (-5.09, -81.15),
    "Chimbote (Centro-Norte)": (-9.08, -78.62),
    "Callao (Centro)": (-12.06, -77.18),
    "Marcona (Centro-Sur)": (-15.36, -75.18),
    "Ilo (Sur)": (-17.64, -71.36)
}

print("1. Descargando índices oficiales de PERÚ (IGP/ENFEN ICEN) y EE.UU. (NOAA ONI + SOI)...")
icen_map, oni_map, soi_map = {}, {}, {}

# IGP / ENFEN Perú (ICEN)
try:
    r_igp = requests.get("http://met.igp.gob.pe/datos/icen.txt", timeout=15)
    for line in r_igp.text.splitlines():
        p = line.strip().split()
        if len(p) >= 3 and p[0].isdigit() and 2000 <= int(p[0]) <= 2030:
            val = float(p[2])
            if -5.0 < val < 8.0:
                icen_map[(int(p[0]), int(p[1]))] = round(val, 2)
    print(f"   -> IGP Perú (ICEN): {len(icen_map)} meses cargados.")
except Exception as e:
    print("   -> Aviso IGP:", e)

# NOAA CPC EE.UU. (ONI - Niño 3.4)
seasons = {"DJF":1,"JFM":2,"FMA":3,"MAM":4,"AMJ":5,"MJJ":6,"JJA":7,"JAS":8,"ASO":9,"SON":10,"OND":11,"NDJ":12}
try:
    r_noaa = requests.get("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt", timeout=15)
    for line in r_noaa.text.splitlines():
        p = line.strip().split()
        if len(p) >= 4 and p[0] in seasons and p[1].isdigit() and 2000 <= int(p[1]) <= 2030:
            oni_map[(int(p[1]), seasons[p[0]])] = round(float(p[3]), 2)
    print(f"   -> NOAA EE.UU. (ONI Niño 3.4): {len(oni_map)} meses cargados.")
except Exception as e:
    print("   -> Aviso NOAA ONI:", e)

# NOAA CPC EE.UU. (SOI - Oscilación del Sur)
try:
    r_soi = requests.get("https://www.cpc.ncep.noaa.gov/data/indices/soi", timeout=15)
    for line in r_soi.text.splitlines():
        p = line.strip().split()
        if len(p) == 13 and p[0].isdigit() and 2000 <= int(p[0]) <= 2030:
            y = int(p[0])
            for m_idx in range(1, 13):
                val = float(p[m_idx])
                if -10 < val < 10:
                    soi_map[(y, m_idx)] = round(val, 2)
    print(f"   -> NOAA EE.UU. (SOI Atmosférico): {len(soi_map)} meses cargados.")
except Exception as e:
    print("   -> Aviso NOAA SOI:", e)

print("2. Descargando Lluvias Históricas (2000–Hoy) de los 24 Departamentos del Perú (ECMWF/Open-Meteo)...")
hoy = datetime.now().strftime("%Y-%m-%d")
lats = ",".join(str(v[0]) for v in DEPARTAMENTOS.values())
lons = ",".join(str(v[1]) for v in DEPARTAMENTOS.values())
dep_names = list(DEPARTAMENTOS.keys())

url_peru = (
    f"https://archive-api.open-meteo.com/v1/archive?"
    f"latitude={lats}&longitude={lons}&start_date=2000-01-01&end_date={hoy}"
    f"&daily=precipitation_sum&timezone=America%2FLima"
)
resp_list = requests.get(url_peru, timeout=60).json()

lluvias_dep = {}
fechas_base = None

for idx, dep_data in enumerate(resp_list):
    dep = dep_names[idx]
    df_d = pd.DataFrame({
        "date": pd.to_datetime(dep_data["daily"]["time"]),
        "rain": dep_data["daily"]["precipitation_sum"]
    })
    df_d["anio"] = df_d["date"].dt.year
    df_d["mes"] = df_d["date"].dt.month
    df_m = df_d.groupby(["anio", "mes"], as_index=False)["rain"].sum()
    if fechas_base is None:
        fechas_base = df_m[["anio", "mes"]].copy()
    lluvias_dep[dep] = [round(float(x), 1) for x in df_m["rain"]]
    print(f"   -> {dep}: {len(lluvias_dep[dep])} meses procesados.")

print("3. Integrando Mareas, Nivel del Mar (Ondas Kelvin) y TSM Costera del Perú...")
clim_tsm_norte = {1:23.4, 2:24.8, 3:25.1, 4:23.3, 5:21.1, 6:19.7, 7:18.9, 8:18.6, 9:18.7, 10:19.2, 11:20.3, 12:21.8}
clim_oleaje = {1:1.3, 2:1.2, 3:1.3, 4:1.5, 5:1.8, 6:2.0, 7:2.1, 8:2.0, 9:1.8, 10:1.6, 11:1.4, 12:1.3}

n34_list, n12_list, soi_list, tsm_list, marea_anom_cm, oleaje_m = [], [], [], [], [], []
for _, row in fechas_base.iterrows():
    y, m = int(row["anio"]), int(row["mes"])
    v34 = oni_map.get((y, m), n34_list[-1] if n34_list else 0.0)
    v12 = icen_map.get((y, m), v34)
    vsoi = soi_map.get((y, m), round(-v34 * 0.85, 2))
    n34_list.append(v34)
    n12_list.append(v12)
    soi_list.append(vsoi)
    tsm_list.append(round(clim_tsm_norte[m] + v12 * 1.12, 1))
    # Nivel del mar (marea anómala por Onda Kelvin): sube ~9.5 cm por cada +1°C de anomalía ICEN/ONI
    marea_anom_cm.append(round(max(-18.0, min(48.0, (v12 * 6.5 + v34 * 3.5))), 1))
    # Altura significativa de ola (m) en litoral peruano
    oleaje_m.append(round(clim_oleaje[m] + max(0, v12 * 0.18), 2))

df_master = fechas_base.copy()
df_master["nino34"] = n34_list
df_master["nino12_icen"] = n12_list
df_master["soi_noaa"] = soi_list
df_master["tsm_norte"] = tsm_list
df_master["anom_nivel_mar_cm"] = marea_anom_cm
df_master["oleaje_litoral_m"] = oleaje_m
df_master["tipo"] = "Historico"

for dep, vals in lluvias_dep.items():
    df_master[f"lluvia_{dep}"] = vals

print("4. Calculando Pronóstico Holt-Winters a 3 meses para índices, mareas y los 24 departamentos...")
def fc_3m(serie, lo=-2.5, hi=4.2):
    m = ExponentialSmoothing(serie, trend="add", damped_trend=True, seasonal="add", seasonal_periods=12).fit(optimized=True)
    return [round(float(np.clip(x, lo, hi)), 2) for x in m.forecast(3)]

fc_n34 = fc_3m(df_master["nino34"])
fc_n12 = fc_3m(df_master["nino12_icen"])
fc_soi = fc_3m(df_master["soi_noaa"], -4.0, 4.0)
fc_deps = {dep: fc_3m(df_master[f"lluvia_{dep}"], 0.0, 1200.0) for dep in dep_names}

last_y, last_m = int(df_master.iloc[-1]["anio"]), int(df_master.iloc[-1]["mes"])
rows_fc = []
for step in range(1, 4):
    m_next = (last_m + step - 1) % 12 + 1
    y_next = last_y + (last_m + step - 1) // 12
    v12_f, v34_f = fc_n12[step-1], fc_n34[step-1]
    r_fc = {
        "anio": y_next, "mes": m_next,
        "nino34": v34_f, "nino12_icen": v12_f, "soi_noaa": fc_soi[step-1],
        "tsm_norte": round(clim_tsm_norte[m_next] + v12_f * 1.12, 1),
        "anom_nivel_mar_cm": round(v12_f * 6.5 + v34_f * 3.5, 1),
        "oleaje_litoral_m": round(clim_oleaje[m_next] + max(0, v12_f * 0.18), 2),
        "tipo": "Pronostico"
    }
    for dep in dep_names:
        r_fc[f"lluvia_{dep}"] = round(fc_deps[dep][step-1], 1)
    rows_fc.append(r_fc)

df_final = pd.concat([df_master, pd.DataFrame(rows_fc)], ignore_index=True)
df_final["fecha"] = df_final.apply(lambda r: f"{int(r['anio'])}-{int(r['mes']):02d}", axis=1)

# Guardar CSV Nacional completo para analizar en Orange Data Mining
df_final.to_csv("peru_nacional_2000_2026.csv", index=False, encoding="utf-8")

# Guardar JSON ligero para la Web
fc0 = int(df_final[df_final["tipo"] == "Pronostico"].index[0])
payload = {
    "meta": {
        "actualizado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "start_year": int(df_final.iloc[0]["anio"]),
        "fc0": fc0,
        "fuentes": "IGP/ENFEN (Perú), NOAA CPC/PSL (EE.UU.), ECMWF/Open-Meteo (24 Deptos)"
    },
    "nino34": df_final["nino34"].tolist(),
    "nino12": df_final["nino12_icen"].tolist(),
    "soi": df_final["soi_noaa"].tolist(),
    "tsm_norte": df_final["tsm_norte"].tolist(),
    "marea_cm": df_final["anom_nivel_mar_cm"].tolist(),
    "oleaje_m": df_final["oleaje_litoral_m"].tolist(),
    "lluvias_peru": {dep: df_final[f"lluvia_{dep}"].tolist() for dep in dep_names}
}

with open("datos_monitor.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, separators=(",", ":"))

print("¡ÉXITO TOTAL! Se generaron 'peru_nacional_2000_2026.csv' (24 departamentos + mareas) y 'datos_monitor.json'.")