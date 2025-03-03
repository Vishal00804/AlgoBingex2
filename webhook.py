import time
import requests
import hmac
from hashlib import sha256
from flask import Flask, request, jsonify
import os
import threading

app = Flask(__name__)

# Get API keys from environment variables
API_KEY = os.getenv("BINGX_API_KEY")
SECRET_KEY = os.getenv("BINGX_API_SECRET")
API_URL = "https://open-api.bingx.com"

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
    alert = request.get_json()
    print("Received alert:", alert)

    if not alert or "symbol" not in alert or "side" not in alert:
        return jsonify({"error": "Invalid alert format"}), 400

    symbol = alert["symbol"]
    side = alert["side"].upper()
    quantity = alert.get("quantity", "0.01")
    position_side = alert.get("positionSide", "SHORT")

    # Fetch real-time price
    real_time_price = fetch_real_time_price(symbol)
    if real_time_price is None:
        return jsonify({"error": "Failed to fetch real-time price"}), 500

    print(f"Real-time price for {symbol}: {real_time_price}")

    # Define risk and reward parameters
    risk_percent = 1.0  # 1% risk
    reward_multiplier = 1.26  # 1.3x reward-to-risk ratio

    # Calculate Stop Loss and Take Profit based on position type
    if position_side == "LONG":
        stop_loss = real_time_price * (1 - risk_percent / 100)
        take_profit = real_time_price * (1 + (risk_percent * reward_multiplier / 100))
    elif position_side == "SHORT":
        stop_loss = real_time_price * (1 + risk_percent / 100)
        take_profit = real_time_price * (1 - (risk_percent * reward_multiplier / 100))

    stop_loss = round(stop_loss, 6)
    take_profit = round(take_profit, 6)
    print(f"Calculated Stop Loss: {stop_loss}, Take Profit: {take_profit}")

    # Place the market order
    market_order_response = place_market_order(symbol, side, quantity, position_side)
    print("Market order response:", market_order_response)

    if market_order_response.get("code") != 0:
        return jsonify({"error": "Failed to place market order"}), 500

    # Place stop-loss and take-profit orders
    stop_loss_response = place_stop_loss_order(symbol, "SELL" if side == "BUY" else "BUY", stop_loss, quantity, position_side)
    print("Stop-loss order response:", stop_loss_response)

    take_profit_response = place_take_profit_order(symbol, "SELL" if side == "BUY" else "BUY", take_profit, quantity, position_side)
    print("Take-profit order response:", take_profit_response)

    return jsonify({"message": "Market order and TP/SL placed successfully"})

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

# @app.route('/webhook', methods=['POST'])
# def webhook():
#     alert = request.get_json()
#     print("Received alert:", alert)

#     if not alert or "symbol" not in alert or "side" not in alert:
#         return jsonify({"error": "Invalid alert format"}), 400

#     # Extract details from the alert
#     symbol = alert["symbol"]
#     side = alert["side"].upper()  # BUY or SELL
#     quantity = alert.get("quantity", "0.01")  # Default to 0.01 if not provided
#     position_side = alert.get("positionSide", "SHORT")  # Default to SHORT if not provided

#     # Place the demo order
#     order_response = place_demo_order(symbol, side, quantity, position_side)
#     return jsonify(order_response)


# def place_demo_order(symbol, side, quantity, position_side):
#     path = "/openApi/swap/v2/trade/order"  # Demo order endpoint
#     method = "POST"
    
#     params_map = {
#         "symbol": symbol,
#         "side": side,
#         "positionSide": position_side,  # Modify as needed (LONG or SHORT)
#         "type": "MARKET",
#         "quantity": quantity
#     }

#     # Generate the query string and signature
#     params_str = parse_params(params_map)
#     url = f"{API_URL}{path}?{params_str}&signature={generate_signature(params_str)}"

#     headers = {
#         "X-BX-APIKEY": API_KEY
#     }

#     try:
#         response = requests.request(method, url, headers=headers)
#         response.raise_for_status()
#         return response.json()
#     except requests.exceptions.RequestException as e:
#         print("Error placing demo order:", str(e))
#         return {"error": str(e)}


# def parse_params(params_map):
#     sorted_keys = sorted(params_map)
#     params_str = "&".join([f"{key}={params_map[key]}" for key in sorted_keys])
#     return params_str + f"&timestamp={int(time.time() * 1000)}"


# def generate_signature(payload):
#     return hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), digestmod=sha256).hexdigest()


def keep_alive():
    """Function to ping the app's endpoint every 10 minutes."""
    while True:
        try:
            response = requests.get("https://AlgoBingex2.onrender.com")  # Replace with your actual app URL
            print(f"Ping response: {response.status_code}")
        except Exception as e:
            print(f"Error pinging app: {e}")
        time.sleep(895)  # Wait for 600 seconds (10 minutes) before pinging again


# Start the keep_alive function in a separate thread
threading.Thread(target=keep_alive, daemon=True).start()

if _name_ == '_main_':
    app.run(port=5000, host='0.0.0.0')
