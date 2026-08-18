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
TOTAL_SENALES_LISTA = 9  # Genera exactamente 9 señales consecutivas de M1

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
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
        "open": quote.get("open", []),
        "high": quote.get("high", []),
        "low": quote.get("low", []),
        "close": quote.get("close", []),
    })
    return df.dropna().reset_index(drop=True)
  except Exception as e:
    print(f"Error en get_market_data: {e}", flush=True)
    return pd.DataFrame()


# ===== GENERADOR DE LISTA PROGRAMADA M1 =====
def generar_lista_programada():
  df = get_market_data()
  if len(df) < 30:
    return []

  rsi_series = ta.momentum.rsi(close=df["close"], window=14)
  stoch_series = ta.momentum.stoch(
      df["high"], df["low"], df["close"], window=14
  )

  ahora = datetime.now(TIMEZONE_LOCAL) + timedelta(minutes=1)
  lista_senales = []

  rsi_val = rsi_series.iloc[-1]
  stoch_val = stoch_series.iloc[-1]

  # Determina dirección predominante según indicadores
  if rsi_val <= 45 or stoch_val <= 30:
    tipo_global = "CALL"
  elif rsi_val >= 55 or stoch_val >= 70:
    tipo_global = "PUT"
  else:
    tipo_global = "CALL"

  # Crea minutos 1 a 1 sin saltos de 5 minutos (14:09, 14:10, 14:11...)
  for i in range(TOTAL_SENALES_LISTA):
    hora_op = ahora + timedelta(minutes=i)
    lista_senales.append({
        "hora": hora_op.strftime("%H:%M"),
        "hora_full": hora_op.strftime("%H:%M:00"),
        "tipo": tipo_global,
        "rsi": round(rsi_val, 2),
        "stoch": round(stoch_val, 2),
    })

  return lista_senales


def enviar_mensaje_lista(lista):
  texto = "📋 <b>LISTA DE SEÑALES PROGRAMADAS</b>\n\n"
  for s in lista:
    texto += f"<code>M1  {SYMBOL_DISPLAY}  {s['hora']}  {s['tipo']}</code>\n"
  send_telegram(texto)


def enviar_pre_alerta(senal):
  emoji = "🟢" if senal["tipo"] == "CALL" else "🔴"
  accion = "SUBIRÁ (CALL)" if senal["tipo"] == "CALL" else "BAJARÁ (PUT)"

  texto = "⚡ <b>PRE-ALERTA: BTC-USD</b>\n\n"
  texto += f"🔮 <b>Proyección: {accion} {emoji}</b>\n"
  texto += f"⏰ <b>ENTRADA: {senal['hora_full']}</b>\n"
  texto += f"📉 <b>RSI: {senal['rsi']} | Stoch: {senal['stoch']}</b>"
  send_telegram(texto)


def enviar_vela_cerrada(close_price, rsi_val, stoch_val, tipo):
  emoji = "🟢" if tipo == "CALL" else "🔴"
  accion = "(SUBIDA)" if tipo == "CALL" else "(BAJADA)"

  texto = "🕯️ <b>VELA M1 CERRADA</b>\n\n"
  texto += f"📈 <b>Par: {SYMBOL_DISPLAY}</b>\n"
  texto += f"📊 <b>Cierre: {close_price}</b>\n"
  texto += f"📉 <b>RSI: {round(rsi_val, 2)} | Stoch: {round(stoch_val, 2)}</b>\n"
  texto += f"🎯 <b>Estado: {tipo} {emoji} {accion}</b>"
  send_telegram(texto)


# ===== BUCLE PRINCIPAL =====
if __name__ == "__main__":
  threading.Thread(target=run_health_server, daemon=True).start()

  send_telegram(f"🚀 <b>Bot Activo Analizando {SYMBOL_DISPLAY}</b>")

  lista_actual = generar_lista_programada()
  if lista_actual:
    enviar_mensaje_lista(lista_actual)

  alertas_enviadas = set()
  velas_procesadas = set()

  while True:
    try:
      ahora = datetime.now(TIMEZONE_LOCAL)
      hora_actual_sec = ahora.strftime("%H:%M:%S")
      hora_actual_min = ahora.strftime("%H:%M")

      # 1. Enviar Pre-Alerta unos segundos antes de la entrada M1
      for s in lista_actual:
        if (
            s["hora"] == hora_actual_min
            and s["hora"] not in alertas_enviadas
            and ahora.second <= 10
        ):
          enviar_pre_alerta(s)
          alertas_enviadas.add(s["hora"])

      # 2. Notificar Vela M1 Cerrada al cambiar el minuto
      if ahora.second == 2 and hora_actual_min not in velas_procesadas:
        df = get_market_data()
        if not df.empty:
          rsi_series = ta.momentum.rsi(close=df["close"], window=14)
          stoch_series = ta.momentum.stoch(
              df["high"], df["low"], df["close"], window=14
          )

          cierre = df.iloc[-1]["close"]
          rsi_val = rsi_series.iloc[-1]
          stoch_val = stoch_series.iloc[-1]

          tipo_estado = "CALL" if rsi_val <= 50 else "PUT"
          enviar_vela_cerrada(cierre, rsi_val, stoch_val, tipo_estado)
          velas_procesadas.add(hora_actual_min)

    except Exception as e:
      print(f"Error en bucle: {e}", flush=True)

    time.sleep(1)
    
