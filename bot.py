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
SYMBOL = "EURUSD-OTC"
TIMEZONE_LOCAL = ZoneInfo("America/Panama")

print(f"--- BOT CON ANÁLISIS BALANCEADO CALL/PUT ({SYMBOL}) ---", flush=True)

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
        else:
            print(f"Mensaje enviado con éxito a Telegram.", flush=True)
    except Exception as e:
        print(f"Error Telegram Exception: {e}", flush=True)

def get_market_data():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range=1d&interval=1m"
    try:
        res = session.get(url, timeout=10)
        if res.status_code != 200:
            print(f"Error recuperando datos del mercado ({SYMBOL}): Status {res.status_code}", flush=True)
            return pd.DataFrame()

        data = res.json()
        result = data.get('chart', {}).get('result')
        
        if not result or len(result) == 0:
            return pd.DataFrame()

        chart_data = result[0]
        timestamps = chart_data.get('timestamp', [])
        quote = chart_data.get('indicators', {}).get('quote', [{}])[0]

        if not timestamps or not quote:
            return pd.DataFrame()

        df = pd.DataFrame({
            'timestamp': timestamps,
            'high': quote.get('high', []),
            'low': quote.get('low', []),
            'close': quote.get('close', [])
        })
        
        return df.dropna().reset_index(drop=True)
    except Exception as e:
        print(f"Error al procesar datos de mercado: {e}", flush=True)
        return pd.DataFrame()

def analyze():
    global LAST_PROCESSED_TIMESTAMP, PRE_ALERT_SENT_FOR_TIMESTAMP
    
    try:
        df = get_market_data()
        
        if len(df) < 20: 
            return

        ahora = datetime.now(TIMEZONE_LOCAL)
        segundo_actual = ahora.second
        
        # Indicadores técnicos
        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        stoch_k = ta.momentum.stoch(
            high=df['high'], 
            low=df['low'], 
            close=df['close'], 
            window=14, 
            smooth_window=3
        )

        current_candle = df.iloc[-1]
        current_timestamp = current_candle['timestamp']
        
        rsi_actual = rsi_series.iloc[-1]
        stoch_actual = stoch_k.iloc[-1]

        # -------------------------------------------------------------
        # 1. PRE-ALERTA (Evalúa entre el segundo 25 y 45)
        # -------------------------------------------------------------
        if 25 <= segundo_actual <= 45 and PRE_ALERT_SENT_FOR_TIMESTAMP != current_timestamp:
            
            # Criterios balanceados para Pre-Alerta (Niveles intermedios)
            pre_call = (rsi_actual <= 35) or (stoch_actual <= 25)
            pre_put = (rsi_actual >= 65) or (stoch_actual >= 75)

            direccion = None
            if pre_call and not pre_put:
                direccion = "SUBIRÁ (CALL) 🟢"
            elif pre_put and not pre_call:
                direccion = "BAJARÁ (PUT) 🔴"

            if direccion:
                momento_entrada = ahora + timedelta(minutes=1)
                hora_entrada_exacta = momento_entrada.strftime("%H:%M:00")

                msg = (
                    f"⚡ <b>PRE-ALERTA DETECTADA</b>\n\n"
                    f"📈 <b>Par:</b> {SYMBOL}\n"
                    f"🔮 <b>Proyección:</b> <b>{direccion}</b>\n"
                    f"⏰ <b>PRÓXIMA ENTRADA:</b> <code>{hora_entrada_exacta}</code>\n"
                    f"📉 <b>RSI:</b> {rsi_actual:.2f} | <b>Stoch:</b> {stoch_actual:.2f}\n\n"
                    f"📌 <i>Prepárate para entrar a las {hora_entrada_exacta}</i>"
                )
                send_telegram(msg)
                PRE_ALERT_SENT_FOR_TIMESTAMP = current_timestamp

        # -------------------------------------------------------------
        # 2. REPORTE EN CAMBIO DE VELA (M1)
        # -------------------------------------------------------------
        closed_candle = df.iloc[-2]
        closed_timestamp = closed_candle['timestamp']
        closed_rsi = rsi_series.iloc[-2]
        closed_stoch = stoch_k.iloc[-2]

        if LAST_PROCESSED_TIMESTAMP != closed_timestamp:
            LAST_PROCESSED_TIMESTAMP = closed_timestamp
            
            hora_vela = datetime.fromtimestamp(closed_timestamp, tz=TIMEZONE_LOCAL).strftime("%H:%M")
            proxima_vela = (datetime.fromtimestamp(closed_timestamp, tz=TIMEZONE_LOCAL) + timedelta(minutes=1)).strftime("%H:%M:00")

            # Evaluación estricta y mutuamente excluyente
            # Sobreventa (CALL): RSI <= 30 o Estocástico <= 20
            # Sobrecompra (PUT): RSI >= 70 o Estocástico >= 80
            es_call = (closed_rsi <= 30) or (closed_stoch <= 20)
            es_put = (closed_rsi >= 70) or (closed_stoch >= 80)

            if es_call and not es_put:
                estado = "CALL 🟢 (ALERTA DE SUBIDA)"
            elif es_put and not es_call:
                estado = "PUT 🔴 (ALERTA DE BAJADA)"
            else:
                estado = "SIN ALERTA (MERCADO NEUTRAL) ⚪"

            msg = (
                f"🕯️ <b>CAMBIO DE VELA M1</b> ({hora_vela})\n\n"
                f"📈 <b>Par:</b> {SYMBOL}\n"
                f"📊 <b>Precio Cierre:</b> {closed_candle['close']}\n"
                f"📉 <b>RSI:</b> {closed_rsi:.2f} | <b>Stoch:</b> {closed_stoch:.2f}\n"
                f"🎯 <b>Estado:</b> {estado}\n\n"
                f"⏳ <b>Próximo Análisis / Vela:</b> <code>{proxima_vela}</code>"
            )
            send_telegram(msg)

    except Exception as e:
        print(f"Error en análisis: {e}", flush=True)

# ===== INICIALIZACIÓN =====
threading.Thread(target=run_health_server, daemon=True).start()
send_telegram(f"🚀 <b>Bot Activo</b>\n<i>Monitoreando {SYMBOL} con alertas balanceadas CALL/PUT.</i>")

while True:
    analyze()
    time.sleep(5)
