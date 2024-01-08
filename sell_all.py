import datetime
import datetime
import json
import os
from config import TESTNET
from dotenv import load_dotenv
from binance.client import Client
from print_color import print
from binance_client import get_prices

load_dotenv()

api_key=os.getenv('BINANCE_API_KEY_TEST')
api_secret=os.getenv('BINANCE_API_SECRET_TEST')

client = Client(api_key, api_secret, testnet=True)

session_return = 0
coins_bought = {}
coins_bought_file_path = 'coins_bought.json'

logs_file_path = 'logs.json'
logs = []

if os.path.isfile(logs_file_path):
    with open(logs_file_path) as file:
        logs = json.load(file)

if TESTNET:
    coins_bought_file_path = 'testnet_' + coins_bought_file_path

if os.path.isfile(coins_bought_file_path):
    with open(coins_bought_file_path) as file:
        coins_bought = json.load(file)

def sell_all_coins():
    current_prices = get_prices()
    coins_to_delete = []
    for coin in coins_bought:
        buy_price = float(coins_bought[coin]['fills'][0]['price'])
        current_price = current_prices[coin]
        difference = current_price - buy_price
        difference_percent = difference / buy_price
        try:
            client.create_order(
                        symbol=coin,
                        side='SELL',
                        type='MARKET',
                        quantity=coins_bought[coin]['executedQty']
                    )
            print(f"Successfully sold {coin}, profit of {difference_percent*100:.2f}%", color='green', tag='SUCCESS', tag_color='green')
            logs.append({
                "order": "SELL",
                "symbol": coin,
                "volume": coins_bought[coin]['executedQty'],
                "price": current_price,
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "profit": f"{difference} {difference_percent*100:.2f}%",
            })
            coins_to_delete.append(coin)

        except Exception as e:
            print(f"Failed to sell {coin}", color='red', tag='ERROR', tag_color='red')
            print(e)

    for coin in coins_to_delete:
        del coins_bought[coin]

    with open(coins_bought_file_path, 'w') as file:
        json.dump(coins_bought, file, indent=4)

    with open(logs_file_path, 'w') as file:
        json.dump(logs, file, indent=2)


if __name__ == '__main__':
    print("Selling all coins", color='green', tag='INFO', tag_color='green')
    sell_all_coins()