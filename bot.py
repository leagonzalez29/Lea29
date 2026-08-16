import time
import requests
import pandas as pd
import pandas_ta as ta

# --- CONFIGURACIÓN CON TUS DATOS ---
TELEGRAM_TOKEN = "8718351888:AAFnojuq28NyofPweVp0tBpOJRgYSy_JJNs"
CHAT_ID = (544714195)
SIMBOLO = "BTCUSDT"     # Par a analizar (ej: BTCUSDT, ETHUSDT)
TEMPORALIDAD = "15m"    # Temporalidad de las velas (1m, 5m, 15m, 1h)

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

def analizar_mercado():
    # 1. Obtener datos de velas desde la API pública de Binance
    url = f"https://api.binance.com/api/v3/klines?symbol={SIMBOLO}&interval={TEMPORALIDAD}&limit=50"
    res = requests.get(url)
    if res.status_code != 200:
        return

    data = res.json()
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'vol', 'close_time', 'q_vol', 'trades', 'tb_base', 'tb_quote', 'ignore'])
    
    # Convertir datos a tipo numérico
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)

    # 2. Cálculo del indicador RSI
    df['rsi'] = ta.rsi(df['close'], length=14)

    vel_actual = df.iloc[-1]
    vel_previa = df.iloc[-2]

    # 3. Lógica de confirmación de patrón
    # Envolvente Alcista + Sobreventa (RSI < 35) -> Señal de COMPRA
    es_envolvente_alcista = (vel_previa['close'] < vel_previa['open']) and \
                            (vel_actual['close'] > vel_previa['open']) and \
                            (vel_actual['open'] <= vel_previa['close'])

    # Envolvente Bajista + Sobrecompra (RSI > 65) -> Señal de VENTA
    es_envolvente_bajista = (vel_previa['close'] > vel_previa['open']) and \
                            (vel_actual['close'] < vel_previa['open']) and \
                            (vel_actual['open'] >= vel_previa['close'])

    # 4. Enviar alerta según el patrón detectado
    if es_envolvente_alcista and vel_actual['rsi'] < 35:
        msg = f"🟢 *SEÑAL ALCISTA (COMPRA)*\n\n*Activo:* {SIMBOLO}\n*Precio:* ${vel_actual['close']}\n*RSI:* {vel_actual['rsi']:.1f}\n*Patrón:* Envolvente Alcista"
        enviar_telegram(msg)
    elif es_envolvente_bajista and vel_actual['rsi'] > 65:
        msg = f"🔴 *SEÑAL BAJISTA (VENTA)*\n\n*Activo:* {SIMBOLO}\n*Precio:* ${vel_actual['close']}\n*RSI:* {vel_actual['rsi']:.1f}\n*Patrón:* Envolvente Bajista"
        enviar_telegram(msg)

# Bucle infinito para revisar el mercado continuamente cada 60 segundos
print("Bot de trading iniciado...")
while True:
    try:
        analizar_mercado()
    except Exception as e:
        print(f"Error en ejecución: {e}")
    time.sleep(60)
