import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton,
                           ReplyKeyboardMarkup, KeyboardButton, FSInputFile)

import os
TOKEN = os.getenv("TOKEN", "")
CHANNEL = "apexs_trade"
OWNER = "apexstrade_owner"
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")


async def ai_ask(prompt):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "messages": [{"role": "user", "content": prompt}],
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(url, headers=headers, json=body, timeout=30) as r:
            data = await r.json()
    try:
        return data["choices"][0]["message"]["content"]
    except:
        print("AI error:", data)
        return None

async def ai_analysis(coin, tf_name, price, change, low, high, poi):
    prompt = f"""Ты крипто-аналитик. {coin}/USDT, ТФ {tf_name}.
Цена: ${price:.2f}, изменение: {change:+.2f}%
Поддержка: ${low:.2f}
Сопротивление: ${high:.2f}
POI: ${poi:.2f}

Ответь СТРОГО в формате JSON без markdown:
{{
  "thoughts": "3-4 строки анализа, самое важное",
  "long_entry": 84000,
  "long_stop": 83400,
  "long_tp": 85500,
  "short_entry": 82500,
  "short_stop": 83100,
  "short_tp": 81000,
  "rr": "1:2.5",
  "forecast": "up",
  "labels": ["ПРОБОЙ", "ОТКАТ"]
}}"""

    r = await ai_ask(prompt)
    if not r:
        return None
    try:
        r = r.strip().replace("```json", "").replace("```", "").strip()
        import json
        return json.loads(r)
    except:
        print("AI JSON error:", r)
        return None

bot = Bot(token=TOKEN)
dp = Dispatcher()


async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id="@" + CHANNEL, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False


def main_menu():
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💰 Ликвидность"), KeyboardButton(text="📊 ОИ")],
        [KeyboardButton(text="⚖️ Дисбаланс"), KeyboardButton(text="🔥 Ликвидации")],
        [KeyboardButton(text="🧠 Анализ"), KeyboardButton(text="Новости")],
        [KeyboardButton(text="📖 Инструкция"), KeyboardButton(text="📈 EMA")],
        [KeyboardButton(text="💬 Связь")],
    ], resize_keyboard=True)
    return kb


WELCOME = (
    "📊 Вас приветствует бот канала APEXS | TRADE\n\n"
    "Для выбора раздела используйте вкладки ниже ⬇️\n\n"
    "⚠️ Перед использованием советую прочитать «Инструкция».\n\n"
    "📌 Бот — это помощник, а не финансовая рекомендация.\n"
    "Все решения принимаете вы сами. Автор не несёт ответственности за сделки."
)


async def send_welcome(chat_id, edit_message=None):
    photo = "https://files.catbox.moe/zyxpex.jpg" 
    if edit_message:
        try:
            await edit_message.delete()
        except:
            pass
    await bot.send_photo(chat_id, photo=photo, caption=WELCOME, reply_markup=main_menu())


@dp.message(CommandStart())
async def start(msg: types.Message):
    if not await is_subscribed(msg.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url="https://t.me/apexs_trade")],
            [InlineKeyboardButton(text="✅ Проверить", callback_data="check_sub")],
        ])
        await msg.answer("👋 Для использования бота подпишись на канал:", reply_markup=kb)
        return
    await send_welcome(msg.chat.id)


@dp.callback_query(lambda c: c.data == "check_sub")
async def check_sub(call: types.CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        await send_welcome(call.message.chat.id)
    else:
        await call.answer("❌ Ты ещё не подписан!", show_alert=True)


@dp.message(F.text == "💬 Связь")
async def support(msg: types.Message):
    sent = await msg.answer(f"💬 Связь с админом:\n\n@{OWNER}")
    support_msgs[msg.from_user.id] = sent.message_id

from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp


async def get_disbalance(symbol):
    url = f"https://api.bybit.com/v5/market/account-ratio?category=linear&symbol={symbol}USDT&period=1h&limit=1"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            data = await r.json()
    if data.get("retCode") != 0 or not data.get("result", {}).get("list"):
        return None
    item = data["result"]["list"][0]
    buy = float(item["buyRatio"]) * 100
    sell = float(item["sellRatio"]) * 100
    return buy, sell


async def get_price_data(symbol):
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}USDT&interval=60&limit=24"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            data = await r.json()
    if data.get("retCode") != 0 or not data.get("result", {}).get("list"):
        return None
    klines = data["result"]["list"]
    closes = [float(k[4]) for k in reversed(klines)]
    price = closes[-1]
    change = (closes[-1] - closes[0]) / closes[0] * 100
    high = max(float(k[2]) for k in klines)
    low = min(float(k[3]) for k in klines)
    return price, change, high, low, closes


async def get_funding(symbol):
    url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}USDT"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            data = await r.json()
    try:
        return float(data["result"]["list"][0]["fundingRate"]) * 100
    except:
        return None

async def get_open_interest(symbol, interval):
    url = f"https://api.bybit.com/v5/market/open-interest?category=linear&symbol={symbol}USDT&intervalTime={interval}&limit=100"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            data = await r.json()
    if data.get("retCode") != 0 or not data.get("result", {}).get("list"):
        return None
    items = list(reversed(data["result"]["list"]))
    ois = [(int(i["timestamp"]), float(i["openInterest"])) for i in items]
    return ois

def draw_oi(symbol, tf, ois, price):
    W, H = 1200, 650
    img = Image.new("RGB", (W, H), (10, 14, 25))
    d = ImageDraw.Draw(img)

    try:
        fb = ImageFont.truetype("arialbd.ttf", 55)
        fm = ImageFont.truetype("arialbd.ttf", 32)
        fs = ImageFont.truetype("arial.ttf", 24)
        fxs = ImageFont.truetype("arial.ttf", 18)
    except:
        fb = fm = fs = fxs = ImageFont.load_default()

    d.rectangle([0, 0, W, 70], fill=(30, 45, 70))
    d.text((30, 35), "BingX INFO", fill=(80, 200, 120), font=fm, anchor="lm")
    d.text((W // 2, 35), f"{symbol.upper()}  •  {tf}", fill="white", font=fm, anchor="mm")
    d.text((W - 30, 35), "@apexstrade", fill=(80, 200, 120), font=fs, anchor="rm")

    if not ois:
        return None, None

    values = [v * price for _, v in ois]
    current = values[-1]
    change = (values[-1] - values[0]) / values[0] * 100 if values[0] else 0

    d.text((30, 110), f"${current:,.0f}", fill="white", font=fb, anchor="lm")
    col = (80, 220, 130) if change >= 0 else (230, 80, 80)
    arrow = "▲" if change >= 0 else "▼"
    d.text((30, 175), f"Открытый интерес ({tf})", fill=(150, 160, 180), font=fxs, anchor="lm")
    d.text((30, 210), f"{arrow} {change:.2f}%", fill=col, font=fs, anchor="lm")

    # график
    gx1, gx2, gy1, gy2 = 60, 1140, 300, 560
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    points = []
    for i, v in enumerate(values):
        x = gx1 + (gx2 - gx1) * i / (len(values) - 1) if len(values) > 1 else gx1
        y = gy2 - (gy2 - gy1) * (v - mn) / rng
        points.append((x, y))
    d.line(points, fill=(80, 220, 130), width=4)

    text = f"📊 {symbol.upper()} / USDT — ОИ\n"
    text += f"📈 ТФ: {tf}\n\n"
    text += f"💰 Открытый интерес: ${current:,.0f}\n"
    text += f"{arrow} Изменение: {change:.2f}%"

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf, text

def draw_analysis(symbol, tf, klines):
    W, H = 1200, 700
    img = Image.new("RGB", (W, H), (10, 14, 25))
    d = ImageDraw.Draw(img)

    try:
        fb = ImageFont.truetype("arialbd.ttf", 36)
        fm = ImageFont.truetype("arialbd.ttf", 22)
        fs = ImageFont.truetype("arial.ttf", 16)
    except:
        fb = fm = fs = ImageFont.load_default()

    closes = [c for c, v in klines]
    highs = [h for h, v in klines]
    lows = [l for l, v in klines]
    price = closes[-1]
    high = max(highs)
    low = min(lows)

    # шапка
    d.rectangle([0, 0, W, 60], fill=(30, 45, 70))
    d.text((20, 30), "BingX INFO", fill=(80, 200, 120), font=fm, anchor="lm")
    d.text((W // 2, 30), f"{symbol.upper()}  •  {tf}", fill="white", font=fm, anchor="mm")
    d.text((W - 20, 30), "@apexstrade", fill=(80, 200, 120), font=fs, anchor="rm")

    # график
    gx1, gx2, gy1, gy2 = 60, 1140, 100, 600
    mn, mx = low, high
    rng = mx - mn if mx != mn else 1
    step = (gx2 - gx1) / len(klines)
    bw = step * 0.6

    for i, (c, v) in enumerate(klines):
        h, l, o = highs[i], lows[i], (closes[i-1] if i > 0 else c)
        x = gx1 + i * step + step / 2
        yh = gy2 - (gy2 - gy1) * (h - mn) / rng
        yl = gy2 - (gy2 - gy1) * (l - mn) / rng
        yo = gy2 - (gy2 - gy1) * (o - mn) / rng
        yc = gy2 - (gy2 - gy1) * (c - mn) / rng
        color = (80, 200, 100) if c >= o else (230, 80, 80)
        d.line([(x, yh), (x, yl)], fill=color, width=1)
        d.rectangle([x - bw/2, min(yo, yc), x + bw/2, max(yo, yc)], fill=color)

    # POI = 70% объёма
    poi = low + (high - low) * 0.5
    y_poi = gy2 - (gy2 - gy1) * (poi - mn) / rng
    d.line([(gx1, y_poi), (gx2, y_poi)], fill=(120, 180, 255), width=2)

    # Поддержка / Сопротивление
    y_sup = gy2 - (gy2 - gy1) * (low - mn) / rng
    y_res = gy2 - (gy2 - gy1) * (high - mn) / rng
    d.line([(gx1, y_sup), (gx2, y_sup)], fill=(80, 220, 130), width=2)
    d.line([(gx1, y_res), (gx2, y_res)], fill=(230, 80, 80), width=2)
    d.text((gx2 + 5, y_sup), f"${low:.2f}", fill=(80, 220, 130), font=fs, anchor="lm")
    d.text((gx2 + 5, y_res), f"${high:.2f}", fill=(230, 80, 80), font=fs, anchor="lm")
    d.text((gx2 + 5, y_poi), f"POI ${poi:.2f}", fill=(120, 180, 255), font=fs, anchor="lm")

    # зона интереса (жёлтая)
    zi_low = low + (high - low) * 0.4
    zi_high = low + (high - low) * 0.6
    y_zi1 = gy2 - (gy2 - gy1) * (zi_high - mn) / rng
    y_zi2 = gy2 - (gy2 - gy1) * (zi_low - mn) / rng
    d.rectangle([gx1, y_zi1, gx2, y_zi2], fill=(60, 50, 20))
    d.text((gx2 + 5, (y_zi1 + y_zi2) // 2), f"Зона", fill=(240, 200, 60), font=fs, anchor="lm")

    # цена справа
    y_price = gy2 - (gy2 - gy1) * (price - mn) / rng
    d.text((gx2 + 5, y_price), f"${price:.2f}", fill="white", font=fs, anchor="lm")

    return img, low, high, poi, price

def draw_analysis_v3(symbol, tf_name, klines, ai_data, price, change):
    W, H = 1400, 800
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    try:
        fbig = ImageFont.truetype("arialbd.ttf", 40)
        fb = ImageFont.truetype("arialbd.ttf", 22)
        fs = ImageFont.truetype("arial.ttf", 14)
        fxs = ImageFont.truetype("arial.ttf", 11)
    except:
        fbig = fb = fs = fxs = ImageFont.load_default()

    closes = [c for c, v in klines]
    highs = [h for h, v in klines]
    lows = [l for l, v in klines]
    high = max(highs)
    low = min(lows)
    last = closes[-1]

    d.text((20, 30), f"{last:.1f}", fill=(230, 50, 50) if change < 0 else (38, 166, 91), font=fbig)
    d.text((250, 35), f"{symbol.upper()}  •  {tf_name}  •  {change:+.2f}%", fill=(100, 100, 100), font=fb)

    gx1, gx2, gy1, gy2 = 60, 1150, 120, 720
    mn = low - (high - low) * 0.06
    mx = high + (high - low) * 0.06
    rng = mx - mn if mx != mn else 1
    step = (gx2 - gx1) / len(klines)
    bw = step * 0.7

    # Свечи (крупные, с тенями)
    for i in range(len(klines)):
        c, h, l = closes[i], highs[i], lows[i]
        o = closes[i-1] if i > 0 else c
        x = gx1 + i * step + step / 2
        yh = gy2 - (gy2 - gy1) * (h - mn) / rng
        yl = gy2 - (gy2 - gy1) * (l - mn) / rng
        yo = gy2 - (gy2 - gy1) * (o - mn) / rng
        yc = gy2 - (gy2 - gy1) * (c - mn) / rng
        col = (38, 166, 91) if c >= o else (230, 50, 50)
        d.line([(x, yh), (x, yl)], fill=col, width=1)
        d.rectangle([x - bw/2, min(yo, yc), x + bw/2, max(yo, yc)], fill=col)

    # Прозрачные зоны
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # POI
    poi = low + (high - low) * 0.5
    y_poi = gy2 - (gy2 - gy1) * (poi - mn) / rng
    od.rectangle([gx1, y_poi - 25, gx2, y_poi + 25], fill=(150, 100, 220, 60))

    # Зона интереса
    zi = low + (high - low) * 0.25
    y_zi = gy2 - (gy2 - gy1) * (zi - mn) / rng
    od.rectangle([gx1, y_zi - 20, gx2, y_zi + 20], fill=(100, 150, 220, 60))

    # Сопротивление (прозрачная)
    y_res = gy2 - (gy2 - gy1) * (high - mn) / rng
    od.rectangle([gx1, y_res - 20, gx2, y_res + 20], fill=(230, 80, 80, 50))

    # Поддержка (прозрачная)
    y_sup = gy2 - (gy2 - gy1) * (low - mn) / rng
    od.rectangle([gx1, y_sup - 20, gx2, y_sup + 20], fill=(38, 166, 91, 50))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)

    # Линии уровней + плашки
    def level_line(y_val, color, label, sub=""):
        y = gy2 - (gy2 - gy1) * (y_val - mn) / rng
        d.line([(gx1, y), (gx2, y)], fill=color, width=2)
        d.line([(gx2, y), (gx2 + 30, y)], fill=color, width=1)
        d.rectangle([gx2 + 30, y - 14, gx2 + 130, y + 14], fill=color)
        d.text((gx2 + 80, y), f"{y_val:.0f}", fill="white", font=fs, anchor="mm")
        d.text((gx1 + 10, y - 30), label, fill=color, font=fs)
        if sub:
            d.text((gx1 + 10, y + 22), sub, fill=(120, 120, 120), font=fxs)

    level_line(high, (230, 80, 80), "СОПРОТИВЛЕНИЕ", "здесь много стопов")
    level_line(low, (38, 166, 91), "ПОДДЕРЖКА", "ключевая зона")

    # Текущая цена
    y_p = gy2 - (gy2 - gy1) * (last - mn) / rng
    d.line([(gx1, y_p), (gx2 + 30, y_p)], fill=(150, 150, 150), width=1)
    d.rectangle([gx2 + 30, y_p - 14, gx2 + 130, y_p + 14], fill=(30, 30, 30))
    d.text((gx2 + 80, y_p), f"{last:.0f}", fill="white", font=fs, anchor="mm")

    # Шкала справа
    for k in range(6):
        y_val = mn + (mx - mn) * k / 5
        y_pos = gy2 - (gy2 - gy1) * (y_val - mn) / rng
        d.text((W - 20, y_pos), f"{y_val:.1f}", fill=(120, 120, 120), font=fxs, anchor="rm")
        d.line([(gx2, y_pos), (gx2 + 5, y_pos)], fill=(200, 200, 200), width=1)

    return img

def draw_indicator(symbol, kind, closes):
    W, H = 1200, 650
    img = Image.new("RGB", (W, H), (10, 14, 25))
    d = ImageDraw.Draw(img)

    try:
        fb = ImageFont.truetype("arialbd.ttf", 50)
        fm = ImageFont.truetype("arialbd.ttf", 30)
        fs = ImageFont.truetype("arial.ttf", 22)
        fxs = ImageFont.truetype("arial.ttf", 18)
    except:
        fb = fm = fs = fxs = ImageFont.load_default()

    d.rectangle([0, 0, W, 70], fill=(30, 45, 70))
    d.text((30, 35), "BingX INFO", fill=(80, 200, 120), font=fm, anchor="lm")
    d.text((W // 2, 35), f"{symbol.upper()}  •  {kind}", fill="white", font=fm, anchor="mm")
    d.text((W - 30, 35), "@apexstrade", fill=(80, 200, 120), font=fs, anchor="rm")

    gx1, gx2, gy1, gy2 = 60, 1140, 120, 560

    if kind == "EMA 50":
        ema = calc_ema(closes)
        if not ema:
            return None, None
        line_vals = closes[len(closes) - len(ema):]
        mn = min(min(line_vals), min(ema))
        mx = max(max(line_vals), max(ema))
        rng = mx - mn if mx != mn else 1
        p1 = [(gx1 + (gx2 - gx1) * i / (len(line_vals) - 1), gy2 - (gy2 - gy1) * (v - mn) / rng) for i, v in enumerate(line_vals)]
        p2 = [(gx1 + (gx2 - gx1) * i / (len(ema) - 1), gy2 - (gy2 - gy1) * (v - mn) / rng) for i, v in enumerate(ema)]
        d.line(p1, fill=(120, 140, 180), width=3)
        d.line(p2, fill=(255, 200, 60), width=4)
        d.text((60, 90), f"Цена: ${closes[-1]:.4f}", fill="white", font=fs, anchor="lm")
        d.text((W - 60, 90), f"EMA 50: ${ema[-1]:.4f}", fill=(255, 200, 60), font=fs, anchor="rm")
        text = f"📈 {symbol.upper()} — EMA 50\n\n💰 Цена: ${closes[-1]:.4f}\n🟡 EMA 50: ${ema[-1]:.4f}"
        diff = (closes[-1] - ema[-1]) / ema[-1] * 100
        if diff > 0:
            text += f"\n\n🟢 Цена выше EMA ({diff:.2f}%) — бычий сигнал"
        else:
            text += f"\n\n🔴 Цена ниже EMA ({diff:.2f}%) — медвежий сигнал"

    elif kind == "RSI":
        rsi = calc_rsi(closes)
        if not rsi:
            return None, None
        p = [(gx1 + (gx2 - gx1) * i / (len(rsi) - 1), gy2 - (gy2 - gy1) * v / 100) for i, v in enumerate(rsi)]
        d.line([(gx1, gy2 - (gy2 - gy1) * 0.7), (gx2, gy2 - (gy2 - gy1) * 0.7)], fill=(230, 80, 80), width=2)
        d.line([(gx1, gy2 - (gy2 - gy1) * 0.3), (gx2, gy2 - (gy2 - gy1) * 0.3)], fill=(80, 220, 130), width=2)
        d.line(p, fill=(120, 180, 255), width=4)
        cur = rsi[-1]
        d.text((60, 90), f"RSI: {cur:.2f}", fill="white", font=fb, anchor="lm")
        text = f"📊 {symbol.upper()} — RSI\n\n📈 RSI: {cur:.2f}"
        if cur > 70:
            text += "\n\n🔴 Перекупленность (возможен откат)"
        elif cur < 30:
            text += "\n\n🟢 Перепроданность (возможен рост)"
        else:
            text += "\n\n⚪️ Нейтральная зона"

    elif kind == "CVD":
        cvd, cum = [], 0
        for i in range(1, len(closes)):
            cum += closes[i] - closes[i-1]
            cvd.append(cum)
        if not cvd:
            return None, None
        mn, mx = min(cvd), max(cvd)
        rng = mx - mn if mx != mn else 1
        p = [(gx1 + (gx2 - gx1) * i / (len(cvd) - 1), gy2 - (gy2 - gy1) * (v - mn) / rng) for i, v in enumerate(cvd)]
        d.line(p, fill=(180, 120, 255), width=4)
        col = (80, 220, 130) if cvd[-1] >= 0 else (230, 80, 80)
        d.text((60, 90), f"CVD: {cvd[-1]:.2f}", fill=col, font=fb, anchor="lm")
        text = f"📉 {symbol.upper()} — CVD\n\nCVD: {cvd[-1]:.2f}"
        text += "\n\n🟢 Покупатели доминируют" if cvd[-1] > 0 else "\n\n🔴 Продавцы доминируют"

    else:
        return None, None

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf, text

def draw_disbalance(symbol, buy, sell, price, change, high, low, closes, funding):
    W, H = 1200, 600
    img = Image.new("RGB", (W, H), (10, 14, 25))
    d = ImageDraw.Draw(img)

    try:
        fb = ImageFont.truetype("arialbd.ttf", 65)
        fm = ImageFont.truetype("arialbd.ttf", 40)
        fs = ImageFont.truetype("arial.ttf", 26)
        fxs = ImageFont.truetype("arial.ttf", 20)
    except:
        fb = fm = fs = fxs = ImageFont.load_default()

    d.rectangle([0, 0, W, 80], fill=(30, 45, 70))
    d.text((30, 40), "BingX INFO", fill=(80, 200, 120), font=fm, anchor="lm")
    d.text((W // 2, 40), symbol.upper(), fill="white", font=fm, anchor="mm")
    d.text((W - 30, 40), "@apexstrade", fill=(80, 200, 120), font=fs, anchor="rm")

    gx1, gx2, gy1, gy2 = 60, 640, 380, 560
    mn, mx = min(closes), max(closes)
    rng = mx - mn if mx != mn else 1
    points = []
    for i, c in enumerate(closes):
        x = gx1 + (gx2 - gx1) * i / (len(closes) - 1)
        y = gy2 - (gy2 - gy1) * (c - mn) / rng
        points.append((x, y))
    d.line(points, fill=(80, 220, 130), width=3)

    d.text((60, 130), f"${price:.4f}", fill="white", font=fb, anchor="lm")
    col = (80, 220, 130) if change >= 0 else (230, 80, 80)
    arrow = "▲" if change >= 0 else "▼"
    d.text((60, 220), f"{arrow} {change:.2f}% за 24ч", fill=col, font=fs, anchor="lm")
    d.text((60, 270), f"МИН ${low:.4f}", fill=(200, 80, 80), font=fxs, anchor="lm")
    d.text((200, 270), f"МАКС ${high:.4f}", fill=(80, 220, 130), font=fxs, anchor="lm")

    d.line([(680, 100), (680, 560)], fill=(40, 50, 70), width=2)
    d.text((720, 130), "Лонг / Шорт", fill=(150, 160, 180), font=fxs, anchor="lm")

    bx1, bx2, by1, by2 = 720, 1150, 170, 220
    bw = bx2 - bx1
    d.rounded_rectangle([bx1, by1, bx2, by2], radius=25, fill=(230, 80, 80))
    d.rounded_rectangle([bx1, by1, bx1 + bw * buy / 100, by2], radius=25, fill=(80, 200, 100))
    d.text((bx1 + bw * buy / 200, (by1 + by2) // 2), f"{buy:.0f}% L", fill="black", font=fs, anchor="mm")
    d.text((bx2 - bw * sell / 200, (by1 + by2) // 2), f"{sell:.0f}% S", fill="black", font=fs, anchor="mm")

    d.text((720, 280), f"Long: {buy:.2f}%", fill=(80, 220, 130), font=fs, anchor="lm")
    d.text((720, 330), f"Short: {sell:.2f}%", fill=(230, 80, 80), font=fs, anchor="lm")

    if funding is not None:
        fcol = (80, 220, 130) if funding >= 0 else (230, 80, 80)
        d.text((720, 420), "Фандинг (4ч)", fill=(150, 160, 180), font=fxs, anchor="lm")
        d.text((720, 470), f"{funding:+.4f}%", fill=fcol, font=fm, anchor="lm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

async def get_orderbook(symbol):
    url = f"https://api.binance.com/api/v3/depth?symbol={symbol}USDT&limit=5000"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            if r.status != 200:
                return None
            data = await r.json()
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT") as r:
            pdata = await r.json()
    price = float(pdata["price"])
    bids = [(float(p), float(q)) for p, q in data["bids"]]
    asks = [(float(p), float(q)) for p, q in data["asks"]]
    return price, bids, asks



def draw_liquidity(symbol, price, bids, asks, tf):
    tf_percent = {"5м": 0.005, "15м": 0.015, "1ч": 0.025, "4ч": 0.05, "1д": 0.09}
    pct = tf_percent.get(tf, 0.025)
    low = price * (1 - pct)
    high = price * (1 + pct)

    W, H = 1200, 650
    img = Image.new("RGB", (W, H), (10, 14, 25))
    d = ImageDraw.Draw(img)

    try:
        fb = ImageFont.truetype("arialbd.ttf", 55)
        fm = ImageFont.truetype("arialbd.ttf", 32)
        fs = ImageFont.truetype("arial.ttf", 24)
        fxs = ImageFont.truetype("arial.ttf", 18)
    except:
        fb = fm = fs = fxs = ImageFont.load_default()

    d.rectangle([0, 0, W, 70], fill=(30, 45, 70))
    d.text((30, 35), "BingX INFO", fill=(80, 200, 120), font=fm, anchor="lm")
    d.text((W // 2, 35), f"{symbol.upper()}  •  {tf}", fill="white", font=fm, anchor="mm")
    d.text((W - 30, 35), "@apexstrade", fill=(80, 200, 120), font=fs, anchor="rm")

    d.text((30, 110), f"${price:.4f}", fill="white", font=fb, anchor="lm")
    d.text((30, 175), f"Ликвидность ({tf})  •  ${low:.2f} — ${high:.2f}", fill=(150, 160, 180), font=fxs, anchor="lm")

    # фильтр по диапазону
    filt_bids = [(p, q) for p, q in bids if low <= p <= price]
    filt_asks = [(p, q) for p, q in asks if price <= p <= high]

    top_bids = sorted(filt_bids, key=lambda x: -x[1])[:12]
    top_asks = sorted(filt_asks, key=lambda x: -x[1])[:12]
    levels = [(p, q, "bid") for p, q in top_bids] + [(p, q, "ask") for p, q in top_asks]

    if not levels:
        return None, None

    maxq = max(q for _, q, _ in levels)

    y_start = 220
    y_end = 580
    row_h = (y_end - y_start) // len(levels)

    levels_sorted = sorted(levels, key=lambda x: -x[0])
    for i, (p, q, side) in enumerate(levels_sorted):
        y = y_start + i * row_h
        ratio = q / maxq
        if ratio > 0.6:
            color = (255, 255, 255)
            w = W - 60
        elif ratio > 0.3:
            color = (230, 200, 60)
            w = int((W - 60) * 0.75)
        else:
            color = (220, 90, 150)
            w = int((W - 60) * 0.45)
        d.rounded_rectangle([30, y + 4, 30 + w, y + row_h - 4], radius=8, fill=color)
        d.text((40, y + row_h // 2), f"${p:.4f}  •  {q:.1f}", fill="black", font=fxs, anchor="lm")

    # анализ для текста
    strongest = max(levels, key=lambda x: x[1])
    sp, sq, sside = strongest
    side_text = "ПОДДЕРЖКА" if sside == "bid" else "СОПРОТИВЛЕНИЕ"

    top_bid = max(top_bids, key=lambda x: -x[1]) if top_bids else None
    top_ask = max(top_asks, key=lambda x: -x[1]) if top_asks else None

    text = f"💰 {symbol.upper()} / USDT — ${price:.4f}\n"
    text += f"📊 ТФ: {tf}  •  ${low:.2f} — ${high:.2f}\n\n"
    if top_bid:
        text += f"🟢 Поддержка: ${top_bid[0]:.4f} ({top_bid[1]:.1f})\n"
    if top_ask:
        text += f"🔴 Сопротивление: ${top_ask[0]:.4f} ({top_ask[1]:.1f})\n"
    text += f"\n💪 Сильнее всего: {side_text} на ${sp:.4f} ({sq:.1f})"

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf, text



waiting_symbol = {}
support_msgs = {}


@dp.message(F.text == "⚖️ Дисбаланс")
async def disb_start(msg: types.Message):
    waiting_symbol[msg.from_user.id] = "disbalance"
    sent = await msg.answer("✍️ Напишите монету для получения данных (пример: BTC)")
    waiting_symbol[msg.from_user.id] = ("disbalance", sent.message_id)


@dp.message(F.text == "💰 Ликвидность")
async def liq_start(msg: types.Message):
        sent = await msg.answer("💰 Напишите монету (пример: BTC)")
        waiting_symbol[msg.from_user.id] = ("liq", sent.message_id)

@dp.message(F.text == "📊 ОИ")
async def oi_start(msg: types.Message):
    sent = await msg.answer("📊 Напишите монету (пример: BTC)")
    waiting_symbol[msg.from_user.id] = ("oi", sent.message_id)

@dp.message(F.text == "📈 EMA")
async def ind_start(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="EMA 50", callback_data="ind|EMA 50")],
        [InlineKeyboardButton(text="RSI", callback_data="ind|RSI")],
        [InlineKeyboardButton(text="CVD", callback_data="ind|CVD")],
    ])
    await msg.answer("📈 Выбери индикатор:", reply_markup=kb)

@dp.message(F.text == "🧠 Анализ")
async def analysis_start(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Продолжить", callback_data="ai|go")],
    ])
    await msg.answer(
        "🧠 Анализ ИИ\n\n"
        "⚠️ Обновлять анализ советуется раз в 15-30 минут.\n"
        "Не входите без подтверждения.",
        reply_markup=kb
    )


@dp.callback_query(lambda c: c.data == "ai|go")
async def analysis_go(call: types.CallbackQuery):
    await call.message.delete()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTC", callback_data="ai|BTC"),
         InlineKeyboardButton(text="ETH", callback_data="ai|ETH")],
        [InlineKeyboardButton(text="SOL", callback_data="ai|SOL"),
         InlineKeyboardButton(text="XAU", callback_data="ai|XAU")],
    ])
    await call.message.answer("🧠 Выбери монету:", reply_markup=kb)


@dp.callback_query(lambda c: c.data.startswith("ai|") & ~c.data.endswith("go"))
async def analysis_coin(call: types.CallbackQuery):
    coin = call.data.split("|")[1]
    await call.message.delete()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="15м", callback_data=f"aitf|15m|{coin}"),
         InlineKeyboardButton(text="1ч", callback_data=f"aitf|1h|{coin}")],
        [InlineKeyboardButton(text="1д", callback_data=f"aitf|1d|{coin}")],
    ])
    await call.message.answer(f"🧠 {coin} — выбери ТФ:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("ind|"))
async def ind_choice(call: types.CallbackQuery):
    kind = call.data.split("|")[1]
    await call.message.delete()
    sent = await call.message.answer(f"📈 {kind} — напиши монету (пример: BTC)")
    waiting_symbol[call.from_user.id] = (f"ind|{kind}", sent.message_id)


@dp.message(F.text.contains("Новости"))
async def news_start(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Текущие", callback_data="news|current")],
        [InlineKeyboardButton(text="⏪ Прошедшие", callback_data="news|past")],
        [InlineKeyboardButton(text="⏩ Будущие", callback_data="news|future")],
    ])
    await msg.answer("📰 Выбери тип новостей:", reply_markup=kb)

@dp.message()
async def handle_symbol(msg: types.Message):
    if "Инструкция" in (msg.text or ""):
        text = (
            "📖 Инструкция APEXS | TRADE\n\n"
            "⚠️ Бот — это помощник для анализа рынка, "
            "а не финансовый совет. Решения принимаете только вы.\n\n"
            "📋 Вкладки:\n\n"
            "1. 💰 Ликвидность\n"
            "Показывает зоны скопления заявок. Выбираешь монету → ТФ. "
            "Полоски — где много заявок (белые) и мало (розовые).\n\n"
            "2. 📊 ОИ (Открытый интерес)\n"
            "Показывает общий объём открытых позиций в $. "
            "Растёт ОИ — тренд сильный, падает — слабый.\n\n"
            "3. ⚖️ Дисбаланс\n"
            "% лонгов и шортов по аккаунтам. Много лонгов — возможен шорт-сквиз.\n\n"
            "4. 🔥 Ликвидации\n"
            "Скоро. Показывает зоны, где снимают стопы.\n\n"
            "5. 🧠 Анализ ИИ\n"
            "BTC / ETH / XAU / ALT → ТФ. Краткий анализ + вход / стоп / тейк.\n\n"
            "6. 📰 Новости\n"
            "Текущие / Прошедшие / Будущие. По важности.\n\n"
            "7. 📈 EMA / Индикаторы\n"
            "EMA 50 / RSI / CVD.\n\n"
            "8. 💬 Связь\n"
            "Вопросы и проблемы — пиши сюда.\n\n"
            "📌 Обновлять анализ советуется раз в 15-30 минут."
        )
        await msg.answer(text)
        return

    if msg.text == "testai":
        r = await ai_ask("Скажи привет одним словом")
        await msg.answer(f"Ответ ИИ: {r}")
        return

    if msg.from_user.id not in waiting_symbol:
        return
    data = waiting_symbol.pop(msg.from_user.id)
    if not isinstance(data, tuple):
        return
    kind, sent_id = data

    try:
        await bot.delete_message(msg.chat.id, sent_id)
    except:
        pass

    symbol = msg.text.strip().upper()
    if msg.from_user.id in support_msgs:
        try:
            await bot.delete_message(msg.chat.id, support_msgs.pop(msg.from_user.id))
        except:
            pass

    if kind == "disbalance":
        res = await get_disbalance(symbol)
        if not res:
                await msg.answer(f"❌ Монета {symbol} не найдена")
                return
        pd = await get_price_data(symbol)
        if not pd:
            await msg.answer(f"❌ Монета {symbol} не найдена")
            return
        price, change, high, low, closes = pd
        funding = await get_funding(symbol)
        buy, sell = res
        photo = draw_disbalance(symbol, buy, sell, price, change, high, low, closes, funding)
        await msg.answer_photo(types.BufferedInputFile(photo.read(), filename="d.png"))

    elif kind == "liq":
        ob = await get_orderbook(symbol)
        if not ob:
            await msg.answer(f"❌ Монета {symbol} не найдена")
            return
        price, bids, asks = ob
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="5м", callback_data=f"liq|5м|{symbol}"),
             InlineKeyboardButton(text="15м", callback_data=f"liq|15м|{symbol}")],
            [InlineKeyboardButton(text="1ч", callback_data=f"liq|1ч|{symbol}"),
             InlineKeyboardButton(text="4ч", callback_data=f"liq|4ч|{symbol}")],
            [InlineKeyboardButton(text="1д", callback_data=f"liq|1д|{symbol}")],
        ])
        await msg.answer(f"📊 {symbol} — выбери таймфрейм:", reply_markup=kb)

    elif kind == "oi":
        pd = await get_price_data(symbol)
        if not pd:
            await msg.answer(f"❌ Монета {symbol} не найдена")
            return
        price = pd[0]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="15м", callback_data=f"oi|15m|{symbol}"),
             InlineKeyboardButton(text="1ч", callback_data=f"oi|1h|{symbol}")],
            [InlineKeyboardButton(text="1д", callback_data=f"oi|1d|{symbol}")],
        ])
        await msg.answer(f"📊 {symbol} — выбери ТФ:", reply_markup=kb)

    elif kind.startswith("ind|"):
        ind_name = kind.split("|")[1]
        kl = await get_klines(symbol, "60", 100)
        if not kl:
            await msg.answer(f"❌ Монета {symbol} не найдена")
            return
        closes = [c for c, v in kl]
        photo, text = draw_indicator(symbol, ind_name, closes)
        if not photo:
            await msg.answer("❌ Нет данных")
            return
        await msg.answer_photo(
            types.BufferedInputFile(photo.read(), filename="ind.png"),
            caption=text
        )


@dp.callback_query(lambda c: c.data.startswith("liq|"))
async def liq_tf(call: types.CallbackQuery):
    _, tf, symbol = call.data.split("|")
    await call.message.delete()

    ob = await get_orderbook(symbol)
    if not ob:
        await call.message.answer(f"❌ Монета {symbol} не найдена")
        return
    price, bids, asks = ob
    photo, text = draw_liquidity(symbol, price, bids, asks, tf)
    if not photo:
        await call.message.answer("❌ Нет данных")
        return
    await call.message.answer_photo(
        types.BufferedInputFile(photo.read(), filename="l.png"),
        caption=text,
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data.startswith("oi|"))
async def oi_tf(call: types.CallbackQuery):
    _, tf, symbol = call.data.split("|")
    await call.message.delete()

    interval_map = {"15m": "15min", "1h": "1h", "1d": "1d"}
    tf_name = {"15m": "15м", "1h": "1ч", "1d": "1д"}[tf]

    ois = await get_open_interest(symbol, interval_map[tf])
    if not ois:
        await call.message.answer(f"❌ Нет данных")
        return
    pd = await get_price_data(symbol)
    if not pd:
        await call.message.answer(f"❌ Монета {symbol} не найдена")
        return
    price = pd[0]
    photo, text = draw_oi(symbol, tf_name, ois, price)
    if not photo:
        await call.message.answer("❌ Ошибка")
        return
    await call.message.answer_photo(
        types.BufferedInputFile(photo.read(), filename="oi.png"),
        caption=text
    )

    import feedparser

async def get_klines(symbol, interval="60", limit=100):
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}USDT&interval={interval}&limit={limit}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            data = await r.json()
    if data.get("retCode") != 0 or not data.get("result", {}).get("list"):
        return None
    klines = list(reversed(data["result"]["list"]))
    return [(float(k[4]), float(k[5])) for k in klines]  # (close, volume)


def calc_ema(values, period=50):
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(values[:period]) / period]
    for v in values[period:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def calc_rsi(values, period=14):
    if len(values) < period + 1:
        return []
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    rsi = []
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        rs = avg_g / avg_l if avg_l else 100
        rsi.append(100 - 100 / (1 + rs))
    return rsi

NEWS_FEEDS = {
    "ForkLog": "https://forklog.com/feed/",
    "РБК Крипто": "https://www.rbc.ru/crypto/rss",
    "Bits.media": "https://bits.media/rss/",
}



import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta


def get_importance(text):
    t = text.lower()
    high = ["фрс", "ставк", "инфляц", "cpi", "ввп", "фомс", "etf", "взлом", "запрет"]
    mid = ["binance", "sec", "регулир", "листинг", "партнёр", "суд", "иск"]
    if any(w in t for w in high):
        return "🔴 Высокая"
    if any(w in t for w in mid):
        return "🟡 Средняя"
    return "🟢 Низкая"


async def get_news():
    news = []
    async with aiohttp.ClientSession() as session:
        for source, url in NEWS_FEEDS.items():
            try:
                async with session.get(url, timeout=10) as r:
                    if r.status != 200:
                        continue
                    text = await r.text()
                root = ET.fromstring(text)
                items = root.findall(".//item")
                for item in items:
                    title = (item.findtext("title") or "").strip()
                    desc = (item.findtext("description") or "").strip()
                    pub = item.findtext("pubDate") or ""
                    import re
                    desc = re.sub(r"<[^>]+>", "", desc)[:200]
                    if not title:
                        continue
                    imp = get_importance(title + " " + desc)
                    news.append({
                        "title": title,
                        "desc": desc,
                        "source": source,
                        "time": pub,
                        "imp": imp,
                    })
            except Exception as e:
                print(f"{source}: ошибка {e}")
    print(f"Всего: {len(news)}")
    return news

@dp.callback_query(lambda c: c.data.startswith("news|"))
async def news_type(call: types.CallbackQuery):
    _, ntype = call.data.split("|")
    if ntype == "future":
        await call.answer("⏳ Скоро добавим", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Лёгкие", callback_data=f"nimp|{ntype}|low")],
        [InlineKeyboardButton(text="🟡 Средние", callback_data=f"nimp|{ntype}|mid")],
        [InlineKeyboardButton(text="🔴 Важные", callback_data=f"nimp|{ntype}|high")],
    ])
    await call.message.edit_text("📰 Выбери важность:", reply_markup=kb)


@dp.callback_query(lambda c: c.data.startswith("nimp|"))
async def news_importance(call: types.CallbackQuery):
    _, ntype, imp = call.data.split("|")
    await call.message.delete()
    news = await get_news()
    if not news:
        await call.message.answer("❌ Новостей не найдено")
        return
    filters = {"low": "🟢 Низкая", "mid": "🟡 Средняя", "high": "🔴 Высокая"}
    news = [n for n in news if n["imp"] == filters[imp]]
    if not news:
        await call.message.answer(f"❌ {filters[imp]} новостей нет")
        return
    text = f"📅 Новости ({filters[imp]}):\n\n"
    for i, n in enumerate(news[:10], 1):
        text += f"📰 {i}. {n['title']}\n"
        text += f"🕐 {n['time']}  •  {n['source']}\n"
        if n['desc']:
            text += f"📝 {n['desc']}\n"
        text += "\n"
    text += "⏰ Время по Киеву (КВ)"

@dp.message(F.text == "testai")
async def test_ai(msg: types.Message):
    r = await ai_ask("Скажи привет одним словом")
    await msg.answer(f"Ответ ИИ: {r}")

@dp.callback_query(lambda c: c.data.startswith("aitf|"))
async def analysis_tf(call: types.CallbackQuery):
    _, tf, coin = call.data.split("|")
    await call.message.delete()

    interval = {"15m": "15", "1h": "60", "1d": "D"}[tf]
    tf_name = {"15m": "15м", "1h": "1ч", "1d": "1д"}[tf]

    kl = await get_klines(coin, interval, 100)
    if not kl:
        await call.message.answer(f"❌ {coin} не найдена")
        return

    closes = [c for c, v in kl]
    price = closes[-1]
    change = (closes[-1] - closes[0]) / closes[0] * 100
    low = min(c for c, v in kl)
    high = max(c for c, v in kl)
    poi = low + (high - low) * 0.5

    ai = await ai_analysis(coin, tf_name, price, change, low, high, poi)
    if not ai:
        ai = {"thoughts": "Анализ недоступен", "rr": "-",
              "long_entry": 0, "long_stop": 0, "long_tp": 0,
              "short_entry": 0, "short_stop": 0, "short_tp": 0,
              "forecast": "up"}

    img = draw_analysis_v3(coin, tf_name, kl, ai, price, change)

    text = (
        f"🧠 {coin} / USDT — {tf_name}\n"
        f"💰 ${price:.2f}  ({change:+.2f}%)\n\n"
        f"🟢 Поддержка: ${low:.2f}\n"
        f"🔴 Сопротивление: ${high:.2f}\n"
        f"📌 POI: ${poi:.2f}\n\n"
        f"💭 Мысли:\n{ai.get('thoughts', '-')}\n\n"
        f"🎯 Входы:\n"
        f"📈 Лонг: ${ai.get('long_entry', 0)} | 🛑 ${ai.get('long_stop', 0)} | ✅ ${ai.get('long_tp', 0)}\n"
        f"📉 Шорт: ${ai.get('short_entry', 0)} | 🛑 ${ai.get('short_stop', 0)} | ✅ ${ai.get('short_tp', 0)}\n\n"
        f"📊 R/R: {ai.get('rr', '-')}\n"
        f"⚠️ Вход после подтверждения!"
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    await call.message.answer_photo(
        types.BufferedInputFile(buf.read(), filename="a.png"),
        caption=text[:1024]
    )

@dp.message(F.text.contains("📖 Инструкция"))
async def info_handler(msg: types.Message):
    text = (
        "📖 Инструкция APEXS | TRADE\n\n"
        "⚠️ Бот — это помощник для анализа рынка, "
        "а не финансовый совет. Решения принимаете только вы.\n\n"
        "📋 Вкладки:\n\n"
        "1. 💰 Ликвидность\n"
        "Показывает зоны скопления заявок. Выбираешь монету → ТФ. "
        "Полоски — где много заявок (белые) и мало (розовые).\n\n"
        "2. 📊 ОИ (Открытый интерес)\n"
        "Показывает общий объём открытых позиций в $. "
        "Растёт ОИ — тренд сильный, падает — слабый.\n\n"
        "3. ⚖️ Дисбаланс\n"
        "% лонгов и шортов по аккаунтам. Много лонгов — возможен шорт-сквиз.\n\n"
        "4. 🔥 Ликвидации\n"
        "Скоро. Показывает зоны, где снимают стопы.\n\n"
        "5. 🧠 Анализ ИИ\n"
        "BTC / ETH / XAU / ALT → ТФ. Краткий анализ + вход / стоп / тейк.\n\n"
        "6. 📰 Новости\n"
        "Текущие / Прошедшие / Будущие. По важности.\n\n"
        "7. 📈 EMA / Индикаторы\n"
        "EMA 50 / RSI / CVD.\n\n"
        "8. 💬 Связь\n"
        "Вопросы и проблемы — пиши сюда.\n\n"
        "📌 Обновлять анализ советуется раз в 15-30 минут."
    )
    await msg.answer(text)

async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

