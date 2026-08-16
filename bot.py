import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import pandas as pd
import ta
import sys

sys.stdout.reconfigure(line_buffering=True)

TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
CHAT_ID = "544714195"
SYMBOL = "AUDCAD=X"

print("--- INICIANDO SCRIPT AUD/CAD 1M ---", flush=True)

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

def get_market_data():
    # API de Yahoo Finance para AUD/CAD en intervalo de 1m
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range=1d&interval=1m"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers).json()
    
    try:
        quotes = res['chart']['result'][0]['indicators']['quote'][0]['close']
        df = pd.DataFrame(quotes, columns=['close'])
        df = df.dropna().reset_index(drop=True)
        return df
    except Exception as e:
        raise Exception(f"Error parseando datos de Yahoo: {res}")

def analyze():
    try:
        df = get_market_data()
        if len(df) < 14:
            print("Esperando más velas...", flush=True)
            return

        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        last_rsi = rsi_series.dropna().iloc[-1]
        last_price = df['close'].iloc[-1]
        
        print(f"AUD/CAD: {last_price:.5f} | RSI (1m): {last_rsi:.2f}", flush=True)

        if last_rsi < 30:
            send_telegram(f"🚨 COMPRA AUD/CAD (1m)\nRSI: {last_rsi:.2f}\nPrecio: {last_price:.5f}")
        elif last_rsi > 70:
            send_telegram(f"🚨 VENTA AUD/CAD (1m)\nRSI: {last_rsi:.2f}\nPrecio: {last_price:.5f}")
    except Exception as e:
        print(f"Error en análisis: {e}", flush=True)

threading.Thread(target=run_health_server, daemon=True).start()
send_telegram("🚀 ¡Bot activo 24/7 en Render! (Mercado: AUD/CAD 1m)")

while True:
    analyze()
    time.sleep(60)
    
