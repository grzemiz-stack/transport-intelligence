"""Telegram Setup — jednorazowe logowanie i utworzenie pliku sesji.

Uzycie:
    python -m src.agents.telegram_setup

Ten skrypt:
1. Pyta o numer telefonu (interaktywnie)
2. Wysyla kod weryfikacyjny przez Telegram
3. Pyta o kod (interaktywnie)
4. Tworzy plik sesji (.session) w katalogu projektu
5. Plik sesji jest uzywany przez telegram_agent.py (bez ponownego logowania)

WAZNE: Uruchom TEN SKRYPT RAZ na serwerze przez SSH interaktywnie:
    ssh -p 2222 deploy@178.104.73.255
    cd /var/www/transport-intelligence
    python3 -m src.agents.telegram_setup
"""

import asyncio
import os
import sys
from pathlib import Path


def _load_env():
    """Load .env file."""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


async def setup():
    _load_env()

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    session_name = os.environ.get("TELEGRAM_SESSION_NAME", "ti_session")

    if not api_id or not api_hash:
        print("ERROR: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
        print()
        print("Add to .env:")
        print("  TELEGRAM_API_ID=your_api_id")
        print("  TELEGRAM_API_HASH=your_api_hash")
        sys.exit(1)

    api_id = int(api_id)
    session_path = Path(__file__).parent.parent.parent / session_name

    print("=" * 60)
    print("Telegram Setup — Transport Intelligence")
    print("=" * 60)
    print()
    print(f"API ID:       {api_id}")
    print(f"Session file: {session_path}.session")
    print()

    from telethon import TelegramClient

    client = TelegramClient(str(session_path), api_id, api_hash)

    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Already authorized as: {me.first_name} (id={me.id})")
        print("Session file already exists — no setup needed.")
        await client.disconnect()
        return

    # Interactive login
    phone = input("Enter phone number (with country code, e.g. +48123456789): ").strip()
    if not phone:
        print("ERROR: Phone number required")
        await client.disconnect()
        sys.exit(1)

    print(f"Sending verification code to {phone}...")
    await client.send_code_request(phone)

    code = input("Enter the verification code: ").strip()
    if not code:
        print("ERROR: Verification code required")
        await client.disconnect()
        sys.exit(1)

    try:
        await client.sign_in(phone, code)
    except Exception as e:
        if "Two-step verification" in str(e) or "password" in str(e).lower():
            password = input("Two-factor auth enabled. Enter your password: ").strip()
            await client.sign_in(password=password)
        else:
            raise

    me = await client.get_me()
    print()
    print("=" * 60)
    print(f"SUCCESS! Logged in as: {me.first_name} {me.last_name or ''} (id={me.id})")
    print(f"Session saved to: {session_path}.session")
    print()
    print("You can now run:")
    print("  python -m src.agents.telegram_runner --scan-once")
    print("  python -m src.agents.telegram_runner --listen")
    print("=" * 60)

    await client.disconnect()


def main():
    asyncio.run(setup())


if __name__ == "__main__":
    main()
