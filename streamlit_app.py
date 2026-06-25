import asyncio
import ccxt
from ccxt.base.errors import NetworkError, DDoSProtection, RateLimitExceeded
from collections import deque
from datetime import datetime
import logging
from typing import Optional, Dict, Any
import sys
import ssl
import certifi

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class OrderflowScalpingBot:
    """
    High-Frequency Orderflow Imbalance Scalping Bot
    Menggunakan Aggressive Liquidity Detection untuk Binance Futures
    """
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        symbol: str = 'BTC/USDT:USDT',
        demo_mode: bool = True
    ):
        """
        Inisialisasi bot dengan konfigurasi awal
        
        Args:
            api_key: Binance API Key
            api_secret: Binance API Secret
            symbol: Trading pair (format CCXT)
            demo_mode: Gunakan demo trading mode
        """
        self.symbol = symbol
        self.demo_mode = demo_mode
        
        # Inisialisasi exchange dengan konfigurasi yang benar
        exchange_config = {
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
                'warnOnFetchOpenOrdersWithoutSymbol': False,
                'recvWindow': 60000,
            }
        }
        
        # Jika demo mode, override semua URL ke demo server
        if self.demo_mode:
            demo_base = 'https://testnet.binancefuture.com'
            exchange_config['urls'] = {
                'logo': 'https://user-images.githubusercontent.com/1294454/117738721-668c8d80-b205-11eb-8c49-3fad84c4a07f.jpg',
                'api': {
                    'web': demo_base,
                    'fapiPublic': demo_base + '/fapi/v1',
                    'fapiPrivate': demo_base + '/fapi/v1',
                    'fapiPrivateV2': demo_base + '/fapi/v2',
                    'fapiPrivateV3': demo_base + '/fapi/v3',
                    'fapiData': demo_base + '/futures/data',
                    'public': demo_base + '/fapi/v1',
                    'private': demo_base + '/fapi/v1',
                    'v1': demo_base + '/fapi/v1',
                    'v2': demo_base + '/fapi/v2',
                    'v3': demo_base + '/fapi/v3',
                },
                'test': {
                    'fapiPublic': demo_base + '/fapi/v1',
                    'fapiPrivate': demo_base + '/fapi/v1',
                },
                'doc': [
                    'https://binance-docs.github.io/apidocs/futures/en/',
                ],
            }
            
            logger.info("🔧 Demo Trading Mode AKTIF (Binance Futures Testnet)")
            logger.info(f"📡 REST API: {demo_base}")
            logger.info("🌐 WebSocket: wss://stream.binancefuture.com")
        
        self.exchange = ccxt.binanceusdm(exchange_config)
        
        # Buffer untuk orderflow data (sliding window)
        self.trades_buffer = deque(maxlen=500)
        
        # Parameter Risk Management
        self.risk_idr = 100000  # Rp 25.000
        self.usd_idr_rate = 16000  # Kurs IDR ke USD
        self.risk_usd = self.risk_idr / self.usd_idr_rate  # ~$1.56
        self.stop_loss_pct = 0.01  # 1% stop loss awal
        self.trailing_stop_pct = 0.02  # 2% trailing stop
        
        # Parameter Orderflow Imbalance
        self.imbalance_threshold = 1.8  # Pengali threshold
        
        # State Management
        self.position: Optional[Dict[str, Any]] = None
        self.highest_price: Optional[float] = None
        self.lowest_price: Optional[float] = None
        self.current_stop_loss: Optional[float] = None
        
        # Market Info
        self.market_info: Optional[Dict] = None
        
        # Trade tracking untuk deduplikasi
        self.last_trade_id = None
        
    async def initialize(self):
        """Load market info dan validasi koneksi"""
        try:
            logger.info("🔄 Loading market information...")
            
            # Load markets tanpa fetch currencies (skip SSL issue)
            try:
                # Load markets dengan skip currencies
                self.exchange.options['fetchCurrencies'] = False
                markets = self.exchange.load_markets()
                self.market_info = self.exchange.market(self.symbol)
                
                logger.info(f"✅ Market loaded: {self.symbol}")
                logger.info(f"📊 Precision - Amount: {self.market_info['precision']['amount']}, Price: {self.market_info['precision']['price']}")
            except Exception as e:
                logger.warning(f"⚠️ Error loading full market info: {e}")
                # Fallback: set manual market info
                self.market_info = {
                    'id': 'BTCUSDT',
                    'symbol': self.symbol,
                    'precision': {
                        'amount': 3,
                        'price': 2,
                    },
                    'limits': {
                        'amount': {'min': 0.001},
                        'price': {'min': 0.01},
                    }
                }
                logger.info("✅ Using fallback market info")
            
            # Validasi balance (optional, bisa skip jika error)
            try:
                balance = self.exchange.fetch_balance()
                usdt_balance = balance['USDT']['free']
                logger.info(f"💰 USDT Balance: ${usdt_balance:.2f}")
                
                if usdt_balance < self.risk_usd:
                    logger.warning(f"⚠️ Balance rendah! Minimal ${self.risk_usd:.2f}")
                    logger.info("💡 Untuk mendapatkan testnet USDT, gunakan faucet di https://testnet.binancefuture.com")
            except Exception as e:
                logger.warning(f"⚠️ Tidak bisa fetch balance: {e}")
                logger.info("💡 Bot akan tetap berjalan untuk monitoring orderflow")
            
            logger.info(f"✅ Inisialisasi berhasil untuk {self.symbol}")
            
        except Exception as e:
            logger.error(f"❌ Error saat inisialisasi: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def calculate_orderflow_imbalance(self) -> Dict[str, float]:
        """
        Kalkulasi Volume Delta dari orderflow
        
        Returns:
            Dict dengan V_buy, V_sell, dan ratio
        """
        v_buy = 0.0
        v_sell = 0.0
        
        for trade in self.trades_buffer:
            amount = trade['amount']
            side = trade['side']
            
            if side == 'buy':  # Aggressor hit ASK (bullish)
                v_buy += amount
            elif side == 'sell':  # Aggressor hit BID (bearish)
                v_sell += amount
        
        # Hindari division by zero
        ratio_buy = v_buy / v_sell if v_sell > 0 else 0
        ratio_sell = v_sell / v_buy if v_buy > 0 else 0
        
        return {
            'v_buy': v_buy,
            'v_sell': v_sell,
            'ratio_buy': ratio_buy,
            'ratio_sell': ratio_sell
        }
    
    def calculate_position_size(self, entry_price: float) -> float:
        """
        Hitung ukuran posisi berdasarkan risk management
        
        Args:
            entry_price: Harga entry
            
        Returns:
            Amount dalam satuan koin (precision-adjusted)
        """
        # Risk per trade: $1.56
        # Stop loss: 1% dari entry
        stop_distance = entry_price * self.stop_loss_pct
        
        # Position size = Risk / Stop Distance
        raw_amount = self.risk_usd / stop_distance
        
        # Adjust precision sesuai aturan exchange
        amount = self.exchange.amount_to_precision(self.symbol, raw_amount)
        
        return float(amount)
    
    async def execute_market_order(
        self,
        side: str,
        amount: float,
        reduce_only: bool = False
    ) -> Optional[Dict]:
        """
        Eksekusi market order dengan error handling
        
        Args:
            side: 'buy' atau 'sell'
            amount: Jumlah koin
            reduce_only: True jika closing position
            
        Returns:
            Order result atau None jika gagal
        """
        try:
            params = {}
            if reduce_only:
                params['reduceOnly'] = True
            
            order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=amount,
                params=params
            )
            
            logger.info(f"✅ Market Order Executed: {side.upper()} {amount} @ Market")
            return order
            
        except Exception as e:
            logger.error(f"❌ Error executing market order: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def place_stop_loss(
        self,
        side: str,
        amount: float,
        stop_price: float
    ) -> Optional[Dict]:
        """
        Place stop loss order (stop market)
        
        Args:
            side: 'buy' (untuk close short) atau 'sell' (untuk close long)
            amount: Jumlah koin
            stop_price: Trigger price
            
        Returns:
            Order result atau None
        """
        try:
            # Adjust precision
            stop_price = float(self.exchange.price_to_precision(self.symbol, stop_price))
            
            order = self.exchange.create_order(
                symbol=self.symbol,
                type='STOP_MARKET',
                side=side,
                amount=amount,
                params={
                    'stopPrice': stop_price,
                    'reduceOnly': True
                }
            )
            
            logger.info(f"🛡️ Stop Loss Placed: {side.upper()} @ ${stop_price:.2f}")
            return order
            
        except Exception as e:
            logger.error(f"❌ Error placing stop loss: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def open_long_position(self, entry_price: float):
        """Buka posisi LONG dengan stop loss"""
        amount = self.calculate_position_size(entry_price)
        
        logger.info(f"🔄 Opening LONG position: {amount} BTC @ ${entry_price:.2f}")
        
        # Execute market buy
        order = await self.execute_market_order('buy', amount)
        
        if order:
            # Set initial stop loss (1% below entry)
            initial_stop = entry_price * (1 - self.stop_loss_pct)
            await self.place_stop_loss('sell', amount, initial_stop)
            
            self.position = {
                'side': 'long',
                'entry_price': entry_price,
                'amount': amount,
                'timestamp': datetime.now()
            }
            self.highest_price = entry_price
            self.current_stop_loss = initial_stop
            
            logger.info(f"🟢 LONG Position Opened: {amount} @ ${entry_price:.2f}")
            logger.info(f"🛡️ Initial Stop Loss: ${initial_stop:.2f}")
    
    async def open_short_position(self, entry_price: float):
        """Buka posisi SHORT dengan stop loss"""
        amount = self.calculate_position_size(entry_price)
        
        logger.info(f"🔄 Opening SHORT position: {amount} BTC @ ${entry_price:.2f}")
        
        # Execute market sell
        order = await self.execute_market_order('sell', amount)
        
        if order:
            # Set initial stop loss (1% above entry)
            initial_stop = entry_price * (1 + self.stop_loss_pct)
            await self.place_stop_loss('buy', amount, initial_stop)
            
            self.position = {
                'side': 'short',
                'entry_price': entry_price,
                'amount': amount,
                'timestamp': datetime.now()
            }
            self.lowest_price = entry_price
            self.current_stop_loss = initial_stop
            
            logger.info(f"🔴 SHORT Position Opened: {amount} @ ${entry_price:.2f}")
            logger.info(f"🛡️ Initial Stop Loss: ${initial_stop:.2f}")
    
    async def close_position(self, reason: str = "Manual"):
        """Close posisi aktif"""
        if not self.position:
            return
        
        side = 'sell' if self.position['side'] == 'long' else 'buy'
        amount = self.position['amount']
        
        logger.info(f"🔄 Closing position: {self.position['side'].upper()} - Reason: {reason}")
        
        order = await self.execute_market_order(side, amount, reduce_only=True)
        
        if order:
            logger.info(f"🔒 Position Closed: {reason}")
            self.position = None
            self.highest_price = None
            self.lowest_price = None
            self.current_stop_loss = None
    
    async def update_trailing_stop(self, current_price: float):
        """
        Update trailing stop berdasarkan pergerakan harga
        
        Args:
            current_price: Harga real-time saat ini
        """
        if not self.position:
            return
        
        if self.position['side'] == 'long':
            # Update highest price
            if current_price > self.highest_price:
                self.highest_price = current_price
                new_stop = current_price * (1 - self.trailing_stop_pct)
                
                # Hanya update jika stop naik (trailing up)
                if new_stop > self.current_stop_loss:
                    self.current_stop_loss = new_stop
                    logger.info(f"📈 Trailing Stop Updated (LONG): ${new_stop:.2f} | Highest: ${self.highest_price:.2f}")
            
            # Check jika harga menyentuh trailing stop
            if current_price <= self.current_stop_loss:
                logger.info(f"🎯 Trailing Stop Hit! Closing LONG at ${current_price:.2f}")
                await self.close_position("Trailing Stop Hit")
        
        elif self.position['side'] == 'short':
            # Update lowest price
            if current_price < self.lowest_price:
                self.lowest_price = current_price
                new_stop = current_price * (1 + self.trailing_stop_pct)
                
                # Hanya update jika stop turun (trailing down)
                if new_stop < self.current_stop_loss:
                    self.current_stop_loss = new_stop
                    logger.info(f"📉 Trailing Stop Updated (SHORT): ${new_stop:.2f} | Lowest: ${self.lowest_price:.2f}")
            
            # Check jika harga menyentuh trailing stop
            if current_price >= self.current_stop_loss:
                logger.info(f"🎯 Trailing Stop Hit! Closing SHORT at ${current_price:.2f}")
                await self.close_position("Trailing Stop Hit")
    
    async def orderflow_monitor_loop(self):
        """
        Loop utama untuk monitoring orderflow imbalance via REST API polling
        """
        logger.info("🚀 Starting Orderflow Monitor Loop...")
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        log_counter = 0
        
        while True:
            try:
                # Fetch trades dari REST API (polling mode)
                trades = self.exchange.fetch_trades(self.symbol, limit=100)
                
                # Tambahkan ke buffer (hindari duplikasi)
                for trade in trades:
                    trade_id = trade.get('id')
                    existing_ids = [t.get('id') for t in self.trades_buffer]
                    
                    if trade_id not in existing_ids:
                        self.trades_buffer.append(trade)
                
                # Reset error counter on success
                consecutive_errors = 0
                
                # Kalkulasi imbalance hanya jika buffer sudah terisi cukup
                if len(self.trades_buffer) < 50:
                    await asyncio.sleep(2)
                    continue
                
                imbalance = self.calculate_orderflow_imbalance()
                
                # Log status setiap 10 iterasi (throttle logging)
                log_counter += 1
                if log_counter % 10 == 0:
                    logger.info(
                        f"📊 Orderflow | Buffer: {len(self.trades_buffer)} | "
                        f"V_Buy: {imbalance['v_buy']:.4f} | "
                        f"V_Sell: {imbalance['v_sell']:.4f} | "
                        f"Ratio B/S: {imbalance['ratio_buy']:.2f}"
                    )
                
                # Ambil harga terakhir
                if len(trades) > 0:
                    current_price = trades[-1]['price']
                else:
                    await asyncio.sleep(2)
                    continue
                
                # Signal Detection: LONG
                if (imbalance['v_buy'] >= imbalance['v_sell'] * self.imbalance_threshold 
                    and not self.position
                    and imbalance['v_sell'] > 0):
                    
                    logger.info(f"🔥 LONG SIGNAL DETECTED! Imbalance Ratio: {imbalance['ratio_buy']:.2f}x")
                    logger.info(f"📊 V_Buy: {imbalance['v_buy']:.4f} | V_Sell: {imbalance['v_sell']:.4f}")
                    await self.open_long_position(current_price)
                
                # Signal Detection: SHORT
                elif (imbalance['v_sell'] >= imbalance['v_buy'] * self.imbalance_threshold 
                      and not self.position
                      and imbalance['v_buy'] > 0):
                    
                    logger.info(f"🔥 SHORT SIGNAL DETECTED! Imbalance Ratio: {imbalance['ratio_sell']:.2f}x")
                    logger.info(f"📊 V_Buy: {imbalance['v_buy']:.4f} | V_Sell: {imbalance['v_sell']:.4f}")
                    await self.open_short_position(current_price)
                
                await asyncio.sleep(2)  # Polling interval 2 detik
                
            except (NetworkError, DDoSProtection, RateLimitExceeded) as e:
                consecutive_errors += 1
                logger.warning(f"⚠️ Network Error ({consecutive_errors}/{max_consecutive_errors}): {e}. Reconnecting in 5s...")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("❌ Too many consecutive errors. Stopping orderflow loop.")
                    break
                
                await asyncio.sleep(5)
                continue
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"❌ Unexpected error in orderflow loop ({consecutive_errors}/{max_consecutive_errors}): {e}")
                import traceback
                traceback.print_exc()
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("❌ Too many consecutive errors. Stopping orderflow loop.")
                    break
                
                await asyncio.sleep(5)
                continue
    
    async def trailing_stop_monitor_loop(self):
        """
        Loop independen untuk monitoring trailing stop via REST API
        """
        logger.info("🚀 Starting Trailing Stop Monitor Loop...")
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while True:
            try:
                if self.position:
                    # Fetch ticker untuk harga real-time
                    ticker = self.exchange.fetch_ticker(self.symbol)
                    
                    if 'last' in ticker:
                        current_price = ticker['last']
                    elif 'close' in ticker:
                        current_price = ticker['close']
                    else:
                        await asyncio.sleep(2)
                        continue
                    
                    # Update trailing stop
                    await self.update_trailing_stop(current_price)
                    
                    # Kalkulasi PnL
                    pnl_pct = 0
                    pnl_usd = 0
                    if self.position['side'] == 'long':
                        pnl_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
                        pnl_usd = (current_price - self.position['entry_price']) * self.position['amount']
                    else:
                        pnl_pct = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100
                        pnl_usd = (self.position['entry_price'] - current_price) * self.position['amount']
                    
                    logger.info(
                        f"💼 Position: {self.position['side'].upper()} | "
                        f"Entry: ${self.position['entry_price']:.2f} | "
                        f"Current: ${current_price:.2f} | "
                        f"PnL: {pnl_pct:+.2f}% (${pnl_usd:+.2f}) | "
                        f"Stop: ${self.current_stop_loss:.2f}"
                    )
                    
                    # Reset error counter
                    consecutive_errors = 0
                
                await asyncio.sleep(2)  # Update setiap 2 detik
                
            except (NetworkError, DDoSProtection, RateLimitExceeded) as e:
                consecutive_errors += 1
                logger.warning(f"⚠️ Network Error in trailing loop ({consecutive_errors}/{max_consecutive_errors}): {e}. Reconnecting in 5s...")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("❌ Too many consecutive errors. Stopping trailing loop.")
                    break
                
                await asyncio.sleep(5)
                continue
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"❌ Unexpected error in trailing loop ({consecutive_errors}/{max_consecutive_errors}): {e}")
                import traceback
                traceback.print_exc()
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("❌ Too many consecutive errors. Stopping trailing loop.")
                    break
                
                await asyncio.sleep(5)
                continue
    
    async def run(self):
        """
        Jalankan bot dengan dual-loop architecture
        """
        try:
            # Inisialisasi
            await self.initialize()
            
            logger.info("=" * 60)
            logger.info("🤖 BOT STARTED - Orderflow Imbalance Scalping")
            logger.info("=" * 60)
            logger.info(f"📈 Symbol: {self.symbol}")
            logger.info(f"💰 Risk per Trade: ${self.risk_usd:.2f} (Rp {self.risk_idr:,.0f})")
            logger.info(f"🎯 Imbalance Threshold: {self.imbalance_threshold}x")
            logger.info(f"🛡️ Stop Loss: {self.stop_loss_pct*100}%")
            logger.info(f"📊 Trailing Stop: {self.trailing_stop_pct*100}%")
            logger.info("=" * 60)
            
            # Jalankan kedua loop secara paralel
            await asyncio.gather(
                self.orderflow_monitor_loop(),
                self.trailing_stop_monitor_loop()
            )
            
        except KeyboardInterrupt:
            logger.info("🛑 Bot dihentikan oleh user")
            
            # Close posisi jika ada
            if self.position:
                await self.close_position("Bot Shutdown")
            
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            
            # Emergency close
            if self.position:
                try:
                    await self.close_position("Emergency Shutdown")
                except:
                    pass
            
            raise


async def main():
    """
    Entry point utama
    """
    # ============================================
    # KONFIGURASI - GANTI DENGAN API KEY ANDA
    # ============================================
    # Dapatkan API Key dari: https://testnet.binancefuture.com/
    API_KEY = 'oYqfkBgsAxKTgFP3rR3h8bGnqsN2mxUC1PcCY4B7d6dIMbeGIxXM26yaXb09PtfY'
    API_SECRET = 'VZYyWmIqPXT5f4F56X2DAHCyzgse1lHB5hG44tkyXzCl7XN3xP59c5vVVJlaRBTk'
    SYMBOL = 'BTC/USDT:USDT'  # Trading pair
    
    # Inisialisasi bot
    bot = OrderflowScalpingBot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        symbol=SYMBOL,
        demo_mode=True  # Set False untuk live trading
    )
    
    # Jalankan bot
    await bot.run()


if __name__ == "__main__":
    """
    Eksekusi bot
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot terminated gracefully")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
