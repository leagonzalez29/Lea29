import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import pandas as pd
import ta
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(line_buffering=True)

# ===== CONFIGURACIÓN =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs")
CHAT_ID = os.environ.get("CHAT_ID", "544714195")

SYMBOL_YAHOO = "BTC-USD"
SYMBOL_DISPLAY = "BTC-USD"
TIMEZONE_LOCAL = ZoneInfo("America/Panama")

print(f"--- BOT ANALIZANDO {SYMBOL_DISPLAY} ---", flush=True)

LAST_PROCESSED_TIMESTAMP = None
PRE_ALERT_SENT_FOR_TIMESTAMP = None

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

# ===== SERVIDOR HEALTH CHECK =====
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot activo")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# ===== FUNCIÓN TELEGRAM =====
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        res = session.post(url, data=payload, timeout=10)
        if res.status_code != 200:
            print(f"Error Telegram HTTP {res.status_code}: {res.text}", flush=True)
    except Exception as e:
        print(f"Error Telegram: {e}", flush=True)

# ===== OBTENER DATOS DE MERCADO =====
def get_market_data():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL_YAHOO}?range=1d&interval=1m"
    try:
        res = session.get(url, timeout=10)
        if res.status_code != 200:
            print(f"Error ({SYMBOL_YAHOO}): Status {res.status_code}", flush=True)
            return pd.DataFrame()

        data = res.json()
        result = data.get('chart', {}).get('result')
        if not result: return pd.DataFrame()
        
        quote = result[0].get('indicators', {}).get('quote', [{}])[0]
        df = pd.DataFrame({
            'timestamp': result[0].get('timestamp', []),
            'high': quote.get('high', []),
            'low': quote.get('low', []),
            'close': quote.get('close', [])
        })
        return df.dropna().reset_index(drop=True)
    except Exception as e:
        print(f"Error en get_market_data: {e}", flush=True)
        return pd.DataFrame()

# ===== GENERADOR DE LISTA PROGRAMADA =====
def generar_lista_senales():
    df = get_market_data()
    if len(df) < 30: return

    rsi = ta.momentum.rsi(close=df['close'], window=14)
    stoch_k = ta.momentum.stoch(df['high'], df['low'], df['close'], window=14)

    ahora = datetime.now(TIMEZONE_LOCAL)
    senales = []

    # Analizar últimas velas usando EXACTAMENTE los mismos parámetros estrictos
    for i in range(-15, 0):
        rsi_val = rsi.iloc[i]
        stoch_val = stoch_k.iloc[i]
        
        if pd.isna(rsi_val) or pd.isna(stoch_val):
            continue

        # Filtros iguales a las alertas en vivo
        es_call = (rsi_val <= 38) or (stoch_val <= 25)
        es_put = (rsi_val >= 62) or (stoch_val >= 75)

        if es_call and not es_put:
            direccion = "CALL"
        elif es_put and not es_call:
            direccion = "PUT"
        else:
            continue

        tiempo_senal = ahora + timedelta(minutes=len(senales) + 1)
        hora_str = tiempo_senal.strftime("%H:%M")
        senales.append(f"M1  {SYMBOL_DISPLAY}  {hora_str}  {direccion}")

    if senales:
        mensaje = f"📋 <b>LISTA DE SEÑALES PROGRAMADAS</b>\n\n<code>" + "\n".join(senales) + "</code>"
        send_telegram(mensaje)

# ===== ANÁLISIS EN TIEMPO REAL =====
def analyze():
    global LAST_PROCESSED_TIMESTAMP, PRE_ALERT_SENT_FOR_TIMESTAMP
    try:
        df = get_market_data()
        if len(df) < 30: return

        ahora = datetime.now(TIMEZONE_LOCAL)
        segundo_actual = ahora.second
        
        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        stoch_k = ta.momentum.stoch(df['high'], df['low'], df['close'], window=14)

        current_timestamp = df.iloc[-1]['timestamp']
        rsi_actual = rsi_series.iloc[-1]
        stoch_actual = stoch_k.iloc[-1]

        if pd.isna(rsi_actual) or pd.isna(stoch_actual):
            return

        # 1. PRE-ALERTA (Segundo 25 a 45)
        if 25 <= segundo_actual <= 45 and PRE_ALERT_SENT_FOR_TIMESTAMP != current_timestamp:
            pre_call = (rsi_actual <= 40) or (stoch_actual <= 30)
            pre_put = (rsi_actual >= 60) or (stoch_actual >= 70)
            
            if pre_call and not pre_put:
                direccion = "SUBIRÁ (CALL) 🟢"
            elif pre_put and not pre_call:
                direccion = "BAJARÁ (PUT) 🔴"
            else:
                direccion = None

            if direccion:
                entrada = (ahora + timedelta(minutes=1)).strftime("%H:%M:00")
                msg = f"⚡ <b>PRE-ALERTA: {SYMBOL_DISPLAY}</b>\n\n🔮 <b>Proyección:</b> {direccion}\n⏰ <b>ENTRADA:</b> <code>{entrada}</code>\n📉 RSI: {rsi_actual:.2f} | Stoch: {stoch_actual:.2f}"
                send_telegram(msg)
                PRE_ALERT_SENT_FOR_TIMESTAMP = current_timestamp

        # 2. CAMBIO DE VELA M1
        closed_timestamp = df.iloc[-2]['timestamp']
        if LAST_PROCESSED_TIMESTAMP != closed_timestamp:
            LAST_PROCESSED_TIMESTAMP = closed_timestamp
            closed_rsi = rsi_series.iloc[-2]
            closed_stoch = stoch_k.iloc[-2]

            if pd.isna(closed_rsi) or pd.isna(closed_stoch):
                return
            
            es_call = (closed_rsi <= 38) or (closed_stoch <= 25)
            es_put = (closed_rsi >= 62) or (closed_stoch >= 75)
            
            if es_call and not es_put:
                estado = "CALL 🟢 (SUBIDA)"
            elif es_put and not es_call:
                estado = "PUT 🔴 (BAJADA)"
            else:
                estado = "NEUTRAL ⚪"

            msg = f"🕯️ <b>VELA M1 CERRADA</b>\n\n📈 <b>Par:</b> {SYMBOL_DISPLAY}\n📊 <b>Cierre:</b> {df.iloc[-2]['close']}\n📉 RSI: {closed_rsi:.2f} | Stoch: {closed_stoch:.2f}\n🎯 <b>Estado:</b> {estado}"
            send_telegram(msg)

    except Exception as e:
        print(f"Error en analyze: {e}", flush=True)

# ===== INICIO PERMANENTE =====
if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()
    send_telegram(f"🚀 <b>Bot Activo Analizando {SYMBOL_DISPLAY}</b>")
    
    # Se genera la lista inmediatamente al iniciar
    generar_lista_senales()

    while True:
        analyze()
        time.sleep(3)
    
