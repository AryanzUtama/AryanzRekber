"""
Bot Cek Email Moonton — Fase 1
Fitur:
  /cek email@contoh.com  → cek apakah email terhubung ke akun Moonton
  /stats                 → total email yang pernah dicek
Keamanan:
  - Hanya Telegram user ID yang terdaftar yang bisa pakai
  - Email TIDAK disimpan, hanya counter angka
"""

import asyncio
import json
import logging
import random
import re
import time
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

# ================== KONFIGURASI (WAJIB DIISI) ==================
BOT_TOKEN = "ISI_TOKEN_DARI_BOTFATHER"
OWNER_ID = 0  # isi dengan Telegram user ID kamu (angka, bukan username)

# Endpoint Moonton. PENTING: verifikasi dulu dengan curl sebelum dipakai,
# karena endpoint bisa berubah. Lihat README untuk cara ujinya.
MOONTON_ENDPOINT = "https://accountmoonton.com/moonton/password/v1/forget"

# Kata kunci di respons untuk menentukan hasil (sesuaikan setelah uji curl).
# Respons "email terdaftar" biasanya mengandung kata seperti "sent"/"success"
KW_CONNECTED = ["success", "sent", "kami telah mengirim"]
# Respons "email tidak terdaftar" mengandung kata seperti "not found"/"not registered"
KW_NOT_CONNECTED = ["not found", "not registered", "tidak terdaftar", "does not exist"]

COOLDOWN_SECONDS = 10        # jeda minimum antar request ke Moonton
COOLDOWN_JITTER = 5          # tambahan acak 0-5 detik biar tidak pola
REQUEST_TIMEOUT = 20         # detik
COUNTER_FILE = "counter.txt" # cuma 1 angka, tidak ada email tersimpan
# ================================================================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

_last_request = 0.0

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

# deteksi typo domain umum -> saran perbaikan
TYPO_DOMAINS = {
    "gmial.com": "gmail.com",
    "gmal.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gnail.com": "gmail.com",
    "yaho.com": "yahoo.com",
    "yahooo.com": "yahoo.com",
    "outlok.com": "outlook.com",
    "hotmial.com": "hotmail.com",
    "icloud.con": "icloud.com",
    "gmail.co": "gmail.com",
    "gmail.cm": "gmail.com",
}


def owner_only(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == OWNER_ID


def get_counter() -> int:
    try:
        return int(Path(COUNTER_FILE).read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def bump_counter() -> None:
    Path(COUNTER_FILE).write_text(str(get_counter() + 1))


async def ask_moonton(email: str) -> str:
    """Kirim request ke Moonton, kembalikan teks respons."""
    payload = {"email": email}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            MOONTON_ENDPOINT,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        ) as resp:
            body = await resp.text()
            return body.lower()


async def cooldown_wait() -> None:
    global _last_request
    wait = COOLDOWN_SECONDS + random.uniform(0, COOLDOWN_JITTER)
    elapsed = time.monotonic() - _last_request
    if elapsed < wait:
        await asyncio.sleep(wait - elapsed)
    _last_request = time.monotonic()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not owner_only(message):
        return  # diam saja
    await message.answer(
        "Bot Cek Moonton siap.\n"
        "\nPerintah:\n"
        "/cek email@contoh.com — cek email terhubung ke Moonton atau tidak\n"
        "/stats — total email yang pernah kamu cek"
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not owner_only(message):
        return
    await message.answer(f"Total email yang pernah dicek: {get_counter()}")


@dp.message(Command("cek"))
async def cmd_cek(message: Message, command: CommandObject):
    if not owner_only(message):
        return

    email = (command.args or "").strip().lower()

    # validasi format
    if not email:
        await message.answer("Cara pakai: /cek email@contoh.com")
        return
    if not EMAIL_RE.match(email):
        await message.answer("Format email salah. Contoh benar: /cek nama@gmail.com")
        return

    # cek typo domain
    domain = email.split("@", 1)[1]
    if domain in TYPO_DOMAINS:
        await message.answer(
            f"Mungkin maksudnya *{email.split('@', 1)[0]}@{TYPO_DOMAINS[domain]}*? "
            "Coba kirim ulang dengan ejaan yang benar.",
            parse_mode="Markdown",
        )
        return

    status = await message.answer("Mengecek, tunggu sebentar...")

    try:
        await cooldown_wait()
        body = await ask_moonton(email)
    except asyncio.TimeoutError:
        await status.edit_text("Moonton tidak menjawab (timeout). Coba lagi nanti.")
        return
    except Exception as e:
        logging.exception("request gagal")
        await status.edit_text(f"Gagal menghubungi Moonton: {type(e).__name__}")
        return

    if any(k in body for k in KW_NOT_CONNECTED):
        bump_counter()
        await status.edit_text("Email ini *tidak terhubung* ke akun Moonton.", parse_mode="Markdown")
    elif any(k in body for k in KW_CONNECTED):
        bump_counter()
        await status.edit_text("Email ini *terhubung* ke akun Moonton.", parse_mode="Markdown")
    else:
        # respons tidak dikenali — endpoint mungkin berubah
        logging.warning("Respons tidak dikenali: %s", body[:300])
        await status.edit_text(
            "Bot tidak bisa membaca jawaban Moonton (respons berubah?). "
            "Cek log server untuk melihat respons mentahnya."
        )


async def main():
    if BOT_TOKEN == "ISI_TOKEN_DARI_BOTFATHER" or OWNER_ID == 0:
        raise SystemExit("Isi dulu BOT_TOKEN dan OWNER_ID di bagian konfigurasi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
      
