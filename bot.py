from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import random
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

CANTIDAD_SENALES = random.randint(7, 10)

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
})

PANEL_MESSAGE_ID = None
LISTA_SENALES = []
GANANCIAS = 0
PERDIDAS = 0


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


# ===== GENERACIÓN DE SEÑALES MEJORADA CON TENDENCIA Y RSI REAL =====
def proyectar_horarios():
  df = get_market_data()
  if len(df) < 30:
    return []

  # Indicadores Técnicos
  rsi = ta.momentum.rsi(close=df["close"], window=14).iloc[-1]
  ema_rapida = ta.trend.ema_indicator(close=df["close"], window=9).iloc[-1]
  ema_lenta = ta.trend.ema_indicator(close=df["close"], window=21).iloc[-1]

  ahora = datetime.now(TIMEZONE_LOCAL)
  senales_programadas = []

  # Determinar dirección base respetando la tendencia real del mercado
  if pd.isna(rsi) or pd.isna(ema_rapida) or pd.isna(ema_lenta):
    direccion_base = "ARRIBA"
  elif rsi >= 70:
    direccion_base = "ABAJO"  # Sobrecompra extrema -> Posible reversión
  elif rsi <= 30:
    direccion_base = "ARRIBA"  # Sobreventa extrema -> Posible rebote
  elif ema_rapida > ema_lenta:
    direccion_base = "ARRIBA"  # Tendencia Alcista -> Operar a favor
  else:
    direccion_base = "ABAJO"  # Tendencia Bajista -> Operar a favor

  for m in range(1, CANTIDAD_SENALES + 1):
    # Si el mercado no está en extremos, varía la proyección manteniendo el sesgo de la tendencia
    if 30 < rsi < 70:
      direccion = (
          direccion_base if m % 3 != 0 else (
              "ABAJO" if direccion_base == "ARRIBA" else "ARRIBA"
          )
      )
    else:
      direccion = direccion_base

    hora_entrada = ahora + timedelta(minutes=m)
    hora_salida = hora_entrada + timedelta(minutes=1)

    senales_programadas.append({
        "hora_entrada": hora_entrada.strftime("%H:%M"),
        "hora_salida": hora_salida.strftime("%H:%M"),
        "direccion": direccion,
        "estado": "PENDIENTE",
        "precio_entrada": None,
        "precio_salida": None,
    })

  return senales_programadas


def construir_mensaje_panel(entrada_activa=None):
  texto = "OPERACIONES : 🟢🔴\n"
  texto += f"<b>{SYMBOL_DISPLAY}</b>\n"
  texto += f"<b>{GANANCIAS} - {PERDIDAS} PROFIT :)</b>\n\n"

  for s in LISTA_SENALES:
    marca = ""
    if s["estado"] == "POSI":
      marca = " POSI ✅"
    elif s["estado"] == "NEGA":
      marca = " ❌"

    texto += f"<code>{s['hora_entrada']} - {s['direccion']}{marca}</code>\n"

  if entrada_activa:
    emoji_dir = "⬆️" if entrada_activa["direccion"] == "ARRIBA" else "⬇️"
    tipo_op = "COMPRA" if entrada_activa["direccion"] == "ARRIBA" else "VENTA"
    texto += (
        f"\n🔴 <b>{tipo_op} | {entrada_activa['direccion']} {emoji_dir}</b>\n"
    )
    texto += (
        f"Entrada: {entrada_activa['hora_entrada']} Salida:"
        f" {entrada_activa['hora_salida']}"
    )

  return texto


def procesar_catalogador():
  global PANEL_MESSAGE_ID, LISTA_SENALES, GANANCIAS, PERDIDAS

  ahora = datetime.now(TIMEZONE_LOCAL)
  hora_actual_str = ahora.strftime("%H:%M")
  df = get_market_data()

  if df.empty:
    return

  precio_actual = df.iloc[-1]["close"]
  actualizar_panel = False
  operacion_en_curso = None

  for s in LISTA_SENALES:
    # Capturar Entrada
    if (
        s["estado"] == "PENDIENTE"
        and s["hora_entrada"] == hora_actual_str
        and s["precio_entrada"] is None
    ):
      s["precio_entrada"] = precio_actual
      operacion_en_curso = s
      actualizar_panel = True

    if (
        s["estado"] == "PENDIENTE"
        and s["precio_entrada"] is not None
        and s["hora_salida"] >= hora_actual_str
    ):
      operacion_en_curso = s

    # Cierre de operación al terminar el minuto
    if (
        s["estado"] == "PENDIENTE"
        and s["precio_entrada"] is not None
        and hora_actual_str >= s["hora_salida"]
    ):
      s["precio_salida"] = precio_actual

      if s["direccion"] == "ARRIBA":
        ganada = s["precio_salida"] > s["precio_entrada"]
      else:
        ganada = s["precio_salida"] < s["precio_entrada"]

      if ganada:
        s["estado"] = "POSI"
        GANANCIAS += 1
      else:
        s["estado"] = "NEGA"
        PERDIDAS += 1

      actualizar_panel = True

  if actualizar_panel and PANEL_MESSAGE_ID:
    nuevo_texto = construir_mensaje_panel(operacion_en_curso)
    edit_telegram(PANEL_MESSAGE_ID, nuevo_texto)


# ===== BUCLE PRINCIPAL =====
if __name__ == "__main__":
  threading.Thread(target=run_health_server, daemon=True).start()

  print(f"--- BOT ANALIZANDO {SYMBOL_DISPLAY} ---", flush=True)

  LISTA_SENALES = proyectar_horarios()

  if LISTA_SENALES:
    msg_inicial = construir_mensaje_panel()
    PANEL_MESSAGE_ID = send_telegram(msg_inicial)

  while True:
    try:
      procesar_catalogador()
    except Exception as e:
      print(f"Error en bucle principal: {e}", flush=True)

    time.sleep(3)
      
