import requests
import time
import hmac
from hashlib import sha256
from flask import Flask, request, jsonify
import os
import threading
import random
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def home():
    return "Webhook is running!", 200

# === BingX API Keys from Render Environment Variables ===
API_KEY = os.getenv("BINGX_API_KEY")
SECRET_KEY = os.getenv("BINGX_API_SECRET")
API_URL = "https://open-api.bingx.com"

# === Telegram Bot Settings (your details) ===
TELEGRAM_TOKEN = "8397925422:AAHY6tqar3hKLa0n_M8rWt3NBaIV3oB70kk"
TELEGRAM_CHAT_ID = "5666506724"

# === Risk/Reward settings for each symbol ===
symbol_risk_reward = {
    "PUMP-USDT": {"risk_percent": 0.98, "reward_multiplier": 1.45, "tp_sl": "NO"},
    "DOGE-USDT": {"risk_percent": 1.0, "reward_multiplier": 1.38, "tp_sl": "NO"},
    "POPCAT-USDT": {"risk_percent": 0.98, "reward_multiplier": 1.45, "tp_sl": "NO"},
    "ETH-USDT": {"risk_percent": 0.98, "reward_multiplier": 1.45, "tp_sl": "NO"},
    "SOL-USDT": {"risk_percent": 0.98, "reward_multiplier": 1.45, "tp_sl": "NO"},
    "FLOKI-USDT": {"risk_percent": 0.98, "reward_multiplier": 1.45, "tp_sl": "NO"},
    "PENGU-USDT": {"risk_percent": 0.98, "reward_multiplier": 1.45, "tp_sl": "NO"},
    "ENA-USDT": {"risk_percent": 0.98, "reward_multiplier": 1.45, "tp_sl": "NO"},
}

# === Telegram Message Sender ===
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload)
        if r.status_code != 200:
            print("Telegram send error:", r.text)
    except Exception as e:
        print("Telegram send failed:", e)

# === LuxAlgo Styled Message Builder ===
def build_luxalgo_message(signal_type, symbol, direction, position_side, entry_price, tp=None, sl=None):
    current_time = datetime.utcnow().strftime("%d %b %Y | %I:%M %p UTC")
    if signal_type == "ENTRY":
        return (
            f"💎 *LUXAALGO SIGNAL* 💎\n"
            f"*Symbol:* {symbol}\n"
            f"*Direction:* {direction} {'📈' if direction == 'LONG' else '📉'}\n"
            f"*Position Side:* {position_side}\n"
            f"*Entry:* {entry_price} USDT\n\n"
            f"📅 {current_time}"
        )
    elif signal_type == "EXIT":
        return (
            f"🏁 *TRADE EXIT* 🏁\n"
            f"*Symbol:* {symbol}\n"
            f"*Exit Price:* {entry_price} USDT\n"
            f"*TP:* {tp} | *SL:* {sl}\n\n"
            f"📅 {current_time}"
        )

# === Fetch real-time price ===
def fetch_real_time_price(symbol):
    path = "/openApi/swap/v1/ticker/price"
    params_map = {"symbol": symbol}
    params_str = parse_params(params_map)
    url = f"{API_URL}{path}?{params_str}&signature={generate_signature(params_str)}"
    headers = {"X-BX-APIKEY": API_KEY}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data["code"] == 0:
            return float(data["data"]["price"])
        else:
            print(f"Error fetching price: {data['msg']}")
            return None
    except Exception as e:
        print(f"Failed to fetch real-time price: {e}")
        return None

# === TradingView Webhook Endpoint ===
@app.route('/webhook', methods=['POST'])
def webhook():
    alert = request.get_json(force=True, silent=True)
    if not alert:
        return jsonify({"error": "Invalid request, missing JSON payload"}), 400

    print("Received alert:", alert)

    symbol = alert.get("symbol")
    side = alert.get("side", "").upper()
    quantity = alert.get("quantity", "0.01")
    position_side = alert.get("positionSide", "LONG")
    leverage = alert.get("leverage", "1")

    if side == "NONE":
        return jsonify({"status": "ping received — no trade executed"}), 200

    if side not in ["BUY", "SELL"]:
        return jsonify({"error": "Invalid side value"}), 400

    if not symbol:
        return jsonify({"error": "Missing symbol in alert"}), 400

    # Set leverage
    set_leverage_response = set_leverage(symbol, position_side, leverage)
    if set_leverage_response.get("code") != 0:
        return jsonify({"error": "Failed to set leverage"}), 500

    # Fetch price
    real_time_price = fetch_real_time_price(symbol)
    if real_time_price is None:
        return jsonify({"error": "Failed to fetch real-time price"}), 500

    # Risk & TP/SL
    risk_settings = symbol_risk_reward.get(symbol, {"risk_percent": 0.91, "reward_multiplier": 1.5, "tp_sl": "NO"})
    risk_percent = risk_settings["risk_percent"]
    reward_multiplier = risk_settings["reward_multiplier"]
    tp_sl_enabled = risk_settings["tp_sl"].upper()

    if position_side == "LONG":
        stop_loss = real_time_price * (1 - risk_percent / 100)
        take_profit = real_time_price * (1 + (risk_percent * reward_multiplier / 100))
    else:
        stop_loss = real_time_price * (1 + risk_percent / 100)
        take_profit = real_time_price * (1 - (risk_percent * reward_multiplier / 100))

    stop_loss = round(stop_loss, 6)
    take_profit = round(take_profit, 6)

    # === Market Order ===
    market_order_response = place_market_order(symbol, side, quantity, position_side)
    if market_order_response.get("code") != 0:
        return jsonify({"error": "Failed to place market order"}), 500

    # 📢 Send LuxAlgo Styled Entry
    direction = "LONG" if side == "BUY" else "SHORT"
    send_telegram_message(build_luxalgo_message("ENTRY", symbol, direction, position_side, real_time_price))

    # === TP/SL Orders ===
    if tp_sl_enabled == "YES":
        stop_loss_response = place_stop_loss_order(symbol, "SELL" if side == "BUY" else "BUY", stop_loss, quantity, position_side)
        take_profit_response = place_take_profit_order(symbol, "SELL" if side == "BUY" else "BUY", take_profit, quantity, position_side)

        # 📢 Send LuxAlgo Styled Exit Targets
        send_telegram_message(build_luxalgo_message("EXIT", symbol, direction, position_side, real_time_price, tp=take_profit, sl=stop_loss))

    return jsonify({"message": "Trade executed and Telegram sent"}), 200

# === BingX API helper functions ===
def set_leverage(symbol, position_side, leverage):
    path = "/openApi/swap/v2/trade/leverage"
    params_map = {"symbol": symbol, "side": position_side, "leverage": str(leverage)}
    return send_request("POST", path, params_map)

def place_market_order(symbol, side, quantity, position_side):
    path = "/openApi/swap/v2/trade/order"
    params_map = {"symbol": symbol, "side": side, "positionSide": position_side, "type": "MARKET", "quantity": quantity}
    return send_request("POST", path, params_map)

def place_stop_loss_order(symbol, side, stop_loss_price, quantity, position_side):
    path = "/openApi/swap/v2/trade/order"
    params_map = {"symbol": symbol, "side": side, "type": "STOP_MARKET", "stopPrice": f"{stop_loss_price:.6f}", "quantity": quantity, "positionSide": position_side}
    return send_request("POST", path, params_map)

def place_take_profit_order(symbol, side, take_profit_price, quantity, position_side):
    path = "/openApi/swap/v2/trade/order"
    params_map = {"symbol": symbol, "side": side, "type": "TAKE_PROFIT_MARKET", "stopPrice": f"{take_profit_price:.6f}", "quantity": quantity, "positionSide": position_side}
    return send_request("POST", path, params_map)

def send_request(method, path, params_map):
    params_str = parse_params(params_map)
    url = f"{API_URL}{path}?{params_str}&signature={generate_signature(params_str)}"
    headers = {"X-BX-APIKEY": API_KEY}
    try:
        response = requests.request(method, url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

def parse_params(params_map):
    sorted_keys = sorted(params_map)
    params_str = "&".join([f"{key}={params_map[key]}" for key in sorted_keys])
    return params_str + f"&timestamp={int(time.time() * 1000)}"

def generate_signature(payload):
    return hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), digestmod=sha256).hexdigest()

# === Keep Render alive ===
def keep_alive():
    while True:
        try:
            unique_id = random.randint(1000, 9999)
            url = f"https://AlgoBingex2.onrender.com?uid={unique_id}"
            requests.get(url)
        except:
            pass
        time.sleep(600)

threading.Thread(target=keep_alive, daemon=True).start()

if __name__ == '__main__':
    PORT = os.getenv("PORT", 10000)
    app.run(port=int(PORT), host='0.0.0.0')
