import requests
import time
import json
import os

CLIENT_ID = "226533"
CLIENT_SECRET = "ca333572e6dad946b2d4c40c7f216f2bf916510a"
TOKEN_FILE = "data/token.json"


# =========================
# AUTH (STRAVA)
# =========================

def get_access_token(code):
    url = "https://www.strava.com/oauth/token"

    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code"
    }

    response = requests.post(url, data=payload)
    return response.json()


def refresh_access_token(refresh_token):
    url = "https://www.strava.com/oauth/token"

    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    response = requests.post(url, data=payload)
    return response.json()


# =========================
# TOKEN STORAGE
# =========================

def save_token(token_data):
    os.makedirs("data", exist_ok=True)

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=4)


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None

    with open(TOKEN_FILE, "r") as f:
        return json.load(f)


def is_token_expired(token_data):
    if "expires_at" not in token_data:
        raise ValueError(f"Token inválido: {token_data}")

    return time.time() > token_data["expires_at"]


# =========================
# TOKEN FLOW
# =========================

def get_valid_token():
    token_data = load_token()

    # 🔐 primeira vez
    if not token_data:
        print("❌ Token não encontrado.")
        print("👉 Gere um code manualmente e rode novamente com ele.")
        return None

    # 🔄 refresh automático
    if is_token_expired(token_data):
        print("🔄 Token expirado, atualizando...")
        token_data = refresh_access_token(token_data["refresh_token"])

        if "access_token" not in token_data:
            print("❌ Erro ao atualizar token:")
            print(token_data)
            return None

        save_token(token_data)
    else:
        print("✅ Token válido")

    return token_data["access_token"]