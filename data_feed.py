import ccxt
import pandas as pd
import time

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

# --- TEKNİK GÖSTERGELER (Pandas ile Manuel Hesaplama) ---

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
    """Volatiliteyi ölçmek için Average True Range"""
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
                # Kaldıraçlı tokenları ve hacimsizleri ele
                if 'UP/' not in symbol and 'DOWN/' not in symbol:
                    # Hacim Filtresi (Testnet'te hacim az olabilir ama yine de 0 olmasın)
                    quote_volume = tickers[symbol].get('quoteVolume', 0)
                    if quote_volume is not None and quote_volume > 0: 
                        usdt_pairs.append(symbol)
        
        # En çok hareket edenleri (Yüzde değişime göre) sırala (Mutlak değer)
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
        # Trend analizi için 200+ mum çekiyoruz
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=205)
        if not bars or len(bars) < 200: return None
        
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 1. RSI
        df['rsi'] = rsi_hesapla(df['close'])
        
        # 2. EMA 200
        df['ema200'] = ema_hesapla(df['close'], 200)
        
        # 3. MACD
        macd, signal = macd_hesapla(df['close'])
        df['macd'] = macd
        df['macd_signal'] = signal

        # 4. ATR (Yeni Eklendi - Risk Yönetimi İçin)
        df['atr'] = atr_hesapla(df)
        
        son = df.iloc[-1]
        
        # Trend Yönü
        trend_yonu = "YUKSELIŞ (BULL)" if son['close'] > son['ema200'] else "DUSUS (BEAR)"
        
        # MACD Sinyali
        macd_sinyali = "AL" if son['macd'] > son['macd_signal'] else "SAT"

        # Destek/Direnç (Son 50 muma göre daha hassas)
        son_donem = df.iloc[-50:]
        
        return {
            'symbol': symbol,
            'fiyat': son['close'],
            'rsi': son['rsi'],
            'trend': trend_yonu,      
            'macd': macd_sinyali,     
            'atr': son['atr'], # Volatiliteyi main.py'ye göndereceğiz
            'destek': son_donem['low'].min(), 
            'direnc': son_donem['high'].max()
        }

    except Exception as e:
        print(f"Veri Analiz Hatası ({symbol}): {e}")
        return None

def piyasayi_tara():
    av_listesi = hareketli_coinleri_bul()
    print(f"🎯 Hedef Listesi ({len(av_listesi)} Coin Bulundu): {av_listesi}")
    print(f"\n--- WOLF DERİN ANALİZ YAPIYOR (RSI + EMA + MACD + ATR) ---\n")
    
    firsatlar = []
    for symbol in av_listesi:
        veri = verileri_getir_ve_analiz_et(symbol)
        if veri:
            print(f"{symbol:<18} | Fiyat:{veri['fiyat']:<10.4f} | RSI:{veri['rsi']:.1f} | ATR:{veri['atr']:.4f}")
            firsatlar.append(veri)
            
    return firsatlar

if __name__ == "__main__":
    piyasayi_tara()
