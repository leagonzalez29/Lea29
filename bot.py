import os
import requests
import pandas as pd
import ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ===== CONFIGURACIÓN =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
CHAT_ID = os.environ.get("CHAT_ID", "TU_CHAT_ID_AQUI")
SYMBOL_YAHOO = "AUDCAD=X"     # Par en Yahoo Finance
SYMBOL_DISPLAY = "AUDCAD-OTC" # Nombre visible en la lista
TIMEZONE_LOCAL = ZoneInfo("America/Panama")

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
})

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        session.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

def obtener_datos_mercado():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL_YAHOO}?range=1d&interval=1m"
    try:
        res = session.get(url, timeout=10)
        if res.status_code != 200: return pd.DataFrame()
        
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
    except Exception:
        return pd.DataFrame()

def generar_lista_senales():
    """Analiza las velas pasadas y proyecta señales en bloque para los próximos minutos."""
    df = obtener_datos_mercado()
    if len(df) < 30:
        print("No hay suficientes datos para generar la lista.")
        return

    # Cálculo de Indicadores
    rsi = ta.momentum.rsi(close=df['close'], window=14)
    stoch_k = ta.momentum.stoch(df['high'], df['low'], df['close'], window=14)

    ahora = datetime.now(TIMEZONE_LOCAL)
    senales = []

    # Proyección/Estrategia de señales para los siguientes minutos
    # Recorremos las últimas velas para identificar patrones y generar la lista
    for i in range(-20, 0):
        rsi_val = rsi.iloc[i]
        stoch_val = stoch_k.iloc[i]
        
        if pd.isna(rsi_val) or pd.isna(stoch_val):
            continue

        # Lógica de dirección
        if rsi_val <= 42 or stoch_val <= 30:
            direccion = "CALL"
        elif rsi_val >= 58 or stoch_val >= 70:
            direccion = "PUT"
        else:
            continue

        # Asignar tiempo proyectado progresivo a partir de la hora actual
        tiempo_senal = ahora + timedelta(minutes=len(senales) + 1)
        hora_str = tiempo_senal.strftime("%H:%M")
        
        # Formato exacto requerido: M1 AUDCAD-OTC HH:MM DIRECCION
        linea = f"M1  {SYMBOL_DISPLAY}  {hora_str}  {direccion}"
        senales.append(linea)

    if senales:
        # Formatear lista en bloque de código HTML para fácil copiado
        mensaje_encabezado = f"📋 <b>LISTA DE SEÑALES PROGRAMADAS</b>\n<code>{SYMBOL_DISPLAY}</code>\n\n"
        cuerpo_lista = "\n".join(senales)
        mensaje_final = f"{mensaje_encabezado}<code>{cuerpo_lista}</code>"
        
        send_telegram(mensaje_final)
    else:
        print("No se encontraron condiciones para armar la lista.")

if __name__ == "__main__":
    generar_lista_senales()
        
