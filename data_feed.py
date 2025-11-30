import ccxt
import pandas as pd
import time
import math # Matematik kütüphanesi eklendi (NaN kontrolü için)

# --- Borsa Bağlantısı ---
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'},
})

# --- URL AYARLARI (BINANCE TESTNET) ---
exchange.urls['api'] = {
    'fapiPublic': 'https://testnet.binancefuture.com/fapi/v1',
    'fapiPrivate': 'https://testnet.binancefuture.com/fapi/v1',
    'fapiPrivateV2': 'https://testnet.binancefuture.com/fapi/v2',
    'public': 'https://testnet.binancefuture.com/fapi/v1',
    'private': 'https://testnet.binancefuture.com/fapi/v1',
    'sapi': 'https://testnet.binancefuture.com/fapi/v1',
    'dapiPublic': 'https://testnet.binancefuture.com/dapi/v1',
    'dapiPrivate': 'https://testnet.binancefuture.com/dapi/v1',
    'dapiPrivateV2': 'https://testnet.binancefuture.com/dapi/v2',
}

# --- TEKNİK GÖSTERGELER ---

def rsi_hesapla(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    ema_gain = gain.ewm(com=period-1, adjust=False).mean()
    ema_loss = loss.ewm(com=period-1, adjust=False).mean()
    rs = ema_gain / ema_loss
    return 100 - (100 / (1 + rs))

def ema_hesapla(series, period=200):
    return series.ewm(span=period, adjust=False).mean()

def macd_hesapla(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def atr_hesapla(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.ewm(span=period, adjust=False).mean()

# -------------------------------------

def hareketli_coinleri_bul(limit=15):
    print("📡 Piyasadaki en hareketli ve hacimli coinler taranıyor...")
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = []
        
        for symbol in tickers:
            if '/USDT' in symbol: 
                if 'UP/' not in symbol and 'DOWN/' not in symbol:
                    # Hacim Filtresi: Testnet'te bile olsa 0 hacimli coinleri alma
                    quote_volume = tickers[symbol].get('quoteVolume', 0)
                    if quote_volume is not None and quote_volume > 1000: # En az 1000$ hacim olsun
                        usdt_pairs.append(symbol)
        
        sorted_tickers = sorted(
            usdt_pairs, 
            key=lambda x: abs(tickers[x]['percentage'] if tickers[x]['percentage'] else 0), 
            reverse=True
        )
        return sorted_tickers[:limit]
    except Exception as e:
        print(f"Tarama Hatası: {e}")
        return []

def verileri_getir_ve_analiz_et(symbol):
    try:
        # Daha fazla mum çekelim ki EMA200 kesin hesaplansın
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=300)
        if not bars or len(bars) < 205: return None
        
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Göstergeleri Hesapla
        df['rsi'] = rsi_hesapla(df['close'])
        df['ema200'] = ema_hesapla(df['close'], 200)
        macd, signal = macd_hesapla(df['close'])
        df['macd'] = macd
        df['macd_signal'] = signal
        df['atr'] = atr_hesapla(df)
        
        son = df.iloc[-1]
        
        # --- KALİTE KONTROL (NAN CHECK) ---
        # Eğer hesaplanan değerlerden biri bozuksa (NaN), bu veriyi hiç gönderme!
        if math.isnan(son['rsi']) or math.isnan(son['ema200']) or math.isnan(son['atr']):
            # Logu kirletmemek için sessizce geçebiliriz veya uyarabiliriz
            # print(f"⚠️ {symbol} verisi yetersiz (NaN), atlanıyor.")
            return None
        # ----------------------------------
        
        trend_yonu = "YUKSELIŞ (BULL)" if son['close'] > son['ema200'] else "DUSUS (BEAR)"
        macd_sinyali = "AL" if son['macd'] > son['macd_signal'] else "SAT"
        
        son_donem = df.iloc[-50:]
        
        return {
            'symbol': symbol,
            'fiyat': son['close'],
            'rsi': son['rsi'],
            'trend': trend_yonu,      
            'macd': macd_sinyali,     
            'atr': son['atr'],
            'destek': son_donem['low'].min(), 
            'direnc': son_donem['high'].max()
        }

    except Exception as e:
        return None

def piyasayi_tara():
    av_listesi = hareketli_coinleri_bul()
    print(f"🎯 Ham Liste ({len(av_listesi)} Coin): Taranıyor...")
    
    firsatlar = []
    print(f"\n{'SYMBOL':<20} | {'FİYAT':<10} | {'RSI':<6} | {'ATR':<8}")
    print("-" * 55)
    
    for symbol in av_listesi:
        veri = verileri_getir_ve_analiz_et(symbol)
        if veri:
            print(f"{symbol:<20} | {veri['fiyat']:<10.4f} | {veri['rsi']:<6.1f} | {veri['atr']:.4f}")
            firsatlar.append(veri)
            
    print(f"\n✅ Analize Hazır Temiz Veri Sayısı: {len(firsatlar)}")
    return firsatlar

if __name__ == "__main__":
    piyasayi_tara()
