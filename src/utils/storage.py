import json
from datetime import datetime
import os
import pandas as pd
import os
from datetime import datetime
import pandas as pd

# 📁 Caminho do consolidado (fixo)
CONSOLIDATED_PATH = "data/processed/activities_consolidated.csv"
LAPS_CONSOLIDATED_PATH          = "data/processed/activity_laps_consolidated.csv"
BEST_EFFORTS_CONSOLIDATED_PATH  = "data/processed/activity_best_efforts_consolidated.csv"
LAPS_SNAPSHOT_DIR               = "data/processed/snapshots/laps"
BEST_EFFORTS_SNAPSHOT_DIR       = "data/processed/snapshots/best_efforts"
_BASE_DIR = "data"


# ───────────────────────────────
# 🟤 RAW (mantém snapshot)
# ───────────────────────────────
def save_raw_data(data, prefix="activities"):
    import json
    from datetime import datetime
    raw_dir = f"{_BASE_DIR}/raw"
    os.makedirs(raw_dir, exist_ok=True)
 
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{raw_dir}/{prefix}_{timestamp}.json"
 
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
 
    print(f"💾 Dados brutos salvos em: {filename}")



# ───────────────────────────────
# ⚙️ PROCESSED SNAPSHOT (mantém)
# ───────────────────────────────
def save_processed_snapshot(df, prefix="activities"):
    from datetime import datetime
    processed_dir = f"{_BASE_DIR}/processed"
    os.makedirs(processed_dir, exist_ok=True)
 
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{processed_dir}/{prefix}_{timestamp}.csv"
 
    df.to_csv(
        filename,
        index=False,
        sep=";",
        encoding="utf-8-sig",
        date_format="%d/%m/%Y %H:%M:%S"
    )
 
    print(f"📦 Snapshot salvo em: {filename}")



# ───────────────────────────────
# 🟢 PROCESSED CONSOLIDADO
# ───────────────────────────────
def save_processed_data(df):

    os.makedirs("data/processed", exist_ok=True)

    if "id" not in df.columns:
        raise ValueError("❌ DataFrame precisa ter coluna 'id'")

    if os.path.exists(CONSOLIDATED_PATH):
        existing_df = pd.read_csv(CONSOLIDATED_PATH, sep=";")

        existing_df = existing_df.drop_duplicates(subset="id")

        existing_ids = set(existing_df["id"])

        new_df = df[~df["id"].isin(existing_ids)]

        if new_df.empty:
            print("⚠️ Nenhuma atividade nova para adicionar.")
            return

        final_df = pd.concat([existing_df, new_df], ignore_index=True)

        print(f"➕ {len(new_df)} novas atividades adicionadas")

    else:
        final_df = df
        print("📄 Criando base consolidada inicial")

    if "start_date" in final_df.columns:
        final_df["start_date"] = pd.to_datetime(
            final_df["start_date"],
            dayfirst=True,
            utc=True,          # ✅ resolve o FutureWarning
            errors="coerce"
        )
        # Remove o fuso horário antes de salvar (mantém o horário como está)
        final_df["start_date"] = final_df["start_date"].dt.tz_localize(None)
        final_df = final_df.sort_values(by="start_date")

    final_df.to_csv(       # ✅ estava faltando esse bloco inteiro
        CONSOLIDATED_PATH,
        index=False,
        sep=";",
        encoding="utf-8-sig",
        date_format="%d/%m/%Y %H:%M:%S"
    )

    print(f"💾 Base consolidada atualizada: {CONSOLIDATED_PATH}")


# ───────────────────────────────
# 🕐 TIMESTAMP DA ÚLTIMA ATIVIDADE
# ───────────────────────────────
def get_last_activity_timestamp():
    """
    Lê o CSV consolidado e retorna o timestamp Unix (int) da atividade
    mais recente já salva. Retorna None se não houver base ainda.

    Usar como parâmetro `after` em get_activities() para sincronização incremental.
    """
    if not os.path.exists(CONSOLIDATED_PATH):
        print("ℹ️  Nenhuma base consolidada encontrada — extração completa será feita.")
        return None

    df = pd.read_csv(CONSOLIDATED_PATH, sep=";")

    if "start_date" not in df.columns or df.empty:
        print("⚠️  Coluna 'start_date' ausente ou base vazia — extração completa será feita.")
        return None

    df["start_date"] = pd.to_datetime(
    df["start_date"],
    dayfirst=True,
    errors="coerce"
)

    last_date = df["start_date"].max()

    if pd.isna(last_date):
        print("⚠️  Nenhuma data válida encontrada — extração completa será feita.")
        return None

    unix_ts = int(last_date.timestamp())
    print(f"📅 Última atividade em: {last_date.strftime('%d/%m/%Y %H:%M:%S')} → after={unix_ts}")
    return unix_ts





# ─── Helpers internos ────────────────────────────────────────────────────────
def _ensure_dir(path):
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)


def _read_csv_safe(path):
    if os.path.exists(path):
        try:
            return pd.read_csv(path, sep=";", encoding="utf-8-sig")
        except Exception as e:
            print(f"⚠️  Erro lendo {path}: {e}")
    return pd.DataFrame()


# ─── LAPS ────────────────────────────────────────────────────────────────────
def save_laps_data(df_laps, path=LAPS_CONSOLIDATED_PATH):
    """Mescla laps novos no consolidado. Dedupe por lap_id."""
    if df_laps is None or df_laps.empty:
        print("ℹ️  Nenhum lap novo para salvar.")
        return

    _ensure_dir(path)
    existing = _read_csv_safe(path)

    if not existing.empty:
        combined = pd.concat([existing, df_laps], ignore_index=True)
        if "lap_id" in combined.columns:
            combined = combined.drop_duplicates(subset=["lap_id"], keep="last")
        else:
            combined = combined.drop_duplicates(keep="last")
    else:
        combined = df_laps.copy()

    combined.to_csv(path, sep=";", encoding="utf-8-sig", index=False)
    print(f"💾 Laps consolidados: {len(combined)} registros em {path}")


def save_laps_snapshot(df_laps, snapshot_dir=LAPS_SNAPSHOT_DIR):
    """Snapshot com timestamp."""
    if df_laps is None or df_laps.empty:
        return
    if not os.path.exists(snapshot_dir):
        os.makedirs(snapshot_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(snapshot_dir, f"laps_{timestamp}.csv")
    df_laps.to_csv(path, sep=";", encoding="utf-8-sig", index=False)
    print(f"📸 Snapshot laps em {path}")


# ─── BEST EFFORTS ────────────────────────────────────────────────────────────
def save_best_efforts_data(df_be, path=BEST_EFFORTS_CONSOLIDATED_PATH):
    """Mescla best_efforts novos no consolidado. Dedupe por best_effort_id."""
    if df_be is None or df_be.empty:
        print("ℹ️  Nenhum best_effort novo para salvar.")
        return

    _ensure_dir(path)
    existing = _read_csv_safe(path)

    if not existing.empty:
        combined = pd.concat([existing, df_be], ignore_index=True)
        if "best_effort_id" in combined.columns:
            combined = combined.drop_duplicates(subset=["best_effort_id"], keep="last")
        else:
            combined = combined.drop_duplicates(keep="last")
    else:
        combined = df_be.copy()

    combined.to_csv(path, sep=";", encoding="utf-8-sig", index=False)
    print(f"💾 Best efforts: {len(combined)} registros em {path}")


def save_best_efforts_snapshot(df_be, snapshot_dir=BEST_EFFORTS_SNAPSHOT_DIR):
    """Snapshot com timestamp."""
    if df_be is None or df_be.empty:
        return
    if not os.path.exists(snapshot_dir):
        os.makedirs(snapshot_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(snapshot_dir, f"best_efforts_{timestamp}.csv")
    df_be.to_csv(path, sep=";", encoding="utf-8-sig", index=False)
    print(f"📸 Snapshot best_efforts em {path}")