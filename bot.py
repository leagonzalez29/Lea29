import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import pandas as pd
import ta
import sys

# Forzar escritura inmediata en logs
sys.stdout.reconfigure(line_buffering=True)

TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
CHAT_ID = "544714195"
SYMBOL = "BTCUSDT"
INTERVAL = "15m"

print("--- INICIANDO SCRIPT ---", flush=True)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot activo")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        res = requests.post(url, data=payload)
        print(f"Respuesta de Telegram: {res.text}", flush=True)
    except Exception as e:
        print(f"Error enviando mensaje: {e}", flush=True)

def get_binance_data():
    url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit=100"
    res = requests.get(url).json()
    df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
    df['close'] = df['close'].astype(float)
    return df

def analyze():
    try:
        df = get_binance_data()
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        last_rsi = df['rsi'].iloc[-1]
        last_price = df['close'].iloc[-1]
        print(f"BTC: ${last_price} | RSI: {last_rsi:.2f}", flush=True)

        if last_rsi < 30:
            send_telegram(f"🚨 COMPRA BTCUSDT\nRSI: {last_rsi:.2f}\nPrecio: ${last_price}")
        elif last_rsi > 70:
            send_telegram(f"🚨 VENTA BTCUSDT\nRSI: {last_rsi:.2f}\nPrecio: ${last_price}")
    except Exception as e:
        print(f"Error en análisis: {e}", flush=True)

# Arranque
print("--- INICIANDO SERVIDOR WEB Y MENSAJE ---", flush=True)
threading.Thread(target=run_health_server, daemon=True).start()
send_telegram("🚀 ¡Bot activo 24/7 en Render!")

while True:
    analyze()
    time.sleep(60)
