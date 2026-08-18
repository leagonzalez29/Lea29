import os
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import ta

sys.stdout.reconfigure(line_buffering=True)

# ===== CONFIGURACIÓN Y VARIABLES DE ENTORNO =====
TELEGRAM_TOKEN = os.environ.get(
    "TELEGRAM_TOKEN", "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
)
CHAT_ID = os.environ.get("CHAT_ID", "544714195")

SYMBOL_YAHOO = "BTC-USD"
SYMBOL_DISPLAY = "BTC-USD"
TIMEZONE_LOCAL = ZoneInfo("America/Panama")
HORAS_PROYECCION = 2  # Proyección para las próximas 2 horas

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
})

# Estado global del panel
PANEL_MESSAGE_ID = None
LISTA_SENALES = []
GANANCIAS = 0
PERDIDAS = 0


# ===== SERVIDOR HEALTH CHECK PARA RENDER =====
class HealthCheckHandler(BaseHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    self.wfile.write(b"Bot activo y catalogando")

  def do_HEAD(self):
    self.send_response(200)
    self.end_headers()

  def log_message(self, format, *args):
    return


def run_health_server():
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
  server.serve_forever()


# ===== FUNCIONES DE CONEXIÓN A TELEGRAM =====
def send_telegram(message):
  """Envía un mensaje nuevo y retorna el message_id para poder editarlo después."""
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
  payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
  try:
    res = session.post(url, data=payload, timeout=10)
    if res.status_code == 200:
      return res.json().get("result", {}).get("message_id")
    else:
      print(f"Error Telegram HTTP {res.status_code}: {res.text}", flush=True)
  except Exception as e:
    print(f"Error enviando mensaje a Telegram: {e}", flush=True)
  return None


def edit_telegram(message_id, message):
  """Actualiza el mensaje existente en Telegram con los resultados en vivo."""
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
    print(f"Error editando mensaje en Telegram: {e}", flush=True)


# ===== OBTENCIÓN DE DATOS DE MERCADO =====
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


# ===== GENERACIÓN Y PROYECCIÓN DE SEÑALES (PUNTOS ALTOS Y BAJOS) =====
def proyectar_horarios():
  """Genera el bloque proyectado identificando techos y suelos."""
  df = get_market_data()
  if len(df) < 30:
    return []

  rsi_series = ta.momentum.rsi(close=df["close"], window=14)
  stoch_series = ta.momentum.stoch(
      df["high"], df["low"], df["close"], window=14
  )

  bb = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
  bb_high = bb.bollinger_hband()
  bb_low = bb.bollinger_lband()

  ahora = datetime.now(TIMEZONE_LOCAL)
  senales_programadas = []

  total_minutos = HORAS_PROYECCION * 60
  intervalo = 6  # Espaciado de 6 minutos entre operaciones

  for m in range(2, total_minutos, intervalo):
    idx = -(m % 25) - 1

    rsi_val = rsi_series.iloc[idx]
    stoch_val = stoch_series.iloc[idx]
    close_val = df["close"].iloc[idx]
    bb_h_val = bb_high.iloc[idx]
    bb_l_val = bb_low.iloc[idx]

    if pd.isna(rsi_val) or pd.isna(stoch_val):
      continue

    # PUNTO ALTO / TECHO = VENDER (ABAJO)
    es_punto_alto = (
        (rsi_val >= 60) or (stoch_val >= 70) or (close_val >= bb_h_val)
    )

    # PUNTO BAJO / SUELO = COMPRAR (ARRIBA)
    es_punto_bajo = (
        (rsi_val <= 40) or (stoch_val <= 30) or (close_val <= bb_l_val)
    )

    if es_punto_alto and not es_punto_bajo:
      direccion = "ABAJO"
    elif es_punto_bajo and not es_punto_alto:
      direccion = "ARRIBA"
    else:
      # Alternancia dinámica si se encuentra en zona neutra
      direccion = "ARRIBA" if (len(senales_programadas) % 2 == 0) else "ABAJO"

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


# ===== CONSTRUCTO DE LA PLANTILLA VISUAL =====
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


# ===== BUCLE DE VERIFICACIÓN Y EVALUACIÓN =====
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
    # 1. CAPTURAR ENTRADA
    if (
        s["estado"] == "PENDIENTE"
        and s["hora_entrada"] == hora_actual_str
        and s["precio_entrada"] is None
    ):
      s["precio_entrada"] = precio_actual
      print(
          f"[{hora_actual_str}] Entrada registrada en {precio_actual} para"
          f" {s['direccion']}",
          flush=True,
      )
      operacion_en_curso = s
      actualizar_panel = True

    if (
        s["estado"] == "PENDIENTE"
        and s["precio_entrada"] is not None
        and s["hora_salida"] >= hora_actual_str
    ):
      operacion_en_curso = s

    # 2. EVALUAR RESULTADO
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

      print(
          f"[{hora_actual_str}] Operación finalizada: {s['estado']} | Entrada:"
          f" {s['precio_entrada']} -> Salida: {s['precio_salida']}",
          flush=True,
      )
      actualizar_panel = True

  if actualizar_panel and PANEL_MESSAGE_ID:
    nuevo_texto = construir_mensaje_panel(operacion_en_curso)
    edit_telegram(PANEL_MESSAGE_ID, nuevo_texto)


# ===== ARRANQUE DEL BOT =====
if __name__ == "__main__":
  # Iniciar servidor Web en segundo plano (Render)
  threading.Thread(target=run_health_server, daemon=True).start()

  # Crear y publicar bloque de señales inicial
  LISTA_SENALES = proyectar_horarios()

  if LISTA_SENALES:
    msg_inicial = construir_mensaje_panel()
    PANEL_MESSAGE_ID = send_telegram(msg_inicial)
    print(
        f"--- PANEL PUBLICADO CORRECTAMENTE (ID: {PANEL_MESSAGE_ID}) ---",
        flush=True,
    )

  # Monitoreo del reloj continuo
  while True:
    try:
      procesar_catalogador()
    except Exception as e:
      print(f"Error en bucle principal: {e}", flush=True)

    time.sleep(5)
      
