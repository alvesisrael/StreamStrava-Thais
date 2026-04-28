from src.auth.strava_auth       import get_valid_token
from src.ingestion.get_activities import get_all_enriched_activities
from src.processing.transform   import (
    transform_activities,
    transform_laps,
    transform_best_efforts,
)
from src.enrichment.weather     import enrich_with_weather, backfill_weather
from src.utils.storage          import (
    save_raw_data,
    save_processed_snapshot,
    save_processed_data,
    get_last_activity_timestamp,
    CONSOLIDATED_PATH,
    save_laps_data,
    save_laps_snapshot,
    save_best_efforts_data,
    save_best_efforts_snapshot,
)



def main():
    # 1. Autenticação
    access_token = get_valid_token()

    # 2. Incremental
    after = get_last_activity_timestamp()
    if after:
        print(f"⏩ Extraindo atividades após timestamp {after}")
    else:
        print("🔄 Primeira execução ou histórico completo")

    # 3. Ingestão — agora retorna TUPLA
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
        print("✅ Nada novo pra processar.")
        return

    # 4. Raw
    save_raw_data(raw_activities)

    # 5. Transform activities + clima
    df_activities = transform_activities(raw_activities)
    df_activities = enrich_with_weather(df_activities)

    # 6. Transform laps e best_efforts
    df_laps         = transform_laps(raw_laps)
    df_best_efforts = transform_best_efforts(raw_best_efforts)

    # 7. Snapshots
    save_processed_snapshot(df_activities)
    save_laps_snapshot(df_laps)
    save_best_efforts_snapshot(df_best_efforts)

    # 8. Consolidados
    save_processed_data(df_activities)
    save_laps_data(df_laps)
    save_best_efforts_data(df_best_efforts)

    print("\n✅ Pipeline concluído com sucesso.")
    print(f"   • Atividades:   {len(df_activities)}")
    print(f"   • Laps:         {len(df_laps)}")
    print(f"   • Best efforts: {len(df_best_efforts)}")


def run_backfill():
    """
    Rode UMA vez pra preencher laps/best_efforts do histórico:
        python -c "from main import run_backfill; run_backfill()"
    """
    import pandas as pd
    from src.ingestion.get_activities import backfill_laps_and_best_efforts
    from src.utils.storage            import CONSOLIDATED_PATH

    access_token = get_valid_token()

    df = pd.read_csv(CONSOLIDATED_PATH, sep=";", encoding="utf-8-sig")
    activity_ids = df["id"].dropna().astype(int).tolist()

    print(f"🔁 Backfill sobre {len(activity_ids)} atividades existentes")
    # Pra rodar em lote menor, descomenta:
    # activity_ids = activity_ids[:50]

    raw_laps, raw_be = backfill_laps_and_best_efforts(
        access_token,
        activity_ids,
        fetch_laps=True,
        fetch_best_efforts=True,
    )

    df_laps = transform_laps(raw_laps)
    df_be   = transform_best_efforts(raw_be)

    save_laps_snapshot(df_laps)
    save_best_efforts_snapshot(df_be)
    save_laps_data(df_laps)
    save_best_efforts_data(df_be)

    print("\n✅ Backfill concluído.")


if __name__ == "__main__":
    main()