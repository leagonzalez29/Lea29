from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import sys
import threading
import time
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import ta

sys.stdout.reconfigure(line_buffering=True)

# ===== CONFIGURACIÓN =====
TELEGRAM_TOKEN = os.environ.get(
    "TELEGRAM_TOKEN", "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
)
CHAT_ID = os.environ.get("CHAT_ID", "544714195")

SYMBOL_YAHOO = "BTC-USD"
SYMBOL_DISPLAY = "BTC-USD"
TIMEZONE_LOCAL = ZoneInfo("America/Panama")

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
})

PANEL_MESSAGE_ID = None
OPERACION_ACTIVA = None
GANANCIAS = 0
PERDIDAS = 0
ULTIMA_MINUTA_EVALUADA = None


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


# ===== CONEXIÓN TELEGRAM =====
def send_telegram(message):
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
  payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
  try:
    res = session.post(url, data=payload, timeout=10)
    if res.status_code == 200:
      return res.json().get("result", {}).get("message_id")
  except Exception as e:
    print(f"Error Telegram: {e}", flush=True)
  return None


def edit_telegram(message_id, message):
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
  payload = {
      "chat_id": CHAT_ID,
      "message_id": message_id,
      "text": message,
      "parse_mode": "HTML",
  }
  try:
    session.post(url, data=payload, timeout=10)
  except Exception as e:
    print(f"Error editando Telegram: {e}", flush=True)


# ===== DATOS DE MERCADO =====
def get_market_data():
  url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL_YAHOO}?range=1d&interval=1m"
  try:
    res = session.get(url, timeout=10)
    if res.status_code != 200:
      return pd.DataFrame()

    data = res.json()
    result = data.get("chart", {}).get("result")
    if not result:
      return pd.DataFrame()

    quote = result[0].get("indicators", {}).get("quote", [{}])[0]
    df = pd.DataFrame({
        "timestamp": result[0].get("timestamp", []),
        "high": quote.get("high", []),
        "low": quote.get("low", []),
        "close": quote.get("close", []),
    })
    return df.dropna().reset_index(drop=True)
  except Exception as e:
    print(f"Error en get_market_data: {e}", flush=True)
    return pd.DataFrame()


# ===== EVALUAR OPORTUNIDAD EN TIEMPO REAL =====
def evaluar_entrada_mercado():
  df = get_market_data()
  if len(df) < 30:
    return None

  rsi = ta.momentum.rsi(close=df["close"], window=14).iloc[-1]
  stoch = ta.momentum.stoch(
      df["high"], df["low"], df["close"], window=14
  ).iloc[-1]

  if pd.isna(rsi) or pd.isna(stoch):
    return None

  # Condición estricta de COMPRA (Sobreventa confirmada)
  if rsi <= 35 and stoch <= 20:
    return "ARRIBA"

  # Condición estricta de VENTA (Sobrecompra confirmada)
  if rsi >= 65 and stoch >= 80:
    return "ABAJO"

  return None


def construir_mensaje_panel():
  texto = "OPERACIONES : 🟢🔴\n"
  texto += f"<b>{SYMBOL_DISPLAY}</b>\n"
  texto += f"<b>{GANANCIAS} - {PERDIDAS} PROFIT :)</b>\n\n"

  if OPERACION_ACTIVA:
    op = OPERACION_ACTIVA
    emoji_dir = "⬆️" if op["direccion"] == "ARRIBA" else "⬇️"
    tipo_op = "COMPRA" if op["direccion"] == "ARRIBA" else "VENTA"

    marca = ""
    if op["estado"] == "POSI":
      marca = " POSI ✅"
    elif op["estado"] == "NEGA":
      marca = " ❌"

    texto += f"<code>{op['hora_entrada']} - {op['direccion']}{marca}</code>\n"
    texto += f"\n🔴 <b>{tipo_op} | {op['direccion']} {emoji_dir}</b>\n"
    texto += f"Entrada: {op['hora_entrada']} Salida: {op['hora_salida']}"
  else:
    texto += "<i>Buscando oportunidad de alta probabilidad... ⏳</i>"

  return texto


def procesar_bot():
  global PANEL_MESSAGE_ID, OPERACION_ACTIVA, GANANCIAS, PERDIDAS, ULTIMA_MINUTA_EVALUADA

  ahora = datetime.now(TIMEZONE_LOCAL)
  hora_actual_str = ahora.strftime("%H:%M")
  segundo_actual = ahora.second

  df = get_market_data()
  if df.empty:
    return

  precio_actual = df.iloc[-1]["close"]

  # 1. Monitorear y cerrar operación activa si concluyó
  if OPERACION_ACTIVA and OPERACION_ACTIVA["estado"] == "EN_CURSO":
    if hora_actual_str >= OPERACION_ACTIVA["hora_salida"]:
      OPERACION_ACTIVA["precio_salida"] = precio_actual

      if OPERACION_ACTIVA["direccion"] == "ARRIBA":
        ganada = (
            OPERACION_ACTIVA["precio_salida"]
            > OPERACION_ACTIVA["precio_entrada"]
        )
      else:
        ganada = (
            OPERACION_ACTIVA["precio_salida"]
            < OPERACION_ACTIVA["precio_entrada"]
        )

      if ganada:
        OPERACION_ACTIVA["estado"] = "POSI"
        GANANCIAS += 1
      else:
        OPERACION_ACTIVA["estado"] = "NEGA"
        PERDIDAS += 1

      edit_telegram(PANEL_MESSAGE_ID, construir_mensaje_panel())
      time.sleep(5)  # Breve pausa tras resultado
      OPERACION_ACTIVA = None
      return

  # 2. Buscar nueva entrada solo en el segundo 50 a 58 de cada minuto (si no hay posición activa)
  if not OPERACION_ACTIVA and 50 <= segundo_actual <= 58:
    if ULTIMA_MINUTA_EVALUADA != hora_actual_str:
      direccion = evaluar_entrada_mercado()

      if direccion:
        ULTIMA_MINUTA_EVALUADA = hora_actual_str
        hora_entrada = ahora + timedelta(minutes=1)
        hora_salida = hora_entrada + timedelta(minutes=1)

        OPERACION_ACTIVA = {
            "hora_entrada": hora_entrada.strftime("%H:%M"),
            "hora_salida": hora_salida.strftime("%H:%M"),
            "direccion": direccion,
            "estado": "EN_CURSO",
            "precio_entrada": precio_actual,
            "precio_salida": None,
        }

        if PANEL_MESSAGE_ID:
          edit_telegram(PANEL_MESSAGE_ID, construir_mensaje_panel())
        else:
          PANEL_MESSAGE_ID = send_telegram(construir_mensaje_panel())


# ===== BUCLE PRINCIPAL =====
if __name__ == "__main__":
  threading.Thread(target=run_health_server, daemon=True).start()

  print(f"--- BOT DE ANÁLISIS EN TIEMPO REAL: {SYMBOL_DISPLAY} ---", flush=True)

  msg_inicial = construir_mensaje_panel()
  PANEL_MESSAGE_ID = send_telegram(msg_inicial)

  while True:
    try:
      procesar_bot()
    except Exception as e:
      print(f"Error en bucle principal: {e}", flush=True)

    time.sleep(2)
    
