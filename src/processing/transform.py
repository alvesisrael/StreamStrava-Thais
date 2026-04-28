import pandas as pd

def transform_laps(raw_laps):
    """Converte list[dict] de laps em DataFrame tipado."""
    if not raw_laps:
        return pd.DataFrame(columns=[
            "activity_id", "activity_sport_type", "lap_id", "lap_index", "split", "name",
            "start_date", "distance_m", "distance_km",
            "moving_time_sec", "elapsed_time_sec",
            "average_speed", "max_speed",
            "average_heartrate", "max_heartrate",
            "average_cadence", "total_elevation_gain",
            "start_index", "end_index",
            "pace_sec_km", "pace_formatted",
        ])

    df = pd.DataFrame(raw_laps)

    if "start_date" in df.columns:
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")

    numeric_cols = [
        "distance_m", "distance_km",
        "moving_time_sec", "elapsed_time_sec",
        "average_speed", "max_speed",
        "average_heartrate", "max_heartrate",
        "average_cadence", "total_elevation_gain",
        "start_index", "end_index",
        "pace_sec_km", "lap_index", "split",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    preferred_order = [
        "activity_id", "activity_sport_type",
        "lap_id", "lap_index", "split", "name",
        "start_date",
        "distance_m", "distance_km",
        "moving_time_sec", "elapsed_time_sec",
        "average_speed", "max_speed",
        "average_heartrate", "max_heartrate",
        "average_cadence", "total_elevation_gain",
        "start_index", "end_index",
        "pace_sec_km", "pace_formatted",
    ]
    ordered = [c for c in preferred_order if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    return df[ordered + remaining]

def transform_best_efforts(raw_best_efforts):
    """Converte list[dict] de best_efforts em DataFrame tipado."""
    if not raw_best_efforts:
        return pd.DataFrame(columns=[
            "activity_id", "activity_sport_type",
            "best_effort_id", "name",
            "distance_m", "distance_km",
            "moving_time_sec", "elapsed_time_sec",
            "pr_rank", "is_pr", "start_date",
            "start_index", "end_index",
            "pace_sec_km", "pace_formatted",
        ])

    df = pd.DataFrame(raw_best_efforts)

    if "start_date" in df.columns:
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")

    numeric_cols = [
        "distance_m", "distance_km",
        "moving_time_sec", "elapsed_time_sec",
        "pr_rank", "start_index", "end_index", "pace_sec_km",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "pr_rank" in df.columns:
        df["is_pr"] = df["pr_rank"].notna()

    preferred_order = [
        "activity_id", "activity_sport_type",
        "best_effort_id", "name",
        "distance_m", "distance_km",
        "moving_time_sec", "elapsed_time_sec",
        "pr_rank", "is_pr", "start_date",
        "start_index", "end_index",
        "pace_sec_km", "pace_formatted",
    ]
    ordered = [c for c in preferred_order if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    return df[ordered + remaining]

def transform_activities(raw_activities):
    df = pd.DataFrame(raw_activities)

    # 📅 Converte data
    df["start_date"] = pd.to_datetime(df["start_date"])

    # 🔒 Garante tipos numéricos nos campos que vieram do enriquecimento
    numeric_cols = [
        "distance_km", "elevation_gain",
        "average_heartrate", "max_heartrate",
        "moving_time_sec", "elapsed_time_sec",
        "calories", "suffer_score", "average_cadence",
        "efficiency_index", "average_speed", "max_speed",
        # ✅ NOVO: coordenadas
        "latitude", "longitude",
        # ✅ NOVO: colunas de clima (presentes após enrich_with_weather)
        "weather_temp", "weather_feels_like", "weather_humidity",
        "weather_precipitation", "weather_rain",
        "weather_wind_speed", "weather_wind_gusts",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ⏱️ pace_sec_km como inteiro
    if "pace_sec_km" in df.columns:
        df["pace_sec_km"] = pd.to_numeric(df["pace_sec_km"], errors="coerce")
        df["pace_sec_km"] = df["pace_sec_km"].round(0).astype("Int64")

    # 🧹 Seleciona e ordena as colunas relevantes
    columns = [
        "id",
        "name",
        "sport_type",
        "start_date",
        "distance_km",
        "moving_time_sec",
        "elapsed_time_sec",
        "elevation_gain",
        "average_heartrate",
        "max_heartrate",
        "average_cadence",
        "average_speed",
        "max_speed",
        "pace_sec_km",
        "pace_formatted",
        "efficiency_index",
        "calories",
        "suffer_score",
        "pr_count",
        "achievement_count",
        # ✅ NOVO: coordenadas — necessárias para o weather.py funcionar
        # e úteis para futuros mapas no Power BI
        "latitude",
        "longitude",
        # ✅ NOVO: dados climáticos — preenchidos pelo enrich_with_weather()
        # Ficam NULL para atividades sem coordenada (treinos indoor, etc.)
        "weather_temp",
        "weather_feels_like",
        "weather_humidity",
        "weather_precipitation",
        "weather_rain",
        "weather_wind_speed",
        "weather_wind_gusts",
        "weather_code",
        "weather_condition",
    ]

    # Mantém apenas as colunas que existirem no df
    columns = [c for c in columns if c in df.columns]

    return df[columns]