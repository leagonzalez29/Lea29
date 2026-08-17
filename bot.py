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
TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
CHAT_ID = "544714195"
SYMBOL = "AUDCAD=X"
TIMEZONE_LOCAL = ZoneInfo("America/Panama")

print("--- BOT COMPLETO: NOTIFICACIONES CONTINUAS + ANÁLISIS BALANCEADO ---", flush=True)

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
        
        # Indicadores técnicos equilibrados
        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        stoch_k = ta.momentum.stoch(high=df['high'], low=df['low'], close=df['close'], window=14, smooth_window=3)
        sma_fast = ta.trend.sma_indicator(close=df['close'], window=5)

        current_candle = df.iloc[-1]
        current_timestamp = current_candle['timestamp']
        
        rsi_actual = rsi_series.iloc[-1]
        stoch_actual = stoch_k.iloc[-1]
        close_actual = current_candle['close']
        sma_actual = sma_fast.iloc[-1]

        # -------------------------------------------------------------
        # 1. PRE-ALERTA (Entre segundo :25 y :45 de la vela activa)
        # -------------------------------------------------------------
        if 25 <= segundo_actual <= 45 and PRE_ALERT_SENT_FOR_TIMESTAMP != current_timestamp:
            
            # Evaluación equilibrada para CALL y PUT
            prediccion_subida = (rsi_actual <= 42 and stoch_actual <= 30) or (close_actual > sma_actual and rsi_actual < 48)
            prediccion_bajada = (rsi_actual >= 58 and stoch_actual >= 70) or (close_actual < sma_actual and rsi_actual > 52)

            direccion = None
            if prediccion_subida:
                direccion = "SUBIRÁ (CALL) 🟢"
            elif prediccion_bajada:
                direccion = "BAJARÁ (PUT) 🔴"

            if direccion:
                momento_entrada = ahora + timedelta(minutes=1)
                hora_entrada_exacta = momento_entrada.strftime("%H:%M:00")

                msg = (
                    f"⚡ <b>PRE-ALERTA DETECTADA</b>\n\n"
                    f"📈 <b>Par:</b> {SYMBOL}\n"
                    f"🔮 <b>Proyección:</b> <b>{direccion}</b>\n"
                    f"⏰ <b>PRÓXIMA ALERTA / ENTRADA:</b> <code>{hora_entrada_exacta}</code>\n"
                    f"📉 <b>RSI:</b> {rsi_actual:.2f} | <b>Stoch:</b> {stoch_actual:.2f}\n\n"
                    f"📌 <i>Prepárate para entrar exactamente a las {hora_entrada_exacta}</i>"
                )
                send_telegram(msg)
                PRE_ALERT_SENT_FOR_TIMESTAMP = current_timestamp

        # -------------------------------------------------------------
        # 2. REPORTE CONTINUO EN CADA CAMBIO DE VELA (Con o Sin Alerta)
        # -------------------------------------------------------------
        closed_candle = df.iloc[-2]
        closed_timestamp = closed_candle['timestamp']
        closed_rsi = rsi_series.iloc[-2]
        closed_stoch = stoch_k.iloc[-2]

        if LAST_PROCESSED_TIMESTAMP != closed_timestamp:
            LAST_PROCESSED_TIMESTAMP = closed_timestamp
            
            hora_vela = datetime.fromtimestamp(closed_timestamp, tz=TIMEZONE_LOCAL).strftime("%H:%M")
            proxima_vela = (datetime.fromtimestamp(closed_timestamp, tz=TIMEZONE_LOCAL) + timedelta(minutes=1)).strftime("%H:%M:00")

            # Determina si hay señal o si el mercado está neutral
            if closed_rsi <= 35 or closed_stoch <= 20:
                estado = "CALL 🟢 (ENTRADA CONFIRMADA A LA ALZA)"
            elif closed_rsi >= 65 or closed_stoch >= 80:
                estado = "PUT 🔴 (ENTRADA CONFIRMADA A LA BAJA)"
            else:
                estado = "SIN ALERTA (MERCADO NEUTRAL) ⚪"

            msg = (
                f"🕯️ <b>CAMBIO DE VELA M1</b> ({hora_vela})\n\n"
                f"📈 <b>Par:</b> {SYMBOL}\n"
                f"📊 <b>Precio Cierre:</b> {closed_candle['close']}\n"
                f"📉 <b>RSI:</b> {closed_rsi:.2f}\n"
                f"🎯 <b>Estado:</b> {estado}\n\n"
                f"⏳ <b>Próximo Análisis / Vela:</b> <code>{proxima_vela}</code>"
            )
            send_telegram(msg)

    except Exception as e:
        print(f"Error en análisis: {e}", flush=True)

# ===== INICIALIZACIÓN =====
threading.Thread(target=run_health_server, daemon=True).start()
send_telegram("🚀 <b>Bot Activo con Notificación Continua</b>\n<i>Informando velas neutrales y estimación de próxima alerta.</i>")

while True:
    analyze()
    time.sleep(5)

