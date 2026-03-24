from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uvicorn
import os
import time
import asyncio
import requests
import json
from dotenv import load_dotenv
import hashlib
import hmac
import base64

load_dotenv()

app = FastAPI(title="Bot de Trading Automático")

# ==================== CONFIGURACIÓN ====================
MODO_SIMULACION = os.getenv("MODO_SIMULACION", "True") == "True"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
API_KEY = os.getenv("KUCOIN_API_KEY", "")
API_SECRET = os.getenv("KUCOIN_API_SECRET", "")
API_PASSPHRASE = os.getenv("KUCOIN_API_PASSPHRASE", "")

print("=" * 50)
print("🤖 BOT DE TRADING AUTOMÁTICO")
print(f"Modo: {'SIMULACIÓN' if MODO_SIMULACION else 'REAL'}")
print(f"Alertas Telegram: {'✅ Activo' if TELEGRAM_TOKEN else '❌ Inactivo'}")
print("=" * 50)

# ==================== FUNCIONES KUCOIN ====================
def kucoin_auth(method, endpoint, body=""):
    timestamp = str(int(time.time() * 1000))
    str_to_sign = timestamp + method + endpoint + body
    signature = base64.b64encode(
        hmac.new(API_SECRET.encode('utf-8'), str_to_sign.encode('utf-8'), hashlib.sha256).digest()
    ).decode('utf-8')
    passphrase = base64.b64encode(
        hmac.new(API_SECRET.encode('utf-8'), API_PASSPHRASE.encode('utf-8'), hashlib.sha256).digest()
    ).decode('utf-8')
    return {
        "KC-API-KEY": API_KEY,
        "KC-API-SIGN": signature,
        "KC-API-TIMESTAMP": timestamp,
        "KC-API-PASSPHRASE": passphrase,
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }

def kucoin_request(method, endpoint, data=None):
    url = "https://api.kucoin.com" + endpoint
    body = json.dumps(data) if data else ""
    headers = kucoin_auth(method, endpoint, body)
    if method == "GET":
        resp = requests.get(url, headers=headers)
    else:
        resp = requests.post(url, headers=headers, data=body)
    return resp.json()

# ==================== FUNCIONES TELEGRAM ====================
def enviar_telegram(mensaje):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje})
        except:
            pass

# ==================== OBTENER PRECIO ====================
def obtener_precio():
    try:
        resp = requests.get("https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=BTC-USDT")
        return float(resp.json()["data"]["price"])
    except:
        return None

# ==================== OBTENER NOTICIAS ====================
def obtener_noticias():
    try:
        # CryptoPanic API (gratis)
        resp = requests.get("https://cryptopanic.com/api/v1/posts/?auth_token=TU_TOKEN&currencies=BTC&kind=news")
        if resp.status_code == 200:
            return resp.json().get("results", [])[:5]
    except:
        pass
    # Noticias de ejemplo si la API falla
    return [
        {"title": "Bitcoin supera los $70,000 por aprobación de ETF", "published_at": datetime.now().isoformat()},
        {"title": "ETF de Bitcoin rompe récord de volumen", "published_at": datetime.now().isoformat()}
    ]

# ==================== ANALIZAR SENTIMIENTO ====================
def analizar_sentimiento(texto):
    texto = texto.lower()
    palabras_bull = ["sube", "aumenta", "crece", "record", "etf", "compras", "aprobacion", "alcista", "rally"]
    palabras_bear = ["baja", "cae", "desploma", "crash", "ventas", "prohibicion", "bajista", "panico"]
    
    score_bull = sum(1 for p in palabras_bull if p in texto)
    score_bear = sum(1 for p in palabras_bear if p in texto)
    
    if score_bull > score_bear:
        return {"sentimiento": "bullish", "accion": "COMPRAR", "confianza": min(60 + score_bull * 10, 95)}
    elif score_bear > score_bull:
        return {"sentimiento": "bearish", "accion": "VENDER", "confianza": min(60 + score_bear * 10, 95)}
    else:
        return {"sentimiento": "neutral", "accion": "ESPERAR", "confianza": 50}

# ==================== EJECUTAR ORDEN ====================
def ejecutar_orden(accion, cantidad_usdt=10):
    precio = obtener_precio()
    if not precio:
        return {"error": "No se pudo obtener precio"}
    
    cantidad_btc = cantidad_usdt / precio
    
    if MODO_SIMULACION:
        return {
            "modo": "SIMULACIÓN",
            "accion": accion,
            "precio": precio,
            "cantidad_usdt": cantidad_usdt,
            "cantidad_btc": cantidad_btc,
            "mensaje": f"🔵 SIMULACIÓN: {accion} ${cantidad_usdt} BTC a ${precio:,.2f}"
        }
    
    # Modo REAL
    try:
        lado = "buy" if accion == "COMPRAR" else "sell"
        orden_data = {
            "clientOid": str(int(time.time() * 1000)),
            "side": lado,
            "symbol": "BTC-USDT",
            "type": "market",
            "size": str(cantidad_btc)
        }
        resultado = kucoin_request("POST", "/api/v1/orders", orden_data)
        return {"modo": "REAL", "resultado": resultado}
    except Exception as e:
        return {"error": str(e)}

# ==================== LOOP AUTOMÁTICO ====================
async def loop_automatico():
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔍 Buscando noticias...")
            noticias = obtener_noticias()
            
            for noticia in noticias[:3]:
                titulo = noticia.get("title", "")
                analisis = analizar_sentimiento(titulo)
                
                if analisis["accion"] != "ESPERAR" and analisis["confianza"] >= 70:
                    print(f"⚠️ Noticia importante: {titulo[:80]}")
                    print(f"🎯 Acción: {analisis['accion']} ({analisis['confianza']}% confianza)")
                    
                    resultado = ejecutar_orden(analisis["accion"])
                    print(resultado.get("mensaje", json.dumps(resultado)))
                    
                    enviar_telegram(f"🤖 {analisis['accion']} BTC\n📰 {titulo[:100]}\n💰 ${resultado.get('cantidad_usdt', 10)} a ${resultado.get('precio', '?')}")
                    
                    historial_trades.append({
                        "fecha": datetime.now().isoformat(),
                        "accion": analisis["accion"],
                        "noticia": titulo[:100],
                        "precio": resultado.get("precio")
                    })
            
            await asyncio.sleep(300)  # 5 minutos
            
        except Exception as e:
            print(f"Error en loop: {e}")
            await asyncio.sleep(60)

# ==================== ENDPOINTS API ====================
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(loop_automatico())
    print("✅ Loop automático iniciado (cada 5 minutos)")

@app.get("/")
def home():
    return {
        "mensaje": "Bot de Trading Automático",
        "modo": "SIMULACIÓN" if MODO_SIMULACION else "REAL",
        "estado": "activo",
        "loop": "cada 5 minutos"
    }

@app.get("/precio")
def precio():
    return {"bitcoin_usdt": obtener_precio()}

@app.post("/noticia")
def analizar(noticia: dict):
    titulo = noticia.get("titulo", "")
    analisis = analizar_sentimiento(titulo)
    return analisis

@app.get("/historial")
def historial():
    return {"trades": historial_trades[-20:]}

@app.get("/estado")
def estado():
    return {
        "modo": "SIMULACIÓN" if MODO_SIMULACION else "REAL",
        "trades_hoy": len([t for t in historial_trades if t["fecha"].startswith(datetime.now().strftime("%Y-%m-%d"))]),
        "total_trades": len(historial_trades)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)