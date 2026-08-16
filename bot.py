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

TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
CHAT_ID = "544714195"
SYMBOL = "AUDCAD=X"
TIMEZONE_LOCAL = ZoneInfo("America/Panama")

print("--- INICIANDO SCRIPT DE ALTA FRECUENCIA DE SEÑALES ---", flush=True)

LAST_CANDLE_TIMESTAMP = None
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

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
        res = session.post(url, data=payload, timeout=10)
        print(f"Respuesta Telegram: {res.status_code}", flush=True)
    except Exception as e:
        print(f"Error enviando mensaje: {e}", flush=True)

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
        raise Exception(f"Error parseando datos de Yahoo: {e}")

def analyze():
    global LAST_CANDLE_TIMESTAMP
    ahora_local = datetime.now(TIMEZONE_LOCAL)

    try:
        df = get_market_data()
        if len(df) < 15:
            return

        latest_candle = df.iloc[-1]
        candle_time = latest_candle['timestamp']
        last_price = latest_candle['close']

        if LAST_CANDLE_TIMESTAMP == candle_time:
            return

        LAST_CANDLE_TIMESTAMP = candle_time

        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        last_rsi = rsi_series.dropna().iloc[-1]
        hora_actual = ahora_local.strftime("%H:%M")

        # UMBRALES MÁS FLEXIBLES PARA OBTENER MÁS SEÑALES
        direccion = None
        if last_rsi < 45:
            direccion = "CALL"
        elif last_rsi > 55:
            direccion = "PUT"

        # Si hay tendencia clara, envía la plantilla de señal directa que pediste
        if direccion:
            mensaje = (
                f"📊 <b>NUEVA SEÑAL DETECTADA</b>\n\n"
                f"M1 AUD/CAD {hora_actual} <b>{direccion}</b>\n\n"
                f"📉 <b>RSI Actual:</b> {last_rsi:.2f}\n"
                f"📊 <b>Precio:</b> {last_price:.5f}\n\n"
                "<b>CALL= OPERATIVA A LA ALZA</b>\n"
                "<b>PUT= OPERATIVA A LA BAJA</b>\n\n"
                "Recuerden que tenemos una efectividad de un 90% sin MG. Con MG nuestra efectividad sube hasta un 95%."
            )
            send_telegram(mensaje)

    except Exception as e:
        print(f"Error en análisis: {e}", flush=True)

threading.Thread(target=run_health_server, daemon=True).start()
send_telegram("🚀 <b>¡Bot de alta frecuencia activado!</b>\n<i>Enviará múltiples señales basadas en los rangos del RSI.</i>")

while True:
    analyze()
    time.sleep(10)
    
