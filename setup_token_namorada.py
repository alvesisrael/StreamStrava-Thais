# ============================================================
#  setup_token_namorada.py
#  Gera o token correto (com activity:read_all) para a namorada
#
#  Como usar:
#    1. Rode: python setup_token_namorada.py
#    2. O navegador vai abrir a página de autorização do Strava
#    3. Ela loga com a conta DELA e clica em Autorizar
#    4. O navegador vai para uma página de erro — NORMAL
#    5. Copie a URL completa da barra de endereço e cole aqui
# ============================================================

import requests
import json
import os
import webbrowser

CLIENT_ID     = "231028"
CLIENT_SECRET = "e45bc4e98b31dae2c45d82a86eaf01c475f96607"
REDIRECT_URI  = "http://localhost"
TOKEN_FILE    = "data/namorada/token.json"

# ── 1. Gera e abre o link de autorização ────────────────────────────────────
auth_url = (
    f"https://www.strava.com/oauth/authorize"
    f"?client_id={CLIENT_ID}"
    f"&response_type=code"
    f"&redirect_uri={REDIRECT_URI}"
    f"&approval_prompt=force"
    f"&scope=activity:read_all,read"
)

print("\n🔗 Abrindo o link de autorização no navegador...")
print("   (Se não abrir automático, copie e cole o link abaixo)\n")
print(f"   {auth_url}\n")
webbrowser.open(auth_url)

print("─" * 60)
print("IMPORTANTE:")
print("  • Faça login com a conta do Strava DELA")
print("  • Clique em Autorizar")
print("  • O navegador vai abrir uma página de erro — isso é normal")
print("  • Copie a URL COMPLETA da barra de endereço")
print("─" * 60)

callback_url = input("\nCole a URL aqui: ").strip()

# ── 2. Extrai o code da URL ──────────────────────────────────────────────────
if "code=" in callback_url:
    code = callback_url.split("code=")[1].split("&")[0]
else:
    code = callback_url.strip()

print(f"\n🔑 Code extraído: {code[:10]}...")
print("🔄 Trocando code por token com escopo correto...")

# ── 3. Troca o code pelo token ───────────────────────────────────────────────
response = requests.post(
    "https://www.strava.com/oauth/token",
    data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          code,
        "grant_type":    "authorization_code",
    }
)

token_data = response.json()

if "access_token" not in token_data:
    print(f"\n❌ Erro ao obter token: {token_data}")
else:
    os.makedirs("data/namorada", exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=4)

    print(f"\n✅ Token salvo em {TOKEN_FILE}")
    print(f"   Scope:   {token_data.get('scope', 'N/A')}")
    print(f"   Atleta:  {token_data.get('athlete', {}).get('firstname', '?')} "
          f"{token_data.get('athlete', {}).get('lastname', '')}")
    print("\n🚀 Agora rode: python mainNamorada.py")