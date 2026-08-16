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
SYMBOL = "EURUSD=X"
TIMEZONE_LOCAL = ZoneInfo("America/Panama")  # UTC-5

print("--- INICIANDO SCRIPT EUR/USD 1M (CICLO DE 24 HORAS) ---", flush=True)

LAST_CANDLE_TIMESTAMP = None
ULTIMA_FECHA_RESUMEN = None

# Acumuladores diarios
contador_calls = 0
contador_puts = 0
precio_apertura_dia = None
precio_actual = None

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

# ===== LÓGICA DE ANÁLISIS =====
def analyze():
    global LAST_CANDLE_TIMESTAMP, ULTIMA_FECHA_RESUMEN
    global contador_calls, contador_puts, precio_apertura_dia, precio_actual
    
    ahora_local = datetime.now(TIMEZONE_LOCAL)
    fecha_hoy = ahora_local.strftime("%Y-%m-%d")

    # 1. ENVIAR RESUMEN CADA 24 HORAS (A la medianoche 00:00)
    if ULTIMA_FECHA_RESUMEN is not None and ULTIMA_FECHA_RESUMEN != fecha_hoy:
        # Calcular balance general de las 24h
        tendencia = "BULLISH (ALCISTA)" if (precio_actual or 0) >= (precio_apertura_dia or 0) else "BEARISH (BAJISTA)"
        
        mensaje_diario = (
            "📈 <b>INFORME RESUMEN 24 HORAS DE MERCADO</b> 📉\n\n"
            f"🔰 <b>ACTIVO:</b> EUR/USD\n"
            f"📅 <b>FECHA CERRADA:</b> {ULTIMA_FECHA_RESUMEN}\n"
            f"🟢 <b>SEÑALES CALL GENERADAS:</b> {contador_calls}\n"
            f"🔴 <b>SEÑALES PUT GENERADAS:</b> {contador_puts}\n"
            f"📊 <b>TENDENCIA GENERAL 24H:</b> {tendencia}\n\n"
            "🔄 <b>REINICIANDO CICLO PARA LAS PRÓXIMAS 24 HORAS...</b>"
        )
        send_telegram(mensaje_diario)
        
        # Reiniciar contadores para las nuevas 24 horas
        contador_calls = 0
        contador_puts = 0
        precio_apertura_dia = None

    ULTIMA_FECHA_RESUMEN = fecha_hoy

    try:
        df = get_market_data()
        if len(df) < 15:
            return

        latest_candle = df.iloc[-1]
        candle_time = latest_candle['timestamp']
        last_price = latest_candle['close']
        precio_actual = last_price

        # Guardar precio inicial de las 24 horas
        if precio_apertura_dia is None:
            precio_apertura_dia = last_price

        if LAST_CANDLE_TIMESTAMP == candle_time:
            return

        LAST_CANDLE_TIMESTAMP = candle_time

        # Cálculo de RSI
        rsi_series = ta.momentum.rsi(close=df['close'], window=14)
        last_rsi = rsi_series.dropna().iloc[-1]
        hora_actual = ahora_local.strftime("%H:%M:%S")

        direccion = "NEUTRAL"
        if last_rsi < 30:
            direccion = "🟢 CALL (COMPRA)"
            contador_calls += 1
        elif last_rsi > 70:
            direccion = "🔴 PUT (VENTA)"
            contador_puts += 1

        print(f"[{hora_actual}] Vela 1m EUR/USD | Precio: {last_price:.5f} | RSI: {last_rsi:.2f} | {direccion}", flush=True)

        # Solo notificar a Telegram si se genera una señal real de compra o venta
        if direccion != "NEUTRAL":
            mensaje = (
                "⚠️ <b>SEÑAL DE MERCADO EN TIEMPO REAL</b>\n\n"
                "🔰 <b>ACTIVO:</b> EUR/USD\n"
                f"⏰ <b>HORA:</b> {hora_actual}\n"
                f"📊 <b>PRECIO:</b> {last_price:.5f}\n"
                f"📉 <b>RSI (14):</b> {last_rsi:.2f}\n"
                f"🎯 <b>OPERACIÓN SUGERIDA:</b> {direccion}\n\n"
                "🔥 <b>Bot de Monitoreo Activo</b> 🔥"
            )
            send_telegram(mensaje)

    except Exception as e:
        print(f"Error en análisis: {e}", flush=True)

# ===== INICIALIZACIÓN =====
threading.Thread(target=run_health_server, daemon=True).start()

send_telegram("🚀 <b>¡Bot en Render Iniciado!</b>\n<i>Monitoreando EUR/USD continuamente. Generará reporte y reiniciará cada 24h.</i>")

while True:
    analyze()
    time.sleep(10)
        
