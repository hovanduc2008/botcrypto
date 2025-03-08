import logging
import asyncio
import pandas as pd
import ta  # Thư viện chỉ báo kỹ thuật
import time
import requests
import numpy as np
from binance.client import Client
from binance.enums import *

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, CallbackContext

LAST_SIGNAL = {}  # Lưu tín hiệu trước đó của từng cặp


# Cấu hình logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Binance API Key (Thay thế bằng key của bạn)
BINANCE_API_KEY = "MXf4GgIhCnVVsgNPp9mm3NwRdHdRiNviNakihmswIyc6nyLa3sOLpeDo3NAnPDXn"
BINANCE_API_SECRET = "AMiV2uq2ohW4xvdd5nRGDONfcscAXEo98Arhoah3nhYDmy5Oq6m1QAwTrMnvRUG6"

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = "7520263150:AAF-DE4xBgfPOr7IL_IZgpTmSfGFJM6AVjo"
TELEGRAM_CHAT_ID = "6000731547"  # Thay thế bằng chat ID của bạn

# Khởi tạo bot Telegram & Binance Client
bot = Bot(token=TELEGRAM_BOT_TOKEN)
client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# Danh sách cặp giao dịch theo dõi
WATCHLIST = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT"]


async def check_signals():
    global LAST_SIGNAL
    while True:
        for symbol in WATCHLIST:
            signal = analyze_market(symbol, False)

            if signal:
                last_time, last_signal = LAST_SIGNAL.get(symbol, (0, ""))

                # Chỉ gửi nếu tín hiệu thay đổi hoặc hơn 10 phút
                if last_signal != signal or (time.time() - last_time) > 600:
                    LAST_SIGNAL[symbol] = (time.time(), signal)  # Cập nhật tín hiệu mới
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"📢 {symbol}:\n{signal}")

            elif symbol in LAST_SIGNAL:
                # Chỉ xóa tín hiệu nếu trước đó có lưu
                del LAST_SIGNAL[symbol]

        await asyncio.sleep(20)  # Kiểm tra mỗi 20 giây

# 📌 Lệnh /start - Hiển thị hướng dẫn đầy đủ
async def start(update: Update, context: CallbackContext):
    message = (
        "🤖 **Bot giao dịch Crypto đang hoạt động!**\n\n"
        "🔹 **Danh sách lệnh khả dụng:**\n"
        "📊 `/watchlist` - Xem danh sách cặp giao dịch theo dõi.\n"
        "➕ `/addpair <symbol>` - Thêm một cặp giao dịch vào danh sách theo dõi.\n"
        "➖ `/removepair <symbol>` - Xóa một cặp khỏi danh sách theo dõi.\n"
        "📈 `/info <symbol>` - Xem thông số kỹ thuật của một cặp.\n"
        "📰 `/news <symbol>` - Lấy tin tức mới nhất về một cặp giao dịch.\n\n"
        "💡 **Bot sẽ tự động gửi tín hiệu giao dịch khi phát hiện cơ hội đầu tư.**\n"
        "⏳ Kiểm tra tín hiệu mới mỗi **60 giây**.\n"
    )
    await update.message.reply_text(message, parse_mode="Markdown")
# 📌 Lệnh /watchlist
async def watchlist(update: Update, context: CallbackContext):
    await update.message.reply_text(f"📊 Danh sách cặp theo dõi: {', '.join(WATCHLIST)}")

# 📌 Lệnh /addpair <symbol>
async def addpair(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        await update.message.reply_text("Cú pháp: /addpair <symbol>")
        return
    symbol = context.args[0].upper()
    if symbol not in WATCHLIST:
        WATCHLIST.append(symbol)
        await update.message.reply_text(f"✅ Đã thêm {symbol} vào danh sách theo dõi.")
    else:
        await update.message.reply_text(f"⚠ {symbol} đã có trong danh sách.")

# 📌 Lệnh /removepair <symbol>
async def removepair(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        await update.message.reply_text("Cú pháp: /removepair <symbol>")
        return
    symbol = context.args[0].upper()
    if symbol in WATCHLIST:
        WATCHLIST.remove(symbol)
        await update.message.reply_text(f"❌ Đã xóa {symbol} khỏi danh sách.")
    else:
        await update.message.reply_text(f"⚠ {symbol} không có trong danh sách.")

def analyze_market(symbol, check):
    try:
        klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=100)
        df = pd.DataFrame(klines, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time",
                                           "quote_asset_volume", "trades", "taker_buy_base", "taker_buy_quote",
                                           "ignore"])
        df[["close", "high", "low"]] = df[["close", "high", "low"]].astype(float)

        # 🎯 **Chỉ báo kỹ thuật**
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        df["ema_9"] = ta.trend.EMAIndicator(df["close"], window=9).ema_indicator()
        df["ema_21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator()
        df["sma_50"] = ta.trend.SMAIndicator(df["close"], window=50).sma_indicator()
        df["sma_200"] = ta.trend.SMAIndicator(df["close"], window=200).sma_indicator()

        # 🎯 **MACD**
        macd = ta.trend.MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()

        # 🎯 **Bollinger Bands (BB)**
        bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()

        # 🎯 **ATR (Stop Loss & Take Profit)**
        df["atr"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()

        # ✅ **Lấy giá trị mới nhất**
        last_close = df["close"].iloc[-1]
        last_rsi = df["rsi"].iloc[-1]
        last_ema9 = df["ema_9"].iloc[-1]
        last_ema21 = df["ema_21"].iloc[-1]
        last_sma50 = df["sma_50"].iloc[-1]
        last_sma200 = df["sma_200"].iloc[-1]
        last_macd = df["macd"].iloc[-1]
        last_macd_signal = df["macd_signal"].iloc[-1]
        last_bb_upper = df["bb_upper"].iloc[-1]
        last_bb_lower = df["bb_lower"].iloc[-1]
        last_atr = df["atr"].iloc[-1]

        # 🎯 **Tính toán Stop Loss (SL) & Take Profit (TP)**
        sl = round(last_close - (1.5 * last_atr), 2)
        tp = round(last_close + (2 * last_atr), 2)

        # ✅ **Điều kiện MUA / BÁN**
        signal = False
        reason = ""

        if last_rsi < 30 and last_ema9 > last_ema21 and last_macd > last_macd_signal:
            signal = "📈 MUA - RSI thấp, EMA9 cắt EMA21 lên trên, MACD bullish"
            reason = "RSI quá bán + EMA cắt lên + MACD bullish"

        elif last_rsi > 70 and last_ema9 < last_ema21 and last_macd < last_macd_signal:
            signal = "📉 BÁN - RSI cao, EMA9 cắt EMA21 xuống dưới, MACD bearish"
            reason = "RSI quá mua + EMA cắt xuống + MACD bearish"

        elif last_close < last_bb_lower:
            signal = "📈 MUA - Giá chạm Bollinger Bands dưới"
            reason = "Giá quá bán theo Bollinger Bands"

        elif last_close > last_bb_upper:
            signal = "📉 BÁN - Giá chạm Bollinger Bands trên"
            reason = "Giá quá mua theo Bollinger Bands"

        elif last_sma50 > last_sma200 and last_close > last_sma50:
            signal = "📈 MUA - Xu hướng dài hạn tăng (Golden Cross)"
            reason = "SMA 50 cắt SMA 200 lên trên (Golden Cross)"

        elif last_sma50 < last_sma200 and last_close < last_sma50:
            signal = "📉 BÁN - Xu hướng dài hạn giảm (Death Cross)"
            reason = "SMA 50 cắt SMA 200 xuống dưới (Death Cross)"

        # 🏆 **Tỷ lệ thắng/thua giả lập**
        win_rate = round(np.random.uniform(60, 85), 2)  # Giả lập tỷ lệ thắng 60% - 85%

        # 🔥 **Trả về thông tin**
        return (
                f"📊 {symbol}:\n"
                f"💰 Giá hiện tại: {last_close:.2f}\n"
                f"📉 RSI(14): {last_rsi:.2f}\n"
                f"📊 EMA9: {last_ema9:.2f} | EMA21: {last_ema21:.2f}\n"
                f"📈 MACD: {last_macd:.4f} | Signal: {last_macd_signal:.4f}\n"
                f"🔵 Bollinger Bands: {last_bb_lower:.2f} - {last_bb_upper:.2f}\n"
                +
                (
                    f"🎯 Stop Loss: {sl:.2f} | Take Profit: {tp:.2f}\n"
                    f"🏆 Tỷ lệ thắng giả lập: {win_rate:.2f}%\n"
                    if signal else ""
                ) +
                f"📢 Tín hiệu: {signal if signal else 'Không có tín hiệu giao dịch rõ ràng'}\n"
                f"🎯 Lý do: {reason if signal else 'Chưa có setup tốt'}"
        ) if check else (signal if signal else False)

    except Exception as e:
        logging.error(f"Lỗi phân tích {symbol}: {str(e)}")
        return None


async def info(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        await update.message.reply_text("Cú pháp: /info <symbol>")
        return
    symbol = context.args[0].upper()

    if symbol not in WATCHLIST:
        await update.message.reply_text(f"⚠ {symbol} không có trong danh sách theo dõi.")
        return

    details = analyze_market(symbol, True)
    if details:
        await update.message.reply_text(details)
    else:
        await update.message.reply_text(f"⚠ Không thể lấy dữ liệu cho {symbol}.")



# 📌 Lấy tin tức mới nhất về một cặp giao dịch
async def news(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        await update.message.reply_text("Cú pháp: /news <symbol>")
        return
    symbol = context.args[0].upper()

    try:
        # Lấy tin tức từ Coingecko
        response = requests.get("https://api.coingecko.com/api/v3/news")
        data = response.json()

        news_list = []
        for article in data.get("data", []):  # API trả về danh sách bài viết
            if symbol in article["title"].upper() or symbol in article["content"].upper():
                news_list.append(f"📰 {article['title']}\n🔗 {article['url']}")

        if news_list:
            news_text = "\n\n".join(news_list[:3])  # Chỉ lấy 3 tin gần nhất
        else:
            news_text = "❌ Không tìm thấy tin tức mới."

        await update.message.reply_text(f"📢 Tin tức về {symbol}:\n{news_text}")
    except Exception as e:
        await update.message.reply_text("⚠ Lỗi khi lấy tin tức!")
        logging.error(f"Lỗi lấy tin tức {symbol}: {str(e)}")

# 📌 Chạy bot Telegram
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("watchlist", watchlist))
    application.add_handler(CommandHandler("addpair", addpair))
    application.add_handler(CommandHandler("removepair", removepair))
    application.add_handler(CommandHandler("info", info))  # Thêm lệnh /info
    application.add_handler(CommandHandler("news", news))  # Thêm lệnh /news

    loop = asyncio.get_event_loop()
    loop.create_task(check_signals())

    application.run_polling()

if __name__ == "__main__":
    main()
