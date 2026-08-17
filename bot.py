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

print("--- INICIANDO BOT OPTIMIZADO (FILTRO SEÑALES Y ANTI-SPAM) ---", flush=True)

LAST_PROCESSED_TIMESTAMP = None
PRE_ALERT_SENT_FOR_TIMESTAMP = None

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

# ===== SERVIDOR HEALTH CHECK =====
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
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        session.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}", flush=True)

def get_market_data():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range=1d&interval=1m"
    res = session.get(url, timeout=10).json()
    result = res['chart']['result'][0]
    df = pd.DataFrame({'timestamp': result['timestamp'], 'close': result['indicators']['quote'][0]['close']})
    return df.dropna().reset_index(drop=True)

def analyze():
    global LAST_PROCESSED_TIMESTAMP, PRE_ALERT_SENT_FOR_TIMESTAMP
    
    try:
        df = get_market_data()
        if len(df) < 15: return

        ahora = datetime.now(TIMEZONE_LOCAL)
        segundo_actual = ahora.second
        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        
        # 1. LÓGICA DE PRE-ALERTA (ANTI-SPAM)
        current_candle = df.iloc[-1]
        current_timestamp = current_candle['timestamp']
        current_rsi = rsi_series.iloc[-1]

        if 45 <= segundo_actual <= 55 and PRE_ALERT_SENT_FOR_TIMESTAMP != current_timestamp:
            if current_rsi <= 33 or current_rsi >= 67:
                direccion = "CALL 🟢" if current_rsi <= 33 else "PUT 🔴"
                msg = f"⚠️ <b>PRE-ALERTA</b>\n\n{SYMBOL} ➔ <b>{direccion}</b>\n📉 RSI: {current_rsi:.2f}"
                send_telegram(msg)
                PRE_ALERT_SENT_FOR_TIMESTAMP = current_timestamp

        # 2. SEÑAL CONFIRMADA (SÓLO SI ES CALL O PUT)
        closed_candle = df.iloc[-2]
        closed_timestamp = closed_candle['timestamp']
        closed_rsi = rsi_series.iloc[-2]

        if LAST_PROCESSED_TIMESTAMP != closed_timestamp:
            LAST_PROCESSED_TIMESTAMP = closed_timestamp
            
            estado = None
            if closed_rsi <= 30: estado = "CALL 🟢 (SOBREVENTA)"
            elif closed_rsi >= 70: estado = "PUT 🔴 (SOBRECOMPRA)"

            if estado: # Solo envía si hay señal, ignora neutral
                hora_vela = datetime.fromtimestamp(closed_timestamp, tz=TIMEZONE_LOCAL).strftime("%H:%M")
                msg = (f"📊 <b>SEÑAL CONFIRMADA</b> ({hora_vela})\n\n"
                       f"📈 {SYMBOL} ➔ {estado}\n"
                       f"📉 RSI: {closed_rsi:.2f}")
                send_telegram(msg)

    except Exception as e:
        print(f"Error: {e}", flush=True)

# ===== INICIALIZACIÓN =====
threading.Thread(target=run_health_server, daemon=True).start()
send_telegram("🚀 <b>Bot Optimizado Activo</b>\n<i>Filtro de señales: Solo CALL/PUT.</i>")

while True:
    analyze()
    time.sleep(7) # Ajustado a 7s para evitar redundancia rápida
    
