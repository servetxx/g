import ccxt
import pandas as pd
import pandas_ta as ta
from datetime import datetime
import time

# Binance API key
API_KEY = "Jjin5M9cYG8TQuZBksuhsLzfjuHadt5RCqyU0UN7FnC59MyWMhRXo6SXcG3CPCna"
API_SECRET = "Xw9MmLHhs2qVP1ABgNt9gZ515SHIynIoCKU2gPBDeuqC3D4Dqa0RCFnQPpnN6s6C"

# Binance borsasına bağlan (API key ile)
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
})

# RSI hesaplama
def calculate_rsi(closes, window=14):
    df = pd.DataFrame(closes, columns=['close'])
    if len(df) < window:
        return None  # Yeterli veri yoksa None döndür
    rsi = df.ta.rsi(length=window)
    return rsi.iloc[-1] if not rsi.empty else None

# MACD hesaplama
def calculate_macd(closes, short_window=12, long_window=26, signal_window=9):
    df = pd.DataFrame(closes, columns=['close'])
    macd = df.ta.macd(fast=short_window, slow=long_window, signal=signal_window)
    return macd['MACD_12_26_9'].iloc[-1], macd['MACDs_12_26_9'].iloc[-1]

# Mevcut bakiyeyi al
def get_balance():
    balance = exchange.fetch_balance()
    return balance

# Minimum işlem miktarını kontrol et
def check_min_amount(symbol, amount):
    market = exchange.market(symbol)
    min_amount = market['limits']['amount']['min']
    return amount >= min_amount

# Alım emri gönder
def place_buy_order(symbol, amount_usdt):
    try:
        ticker = exchange.fetch_ticker(symbol)
        amount_coin = amount_usdt / ticker['last']
        if not check_min_amount(symbol, amount_coin):
            print(f"{datetime.now()} - Alım emri iptal edildi: Miktar {amount_coin} minimum miktarın altında.")
            return None
        order = exchange.create_market_buy_order(symbol, amount_coin)
        print(f"{datetime.now()} - Alım emri başarıyla gönderildi. Alınan miktar: {amount_coin} {symbol.split('/')[0]}")
        return order
    except Exception as e:
        print(f"{datetime.now()} - Alım emri gönderilirken hata oluştu: {e}")
        return None

# Satım emri gönder
def place_sell_order(symbol, amount_coin):
    try:
        if not check_min_amount(symbol, amount_coin):
            print(f"{datetime.now()} - Satım emri iptal edildi: Miktar {amount_coin} minimum miktarın altında.")
            return None
        order = exchange.create_market_sell_order(symbol, amount_coin)
        print(f"{datetime.now()} - Satım emri başarıyla gönderildi. Satılan miktar: {amount_coin} {symbol.split('/')[0]}")
        return order
    except Exception as e:
        print(f"{datetime.now()} - Satım emri gönderilirken hata oluştu: {e}")
        return None

# Binance'den fiyat verilerini çek
def fetch_ticker(symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        print(f"Veri çekilirken hata oluştu: {e}")
        return None

# Binance'den 1 dakikalık verileri çek
def fetch_ohlcv(symbol, timeframe='1m', limit=100):
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        print(f"Veri çekildi: {len(data)} mum")
        return data
    except Exception as e:
        print(f"Veri çekilirken hata oluştu: {e}")
        return []

# Ana işlem döngüsü
def main(symbols, quote_currency, stop_loss_pct, take_profit_pct):
    symbol_states = {symbol: {'rsi_triggered': False, 'rsi_condition': None, 'buy_price': None} for symbol in symbols}

    while True:
        balance = get_balance()
        quote_balance = balance['total'][quote_currency]

        for symbol in symbols:
            base_currency = symbol.split('/')[0]
            base_balance = balance['total'][base_currency]

            # Anlık fiyatı al
            current_price = fetch_ticker(symbol)
            if current_price is None:
                time.sleep(60)
                continue

            # 1 dakikalık verileri çek
            ohlcv = fetch_ohlcv(symbol, timeframe='1m', limit=100)
            closes = [x[4] for x in ohlcv]  # Kapanış fiyatlarını al

            # RSI hesapla
            rsi = calculate_rsi(closes)
            macd, signal = calculate_macd(closes)

            print(f"\n{datetime.now()} - {symbol} Güncel Fiyat: {current_price}")
            print(f"RSI: {rsi}")
            print(f"MACD: {macd}, Signal: {signal}")

            symbol_state = symbol_states[symbol]

            # RSI sinyalini kontrol et
            if not symbol_state['rsi_triggered']:
                if rsi < 30:
                    symbol_state['rsi_triggered'] = True
                    symbol_state['rsi_condition'] = 'buy'
                    print(f"{symbol} RSI aşırı satım bölgesinde, MACD sinyali bekleniyor...")

                if rsi > 70:
                    symbol_state['rsi_triggered'] = True
                    symbol_state['rsi_condition'] = 'sell'
                    print(f"{symbol} RSI aşırı alım bölgesinde, MACD sinyali bekleniyor...")

            # RSI tetiklendiğinde MACD sinyalini kontrol et
            if symbol_state['rsi_triggered'] and symbol_state['rsi_condition'] == 'buy' and macd > signal:
                amount_quote = quote_balance / len(symbols)  # Her sembole eşit miktar ayır
                if amount_quote < 10:  # Minimum 10 USDT ile işlem yap
                    print(f"{datetime.now()} - {symbol} için yeterli USDT bakiyesi yok.")
                    continue

                order = place_buy_order(symbol, amount_quote)
                if order:
                    symbol_state['buy_price'] = current_price  # Alış fiyatını kaydet
                    symbol_state['rsi_triggered'] = False  # RSI tetiklemesini sıfırla
                    symbol_state['rsi_condition'] = None

            if symbol_state['rsi_triggered'] and symbol_state['rsi_condition'] == 'sell' and macd < signal:
                if base_balance <= 0:
                    print(f"{datetime.now()} - {symbol} için yeterli {base_currency} bakiyesi yok.")
                    continue

                order = place_sell_order(symbol, base_balance)
                if order:
                    symbol_state['buy_price'] = None  # Alış fiyatını sıfırla
                    symbol_state['rsi_triggered'] = False  # RSI tetiklemesini sıfırla
                    symbol_state['rsi_condition'] = None

            # Stop-loss ve take-profit kontrolleri
            if symbol_state['buy_price']:
                if current_price <= symbol_state['buy_price'] * (1 - stop_loss_pct):
                    if base_balance <= 0:
                        print(f"{datetime.now()} - {symbol} için yeterli {base_currency} bakiyesi yok.")
                        continue

                    order = place_sell_order(symbol, base_balance)
                    if order:
                        symbol_state['buy_price'] = None  # Alış fiyatını sıfırla
                        symbol_state['rsi_triggered'] = False  # RSI tetiklemesini sıfırla
                        symbol_state['rsi_condition'] = None
                    print(f"{datetime.now()} - {symbol} Stop-loss tetiklendi. Fiyat: {current_price}")

                if current_price >= symbol_state['buy_price'] * (1 + take_profit_pct):
                    if base_balance <= 0:
                        print(f"{datetime.now()} - {symbol} için yeterli {base_currency} bakiyesi yok.")
                        continue

                    order = place_sell_order(symbol, base_balance)
                    if order:
                        symbol_state['buy_price'] = None  # Alış fiyatını sıfırla
                        symbol_state['rsi_triggered'] = False  # RSI tetiklemesini sıfırla
                        symbol_state['rsi_condition'] = None
                    print(f"{datetime.now()} - {symbol} Take-profit tetiklendi. Fiyat: {current_price}")

        # Her 1 dakikada bir işlem yap
        time.sleep(35)

if __name__ == "__main__":
    symbols = ["NOT/USDT", "PEOPLE/USDT", "TRB/USDT"]  # İşlem yapmak istediğiniz coin çiftleri
    quote_currency = "USDT"  # Referans para birimi
    stop_loss_pct = 0.02  # %2 stop-loss
    take_profit_pct = 0.05  # %5 take-profit
    main(symbols, quote_currency, stop_loss_pct, take_profit_pct)
