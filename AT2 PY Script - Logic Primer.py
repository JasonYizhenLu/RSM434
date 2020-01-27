import requests # we need a package to access RIT via API, there may be other packages that can perform the same role (we are using requests to make an HTTP connection)
from time import sleep # to slow the Python loop we will want to be able to pause the code
from itertools import takewhile

s = requests.Session() # necessary to keep Python from having socket connection errors
s.headers.update({'X-API-key': '38M64LST'}) # convenience, we do not need to separately include the API Key in our messaging code as it is already included when we use "s"

# variables that are not changing while the case is running, and may appear in multiple spots - one change in the variable here applies to every instance, otherwise I would have to go through the code to change every instance; these are not inside a function which makes them "global" instead of "local" and they can be used by any function
TARGET_SHARES = 100000
NUMBER_TRADERS = 40
EXPECTED_SHARES = 1000000 + (NUMBER_TRADERS / 2) * 100000
TICKER_SYMBOL = 'MC'

def get_tick_status(): # this function queries the status of the case ("ACTIVE", "STOPPED", "PAUSED") which we will use in our "while" loop
    resp = s.get('http://localhost:9999/v1/case') 
    if resp.ok: 
        case = resp.json()
        return case['tick'], case['status'], case['tick']/case['ticks_per_period'] # the code does not use the "tick" value, but may be useful if the code is modified

def get_bid_ask(ticker): # this function queries the order book for price and volume data; specifically finds the best bid and offer (BBO) prices and the total volume bid and offered at the BBO (i.e. multiple orders may be placed at the same price, this function consolidates the volume over all orders at the BBO)
    payload = {'ticker': ticker} 
    resp = s.get('http://localhost:9999/v1/securities/book', params = payload) 
    if resp.ok:
        book = resp.json() 
        bid_book = book['bids']
        ask_book = book['asks']
        
        bid_price_fn = bid_book[0]['price']
        ask_price_fn = ask_book[0]['price'] 
        
        bid_volume_fn = sum(item['quantity'] - item['quantity_filled'] for item in takewhile(lambda item: item["price"] == bid_price_fn, bid_book))
        ask_volume_fn = sum(item['quantity'] - item['quantity_filled'] for item in takewhile(lambda item: item["price"] == ask_price_fn, ask_book))
      
        return bid_price_fn, bid_volume_fn, ask_price_fn, ask_volume_fn 

def get_position(ticker): # this function queries my position and the market's volume; we need both pieces of information to make trading decisions, giving the calculations in the "main" function
    payload = {'ticker': ticker}
    resp = s.get('http://localhost:9999/v1/securities', params = payload)
    if resp.ok:
        securities = resp.json()
        current_position_fn = securities[0]['position']
        market_volume_fn = securities[0]['volume']

        return current_position_fn, market_volume_fn

def limit_order(ticker:str, quantity:int, side:str, price:float):
    return s.post('http://localhost:9999/v1/orders', params = {'ticker': ticker, 'type': 'LIMIT', 'quantity': quantity, 'price': price, 'action': side})


def main():
    
    tick, status, progress = get_tick_status() # this function call queries the case status and establishes whether the loop will start
    
    waittime = 20
    while status != 'ACTIVE' and waittime > 0:
        sleep(1)
        waittime -= 1
        tick, status, progress = get_tick_status() # this function call queries the case status and establishes whether the loop will start


    while status == 'ACTIVE': # the loop is the algo - the loop contains the set of instructions (including calls to the functions we define above) that execute our trading strategy; we want these instructions to be repeatedly executed over the duration of the case and use the "while" loop to imnplement this repetition - there are other types of loops that can be used, such as a "for" loop

        # these two lines pull the data to establish the current state of affairs (the market, my position) that feed into the calculations; before we calculate anything we first need the data... the bid and ask volume is not currently used in the "main" function, but may be useful for modified code
        current_position, market_volume = get_position(TICKER_SYMBOL) # 
        bid_price, bid_volume, ask_price, ask_volume = get_bid_ask(TICKER_SYMBOL)
        
        if TARGET_SHARES == current_position:
            break
        
        if TARGET_SHARES > 0:
            side = 'BUY'
            passive_price, active_price = bid_price, ask_price
        else:
            side = 'SELL'
            passive_price, active_price = ask_price, bid_price
        
        diff = abs(TARGET_SHARES-current_position)
        shares_to_trade = diff * min(market_volume / EXPECTED_SHARES, 1)
        shares_to_trade_active = round(shares_to_trade * progress)
        shares_to_trade_passive = shares_to_trade - shares_to_trade_active
        print('percent volume', min(market_volume / EXPECTED_SHARES, 1))
        print('diff', diff)
        print('trade', shares_to_trade)
        limit_order(TICKER_SYMBOL, shares_to_trade_active, side, shares_to_trade_active) # active limit order - the order is intended to be marketable as the price is the BBO ask price
        limit_order(TICKER_SYMBOL, shares_to_trade_passive, side, active_price)
        
#        market_percent = min(market_volume / EXPECTED_SHARES, 1) # the percentage of the expected market volume that has traded, which we will try to match to keep our VWAP close to the market VWAP; the min() function keeps the percentage from going over 100% in the event that we underestimate the expected market volume
#        current_percent = current_position / TARGET_SHARES # the percentage of our order that we have traded
#        shares_to_trade = abs(int((market_percent - current_percent) * TARGET_SHARES)) # the number of shares we need to trade to match the percentage complete for our order with that of the market; the abs() and int() functions clean up the calculation result for use in the message to RIT - volume is always positive and RIT will round an fractional volumes but we want to incorporate the rounding so we don't end up being off by 1 share (or some other round error) at the end of the case
#        shares_to_trade =max(0, min(shares_to_trade, abs(TARGET_SHARES - current_position))) # an error check to make sure we do not enter an order volume that would cause our position to exceed +/- 100,000 shares
#        
#        if TARGET_SHARES > 0 and current_position != TARGET_SHARES: # "if statements are common triggers for launching orders - the order will be sent if the conditions are true; in this case we are identifying that we are buying (TARGET_SHARES > 0) and that we have not yet filled the order (current_position != TARGET_SHARES)
#            shares_to_trade_active = int(shares_to_trade / 2) # splitting the volume traded in half so we can execute part actively and part passively which may reduce our VWAP difference from the market VWAP; we are using the int() function to round the volume
#            shares_to_trade_passive = shares_to_trade - shares_to_trade_active # the other part of the split volume; by subtracting the rounded value of shares_to_trade_active we avoid another fractional volume
#            limit_order(TICKER_SYMBOL, shares_to_trade_active, 'BUY', ask_price) # active limit order - the order is intended to be marketable as the price is the BBO ask price
#            limit_order(TICKER_SYMBOL, shares_to_trade_passive, 'BUY', bid_price)
#            
#        elif TARGET_SHARES < 0 and current_position != TARGET_SHARES: # same logic as above, but launches orders if we are selling
#            shares_to_trade_active = int(shares_to_trade / 2)
#            shares_to_trade_passive = shares_to_trade - shares_to_trade_active
#            limit_order(TICKER_SYMBOL, shares_to_trade_active, 'SELL', bid_price) # active limit order - the order is intended to be marketable as the price is the BBO ask price
#            limit_order(TICKER_SYMBOL, shares_to_trade_passive, 'SELL', ask_price)
        
        sleep(0.5) # pausing the algo to give the passive order a chance to execute before cancelling
        
        s.post('http://localhost:9999/v1/commands/cancel', params = {'ticker': TICKER_SYMBOL}) # cancelling outstanding limit orders to control the volume we have in the book (i.e. the amount we could end up buying or selling); eliminates the risk of a "stale" order being filled that we do not want to be filled
        
        tick, status, progress = get_tick_status() # update the status of the case for our "while" loop - if we do not update the status the loop will continue forever once it starts (unless an error breaks the execution)

if __name__ == '__main__': # convenience to make it easier to run the code
    main() 

