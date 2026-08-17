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

# ===== CONFIGURACIÓN =====
TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
CHAT_ID = "544714195"
SYMBOL = "AUDCAD=X"
TIMEZONE_LOCAL = ZoneInfo("America/Panama")

print("--- INICIANDO SCRIPT DE SEÑALES RSI (CORREGIDO Y OPTIMIZADO) ---", flush=True)

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

# ===== OBTENER DATOS DE YAHOO FINANCE =====
def get_market_data():
    # Rango ampliado a 5 días para asegurar datos históricos suficientes
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range=5d&interval=1m"
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

# ===== LÓGICA DE ANÁLISIS =====
def analyze():
    global LAST_PROCESSED_TIMESTAMP
    ahora_local = datetime.now(TIMEZONE_LOCAL)

    # Filtro de fin de semana (Sábado completo y Domingo antes de las 5:00 PM)
    if ahora_local.weekday() == 5 or (ahora_local.weekday() == 6 and ahora_local.hour < 17):
        print(f"[{ahora_local.strftime('%H:%M:%S')}] Mercado cerrado (Fin de semana). Pausado...", flush=True)
        return

    try:
        df = get_market_data()
        if len(df) < 15:
            print(f"[{ahora_local.strftime('%H:%M:%S')}] Velas insuficientes: {len(df)}", flush=True)
            return

        latest_candle = df.iloc[-1]
        candle_time = latest_candle['timestamp']
        last_price = latest_candle['close']

        # Evaluar la vela ÚNICAMENTE por marca de tiempo (sin bloquear por precio plano)
        if LAST_PROCESSED_TIMESTAMP == candle_time:
            return

        LAST_PROCESSED_TIMESTAMP = candle_time

        # Cálculo de RSI
        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        last_rsi = rsi_series.dropna().iloc[-1]
        hora_actual = ahora_local.strftime("%H:%M")

        # Imprimir en los logs de Render para monitoreo continuo
        print(f"[{hora_actual}] Vela Procesada | Precio: {last_price:.5f} | RSI: {last_rsi:.2f}", flush=True)

        direccion = None
        if last_rsi <= 30:
            direccion = "CALL"
        elif last_rsi >= 70:
            direccion = "PUT"

        # Envío de la alerta si se cumple la condición
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
        print(f"[{ahora_local.strftime('%H:%M:%S')}] Error en análisis: {e}", flush=True)

# ===== INICIALIZACIÓN =====
threading.Thread(target=run_health_server, daemon=True).start()

send_telegram("🚀 <b>Bot de Señales Iniciado</b>\n<i>Monitoreo activo de AUD/CAD M1 corregido.</i>")

while True:
    analyze()
    time.sleep(10)
                
