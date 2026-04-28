# ============================================================
#  main_namorada.py
#  Pipeline de coleta Strava — Atleta: Namorada
#
#  Como usar:
#    python main_namorada.py
#
#  Este arquivo NÃO altera nada dos seus dados (israel).
#  Todos os arquivos dela ficam em: data/namorada/
# ============================================================

import os

# ── 1. Define o atleta ANTES de qualquer import dos módulos src ──────────────
ATHLETE = "namorada"
BASE    = f"data/{ATHLETE}"

# ── 2. Sobrescreve credenciais e caminhos nos módulos compartilhados ─────────
import src.auth.strava_auth as _auth
_auth.CLIENT_ID     = "231028"
_auth.CLIENT_SECRET = "e45bc4e98b31dae2c45d82a86eaf01c475f96607"
_auth.TOKEN_FILE    = f"{BASE}/token.json"

import src.utils.storage as _storage
_storage._BASE_DIR                      = BASE
_storage.CONSOLIDATED_PATH              = f"{BASE}/processed/activities_consolidated.csv"
_storage.LAPS_CONSOLIDATED_PATH         = f"{BASE}/processed/activity_laps_consolidated.csv"
_storage.BEST_EFFORTS_CONSOLIDATED_PATH = f"{BASE}/processed/activity_best_efforts_consolidated.csv"
_storage.LAPS_SNAPSHOT_DIR              = f"{BASE}/processed/snapshots/laps"
_storage.BEST_EFFORTS_SNAPSHOT_DIR      = f"{BASE}/processed/snapshots/best_efforts"

import src.ingestion.get_activities as _ingestion
_ingestion.CHECKPOINT_FILE = f"{BASE}/checkpoint.json"

# ── 3. Agora importa e roda o pipeline normalmente ───────────────────────────
from src.auth.strava_auth        import get_valid_token
from src.ingestion.get_activities import get_all_enriched_activities
from src.processing.transform    import (
    transform_activities,
    transform_laps,
    transform_best_efforts,
)
from src.enrichment.weather      import enrich_with_weather
from src.utils.storage           import (
    save_raw_data,
    save_processed_snapshot,
    save_processed_data,
    save_laps_data,
    save_laps_snapshot,
    save_best_efforts_data,
    save_best_efforts_snapshot,
    get_last_activity_timestamp,
)


def main():
    print(f"\n👤 Atleta: {ATHLETE.upper()}")
    print(f"📁 Dados em: {BASE}/\n")

    # 1. Autenticação
    access_token = get_valid_token()
    if not access_token:
        print(f"\n❌ Token não encontrado em {BASE}/token.json")
        return

    # 2. Incremental
    after = get_last_activity_timestamp()
    if after:
        print(f"⏩ Extraindo atividades após timestamp {after}")
    else:
        print("🔄 Primeira execução — extração completa")

    # 3. Ingestão
    raw_activities, raw_laps, raw_best_efforts = get_all_enriched_activities(
        access_token,
        after=after,
        fetch_details=True,
        fetch_streams=False,
        fetch_laps=True,
    )

    print(f"\n📊 Coletado: "
          f"{len(raw_activities)} atividades | "
          f"{len(raw_laps)} laps | "
          f"{len(raw_best_efforts)} best_efforts")

    if not raw_activities:
        print("✅ Nada novo para processar.")
        return

    # 4. Raw
    save_raw_data(raw_activities)

    # 5. Transform + clima
    df_activities = transform_activities(raw_activities)
    df_activities = enrich_with_weather(df_activities)

    # 6. Transform laps e best_efforts
    df_laps         = transform_laps(raw_laps)
    df_best_efforts = transform_best_efforts(raw_best_efforts)

    # 7. Snapshots
    save_processed_snapshot(df_activities)
    save_laps_snapshot(df_laps,         snapshot_dir=f"{BASE}/processed/snapshots/laps")
    save_best_efforts_snapshot(df_best_efforts, snapshot_dir=f"{BASE}/processed/snapshots/best_efforts")

    # 8. Consolidados — caminhos passados explicitamente (default params são fixados no import)
    save_processed_data(df_activities)
    save_laps_data(df_laps,             path=f"{BASE}/processed/activity_laps_consolidated.csv")
    save_best_efforts_data(df_best_efforts, path=f"{BASE}/processed/activity_best_efforts_consolidated.csv")

    print("\n✅ Pipeline concluído com sucesso.")
    print(f"   • Atividades:   {len(df_activities)}")
    print(f"   • Laps:         {len(df_laps)}")
    print(f"   • Best efforts: {len(df_best_efforts)}")


def run_backfill():
    """
    Busca laps e best_efforts de todas as atividades já salvas no CSV dela.
    Rode UMA vez após a primeira coleta:
        python -c "from mainNamorada import run_backfill; run_backfill()"
    """
    import pandas as pd
    from src.ingestion.get_activities import backfill_laps_and_best_efforts
    from src.processing.transform import transform_laps, transform_best_efforts

    access_token = get_valid_token()
    if not access_token:
        print("❌ Token inválido.")
        return

    consolidated = f"{BASE}/processed/activities_consolidated.csv"
    df = pd.read_csv(consolidated, sep=";", encoding="utf-8-sig")
    activity_ids = df["id"].dropna().astype(int).tolist()

    print(f"🔁 Backfill de {len(activity_ids)} atividades da namorada...")

    raw_laps, raw_be = backfill_laps_and_best_efforts(
        access_token,
        activity_ids,
        fetch_laps=True,
        fetch_best_efforts=True,
    )

    df_laps = transform_laps(raw_laps)
    df_be   = transform_best_efforts(raw_be)

    save_laps_snapshot(df_laps,         snapshot_dir=f"{BASE}/processed/snapshots/laps")
    save_best_efforts_snapshot(df_be,   snapshot_dir=f"{BASE}/processed/snapshots/best_efforts")
    save_laps_data(df_laps,             path=f"{BASE}/processed/activity_laps_consolidated.csv")
    save_best_efforts_data(df_be,       path=f"{BASE}/processed/activity_best_efforts_consolidated.csv")

    print("\n✅ Backfill concluído.")
    print(f"   • Laps:         {len(df_laps)}")
    print(f"   • Best efforts: {len(df_be)}")


if __name__ == "__main__":
    main()