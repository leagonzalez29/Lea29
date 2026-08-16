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

# ===== CONFIGURACIÓN =====
TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
CHAT_ID = "544714195"
SYMBOL = "AUDCAD=X"

print("--- INICIANDO SCRIPT AUD/CAD 1M (CORREGIDO) ---", flush=True)

# Variable global para registrar la última vela procesada y evitar repeticiones
LAST_CANDLE_TIMESTAMP = None
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
        print(f"Respuesta Telegram: {res.status_code}", flush=True)
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}", flush=True)

# ===== OBTENER DATOS DE YAHOO FINANCE =====
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

# ===== LÓGICA DE ANÁLISIS Y DETECCIÓN DE VELA =====
def analyze():
    global LAST_CANDLE_TIMESTAMP
    try:
        df = get_market_data()
        if len(df) < 15:
            return

        # Tomamos el timestamp de la última vela cerrada (penúltima posición)
        latest_candle = df.iloc[-1]
        candle_time = latest_candle['timestamp']
        last_price = latest_candle['close']

        # Si el timestamp es igual al anterior, la vela aún no ha cambiado -> ignorar
        if LAST_CANDLE_TIMESTAMP == candle_time:
            return

        # Si llegamos aquí, ¡HAY NUEVA VELA!
        LAST_CANDLE_TIMESTAMP = candle_time

        # Cálculo de RSI
        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        last_rsi = rsi_series.dropna().iloc[-1]
        hora_actual = datetime.now().strftime("%H:%M:%S")

        print(f"[{hora_actual}] Nueva vela 1m AUD/CAD | Precio: {last_price:.5f} | RSI: {last_rsi:.2f}", flush=True)

        # Evaluamos si hay señal operativa
        direccion = "NEUTRAL"
        if last_rsi < 30:
            direccion = "🟢 CALL (COMPRA)"
        elif last_rsi > 70:
            direccion = "🔴 PUT (VENTA)"

        # Notificación enviada a Telegram por cada cambio de vela
        mensaje = (
            "📊 <b>NUEVA VELA DETECTADA (1M)</b>\n\n"
            "🔰 <b>ACTIVO:</b> AUD/CAD\n"
            f"⏰ <b>HORA:</b> {hora_actual}\n"
            f"📊 <b>PRECIO:</b> {last_price:.5f}\n"
            f"📉 <b>RSI (14):</b> {last_rsi:.2f}\n"
            f"🎯 <b>ESTADO/SEÑAL:</b> {direccion}\n\n"
            "🔥 <b>Bot de Monitoreo Activo</b> 🔥"
        )
        send_telegram(mensaje)

    except Exception as e:
        print(f"Error en análisis: {e}", flush=True)

# ===== INICIALIZACIÓN =====
# Servidor web en hilo secundario
threading.Thread(target=run_health_server, daemon=True).start()

# Mensaje de inicio SOLO UNA VEZ al arrancar el contenedor
send_telegram("🚀 <b>¡Bot iniciado correctamente en Render!</b>\n<i>Monitoreando velas de 1m en AUD/CAD...</i>")

# Bucle principal (Consulta cada 10 segundos sin saturar la red)
while True:
    analyze()
    time.sleep(10)
    
