from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)

# Replace with your BingeX API credentials
BINGEX_API_KEY = "qWXz7LbWGO9Hy5crbg7jkdRUWVPrgQFLBNlLgYYur3HqU2PKyBLEMsG7sPvG8lBrdWFnaDXbeIiReYKYTFGg"
BINGEX_SECRET_KEY = "54xBGgSBOhJUY4NYzc9LgEqcfvrK545qMw5BcD1OMxW1e9wf152RoyNp51hYs5ZJiVJ8IsoKice8Go3btnQ"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        print("Received data:", data)

        # Extract TradingView parameters
        symbol = data.get("symbol", "BTCUSDT")
        side = data.get("side", "buy")  # "buy" or "sell"
        quantity = data.get("quantity", 1)  # Default quantity

        # Call BingeX API to place order
        response = place_order(symbol, side, quantity)
        return jsonify({"status": "success", "response": response})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

def place_order(symbol, side, quantity):
    """Send order to BingeX API"""
    url = "https://api.bingex.com/v1/order"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BINGEX_API_KEY}"
    }
    payload = {
        "symbol": symbol,
        "side": side.upper(),
        "type": "market",
        "quantity": quantity
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    return response.json()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
