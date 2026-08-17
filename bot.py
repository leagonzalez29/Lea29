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

print("--- BOT CON PRE-ALERTA DE IMPULSO ANTICIPADO ACTIVO ---", flush=True)

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
    df = pd.DataFrame({
        'timestamp': result['timestamp'],
        'high': result['indicators']['quote'][0]['high'],
        'low': result['indicators']['quote'][0]['low'],
        'close': result['indicators']['quote'][0]['close']
    })
    return df.dropna().reset_index(drop=True)

def analyze():
    global LAST_PROCESSED_TIMESTAMP, PRE_ALERT_SENT_FOR_TIMESTAMP
    
    try:
        df = get_market_data()
        if len(df) < 20: return

        ahora = datetime.now(TIMEZONE_LOCAL)
        segundo_actual = ahora.second
        
        # Indicadores para análisis anticipado
        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        stoch_k = ta.momentum.stoch(high=df['high'], low=df['low'], close=df['close'], window=14, smooth_window=3)

        current_candle = df.iloc[-1]
        current_timestamp = current_candle['timestamp']
        
        rsi_actual = rsi_series.iloc[-1]
        rsi_previo = rsi_series.iloc[-2]
        stoch_actual = stoch_k.iloc[-1]

        # -------------------------------------------------------------
        # 1. PRE-ALERTA ANTICIPADA (Se evalúa a mitad de vela :25 a :45)
        # Detecta giro de impulso antes del cierre
        # -------------------------------------------------------------
        if 25 <= segundo_actual <= 45 and PRE_ALERT_SENT_FOR_TIMESTAMP != current_timestamp:
            
            # Condición de Subida (CALL): RSI bajo pero subiendo + Estocástico en sobreventa
            prediccion_subida = (rsi_actual < 38 and rsi_actual > rsi_previo) or (stoch_actual <= 20)
            
            # Condición de Bajada (PUT): RSI alto pero bajando + Estocástico en sobrecompra
            prediccion_bajada = (rsi_actual > 62 and rsi_actual < rsi_previo) or (stoch_actual >= 80)

            direccion = None
            if prediccion_subida:
                direccion = "SUBIRÁ (CALL) 🟢"
            elif prediccion_bajada:
                direccion = "BAJARÁ (PUT) 🔴"

            if direccion:
                msg = (
                    f"⚡ <b>PRE-ALERTA ANTICIPADA</b>\n\n"
                    f"📈 <b>Par:</b> {SYMBOL}\n"
                    f"🔮 <b>Proyección:</b> Se anticipa giro a la <b>{direccion}</b>\n"
                    f"📉 <b>RSI Actual:</b> {rsi_actual:.2f}\n"
                    f"📊 <b>Stoch K:</b> {stoch_actual:.2f}\n"
                    f"⏱️ <i>Prepárate para entrar en el segundo :00</i>"
                )
                send_telegram(msg)
                PRE_ALERT_SENT_FOR_TIMESTAMP = current_timestamp

        # -------------------------------------------------------------
        # 2. CONFIRMACIÓN FINAL (En el cambio de vela)
        # -------------------------------------------------------------
        closed_candle = df.iloc[-2]
        closed_timestamp = closed_candle['timestamp']
        closed_rsi = rsi_series.iloc[-2]

        if LAST_PROCESSED_TIMESTAMP != closed_timestamp:
            LAST_PROCESSED_TIMESTAMP = closed_timestamp
            
            estado = None
            if closed_rsi <= 30: estado = "ENTRADA CONFIRMADA EN CALL 🟢"
            elif closed_rsi >= 70: estado = "ENTRADA CONFIRMADA EN PUT 🔴"

            if estado:
                hora_vela = datetime.fromtimestamp(closed_timestamp, tz=TIMEZONE_LOCAL).strftime("%H:%M")
                msg = (f"🎯 <b>SEÑAL DE ENTRADA</b> ({hora_vela})\n\n"
                       f"📈 {SYMBOL} ➔ <b>{estado}</b>\n"
                       f"📉 RSI Cierre: {closed_rsi:.2f}")
                send_telegram(msg)

    except Exception as e:
        print(f"Error en análisis: {e}", flush=True)

# ===== INICIALIZACIÓN =====
threading.Thread(target=run_health_server, daemon=True).start()
send_telegram("🚀 <b>Bot de Análisis Anticipado Activo</b>\n<i>Detectando giros de mercado entre el segundo :25 y :45.</i>")

while True:
    analyze()
    time.sleep(5)
