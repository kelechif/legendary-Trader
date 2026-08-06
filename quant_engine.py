import time
import random

latest_state = {"price": None, "action": None}

def get_price():
    return 30000 + random.uniform(-50, 50)

def strategy(price):
    if price > 30025:
        return "SELL"
    elif price < 29975:
        return "BUY"
    return "HOLD"

def execute(action):
    print(f"Executing: {action}")

print("Simplified Quant Engine Running...\n")

while True:
    price = get_price()
    action = strategy(price)

    latest_state["price"] = price
    latest_state["action"] = action

    print(f"Price: {price:.2f} | Action: {action}")
    execute(action)

    time.sleep(2)
