import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import pandas as pd
import ta
import sys
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True)

TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
CHAT_ID = "544714195"
SYMBOL = "AUDCAD=X"

print("--- INICIANDO SCRIPT AUD/CAD 1M (CON FORMATO) ---", flush=True)

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
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, data=payload)
        print(f"Respuesta de Telegram: {res.text}", flush=True)
    except Exception as e:
        print(f"Error enviando mensaje: {e}", flush=True)

def get_market_data():
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
            return

        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        last_rsi = rsi_series.dropna().iloc[-1]
        last_price = df['close'].iloc[-1]
        hora_actual = datetime.now().strftime("%H:%M:%S")

        print(f"AUD/CAD: {last_price:.5f} | RSI: {last_rsi:.2f}", flush=True)

        if last_rsi < 30:
            mensaje = (
                "⚠️ <b>ATENCIÓN, HA LLEGADO UNA SEÑAL</b>\n\n"
                "🔰 <b>ACTIVO:</b> AUD/CAD\n"
                "⏰ <b>TIEMPO:</b> 1 MINUTO\n\n"
                "<b>HORA DE ENTRADA</b>\n"
                f"📑 {hora_actual}\n"
                f"🟢 <b>DIRECCIÓN:</b> CALL (COMPRA)\n"
                f"📊 <b>PRECIO:</b> {last_price:.5f}\n"
                f"📉 <b>RSI:</b> {last_rsi:.2f}\n\n"
                "🔥 <b>BUENA SUERTE A TODOS</b> 🔥"
            )
            send_telegram(mensaje)

        elif last_rsi > 70:
            mensaje = (
                "⚠️ <b>ATENCIÓN, HA LLEGADO UNA SEÑAL</b>\n\n"
                "🔰 <b>ACTIVO:</b> AUD/CAD\n"
                "⏰ <b>TIEMPO:</b> 1 MINUTO\n\n"
                "<b>HORA DE ENTRADA</b>\n"
                f"📑 {hora_actual}\n"
                f"🔴 <b>DIRECCIÓN:</b> PUT (VENTA)\n"
                f"📊 <b>PRECIO:</b> {last_price:.5f}\n"
                f"📈 <b>RSI:</b> {last_rsi:.2f}\n\n"
                "🔥 <b>BUENA SUERTE A TODOS</b> 🔥"
            )
            send_telegram(mensaje)

    except Exception as e:
        print(f"Error en análisis: {e}", flush=True)

threading.Thread(target=run_health_server, daemon=True).start()
send_telegram("🚀 <b>¡Bot activo 24/7 en Render!</b>\n<i>Mercado: AUD/CAD (1m)</i>")

while True:
    analyze()
    time.sleep(60)
    
