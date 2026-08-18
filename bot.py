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

# ===== CONFIGURACIÓN DEL BOT Y OPERATORIA =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs")
CHAT_ID = os.environ.get("CHAT_ID", "544714195")

SYMBOL = "BTC-USD"
TIMEZONE_LOCAL = ZoneInfo("America/Panama")

# Parámetros de Operación
MONTO_OPERACION = 1           # Monto por operación ($)
TIEMPO_OPERACION = 1          # Duración en minutos
TEMPORALIDAD = "1m"           # "1m" o "5m"
TIPO_OPERACION = "Binarias"   # Tipo de operación
ESTRATEGIA = "Bandas de Bollinger + RSI"

# Parámetros Técnicos
RSI_PERIOD = 14
RSI_OVERBOUGHT = 65
RSI_OVERSOLD = 35
BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2.0

print(f"--- BOT ANALIZANDO {SYMBOL} ({TEMPORALIDAD}) ---", flush=True)

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

def get_market_data():
    # Rango dinámico según temporalidad
    interval_param = TEMPORALIDAD
    range_param = "1d" if TEMPORALIDAD == "1m" else "5d"
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range={range_param}&interval={interval_param}"
    try:
        res = session.get(url, timeout=10)
        if res.status_code != 200:
            print(f"Error ({SYMBOL}): Status {res.status_code}", flush=True)
            return pd.DataFrame()

        data = res.json()
        result = data.get('chart', {}).get('result')
        if not result: return pd.DataFrame()
        
        quote = result[0].get('indicators', {}).get('quote', [{}])[0]
        df = pd.DataFrame({
            'timestamp': result[0].get('timestamp', []),
            'open': quote.get('open', []),
            'high': quote.get('high', []),
            'low': quote.get('low', []),
            'close': quote.get('close', [])
        })
        return df.dropna().reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame()

def analyze():
    global LAST_PROCESSED_TIMESTAMP, PRE_ALERT_SENT_FOR_TIMESTAMP
    try:
        df = get_market_data()
        if len(df) < BOLLINGER_PERIOD + 5: return

        ahora = datetime.now(TIMEZONE_LOCAL)
        segundo_actual = ahora.second
        
        # --- Cálculo de Indicadores ---
        # 1. RSI
        rsi_series = ta.momentum.rsi(close=df['close'], window=RSI_PERIOD)
        
        # 2. Bandas de Bollinger
        bb = ta.volatility.BollingerBands(close=df['close'], window=BOLLINGER_PERIOD, window_dev=BOLLINGER_STD)
        bb_hband = bb.bollinger_hband()
        bb_lband = bb.bollinger_lband()

        current_timestamp = df.iloc[-1]['timestamp']
        close_actual = df.iloc[-1]['close']
        rsi_actual = rsi_series.iloc[-1]
        bb_high_act = bb_hband.iloc[-1]
        bb_low_act = bb_lband.iloc[-1]

        # 1. PRE-ALERTA (Ventana de anticipación)
        if 25 <= segundo_actual <= 45 and PRE_ALERT_SENT_FOR_TIMESTAMP != current_timestamp:
            pre_call = (close_actual <= bb_low_act) and (rsi_actual <= RSI_OVERSOLD + 5)
            pre_put = (close_actual >= bb_high_act) and (rsi_actual >= RSI_OVERBOUGHT - 5)
            
            direccion = None
            if pre_call and not pre_put:
                direccion = "SUBIRÁ (CALL) 🟢"
            elif pre_put and not pre_call:
                direccion = "BAJARÁ (PUT) 🔴"

            if direccion:
                mins_add = 1 if TEMPORALIDAD == "1m" else 5
                entrada = (ahora + timedelta(minutes=mins_add)).strftime("%H:%M:00")
                
                msg = (
                    f"⚡ <b>PRE-ALERTA ({TIPO_OPERACION})</b>\n"
                    f"📈 <b>Par:</b> {SYMBOL} | <b>Gráfico:</b> {TEMPORALIDAD}\n\n"
                    f"🔮 <b>Proyección:</b> {direccion}\n"
                    f"⏰ <b>Hora Entrada:</b> <code>{entrada}</code>\n"
                    f"⏱️ <b>Expiración:</b> {TIEMPO_OPERACION} Min\n"
                    f"💵 <b>Monto Sugerido:</b> ${MONTO_OPERACION}\n\n"
                    f"📊 <b>Indicadores actuales:</b>\n"
                    f"• RSI: {rsi_actual:.2f}\n"
                    f"• Precio: {close_actual:.2f}\n"
                    f"• Banda Sup: {bb_high_act:.2f}\n"
                    f"• Banda Inf: {bb_low_act:.2f}"
                )
                send_telegram(msg)
                PRE_ALERT_SENT_FOR_TIMESTAMP = current_timestamp

        # 2. CONFIRMACIÓN AL CIERRE DE VELA
        closed_timestamp = df.iloc[-2]['timestamp']
        if LAST_PROCESSED_TIMESTAMP != closed_timestamp:
            LAST_PROCESSED_TIMESTAMP = closed_timestamp
            
            closed_close = df.iloc[-2]['close']
            closed_rsi = rsi_series.iloc[-2]
            closed_bb_high = bb_hband.iloc[-2]
            closed_bb_low = bb_lband.iloc[-2]
            
            # Condición Estrategia: Toque/Corte de Banda + RSI
            es_call = (closed_close <= closed_bb_low) and (closed_rsi <= RSI_OVERSOLD)
            es_put = (closed_close >= closed_bb_high) and (closed_rsi >= RSI_OVERBOUGHT)
            
            if es_call and not es_put:
                estado = "🟢 CALL (COMPRA)"
            elif es_put and not es_call:
                estado = "🔴 PUT (VENTA)"
            else:
                estado = "⚪ NEUTRAL"

            msg = (
                f"🕯️ <b>VELA {TEMPORALIDAD.upper()} CERRADA</b>\n\n"
                f"🎯 <b>Señal:</b> {estado}\n"
                f"📌 <b>Tipo:</b> {TIPO_OPERACION}\n"
                f"💰 <b>Monto:</b> ${MONTO_OPERACION} | ⌛ <b>Tiempo:</b> {TIEMPO_OPERACION} min\n\n"
                f"📊 <b>Datos de Cierre:</b>\n"
                f"• Precio Cierre: {closed_close:.2f}\n"
                f"• RSI: {closed_rsi:.2f}\n"
                f"• BB Superior: {closed_bb_high:.2f}\n"
                f"• BB Inferior: {closed_bb_low:.2f}"
            )
            send_telegram(msg)

    except Exception as e:
        print(f"Error: {e}", flush=True)

# ===== INICIO =====
threading.Thread(target=run_health_server, daemon=True).start()

# Mensaje de bienvenida con la parametrización
init_msg = (
    f"🚀 <b>BOT DE TRADING INICIADO</b>\n\n"
    f"📊 <b>Par:</b> {SYMBOL}\n"
    f"⏱️ <b>Temporalidad Gráfico:</b> {TEMPORALIDAD}\n"
    f"📈 <b>Tipo de Operación:</b> {TIPO_OPERACION}\n"
    f"⏳ <b>Tiempo por Operación:</b> {TIEMPO_OPERACION} min\n"
    f"💵 <b>Monto por Operación:</b> ${MONTO_OPERACION}\n"
    f"🧠 <b>Estrategia:</b> {ESTRATEGIA}"
)
send_telegram(init_msg)

while True:
    analyze()
    time.sleep(5)
