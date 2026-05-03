import requests
import time
import json
import os

# ─── Checkpoint ────────────────────────────────────────────────────────────────
CHECKPOINT_FILE = "checkpoint.json"


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            checkpoint = json.load(f)
        print(f"♻️  Checkpoint encontrado — {len(checkpoint['enriched'])} atividades já processadas, retomando...")
        # Compat retroativa
        checkpoint.setdefault("laps", [])
        checkpoint.setdefault("best_efforts", [])
        return checkpoint
    return {"enriched": [], "processed_ids": [], "laps": [], "best_efforts": []}


def save_checkpoint(enriched, processed_ids, laps=None, best_efforts=None):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({
            "enriched": enriched,
            "processed_ids": processed_ids,
            "laps": laps or [],
            "best_efforts": best_efforts or [],
        }, f)


def clear_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print("🗑️  Checkpoint removido (extração concluída).")


# ─── Rate Limit ─────────────────────────────────────────────────────────────────
def check_rate_limit(response):
    limit_header = response.headers.get("X-RateLimit-Limit", "100,1000")
    usage_header = response.headers.get("X-RateLimit-Usage", "0,0")
    limites = [int(x) for x in limit_header.split(",")]
    usos    = [int(x) for x in usage_header.split(",")]
    uso_15min,  limite_15min  = usos[0],  limites[0]
    uso_diario, limite_diario = usos[1],  limites[1]
    return uso_15min, limite_15min, uso_diario, limite_diario


def handle_rate_limit_response(response, enriched, processed_ids, laps=None, best_efforts=None):
    retry_after = int(response.headers.get("X-Retry-After", 900))
    print(f"\n🚫 Rate limit atingido! Progresso salvo ({len(enriched)} atividades).")
    print(f"⏳ Aguardando {retry_after} segundos ({retry_after // 60} min)...")
    save_checkpoint(enriched, processed_ids, laps=laps, best_efforts=best_efforts)
    for remaining in range(retry_after, 0, -60):
        print(f"   ⏱️  {remaining}s restantes...")
        time.sleep(min(60, remaining))
    print("▶️  Retomando extração...\n")


def safe_get(url, headers, params=None, enriched=None, processed_ids=None, laps=None, best_efforts=None, retries=3):
    enriched      = enriched      or []
    processed_ids = processed_ids or []

    for attempt in range(1, retries + 1):
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            uso_15min, limite_15min, uso_diario, limite_diario = check_rate_limit(response)
            if uso_15min >= limite_15min * 0.85:
                print(f"⚠️  {uso_15min}/{limite_15min} requisições usadas nos últimos 15 min.")
            if uso_diario >= limite_diario * 0.85:
                print(f"⚠️  {uso_diario}/{limite_diario} requisições usadas hoje.")
            return response

        elif response.status_code == 429:
            handle_rate_limit_response(response, enriched, processed_ids, laps=laps, best_efforts=best_efforts)

        else:
            print(f"⚠️  Erro HTTP {response.status_code} (tentativa {attempt}/{retries})")
            if attempt < retries:
                time.sleep(2 ** attempt)
    return None


# ─── Extração ──────────────────────────────────────────────────────────────────
def get_activities(access_token, after=None, enriched=None, processed_ids=None):
    url     = "https://www.strava.com/api/v3/athlete/activities"
    headers = {"Authorization": f"Bearer {access_token}"}

    all_activities = []
    page, per_page = 1, 200

    while True:
        params = {"page": page, "per_page": per_page}
        if after:
            params["after"] = after

        response = safe_get(url, headers, params=params, enriched=enriched, processed_ids=processed_ids)
        if response is None:
            print("❌ Falha ao carregar página de atividades.")
            break

        data = response.json()
        if not data:
            break

        all_activities.extend(data)
        print(f"📄 Página {page} carregada ({len(data)} atividades)")
        page += 1

    return all_activities


def get_activity_detail(access_token, activity_id, enriched=None, processed_ids=None, laps=None, best_efforts=None):
    url     = f"https://www.strava.com/api/v3/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = safe_get(
        url, headers,
        enriched=enriched, processed_ids=processed_ids,
        laps=laps, best_efforts=best_efforts,
    )
    if response and response.status_code == 200:
        return response.json()
    print(f"⚠️  Erro ao buscar atividade {activity_id}")
    return None


def get_activity_streams(access_token, activity_id, enriched=None, processed_ids=None, laps=None, best_efforts=None):
    url     = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    headers = {"Authorization": f"Bearer {access_token}"}
    params  = {
        "keys":        "heartrate,velocity_smooth,altitude,cadence,distance,time",
        "key_by_type": True,
    }

    response = safe_get(
        url, headers, params=params,
        enriched=enriched, processed_ids=processed_ids,
        laps=laps, best_efforts=best_efforts,
    )
    if response and response.status_code == 200:
        return response.json()
    print(f"⚠️  Erro ao buscar streams da atividade {activity_id}")
    return None


# ─── ✅ NOVO: Buscar LAPS de uma atividade ─────────────────────────────────────
def get_activity_laps(access_token, activity_id, enriched=None, processed_ids=None, laps=None, best_efforts=None):
    """GET /activities/{id}/laps — retorna list[dict] das voltas."""
    url     = f"https://www.strava.com/api/v3/activities/{activity_id}/laps"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = safe_get(
        url, headers,
        enriched=enriched, processed_ids=processed_ids,
        laps=laps, best_efforts=best_efforts,
    )
    if response and response.status_code == 200:
        return response.json()
    print(f"⚠️  Erro ao buscar laps da atividade {activity_id}")
    return None

# ─── Extração de campos (atividade agregada) ───────────────────────────────────
def extract_fields(activity, detail=None, streams=None):
    """Extrai campos da atividade (nível agregado)."""

    start_latlng = activity.get("start_latlng") or []
    latitude  = start_latlng[0] if len(start_latlng) >= 2 else None
    longitude = start_latlng[1] if len(start_latlng) >= 2 else None

    record = {
        "id":                activity.get("id"),
        "name":              activity.get("name"),
        "type":              activity.get("type"),
        "sport_type":        activity.get("sport_type"),
        "start_date":        activity.get("start_date_local"),
        "distance_m":        activity.get("distance"),
        "distance_km":       round(activity.get("distance", 0) / 1000, 2),
        "moving_time_sec":   activity.get("moving_time"),
        "elapsed_time_sec":  activity.get("elapsed_time"),
        "elevation_gain":    activity.get("total_elevation_gain"),
        "average_heartrate": activity.get("average_heartrate"),
        "max_heartrate":     activity.get("max_heartrate"),
        "average_speed":     activity.get("average_speed"),
        "max_speed":         activity.get("max_speed"),
        "pr_count":          activity.get("pr_count"),
        "achievement_count": activity.get("achievement_count"),
        "latitude":          latitude,
        "longitude":         longitude,
        "map_summary_polyline": (activity.get("map") or {}).get("summary_polyline", ""),
    }

    if detail:
        record.update({
            "calories":           detail.get("calories"),
            "suffer_score":       detail.get("suffer_score"),
            "average_cadence":    detail.get("average_cadence"),
            "description":        detail.get("description"),
            "device_name":        detail.get("device_name"),
            "average_watts":      detail.get("average_watts"),
            "weighted_avg_watts": detail.get("weighted_average_watts"),
            "workout_type":       detail.get("workout_type"),  # ✅ NOVO
            "map_polyline": (detail.get("map") or {}).get("polyline", ""),
        })

    distance_km = record.get("distance_km", 0)
    moving_time = record.get("moving_time_sec", 0)
    if distance_km and distance_km > 0:
        pace_sec = moving_time / distance_km
        record["pace_sec_km"]    = round(pace_sec, 1)
        record["pace_formatted"] = f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"
    else:
        record["pace_sec_km"]    = None
        record["pace_formatted"] = None

    if record.get("average_heartrate") and record.get("pace_sec_km"):
        record["efficiency_index"] = round(record["pace_sec_km"] / record["average_heartrate"], 4)
    else:
        record["efficiency_index"] = None

    if streams:
        hr_data  = streams.get("heartrate", {}).get("data", [])
        cad_data = streams.get("cadence",   {}).get("data", [])

        if hr_data:
            record["stream_hr_min"] = min(hr_data)
            record["stream_hr_max"] = max(hr_data)
            record["stream_hr_avg"] = round(sum(hr_data) / len(hr_data), 1)

            fc_max = 200
            zones  = {"z1": 0, "z2": 0, "z3": 0, "z4": 0, "z5": 0}
            for hr in hr_data:
                pct = hr / fc_max
                if   pct < 0.60: zones["z1"] += 1
                elif pct < 0.70: zones["z2"] += 1
                elif pct < 0.80: zones["z3"] += 1
                elif pct < 0.90: zones["z4"] += 1
                else:            zones["z5"] += 1

            total = len(hr_data)
            record["pct_z1"] = round(zones["z1"] / total * 100, 1)
            record["pct_z2"] = round(zones["z2"] / total * 100, 1)
            record["pct_z3"] = round(zones["z3"] / total * 100, 1)
            record["pct_z4"] = round(zones["z4"] / total * 100, 1)
            record["pct_z5"] = round(zones["z5"] / total * 100, 1)

        if cad_data:
            record["stream_cadence_avg"] = round(sum(cad_data) / len(cad_data), 1)

    return record


# ─── ✅ NOVO: extrair campos de LAPS ────────────────────────────────────────────
def extract_laps_fields(activity_id, activity_sport_type, laps_data):
    """Converte resposta da API de laps em registros tabulares (1 linha por volta)."""
    if not laps_data:
        return []

    records = []
    for lap in laps_data:
        distance_m  = lap.get("distance") or 0
        distance_km = round(distance_m / 1000, 3)
        moving_time = lap.get("moving_time") or 0

        record = {
            "activity_id":          activity_id,
            "activity_sport_type":  activity_sport_type,
            "lap_id":               lap.get("id"),
            "lap_index":            lap.get("lap_index"),
            "split":                lap.get("split"),
            "name":                 lap.get("name"),
            "start_date":           lap.get("start_date_local"),
            "distance_m":           distance_m,
            "distance_km":          distance_km,
            "moving_time_sec":      moving_time,
            "elapsed_time_sec":     lap.get("elapsed_time"),
            "average_speed":        lap.get("average_speed"),
            "max_speed":            lap.get("max_speed"),
            "average_heartrate":    lap.get("average_heartrate"),
            "max_heartrate":        lap.get("max_heartrate"),
            "average_cadence":      lap.get("average_cadence"),
            "total_elevation_gain": lap.get("total_elevation_gain"),
            "start_index":          lap.get("start_index"),
            "end_index":            lap.get("end_index"),
        }

        if distance_km > 0 and moving_time > 0:
            pace_sec = moving_time / distance_km
            record["pace_sec_km"]    = round(pace_sec, 1)
            record["pace_formatted"] = f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"
        else:
            record["pace_sec_km"]    = None
            record["pace_formatted"] = None

        records.append(record)

    return records


# ─── ✅ NOVO: extrair BEST_EFFORTS (só corridas) ───────────────────────────────
def extract_best_efforts_fields(activity_id, activity_sport_type, detail):
    """Extrai os melhores esforços que a Strava calcula dentro da atividade (só Run)."""
    if not detail:
        return []

    best_efforts = detail.get("best_efforts") or []
    records = []

    for be in best_efforts:
        distance_m  = be.get("distance") or 0
        distance_km = round(distance_m / 1000, 3)
        moving_time = be.get("moving_time") or 0

        record = {
            "activity_id":         activity_id,
            "activity_sport_type": activity_sport_type,
            "best_effort_id":      be.get("id"),
            "name":                be.get("name"),       # ex: "5k", "1 mile", "Half Marathon"
            "distance_m":          distance_m,
            "distance_km":         distance_km,
            "moving_time_sec":     moving_time,
            "elapsed_time_sec":    be.get("elapsed_time"),
            "pr_rank":             be.get("pr_rank"),    # 1/2/3 se PR, None caso contrário
            "start_date":          be.get("start_date_local"),
            "start_index":         be.get("start_index"),
            "end_index":           be.get("end_index"),
        }

        if distance_km > 0 and moving_time > 0:
            pace_sec = moving_time / distance_km
            record["pace_sec_km"]    = round(pace_sec, 1)
            record["pace_formatted"] = f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"
        else:
            record["pace_sec_km"]    = None
            record["pace_formatted"] = None

        records.append(record)

    return records


# ─── Pipeline principal ─────────────────────────────────────────────────────────
def get_all_enriched_activities(
    access_token,
    after=None,
    fetch_details=False,
    fetch_streams=False,
    fetch_laps=False,
):
    """
    Retorna TUPLA (enriched, laps, best_efforts).
    - enriched:     1 linha por atividade
    - laps:         1 linha por volta (se fetch_laps=True)
    - best_efforts: 1 linha por best_effort (vem junto do detail, sem chamada extra)
    """
    checkpoint       = load_checkpoint()
    enriched         = checkpoint["enriched"]
    laps_all         = checkpoint["laps"]
    best_efforts_all = checkpoint["best_efforts"]
    processed_ids    = set(checkpoint["processed_ids"])

    activities = get_activities(
        access_token,
        after=after,
        enriched=enriched,
        processed_ids=list(processed_ids),
    )
    print(f"\n🏃 {len(activities)} atividades encontradas na API.\n")

    for i, activity in enumerate(activities):
        activity_id = activity.get("id")
        sport_type  = activity.get("sport_type")

        if activity_id in processed_ids:
            continue

        detail, streams, laps = None, None, None

        if fetch_details:
            detail = get_activity_detail(
                access_token, activity_id,
                enriched=enriched, processed_ids=list(processed_ids),
                laps=laps_all, best_efforts=best_efforts_all,
            )

        if fetch_streams:
            streams = get_activity_streams(
                access_token, activity_id,
                enriched=enriched, processed_ids=list(processed_ids),
                laps=laps_all, best_efforts=best_efforts_all,
            )

        if fetch_laps:
            laps = get_activity_laps(
                access_token, activity_id,
                enriched=enriched, processed_ids=list(processed_ids),
                laps=laps_all, best_efforts=best_efforts_all,
            )

        # Extrações
        record = extract_fields(activity, detail=detail, streams=streams)
        enriched.append(record)

        if laps is not None:
            laps_all.extend(extract_laps_fields(activity_id, sport_type, laps))

        if detail is not None:
            best_efforts_all.extend(extract_best_efforts_fields(activity_id, sport_type, detail))

        processed_ids.add(activity_id)

        if (i + 1) % 20 == 0:
            save_checkpoint(enriched, list(processed_ids), laps=laps_all, best_efforts=best_efforts_all)
            print(f"💾 Checkpoint salvo ({len(enriched)} atividades, "
                  f"{len(laps_all)} laps, {len(best_efforts_all)} best efforts)")

    clear_checkpoint()
    return enriched, laps_all, best_efforts_all


# ─── ✅ NOVO: Backfill pro histórico existente ─────────────────────────────────
def backfill_laps_and_best_efforts(access_token, activity_ids, fetch_laps=True, fetch_best_efforts=True):
    """
    Roda UMA vez pra preencher laps/best_efforts das atividades que já estão no consolidated.
    Retorna (laps_records, best_efforts_records) prontos pra transform + save.
    """
    laps_records         = []
    best_efforts_records = []

    print(f"\n🔁 Backfill: {len(activity_ids)} atividades a reprocessar")
    print(f"   fetch_laps={fetch_laps} | fetch_best_efforts={fetch_best_efforts}\n")

    calls_per_activity = int(fetch_laps) + int(fetch_best_efforts)
    total_calls        = len(activity_ids) * calls_per_activity
    print(f"ℹ️  Estimativa de ~{total_calls} chamadas à API. "
          f"Rate limit: 100/15min. Aguardes automáticos podem ocorrer.\n")

    for i, activity_id in enumerate(activity_ids, start=1):
        detail     = None
        sport_type = None

        if fetch_best_efforts:
            detail = get_activity_detail(access_token, activity_id)
            if detail:
                sport_type = detail.get("sport_type")
                best_efforts_records.extend(
                    extract_best_efforts_fields(activity_id, sport_type, detail)
                )

        if fetch_laps:
            laps = get_activity_laps(access_token, activity_id)
            if laps:
                laps_records.extend(extract_laps_fields(activity_id, sport_type, laps))

        if i % 10 == 0:
            print(f"   → {i}/{len(activity_ids)} reprocessadas "
                  f"({len(laps_records)} laps, {len(best_efforts_records)} best_efforts)")

    print(f"\n✅ Backfill concluído: {len(laps_records)} laps + {len(best_efforts_records)} best_efforts")
    return laps_records, best_efforts_records