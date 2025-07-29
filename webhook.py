import requests
import time
import hmac
from hashlib import sha256
from flask import Flask, request, jsonify
import os
import threading
import random

app = Flask(__name__)

@app.route('/')
def home():
    return "Webhook is running!", 200

# Get API keys from environment variables
API_KEY = os.getenv("BINGX_API_KEY")
SECRET_KEY = os.getenv("BINGX_API_SECRET")
API_URL = "https://open-api.bingx.com"

# Define risk-reward settings for each symbol
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

@app.route('/webhook', methods=['POST'])
def webhook():
    alert = request.get_json(force=True, silent=True)
    if not alert:
        print("Received invalid webhook request: No JSON payload")
        return jsonify({"error": "Invalid request, missing JSON payload"}), 400

    print("Received alert:", alert)

    symbol = alert.get("symbol")
    side = alert.get("side", "").upper()
    quantity = alert.get("quantity", "0.01")
    position_side = alert.get("positionSide", "SHORT")
    leverage = alert.get("leverage", "1")

    # === ✅ FILTER: Ignore fake/ping alerts ===
    if side == "NONE":
        print(f"Fake/Ping alert received for {symbol}. No action taken.")
        return jsonify({"status": "ping received — no trade executed"}), 200

    if side not in ["BUY", "SELL"]:
        print(f"Invalid alert side '{side}' received. Ignored.")
        return jsonify({"error": "Invalid side value"}), 400

    if not symbol:
        return jsonify({"error": "Missing symbol in alert"}), 400

    # === Set leverage ===
    set_leverage_response = set_leverage(symbol, position_side, leverage)
    print("Set leverage response:", set_leverage_response)

    if set_leverage_response.get("code") != 0:
        return jsonify({"error": "Failed to set leverage"}), 500

    # === Fetch real-time price ===
    real_time_price = fetch_real_time_price(symbol)
    if real_time_price is None:
        return jsonify({"error": "Failed to fetch real-time price"}), 500

    print(f"Real-time price for {symbol}: {real_time_price}")

    # === Risk & TP/SL Settings ===
    risk_settings = symbol_risk_reward.get(symbol, {"risk_percent": 0.91, "reward_multiplier": 1.5, "tp_sl": "NO"})
    risk_percent = risk_settings["risk_percent"]
    reward_multiplier = risk_settings["reward_multiplier"]
    tp_sl_enabled = risk_settings["tp_sl"].upper()

    # === Calculate SL/TP ===
    if position_side == "LONG":
        stop_loss = real_time_price * (1 - risk_percent / 100)
        take_profit = real_time_price * (1 + (risk_percent * reward_multiplier / 100))
    else:  # SHORT
        stop_loss = real_time_price * (1 + risk_percent / 100)
        take_profit = real_time_price * (1 - (risk_percent * reward_multiplier / 100))

    stop_loss = round(stop_loss, 6)
    take_profit = round(take_profit, 6)
    print(f"Calculated Stop Loss: {stop_loss}, Take Profit: {take_profit}")

    # === Market Order ===
    market_order_response = place_market_order(symbol, side, quantity, position_side)
    print("Market order response:", market_order_response)

    if market_order_response.get("code") != 0:
        return jsonify({"error": "Failed to place market order"}), 500

    # === TP/SL Orders (if enabled) ===
    if tp_sl_enabled == "YES":
        stop_loss_response = place_stop_loss_order(symbol, "SELL" if side == "BUY" else "BUY", stop_loss, quantity, position_side)
        print("Stop-loss order response:", stop_loss_response)

        take_profit_response = place_take_profit_order(symbol, "SELL" if side == "BUY" else "BUY", take_profit, quantity, position_side)
        print("Take-profit order response:", take_profit_response)

    return jsonify({"message": "Market order and TP/SL placed successfully"}), 200

def set_leverage(symbol, position_side, leverage):
    path = "/openApi/swap/v2/trade/leverage"
    params_map = {
        "symbol": symbol,
        "side": position_side,
        "leverage": str(leverage)
    }
    return send_request("POST", path, params_map)

def place_market_order(symbol, side, quantity, position_side):
    path = "/openApi/swap/v2/trade/order"
    params_map = {
        "symbol": symbol,
        "side": side,
        "positionSide": position_side,
        "type": "MARKET",
        "quantity": quantity
    }
    return send_request("POST", path, params_map)

def place_stop_loss_order(symbol, side, stop_loss_price, quantity, position_side):
    path = "/openApi/swap/v2/trade/order"
    params_map = {
        "symbol": symbol,
        "side": side,
        "type": "STOP_MARKET",
        "stopPrice": f"{stop_loss_price:.6f}",
        "quantity": quantity,
        "positionSide": position_side
    }
    return send_request("POST", path, params_map)

def place_take_profit_order(symbol, side, take_profit_price, quantity, position_side):
    path = "/openApi/swap/v2/trade/order"
    params_map = {
        "symbol": symbol,
        "side": side,
        "type": "TAKE_PROFIT_MARKET",
        "stopPrice": f"{take_profit_price:.6f}",
        "quantity": quantity,
        "positionSide": position_side
    }
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
        print(f"Error in {method} request:", str(e))
        return {"error": str(e)}

def parse_params(params_map):
    sorted_keys = sorted(params_map)
    params_str = "&".join([f"{key}={params_map[key]}" for key in sorted_keys])
    return params_str + f"&timestamp={int(time.time() * 1000)}"

def generate_signature(payload):
    return hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), digestmod=sha256).hexdigest()

def keep_alive():
    while True:
        try:
            unique_id = random.randint(1000, 9999)
            url = f"https://AlgoBingex2.onrender.com?uid={unique_id}"
            response = requests.get(url)
            print(f"Ping response: {response.status_code}, Unique ID: {unique_id}")
        except requests.exceptions.RequestException as e:
            print(f"Error pinging app: {e}")
        time.sleep(600)  # Sleep for 10 minutes

threading.Thread(target=keep_alive, daemon=True).start()

if __name__ == '__main__':
    PORT = os.getenv("PORT", 10000)
    app.run(port=int(PORT), host='0.0.0.0')
