"""
Módulo de enriquecimento com dados climáticos da Open-Meteo Historical API.
"""

import time
from typing import Any

import pandas as pd
import requests
from requests.exceptions import RequestException
import requests
import pandas as pd
import time
from datetime import datetime
from typing import Optional, Dict, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Constantes da API Open-Meteo
# ─────────────────────────────────────────────────────────────────────────────

WEATHER_API_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_VARIABLES = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
    "cloud_cover",
]

# Códigos WMO para descrição do tempo (World Meteorological Organization)
WMO_CODES: dict[int, str] = {
    0: "Céu limpo",
    1: "Principalmente limpo",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Neblina",
    48: "Geada de neblina",
    51: "Garoa leve",
    53: "Garoa moderada",
    55: "Garoa densa",
    61: "Chuva leve",
    63: "Chuva moderada",
    65: "Chuva intensa",
    71: "Neve leve",
    73: "Neve moderada",
    75: "Neve intensa",
    77: "Granizo",
    80: "Pancadas leves",
    81: "Pancadas moderadas",
    82: "Pancadas intensas",
    95: "Tempestade",
    96: "Tempestade c/ granizo leve",
    99: "Tempestade c/ granizo intenso",
}


# ─────────────────────────────────────────────────────────────────────────────
# Funções de fetch e processamento
# ─────────────────────────────────────────────────────────────────────────────# Integração de Clima — Open-Meteo Historical API

# Documento de alterações necessárias para integrar dados climáticos da Open-Meteo ao pipeline Strava existente, enriquecendo atividades com informações meteorológicas detalhadas.



## 1. NOVO ARQUIVO: `src/enrichment/weather.py`

#Módulo completo para enriquecimento de dados climáticos:

#```python


# ─── Configurações da API ────────────────────────────────────────────
WEATHER_API_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_VARIABLES = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
    "cloud_cover"
]

# ─── Mapeamento de códigos WMO para descrições em português ──────────
WMO_CODES = {
    0: "Céu limpo",
    1: "Principalmente limpo",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Neblina",
    48: "Geada de neblina",
    51: "Garoa leve",
    53: "Garoa moderada",
    55: "Garoa densa",
    61: "Chuva leve",
    63: "Chuva moderada",
    65: "Chuva intensa",
    71: "Neve leve",
    73: "Neve moderada",
    75: "Neve intensa",
    77: "Granizo",
    80: "Pancadas leves",
    81: "Pancadas moderadas",
    82: "Pancadas intensas",
    95: "Tempestade",
    96: "Tempestade c/ granizo leve",
    99: "Tempestade c/ granizo intenso"
}


def fetch_hourly_weather(lat: float, lon: float, date_str: str) -> Optional[Dict]:
    """
    Busca dados horários de clima da Open-Meteo Historical API.
    
    Args:
        lat: Latitude da atividade
        lon: Longitude da atividade
        date_str: Data no formato YYYY-MM-DD
        
    Returns:
        Dict com {hora_int: {variável: valor}} ou None se erro
    """
    try:
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": date_str,
            "end_date": date_str,
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": "America/Sao_Paulo",
            "wind_speed_unit": "kmh"
        }
        
        response = requests.get(WEATHER_API_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if "hourly" not in data or not data["hourly"]["time"]:
            return None
        
        # ─── Estruturar dados por hora ────────────────────────────────
        hourly_data = {}
        times = data["hourly"]["time"]
        
        for var in HOURLY_VARIABLES:
            values = data["hourly"].get(var, [])
            for idx, time_str in enumerate(times):
                # Extrair hora do timestamp "2024-01-15T08:00"
                hour = int(time_str.split("T")[1].split(":")[0])
                
                if hour not in hourly_data:
                    hourly_data[hour] = {}
                
                hourly_data[hour][var] = values[idx] if idx < len(values) else None
        
        return hourly_data
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Erro ao buscar clima para ({lat}, {lon}) em {date_str}: {e}")
        return None


def get_weather_for_activity(row: pd.Series, cache: Dict) -> Dict:
    """
    Obtém dados de clima para uma atividade específica.
    
    Args:
        row: Linha do DataFrame com dados da atividade
        cache: Dicionário compartilhado para cache de requisições
        
    Returns:
        Dict com variáveis de clima enriquecidas
    """
    # ─── Extrair coordenadas e data ───────────────────────────────────
    lat = row.get("latitude")
    lon = row.get("longitude")
    start_date = row.get("start_date")
    start_time = row.get("start_time")
    
    if not lat or not lon or pd.isna(lat) or pd.isna(lon):
        return {}
    
    # ─── Criar chave de cache (lat, lon, data) ───────────────────────
    date_str = str(start_date).split(" ")[0] if start_date else None
    if not date_str:
        return {}
    
    cache_key = (round(float(lat), 2), round(float(lon), 2), date_str)
    
    # ─── Buscar dados se não estão em cache ───────────────────────────
    if cache_key not in cache:
        hourly_data = fetch_hourly_weather(float(lat), float(lon), date_str)
        cache[cache_key] = hourly_data
        time.sleep(0.1)  # Rate limiting
    else:
        hourly_data = cache[cache_key]
    
    if not hourly_data:
        return {}
    
    # ─── Extrair hora da atividade ────────────────────────────────────
    try:
        if isinstance(start_time, str):
            hour = int(start_time.split(":")[0])
        else:
            hour = int(start_time.hour) if hasattr(start_time, 'hour') else 0
    except (ValueError, AttributeError, IndexError):
        hour = 0
    
    # ─── Obter dados da hora mais próxima ─────────────────────────────
    hour_data = hourly_data.get(hour, {})
    
    if not hour_data:
        return {}
    
    # ─── Construir resultado com descrição de clima ───────────────────
    weather_code = hour_data.get("weather_code")
    weather_description = WMO_CODES.get(
        int(weather_code) if weather_code else -1,
        f"Código {weather_code}" if weather_code else "Desconhecido"
    )
    
    return {
        "weather_temp": hour_data.get("temperature_2m"),
        "weather_feels_like": hour_data.get("apparent_temperature"),
        "weather_humidity": hour_data.get("relative_humidity_2m"),
        "weather_precipitation": hour_data.get("precipitation"),
        "weather_rain": hour_data.get("rain"),
        "weather_wind_speed": hour_data.get("wind_speed_10m"),
        "weather_wind_gusts": hour_data.get("wind_gusts_10m"),
        "weather_code": weather_code,
        "weather_condition": weather_description
    }


def enrich_with_weather(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enriquece DataFrame de atividades com dados climáticos.
    Suporta processamento incremental (apenas linhas sem dados de clima).
    
    Args:
        df: DataFrame com atividades
        
    Returns:
        DataFrame enriquecido com colunas de clima
    """
    # ─── Validar colunas necessárias ──────────────────────────────────
    if "latitude" not in df.columns or "longitude" not in df.columns:
        print("⚠️  Colunas 'latitude' e 'longitude' não encontradas. Pulando enriquecimento de clima.")
        return df
    
    # ─── Inicializar colunas de clima se não existem ──────────────────
    weather_cols = [
        "weather_temp", "weather_feels_like", "weather_humidity",
        "weather_precipitation", "weather_rain", "weather_wind_speed",
        "weather_wind_gusts", "weather_code", "weather_condition"
    ]
    
    for col in weather_cols:
        if col not in df.columns:
            df[col] = None
    
    # ─── Determinar linhas a processar (incremental) ──────────────────
    if "weather_temp" in df.columns:
        # Processar apenas linhas sem dados de clima E com coordenadas
        mask = (df["weather_temp"].isna()) & (df["latitude"].notna())
    else:
        mask = df["latitude"].notna()
    
    rows_to_process = df[mask].index.tolist()
    
    if not rows_to_process:
        print("✓ Nenhuma atividade para enriquecer com clima.")
        return df
    
    print(f"🌤️  Enriquecendo {len(rows_to_process)} atividades com dados climáticos...")
    
    # ─── Processar com cache compartilhado ────────────────────────────
    cache = {}
    weather_data = {}
    
    for idx, row_idx in enumerate(rows_to_process):
        row = df.loc[row_idx]
        weather_info = get_weather_for_activity(row, cache)
        weather_data[row_idx] = weather_info
        
        if (idx + 1) % 10 == 0:
            print(f"  → {idx + 1}/{len(rows_to_process)} atividades processadas")
    
    # ─── Aplicar dados de clima ao DataFrame ──────────────────────────
    weather_df = pd.DataFrame.from_dict(weather_data, orient="index")
    
    for col in weather_cols:
        if col in weather_df.columns:
            df.loc[weather_df.index, col] = weather_df[col]
    
    print(f"✓ Enriquecimento concluído! {len(weather_data)} atividades atualizadas.")
    
    return df


def backfill_weather(consolidated_path: str) -> None:
    """
    Enriquece histórico completo de atividades salvas com dados climáticos.
    Útil para reprocessar arquivo consolidado já existente.
    
    Args:
        consolidated_path: Caminho do arquivo CSV consolidado
    """
    print(f"📂 Lendo histórico de atividades: {consolidated_path}")
    
    try:
        df = pd.read_csv(consolidated_path, sep=";", encoding="utf-8-sig")
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {consolidated_path}")
        return
    
    print(f"📊 {len(df)} atividades carregadas. Iniciando backfill de clima...")
    
    df = enrich_with_weather(df)
    
    df.to_csv(consolidated_path, sep=";", encoding="utf-8-sig", index=False)
    print(f"✓ Arquivo atualizado: {consolidated_path}")