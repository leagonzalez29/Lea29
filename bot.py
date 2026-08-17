import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import pandas as pd
import ta
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(line_buffering=True)

# ===== CONFIGURACIÓN 24/7 CRIPTO =====
TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
CHAT_ID = "544714195"
SYMBOL = "BTC-USD"  # Criptomoneda activa 24/7
TIMEZONE_LOCAL = ZoneInfo("America/Panama")

print("--- INICIANDO SCRIPT CRIPTO 24/7 (BTC-USD) ---", flush=True)

LAST_PROCESSED_TIMESTAMP = None
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

# ===== SERVIDOR HEALTH CHECK PARA RENDER =====
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

# ===== FUNCIÓN TELEGRAM =====
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        res = session.post(url, data=payload, timeout=10)
        print(f"[{datetime.now(TIMEZONE_LOCAL).strftime('%H:%M:%S')}] Telegram Status: {res.status_code}", flush=True)
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}", flush=True)

# ===== OBTENER DATOS DE MERCADO 24/7 =====
def get_market_data():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range=1d&interval=1m"
    res = session.get(url, timeout=10).json()
    
    try:
        result = res['chart']['result'][0]
        timestamps = result['timestamp']
        quotes = result['indicators']['quote'][0]['close']
        
        df = pd.DataFrame({'timestamp': timestamps, 'close': quotes})
        df = df.dropna().reset_index(drop=True)
        return df
    except Exception as e:
        raise Exception(f"No se pudieron obtener datos en vivo de {SYMBOL}: {e}")

# ===== LÓGICA DE ANÁLISIS =====
def analyze():
    global LAST_PROCESSED_TIMESTAMP
    
    try:
        df = get_market_data()
        if len(df) < 15:
            return

        latest_candle = df.iloc[-1]
        candle_time = latest_candle['timestamp']
        last_price = latest_candle['close']

        if LAST_PROCESSED_TIMESTAMP == candle_time:
            return

        LAST_PROCESSED_TIMESTAMP = candle_time

        # Cálculo de RSI
        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        last_rsi = rsi_series.dropna().iloc[-1]
        hora_actual = datetime.now(TIMEZONE_LOCAL).strftime("%H:%M")

        # Registro visible en logs de Render
        print(f"[{hora_actual}] {SYMBOL} | Precio: ${last_price:,.2f} | RSI: {last_rsi:.2f}", flush=True)

        # Reglas de entrada
        direccion = None
        if last_rsi <= 30:
            direccion = "CALL"
        elif last_rsi >= 70:
            direccion = "PUT"

        # Envío de alerta
        if direccion:
            mensaje = (
                f"🚨 <b>SEÑAL CRIPTO 24/7</b>\n\n"
                f"M1 <b>{SYMBOL}</b> {hora_actual} ➔ <b>{direccion}</b>\n\n"
                f"📉 <b>RSI Actual:</b> {last_rsi:.2f}\n"
                f"📊 <b>Precio:</b> ${last_price:,.2f}\n\n"
                "<b>CALL = ALZA 🟢 | PUT = BAJA 🔴</b>"
            )
            send_telegram(mensaje)

    except Exception as e:
        print(f"Error de análisis: {e}", flush=True)

# ===== INICIALIZACIÓN =====
threading.Thread(target=run_health_server, daemon=True).start()

send_telegram(f"🚀 <b>Bot Cripto 24/7 Iniciado</b>\n<i>Monitoreando {SYMBOL} sin interrupciones por fin de semana.</i>")

while True:
    analyze()
    time.sleep(10)
        
