"""
=======================================================
  MONITEUR CROUS - version GitHub Actions (un seul passage)
=======================================================
"""

import hashlib
import os
import sys
from datetime import datetime, timezone

import requests

URL_A_SURVEILLER = "https://trouverunlogement.lescrous.fr/tools/47/search?bounds=7.1819535_43.7607635_7.323912_43.6454189&locationName=Nice"

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.txt")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def envoyer_telegram(texte: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant - notification non envoyee.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": texte}, timeout=15)
        r.raise_for_status()
        print("Notification Telegram envoyee.")
    except Exception as e:
        print(f"Erreur envoi Telegram : {e}")


def extraire_contenu(page_html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page_html, "html.parser")
        for tag in soup(["script", "style", "noscript", "meta"]):
            tag.decompose()
        section = (
            soup.find("ul", class_=lambda c: c and "results" in c.lower())
            or soup.find("div", class_=lambda c: c and "result" in c.lower())
            or soup.find("main")
            or soup.body
        )
        return section.get_text(separator=" ", strip=True) if section else soup.get_text()
    except Exception:
        return page_html


def hash_contenu(texte: str) -> str:
    return hashlib.md5(texte.encode("utf-8", errors="ignore")).hexdigest()


def lire_etat_precedent():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    return None


def ecrire_etat(hash_actuel: str) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(hash_actuel)


def main() -> None:
    heure = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{heure}] Verification en cours...")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright non installe.")
        sys.exit(1)

    with sync_playwright() as p:
        navigateur = p.chromium.launch(headless=True)
        contexte = navigateur.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = contexte.new_page()

        try:
            page.goto(URL_A_SURVEILLER, wait_until="networkidle", timeout=30000)
            texte_actuel = extraire_contenu(page.content())
        except Exception as e:
            print(f"Erreur lors du chargement de la page : {e}")
            navigateur.close()
            sys.exit(1)

        navigateur.close()

    hash_actuel = hash_contenu(texte_actuel)
    hash_precedent = lire_etat_precedent()

    if hash_precedent is None:
        print("Premier passage - etat de reference enregistre, pas d'alerte envoyee.")
        ecrire_etat(hash_actuel)
        return

    if hash_actuel != hash_precedent:
        print("Changement detecte !")
        apercu = texte_actuel[:500].replace("\n", " ")
        envoyer_telegram(
            f"Changement detecte sur le Crous Nice !\n\n"
            f"Heure : {heure}\n\n"
            f"Apercu : {apercu}...\n\n"
            f"Lien : {URL_A_SURVEILLER}"
        )
        ecrire_etat(hash_actuel)
    else:
        print("Aucun changement.")


if __name__ == "__main__":
    main()
