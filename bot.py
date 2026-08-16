import time
import requests
import pandas as pd
import ta

TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs" # Pega aquí tu Token de BotFather
CHAT_ID = "544714195"
SYMBOL = "BTCUSDT"
INTERVAL = "15m"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

def get_binance_data():
    url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit=100"
    res = requests.get(url).json()
    df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', '_', '_', '_', '_', '_', '_'])
    df['close'] = df['close'].astype(float)
    return df

def analyze():
    df = get_binance_data()
    df['rsi'] = ta.momentum.rsi(df['close'], window=14)
    last_rsi = df['rsi'].iloc[-1]
    last_close = df['close'].iloc[-1]
    print(f"BTC: ${last_close} | RSI: {last_rsi:.2f}")

if __name__ == "__main__":
    send_telegram("🚀 ¡Bot activo 24/7 en Render!")
    while True:
        try:
            analyze()
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(60)
