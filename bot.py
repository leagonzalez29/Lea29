import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import pandas as pd
import ta
import sys
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(line_buffering=True)

# ===== CONFIGURACIÓN =====
TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
CHAT_ID = "544714195"
SYMBOL = "AUDCAD=X"  # Ajustado para AUD/CAD
TIMEZONE_LOCAL = ZoneInfo("America/Panama")

# Rango horario permitido: 12:40:00 a 01:00:00
HORA_INICIO = dtime(12, 40, 0)
HORA_FIN = dtime(13, 0, 0)

print("--- INICIANDO BOT CON FILTRO HORARIO (12:40 - 01:00) ---", flush=True)

LAST_PROCESSED_TIMESTAMP = None
PRE_ALERT_SENT_FOR_TIMESTAMP = None

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

# ===== OBTENER DATOS =====
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
        raise Exception(f"Error parseando datos: {e}")

# ===== LÓGICA DE ANÁLISIS CON PRE-ALERTA =====
def analyze():
    global LAST_PROCESSED_TIMESTAMP, PRE_ALERT_SENT_FOR_TIMESTAMP
    
    try:
        ahora = datetime.now(TIMEZONE_LOCAL)
        hora_actual = ahora.time()

        # RESTRICCIÓN HORARIA: Solo ejecuta si la hora está entre 12:40 y 13:00
        if not (HORA_INICIO <= hora_actual <= HORA_FIN):
            return

        df = get_market_data()
        if len(df) < 15:
            return

        segundo_actual = ahora.second

        # Calcular RSI general
        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        
        # -------------------------------------------------------------
        # 1. PRE-ALERTA (Entre segundo 45 y 55 de la vela activa)
        # -------------------------------------------------------------
        current_candle = df.iloc[-1]
        current_timestamp = current_candle['timestamp']
        current_rsi = rsi_series.dropna().iloc[-1]

        if 45 <= segundo_actual <= 55 and PRE_ALERT_SENT_FOR_TIMESTAMP != current_timestamp:
            pre_direccion = None
            if current_rsi <= 33:
                pre_direccion = "CALL"
            elif current_rsi >= 67:
                pre_direccion = "PUT"

            if pre_direccion:
                mensaje_pre = (
                    f"⚠️ <b>PRE-ALERTA DE ENTRADA</b>\n\n"
                    f"M1 {SYMBOL} ➔ PREPARAR <b>{pre_direccion}</b>\n"
                    f"📉 <b>RSI Aprox:</b> {current_rsi:.2f}\n"
                    f"⏱️ <i>Entrada probable en el próximo minuto (:00)</i>"
                )
                send_telegram(mensaje_pre)
                PRE_ALERT_SENT_FOR_TIMESTAMP = current_timestamp

        # -------------------------------------------------------------
        # 2. SEÑAL CONFIRMADA (Cierre de la vela anterior iloc[-2])
        # -------------------------------------------------------------
        closed_candle = df.iloc[-2]
        closed_timestamp = closed_candle['timestamp']
        closed_price = closed_candle['close']
        closed_rsi = rsi_series.dropna().iloc[-2]

        if LAST_PROCESSED_TIMESTAMP != closed_timestamp:
            LAST_PROCESSED_TIMESTAMP = closed_timestamp
            hora_vela = datetime.fromtimestamp(closed_timestamp, tz=TIMEZONE_LOCAL).strftime("%H:%M")

            print(f"[{hora_vela}] {SYMBOL} | Cierre: {closed_price} | RSI: {closed_rsi:.2f}", flush=True)

            direccion = None
            if closed_rsi <= 30:
                direccion = "CALL"
            elif closed_rsi >= 70:
                direccion = "PUT"

            if direccion:
                mensaje_conf = (
                    f"📊 <b>NUEVA SEÑAL CONFIRMADA</b>\n\n"
                    f"M1 {SYMBOL} {hora_vela} <b>{direccion}</b>\n\n"
                    f"📉 <b>RSI Cierre:</b> {closed_rsi:.2f}\n"
                    f"📊 <b>Precio:</b> {closed_price}\n\n"
                    "<b>CALL = OPERATIVA A LA ALZA</b>\n"
                    "<b>PUT = OPERATIVA A LA BAJA</b>\n\n"
                    "Recuerden que tenemos una efectividad de un 90% sin MG. Con MG nuestra efectividad sube hasta un 95%."
                )
                send_telegram(mensaje_conf)

    except Exception as e:
        print(f"Error de análisis: {e}", flush=True)

# ===== INICIALIZACIÓN =====
threading.Thread(target=run_health_server, daemon=True).start()

send_telegram("🚀 <b>Bot Activo para AUD/CAD</b>\n<i>Filtro horario activado: Solo enviará señales de 12:40 a 01:00.</i>")

while True:
    analyze()
    time.sleep(5)
