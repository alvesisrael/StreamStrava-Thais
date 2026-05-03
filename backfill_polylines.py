"""
backfill_polylines.py
─────────────────────
Adiciona as colunas map_summary_polyline (e opcionalmente map_polyline)
ao activities_consolidated.csv já existente, sem alterar nenhum outro dado.

Uso:
    python backfill_polylines.py --token SEU_ACCESS_TOKEN
    python backfill_polylines.py --token SEU_ACCESS_TOKEN --full   # inclui polyline HD
    python backfill_polylines.py --token SEU_ACCESS_TOKEN --base data/namorada/processed
"""

import argparse
import os
import time
import requests
import pandas as pd

# ── Configuração ───────────────────────────────────────────────────────────────
DEFAULT_BASE = "data/processed"
CSV_NAME     = "activities_consolidated.csv"


# ── Helpers ────────────────────────────────────────────────────────────────────
def rate_check(response):
    usage = response.headers.get("X-RateLimit-Usage", "0,0")
    limit = response.headers.get("X-RateLimit-Limit", "100,1000")
    u15, ud = [int(x) for x in usage.split(",")]
    l15, ld = [int(x) for x in limit.split(",")]
    if u15 >= l15 * 0.85:
        print(f"  ⚠️  Rate limit 15min: {u15}/{l15}")
    return u15, l15


def safe_get(url, headers, params=None, retries=3):
    for attempt in range(1, retries + 1):
        r = requests.get(url, headers=headers, params=params)
        if r.status_code == 200:
            rate_check(r)
            return r
        if r.status_code == 429:
            wait = int(r.headers.get("X-Retry-After", 900))
            print(f"  🚫 Rate limit — aguardando {wait}s...")
            for rem in range(wait, 0, -60):
                print(f"     ⏱️  {rem}s restantes...")
                time.sleep(min(60, rem))
        else:
            print(f"  ⚠️  HTTP {r.status_code} (tentativa {attempt}/{retries})")
            if attempt < retries:
                time.sleep(2 ** attempt)
    return None


# ── Busca summary_polyline via endpoint de lista (barato: 200/página) ──────────
def fetch_summary_polylines(access_token):
    """
    Retorna dict {activity_id: summary_polyline} para TODAS as atividades.
    Usa o endpoint de lista — custa 1 req/200 atividades.
    """
    headers  = {"Authorization": f"Bearer {access_token}"}
    url      = "https://www.strava.com/api/v3/athlete/activities"
    results  = {}
    page     = 1

    print("\n📥 Buscando summary_polyline via endpoint de lista...")
    while True:
        r = safe_get(url, headers, params={"page": page, "per_page": 200})
        if r is None:
            print("  ❌ Erro ao buscar atividades.")
            break
        data = r.json()
        if not data:
            break
        for act in data:
            aid  = act.get("id")
            poly = (act.get("map") or {}).get("summary_polyline", "")
            results[aid] = poly
        print(f"  📄 Página {page}: {len(data)} atividades ({len(results)} no total)")
        page += 1

    print(f"  ✅ {len(results)} polylines obtidos da lista.\n")
    return results


# ── Busca map_polyline via endpoint de detalhe (1 req/atividade) ───────────────
def fetch_full_polylines(access_token, activity_ids, batch_size=95):
    """
    Retorna dict {activity_id: map_polyline} para os IDs fornecidos.
    Usa o endpoint de detalhe — custa 1 req/atividade.
    Faz pausas automáticas para respeitar o rate limit de 100/15min.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    results = {}
    total   = len(activity_ids)

    print(f"📥 Buscando map_polyline (HD) para {total} atividades...")
    print(f"   Estimativa: ~{total} chamadas. Rate limit: 100/15min.\n")

    for i, aid in enumerate(activity_ids, start=1):
        url = f"https://www.strava.com/api/v3/activities/{aid}"
        r   = safe_get(url, headers)
        if r:
            poly = (r.json().get("map") or {}).get("polyline", "")
            results[aid] = poly
        else:
            results[aid] = ""

        if i % 10 == 0:
            print(f"  → {i}/{total} processadas")

        # Pausa proativa a cada 90 chamadas para evitar rate limit
        if i % batch_size == 0 and i < total:
            print(f"  ⏸️  Pausa de 15min para reset de rate limit ({i}/{total})...")
            for rem in range(900, 0, -60):
                print(f"     ⏱️  {rem}s restantes...")
                time.sleep(min(60, rem))
            print("  ▶️  Retomando...\n")

    print(f"  ✅ {len(results)} polylines HD obtidos.\n")
    return results


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Backfill de polylines no activities_consolidated.csv")
    parser.add_argument("--token", required=True,  help="Strava access token")
    parser.add_argument("--base",  default=DEFAULT_BASE, help="Pasta base dos CSVs (default: data/processed)")
    parser.add_argument("--full",  action="store_true",  help="Busca também map_polyline HD (1 req/atividade)")
    args = parser.parse_args()

    csv_path = os.path.join(args.base, CSV_NAME)
    if not os.path.exists(csv_path):
        print(f"❌ CSV não encontrado: {csv_path}")
        return

    # Carrega CSV existente
    df = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig")
    print(f"📂 CSV carregado: {len(df)} atividades em '{csv_path}'")

    # ── summary_polyline (sempre) ──────────────────────────────────────────────
    already_has_summary = (
        "map_summary_polyline" in df.columns
        and df["map_summary_polyline"].notna().any()
        and (df["map_summary_polyline"].astype(str).str.len() > 2).any()
    )

    if already_has_summary:
        missing = df["map_summary_polyline"].isna() | (df["map_summary_polyline"].astype(str).str.len() <= 2)
        n_miss  = missing.sum()
        print(f"  ℹ️  Coluna já existe — {n_miss} atividades sem polyline, atualizando...")
    else:
        print("  ℹ️  Coluna map_summary_polyline não encontrada — criando do zero.")
        df["map_summary_polyline"] = ""

    summary_map = fetch_summary_polylines(args.token)
    df["map_summary_polyline"] = df["id"].map(
        lambda aid: summary_map.get(aid, df.loc[df["id"] == aid, "map_summary_polyline"].values[0]
                                    if aid in df["id"].values else "")
    )
    preenchidos = (df["map_summary_polyline"].astype(str).str.len() > 2).sum()
    print(f"  ✅ map_summary_polyline: {preenchidos}/{len(df)} atividades com rota.")

    # ── map_polyline HD (opcional, --full) ─────────────────────────────────────
    if args.full:
        if "map_polyline" not in df.columns:
            df["map_polyline"] = ""

        ids_sem = df.loc[
            df["map_polyline"].isna() | (df["map_polyline"].astype(str).str.len() <= 2),
            "id"
        ].tolist()

        print(f"\n🔍 {len(ids_sem)} atividades sem map_polyline HD.")
        if ids_sem:
            full_map = fetch_full_polylines(args.token, ids_sem)
            df.loc[df["id"].isin(ids_sem), "map_polyline"] = df.loc[
                df["id"].isin(ids_sem), "id"
            ].map(full_map)
            preen_hd = (df["map_polyline"].astype(str).str.len() > 2).sum()
            print(f"  ✅ map_polyline HD: {preen_hd}/{len(df)} atividades.")

    # ── Salva CSV ──────────────────────────────────────────────────────────────
    df.to_csv(csv_path, sep=";", encoding="utf-8-sig", index=False)
    print(f"\n💾 CSV salvo: {csv_path}")
    print("🎉 Backfill concluído! Reinicie o Streamlit para ver as rotas no mapa.")


if __name__ == "__main__":
    main()