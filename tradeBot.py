from binance.client import Client
import logging
import math
import time
import os
import numpy as np
import talib

#------------------------------------------------------------------------------------

import config
client = Client(config.apiKey, config.apiSecretKey)
tradeAmount = config.tradeAmount
followedMarkets = config.markets

#------------------------------------------------------------------------------------

logger = logging.getLogger('tradeBotLogger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(message)s')
fh = logging.FileHandler('tradeBot.log', mode='w')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)
logger.info('Bot started...')

#------------------------------------------------------------------------------------

intervals = {'1Min' : Client.KLINE_INTERVAL_1MINUTE, '15Min' : Client.KLINE_INTERVAL_15MINUTE, '30Min' : Client.KLINE_INTERVAL_30MINUTE, '1H' : Client.KLINE_INTERVAL_1HOUR, '4H' : Client.KLINE_INTERVAL_4HOUR, '6H' : Client.KLINE_INTERVAL_6HOUR }
stableCoin = 'BUSD'

updateRate = 30
timeSpan = int(60 / updateRate)
ticks = {}

#------------------------------------------------------------------------------------

class Market:
        def __init__ (self, symbol, tactic, **kwargs):
                self.marketname = symbol + stableCoin
                self.coin = symbol 
                self.tactic = tactic
                self.balance = 0.0
                self.precision = client.get_symbol_info(self.marketname)['baseAssetPrecision'] - 2
                self.currentPrice = getCurrentPrice(client, self.marketname)
                self.lastPrice = 0.0

                self.positionActive = False
                self.readyToBuy = False
                self.boughtPrice = 0.0
                self.readyToSell = False
                self.soldPrice = 0.0

                self.macd = 0.0
                self.rsi = 0.0
                self.arrayIndex = 0
                self.macdArray = np.array([0.0] * timeSpan)
                self.rsiArray = np.array([0.0] * timeSpan)
                self.ma200 = 0.0

        def updateArrays(self, macd, rsi):
                self.macdArray[self.arrayIndex] = macd
                self.rsiArray[self.arrayIndex] = rsi

                self.arrayIndex += 1
                if (self.arrayIndex == timeSpan):
                        self.arrayIndex = 0

        def getAverageMacd(self):
                return round(average(self.macdArray), 6)

        def getAverageRsi(self):
                return round(average(self.rsiArray), 2)

#------------------------------------------------------------------------------------

class CandleParser:
	def __init__ (self, candles, **kwargs):
		if candles:
                        self.open =  np.array([float(x[1]) for x in candles])
                        self.high = np.array([float(x[2]) for x in candles])
                        self.low = np.array([float(x[3]) for x in candles])
                        self.close = np.array([float(x[4]) for x in candles])
                        self.volume = np.array([float(x[5]) for x in candles])

                        self.ma20 = talib.SMA(self.close, timeperiod=20)
                        self.ma200 = talib.SMA(self.close, timeperiod=200)
                        self.rsi5 = talib.RSI(self.close, timeperiod=5)   
                        self.dea, self.macdSignal, uaua = talib.MACD(self.close, fastperiod=12, slowperiod=26, signalperiod=9)   
	                
#------------------------------------------------------------------------------------

def average(array):
        array = array[~np.isnan(array)]
        return np.average(array)

#------------------------------------------------------------------------------------

def getPercentDiff(lastPrice, currentPrice):
        return round((currentPrice * 100.0 / lastPrice) - 100.0, 1)

#------------------------------------------------------------------------------------

def getCurrentBalance(client, cointype):
        for currency_balance in client.get_account()[u'balances']:
                if currency_balance[u'asset'] == cointype:
                        return round(float(currency_balance[u'free']), 6)
        return None

#------------------------------------------------------------------------------------

def getCurrentPrice(client, market):
    for ticker in client.get_symbol_ticker():
        if ticker[u'symbol'] == market:
            return float(ticker[u'price'])
    return None

#------------------------------------------------------------------------------------

def updateBalance(client, market):
        market.balance = getCurrentBalance(client, market.coin)

#------------------------------------------------------------------------------------

def logAndPrint(message):
        print(message)
        logger.info(message)

#------------------------------------------------------------------------------------

def buyOrder(market, amount):

        orderPrice = getCurrentPrice(client, market.marketname)
        orderAmount = round(math.floor(amount * 10**ticks[market.coin] / orderPrice)/float(10**ticks[market.coin]), market.precision)

        order = client.order_market_buy(symbol=market.marketname, quantity=orderAmount)

        orderRecorded = False
        while not orderRecorded:
                try:
                        stat = client.get_order(
                                symbol=market.marketname, orderId=order[u'orderId'])
                        orderRecorded = True
                        time.sleep(5)
                except:
                        pass

        n = 0
        canceled = False
        while stat[u'status'] != 'FILLED':
                if (n == 10):
                        stat = client.cancel_order(symbol=market.marketname, orderId=order[u'orderId'])
                        canceled = True
                        break
                stat = client.get_order(
                        symbol=market.marketname, orderId=order[u'orderId'])
                time.sleep(1)
                n += 1

        if not canceled:
                # market.boughtPrice = float(stat[u'price'])
                market.boughtPrice = orderPrice
                market.positionActive = True
                market.readyToBuy = False
                updateBalance(client, market)

                logAndPrint("Bought {} {} at price {}".format(orderAmount, market.coin, market.boughtPrice))
                logAndPrint("Current Balance: {}".format(market.balance))

        return order

#------------------------------------------------------------------------------------

def sellOrder(market, amount):

        orderPrice = getCurrentPrice(client, market.marketname)
        orderAmount = round(math.floor(amount * 10**ticks[market.coin] / orderPrice)/float(10**ticks[market.coin]), market.precision)

        orderAccepted = False
        while not orderAccepted:
                try:
                        order = client.order_market_sell(symbol=market.marketname, quantity=orderAmount)
                        orderAccepted = True
                except:
                        time.sleep(1)
                        pass

        orderRecorded = False
        while not orderRecorded:
                try:
                        stat = client.get_order(symbol=market.marketname, orderId=order[u'orderId'])
                        orderRecorded = True
                except:
                        time.sleep(5)
                        pass

        while stat[u'status'] != 'FILLED':
                stat = client.get_order(symbol=market.marketname, orderId=order[u'orderId'])
                time.sleep(1)

        # market.soldPrice = float(stat[u'price'])
        market.soldPrice = orderPrice
        market.positionActive = False
        market.readyToSell = False
        updateBalance(client, market)

        logAndPrint("Sold {} {} at price {}".format(orderAmount, market.coin, market.soldPrice))
        logAndPrint("Current Balance: {}".format(market.balance))

        return order

#------------------------------------------------------------------------------------

def updateData(market, interval):
        gotData = False
        while not gotData:
                try:
                        candles = client.get_klines(symbol=market.marketname, interval=intervals[interval])
                        gotData = True
                except:
                        logAndPrint("Problem getting the data...")
                        time.sleep(1)
                        pass

        indicators = CandleParser(candles)       
        market.currentPrice = getCurrentPrice(client, market.marketname)
        market.macd = round(indicators.dea[len(candles) - 1] - indicators.macdSignal[len(candles) - 1], 6)
        market.rsi = round(indicators.rsi5[-1], 2)
        market.ma200 = round(indicators.ma200[-1], 2)

        market.updateArrays(market.macd, market.rsi)

#------------------------------------------------------------------------------------

def main():
        markets = []
        for m, t in followedMarkets.items():
                market = Market(m, t) 
                updateBalance(client, market)
                markets.append(market)
                
        for m in markets:
                global ticks
                for filt in client.get_symbol_info(m.marketname)['filters']:
                        if filt['filterType'] == 'LOT_SIZE':
                                ticks[m.coin] = filt['stepSize'].find('1') - 2
                                break

        while (True):
                for m in markets:
                        updateData(m, '15Min')

                        print("RSI: {} | MACD: {} ({}) | {} Balance: {} ".format(m.rsi, m.macd, m.getAverageMacd(), m.coin, m.balance), end='\r')
                        
                        if (m.positionActive == False):
                                if (m.readyToBuy):
                                        if (m.macd > 0.0):
                                                buyOrder(m, tradeAmount)

                                if (m.rsi < 40 and m.macd < 0.0 ):
                                        m.readyToBuy = True

                        elif (m.positionActive == True):
                                if (m.readyToSell):
                                        if (m.macd < 0.0):
                                                sellOrder(m, tradeAmount)

                                if (m.rsi > 70):
                                        m.readyToSell = True

                                # stop-loss
                                elif (m.boughtPrice > m.currentPrice and m.macd < m.getAverageMacd() * 0.98):
                                        sellOrder(m, tradeAmount)

                        m.lastPrice = m.currentPrice

                time.sleep(updateRate)



if __name__ == "__main__":
        main()
