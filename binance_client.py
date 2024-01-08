import datetime
import json
import os
import time
from dotenv import load_dotenv
from binance.client import Client
from print_color import print

from config import PAIR_WITH, FIATS, TIME_DIFFERENCE, CHANGE_IN_PRICE, STOP_LOSS, TAKE_PROFIT, TESTNET, QUANTITY

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


def get_prices():
    print(f"Getting new coin prices - {datetime.datetime.now().strftime('%H:%M:%S')}", color='blue', tag='LOG', tag_color='blue')
    current_prices = {}

    prices = client.get_all_tickers()


    for price in prices:
        symbol = price['symbol']
        if symbol.endswith(PAIR_WITH) and symbol not in FIATS:
            current_prices[symbol] = float(price['price'])
    
    return current_prices
    

def check_price_changes(initial_prices):
    current_prices = get_prices()

    volatile_coins = {}

    for symbol, initial_price in initial_prices.items():
        current_price = current_prices[symbol]
        difference = current_price - initial_price
        difference_percent = difference / initial_price
        if difference_percent > CHANGE_IN_PRICE:
            volatile_coins[symbol] = difference_percent
        if difference_percent > CHANGE_IN_PRICE-0.01 and difference_percent < CHANGE_IN_PRICE:
            print(f"{symbol} almost reached the threshold, current profit is {difference_percent:.2f}%", tag='INFO', tag_color='yellow')

    if volatile_coins:
        print("Found Volatile Coins:", tag='INFO', tag_color='blue')
        for symbol, percentage in volatile_coins.items():
            print(f"{symbol}: {percentage:.2f}%")
    else:
        print("No Volatile Coins found in last check.", tag='EMPTY', tag_color='yellow', color='purple')

    return volatile_coins, current_prices


def convert_volume(volatile_coins, current_prices):
    volume = {}
    lot_size = {}
    for coin in volatile_coins:
        try:
            info = client.get_symbol_info(coin)
            filters = info['filters']
            for f in filters:
                if f['filterType'] == 'LOT_SIZE':
                    step_size = f['stepSize']
                    lot_size[coin] = step_size.index('1') - 1

            if lot_size[coin] < 0:
                lot_size[coin] = 0

        except:
            pass    

        volume[coin] = QUANTITY / current_prices[coin]
        
        if coin not in lot_size:
            volume[coin] = float('{:.1f}'.format(volume[coin]))

        else:
            if lot_size[coin] == 0:
                volume[coin] = int(volume[coin])
            else:
                volume[coin] = float('{:.{}f}'.format(volume[coin], lot_size[coin]))
            
    return volume

def buy_coins(volatile_coins, current_prices):

    volume = convert_volume(volatile_coins, current_prices)
    print("Buying Coins...", tag='LOG', tag_color='blue')
    print(volume)
    orders = {}

    for coin in volatile_coins:
        if coin in coins_bought:
            print(f"Already bought {coin}")
            continue
        try:
            buy_order = client.create_order(
                symbol=coin,
                side='BUY',
                type='MARKET',
                quantity=volume[coin]
            )
            orders[coin] = buy_order
            buy_log = {
                "order": "BUY",
                "symbol": buy_order['symbol'],
                "volume": buy_order['executedQty'],
                "price": current_prices[coin],
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            }

            logs.append(buy_log)
            with open(logs_file_path, 'w') as file:
                json.dump(logs, file, indent=2)

            print(f"Successfully bought {coin} at {current_prices[coin]}", color='magenta', tag='SUCCESS', tag_color='green')
        except Exception as e:
            print(f"Failed to buy {coin}", color='red', tag='ERROR', tag_color='red')
            print(e)
    
    return orders

def update_coins_bought_file(orders):
    coins_bought.update(orders)
    with open(coins_bought_file_path, 'w') as file:
        json.dump(coins_bought, file, indent=4)

def sell_coins(current_prices):    
    coins_to_delete = []

    for coin in coins_bought:
        buy_price = float(coins_bought[coin]['fills'][0]['price'])
        current_price = current_prices[coin]
        difference = current_price - buy_price
        difference_percent = difference / buy_price
        if difference_percent <= STOP_LOSS or difference_percent >= TAKE_PROFIT:
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
                    "profit": f"{difference*float(coins_bought[coin]['executedQty'])}USDT {difference_percent*100:.2f}%",
                })

                coins_to_delete.append(coin)

            except Exception as e:
                print(f"Failed to sell {coin}", color='red', tag='ERROR', tag_color='red')
                print(e)
        else:
            print(f"Coin {coin} did not meet the sell requirements, current profit is {difference_percent*100:.3f}%", color='yellow', tag='WAITING', tag_color='yellow')
    
    for coin in coins_to_delete:
        del coins_bought[coin]
    
    with open(coins_bought_file_path, 'w') as file:
        json.dump(coins_bought, file, indent=4)
    
    with open(logs_file_path, 'w') as file:
        json.dump(logs, file, indent=2)


def current_profit(current_prices):
    #go through logs and calculate profit, you caluclate it by looking if there is a matching sell order to the buy order, if yes, then you calculate the profit
    #if no, calcualate an estimate of the profit by looking at the current price of the coin for the buy orders that dont have a matching sell order

    real_profit = 0
    buy_orders = []
    for log in logs:
        if log['order'] == 'BUY':
            buy_orders.append(log)
        elif log['order'] == 'SELL':
            buy_log = None
            for buy_order in buy_orders:
                if buy_order['symbol'] == log['symbol']:
                    buy_log = buy_order
                    break
            if buy_log:
                buy_orders.remove(buy_log)
                profit = (float(log['price']) - float(buy_log['price'])) * float(log['volume'])
                real_profit += profit
    
    estimated_profit = real_profit
    for buy_order in buy_orders:
        estimated_profit += (current_prices[buy_order['symbol']] - float(buy_order['price'])) * float(buy_order['volume'])
    
    return real_profit, estimated_profit


if __name__ == '__main__':
    print("Starting Binance Moonshot Crypto Bot!", color='magenta', tag='INFO', tag_color='blue', format='bold')
    current_prices = get_prices()
    sell_coins(current_prices)
    real_profit, estimated_profit = current_profit(current_prices)
    print(f"Current profit is {real_profit:.2f} USD, estimated profit is {estimated_profit:.2f} USD", tag='PROFIT', tag_color='blue', color='green')
    while True:
        minutes = TIME_DIFFERENCE // 60
        print(f"Waiting {minutes} minutes for next update... \U0001F634", tag='SLEEPING', tag_color='magenta')
        time.sleep(TIME_DIFFERENCE)
        volatile_coins, new_prices = check_price_changes(current_prices)
        current_prices = new_prices
        sell_coins(current_prices)
        real_profit, estimated_profit = current_profit(current_prices)
        print(f"Current profit is {real_profit:.2f} USD, estimated profit is {estimated_profit:.2f} USD", tag='PROFIT', tag_color='blue', color='green')
        if (len(volatile_coins) > 0):
            orders = buy_coins(volatile_coins, current_prices)
            update_coins_bought_file(orders)
            
