import os
import logging
import time
import threading
import numpy as np
from datetime import datetime, timedelta
import requests
import pytz
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from dotenv import load_dotenv
import talib
import random
from flask import Flask  # Required for anti-sleep functionality
import os
os.environ['TA_LIBRARY_PATH'] = os.path.expanduser('~/ta-lib/lib')
os.environ['LD_LIBRARY_PATH'] = os.path.expanduser('~/ta-lib/lib') + ':' + os.environ.get('LD_LIBRARY_PATH', '')
# Load environment variables
load_dotenv()

# API Configuration
TRADEMADE_API_KEY = os.getenv("TRADEMADE_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "")
RENDER_URL = os.getenv("RENDER_URL", "")  # For health checks

# Trading parameters - optimized for scalping
PAIRS = ["EURUSD", "XAUUSD", "GBPJPY"]
NEW_YORK_TZ = pytz.timezone('America/New_York')
LONDON_TZ = pytz.timezone('Europe/London')
TOKYO_TZ = pytz.timezone('Asia/Tokyo')

# API rate limits
RATE_LIMITS = {
    "trademade": 30
}

# Enhanced scalping strategy configuration
PAIR_CONFIG = {
    "EURUSD": {
        "precision": 5,
        "pip_size": 0.0001,
        "min_profit_pips": 5,
        "max_loss_pips": 3,
        "volume_threshold": 1.2,
        "rsi_period": 3,
        "ema_fast": 5,
        "ema_slow": 13,
        "max_spread": 0.8,
        "api_weight": 1
    },
    "XAUUSD": {
        "precision": 2,
        "pip_size": 0.1,
        "min_profit_pips": 40,
        "max_loss_pips": 25,
        "volume_threshold": 1.3,
        "rsi_period": 4,
        "ema_fast": 8,
        "ema_slow": 21,
        "max_spread": 0.35,
        "api_weight": 2
    },
    "GBPJPY": {
        "precision": 3,
        "pip_size": 0.01,
        "min_profit_pips": 7,
        "max_loss_pips": 4,
        "volume_threshold": 1.25,
        "rsi_period": 4,
        "ema_fast": 6,
        "ema_slow": 18,
        "max_spread": 1.2,
        "api_weight": 1
    }
}

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Flask app for anti-sleep
app = Flask(__name__)
@app.route('/')
def home():
    return "🚀 Professional Scalping Bot Active | " + datetime.utcnow().isoformat()

class ProfessionalScalpingBot:
    def __init__(self):
        # Initialize price tracking
        self.live_prices = {pair: None for pair in PAIRS}
        self.spreads = {pair: 0.0 for pair in PAIRS}
        self.subscribed_users = set()
        self.running = True
        self.api_cache = {}
        self.api_call_count = 0
        self.api_budget_reset_time = time.time()
        
        # Circuit breaker system
        self.consecutive_losses = 0
        self.halted_until = None
        self.pair_cooldowns = {pair: 0 for pair in PAIRS}
        
        # Performance tracking
        self.trade_history = []
        self.starting_balance = 100
        self.current_balance = 100
        
        # Initialize Telegram
        self.updater = Updater(TELEGRAM_TOKEN, use_context=True)
        self.updater.start_polling()
        
        # Add command handlers
        handlers = [
            CommandHandler('start', self.start),
            CommandHandler('subscribe', self.subscribe),
            CommandHandler('status', self.bot_status),
            CommandHandler('performance', self.performance_report),
            CommandHandler('resume', self.resume_trading),
            CommandHandler('cooldown', self.cooldown_pair),
            CommandHandler('health', self.health_check)
        ]
        for handler in handlers:
            self.updater.dispatcher.add_handler(handler)
        
        # Start services
        self.start_services()
        logger.info("Professional Scalping Bot Initialized")

    # ======================
    # ENHANCED API MANAGEMENT
    # ======================
    
    def api_request(self, url, params=None, cache_key=None, cache_duration=60):
        """Highly optimized API request with budget management"""
        # Reset call count every minute
        if time.time() - self.api_budget_reset_time > 60:
            self.api_call_count = 0
            self.api_budget_reset_time = time.time()
            
        # Check if we've exceeded API budget
        if self.api_call_count >= RATE_LIMITS["trademade"]:
            sleep_time = 60 - (time.time() - self.api_budget_reset_time)
            if sleep_time > 0:
                logger.warning(f"API limit reached. Sleeping for {sleep_time:.1f}s")
                time.sleep(sleep_time)
                self.api_call_count = 0
                self.api_budget_reset_time = time.time()
        
        # Check cache first
        if cache_key and cache_key in self.api_cache:
            cached_data = self.api_cache[cache_key]
            if time.time() - cached_data['timestamp'] < cache_duration:
                return cached_data['data']
        
        try:
            # Add API key to params
            params = params or {}
            params['api_key'] = TRADEMADE_API_KEY
            
            response = requests.get(url, params=params, timeout=3)
            response.raise_for_status()
            data = response.json()
            
            # Update cache
            if cache_key:
                self.api_cache[cache_key] = {
                    'data': data,
                    'timestamp': time.time()
                }
                
            self.api_call_count += 1
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected API error: {str(e)}")
            return None

    # ======================
    # ENHANCED RISK MANAGEMENT
    # ======================
    
    def update_performance(self, pair, outcome):
        """Track performance and manage circuit breakers"""
        # Update trade history
        self.trade_history.append({
            "pair": pair,
            "time": datetime.utcnow().isoformat(),
            "outcome": outcome
        })
        
        # Update consecutive losses
        if outcome == "loss":
            self.consecutive_losses += 1
            # Pair cooldown after 2 losses
            self.pair_cooldowns[pair] = time.time() + 1800  # 30 min cooldown
            
            # Global circuit breaker after 3 consecutive losses
            if self.consecutive_losses >= 3:
                self.halted_until = time.time() + 3600  # 1-hour halt
                self.notify_users("🚨 CIRCUIT BREAKER: Trading halted for 1 hour after 3 consecutive losses")
        else:
            self.consecutive_losses = 0
            
        # Update balance (simulated)
        config = PAIR_CONFIG[pair]
        if outcome == "win":
            profit = config['min_profit_pips'] * config['pip_size'] * 100
            self.current_balance += profit
        else:
            loss = config['max_loss_pips'] * config['pip_size'] * 100
            self.current_balance -= loss

    def check_trading_allowed(self, pair):
        """Check if trading is allowed for a pair"""
        # Check global circuit breaker
        if self.halted_until and time.time() < self.halted_until:
            return False
            
        # Check pair cooldown
        if self.pair_cooldowns[pair] > time.time():
            return False
            
        # Check if market is open
        now_utc = datetime.utcnow()
        hour = now_utc.hour
        if not (0 <= hour < 6 or 7 <= hour < 16 or 12 <= hour < 20):
            return False
            
        return True

    # ======================
    # SCALPING ENGINE
    # ======================
    
    def analyze_pair(self, pair):
        """Multi-timeframe analysis for scalping signals"""
        if not self.check_trading_allowed(pair):
            return None
            
        config = PAIR_CONFIG[pair]
        
        # Get live price data
        url = "https://marketdata.trademade.com/api/v1/live"
        params = {"currency": pair}
        
        price_data = self.api_request(url, params, f"live_{pair}", 15)
        if not price_data or 'quotes' not in price_data or not price_data['quotes']:
            return None
            
        quote = price_data['quotes'][0]
        price = float(quote['mid'])
        spread = (float(quote['ask']) - float(quote['bid'])) * 100
        if pair == "XAUUSD":
            spread *= 10
            
        # Spread filter
        if spread > config['max_spread']:
            return None
            
        # Get historical data (use cached data when possible)
        tf1 = self.api_cache.get(f"hist_{pair}_minute")
        if not tf1 or time.time() - tf1['timestamp'] > 120:
            tf1 = self.get_historical_data(pair, "minute", 30)
            
        tf5 = self.api_cache.get(f"hist_{pair}_minute5")
        if not tf5 or time.time() - tf5['timestamp'] > 300:
            tf5 = self.get_historical_data(pair, "minute5", 120)
            
        if not tf1 or not tf5:
            return None
            
        # 1. Trend analysis
        closes_5 = np.array([c['close'] for c in tf5[-6:]])
        if len(closes_5) < 5:
            return None
            
        ema_fast = talib.EMA(closes_5, timeperiod=8)[-1]
        ema_slow = talib.EMA(closes_5, timeperiod=21)[-1]
        trend_direction = 1 if ema_fast > ema_slow else -1
        
        # 2. Momentum analysis
        rsi_5 = talib.RSI(closes_5, timeperiod=7)[-1]
        
        # 3. Entry signals (1min)
        closes_1 = np.array([c['close'] for c in tf1[-5:]])  # Only last 5 candles
        volumes = [c['volume'] for c in tf1[-5:]]
        
        if len(closes_1) < 3:
            return None
            
        # Calculate indicators
        rsi = talib.RSI(closes_1, timeperiod=config['rsi_period'])[-1]
        
        # Volume analysis
        current_volume = volumes[-1] if volumes else 0
        avg_volume = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 0
        volume_ok = current_volume > avg_volume * config['volume_threshold']
        
        # Generate signal
        signal = None
        
        # Buy conditions
        if (trend_direction > 0 and 
            rsi_5 > 40 and
            price > ema_fast and 
            volume_ok and
            rsi < 35):  # Oversold bounce
            signal = "BUY"
                
        # Sell conditions
        elif (trend_direction < 0 and 
              rsi_5 < 60 and
              price < ema_fast and 
              volume_ok and
              rsi > 65):  # Overbought rejection
            signal = "SELL"
                
        if signal:
            # Create signal
            pip_size = config['pip_size']
            
            if signal == "BUY":
                tp = price + config['min_profit_pips'] * pip_size
                sl = price - config['max_loss_pips'] * pip_size
            else:
                tp = price - config['min_profit_pips'] * pip_size
                sl = price + config['max_loss_pips'] * pip_size
                
            signal_id = f"{pair}-{int(time.time())}"
            
            return {
                "signal_id": signal_id,
                "pair": pair,
                "direction": signal,
                "entry": round(price, config['precision']),
                "tp": round(tp, config['precision']),
                "sl": round(sl, config['precision']),
                "expiry": (datetime.utcnow() + timedelta(minutes=2)).isoformat(),
                "confidence": 0.85
            }
            
        return None

    def get_historical_data(self, pair, timeframe, minutes=60):
        """Efficient historical data fetcher"""
        url = "https://marketdata.trademade.com/api/v1/timeseries"
        params = {
            "currency": pair,
            "start_date": (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d-%H:%M"),
            "end_date": datetime.now().strftime("%Y-%m-%d-%H:%M"),
            "format": "records",
            "interval": timeframe,
            "period": 1
        }
        
        data = self.api_request(url, params, f"hist_{pair}_{timeframe}", 300)
        if not data or 'quotes' not in data:
            return None
            
        # Process candles
        candles = []
        for q in data['quotes']:
            candles.append({
                'time': q['date'],
                'open': float(q['open']),
                'high': float(q['high']),
                'low': float(q['low']),
                'close': float(q['close']),
                'volume': float(q.get('volume', 0))
            })
        
        return candles

    # ======================
    # CORE SERVICES
    # ======================
    
    def market_session_manager(self):
        """Manage trading sessions efficiently"""
        while self.running:
            now_utc = datetime.utcnow()
            hour = now_utc.hour
            
            # Define session times (UTC)
            self.tokyo_open = 0 <= hour < 6
            self.london_open = 7 <= hour < 16
            self.new_york_open = 12 <= hour < 20
            self.overlap_open = 12 <= hour < 16
            
            time.sleep(300)  # Check every 5 minutes

    def signal_generation_engine(self):
        """Efficient signal generation with resource limits"""
        while self.running:
            # Get current resource usage
            ram_usage = self.get_memory_usage()
            if ram_usage > 80:  # Over 80% RAM usage
                logger.warning("High RAM usage. Pausing signals.")
                time.sleep(30)
                continue
                
            # Prioritize pairs based on session
            if self.overlap_open:
                pairs = PAIRS
            elif self.new_york_open:
                pairs = ["XAUUSD", "GBPJPY"]
            elif self.london_open:
                pairs = ["EURUSD", "GBPJPY"]
            elif self.tokyo_open:
                pairs = ["GBPJPY"]  # Focus on JPY pairs during Tokyo
            else:
                pairs = []
                time.sleep(30)
                continue
                
            for pair in pairs:
                try:
                    # Check API budget
                    if self.api_call_count >= RATE_LIMITS["trademade"] * 0.8:
                        time.sleep(5)
                        continue
                        
                    signal = self.analyze_pair(pair)
                    if signal:
                        self.send_signal_alert(signal)
                        # Cooldown period
                        time.sleep(10)
                except Exception as e:
                    logger.error(f"Error processing {pair}: {str(e)}")
                    
            # Adaptive sleep
            time.sleep(15)

    def get_memory_usage(self):
        """Simulate memory usage monitoring"""
        # In production, use: psutil.virtual_memory().percent
        return random.randint(30, 70)  # Simulated value

    # ======================
    # ANTI-SLEEP & HEALTH MONITORING
    # ======================
    
    def start_flask_server(self):
        """Start Flask server to prevent Render sleep"""
        if RENDER_URL:
            logger.info(f"Starting Flask server at {RENDER_URL}")
        app.run(host='0.0.0.0', port=5000)
        
    def health_monitor(self):
        """Ping health endpoint to keep Render instance awake"""
        while self.running:
            try:
                if RENDER_URL:
                    requests.get(RENDER_URL, timeout=5)
            except Exception as e:
                logger.warning(f"Health ping failed: {str(e)}")
            time.sleep(300)  # Ping every 5 minutes

    def health_check(self, update: Update, context: CallbackContext):
        """Manual health check command"""
        status = "✅ Bot Operational\n"
        status += f"API Calls: {self.api_call_count}/min\n"
        status += f"Uptime: {timedelta(seconds=time.time() - self.start_time)}"
        update.message.reply_text(status)

    # ======================
    # ENHANCED TELEGRAM INTEGRATION
    # ======================
    
    def send_signal_alert(self, signal: dict):
        """Send scalping signal with MT5 execution templates"""
        config = PAIR_CONFIG[signal["pair"]]
        pip_size = config['pip_size']
        entry = signal['entry']
        tp = signal['tp']
        sl = signal['sl']
        pip_diff = abs(tp - entry) / pip_size
        pip_name = "points" if signal["pair"] == "XAUUSD" else "pips"

        # MT5 Execution Templates
        mt5_template = ""
        if signal["direction"] == "BUY":
            mt5_template = (
                f"OrderSend(\"{signal['pair']}\", OP_BUY, 0.01, Ask, 3, {sl}, {tp}, "
                "\"ScalpSignal\", 0, 0, clrGreen);"
            )
        else:
            mt5_template = (
                f"OrderSend(\"{signal['pair']}\", OP_SELL, 0.01, Bid, 3, {sl}, {tp}, "
                "\"ScalpSignal\", 0, 0, clrRed);"
            )

        # Format message
        message = (
            f"⚡️ *PRO SCALPING SIGNAL* ⚡️\n"
            f"```\n"
            f"Pair: {signal['pair']}\n"
            f"Direction: {signal['direction']}\n"
            f"Entry: {entry}\n"
            f"TP: {tp} ({pip_diff:.1f} {pip_name})\n"
            f"SL: {sl}\n"
            f"Expires: 2 minutes\n"
            f"```\n"
            f"🚀 *MT5 Execution*\n"
            f"```mql5\n"
            f"{mt5_template}\n"
            f"```\n"
            f"📊 *Performance Stats*\n"
            f"Win Rate: {self.calculate_win_rate()}% | Balance: ${self.current_balance:.2f}"
        )
        self.notify_users(message)
        logger.info(f"Sent signal: {signal['pair']} {signal['direction']}")

    def calculate_win_rate(self):
        """Calculate current win rate"""
        if not self.trade_history:
            return 0
        wins = sum(1 for t in self.trade_history if t['outcome'] == 'win')
        return (wins / len(self.trade_history)) * 100

    def notify_users(self, message: str):
        """Send message to subscribed users"""
        for user_id in list(self.subscribed_users):
            try:
                self.updater.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {user_id}: {str(e)}")

    # ======================
    # COMMAND HANDLERS
    # ======================
    
    def start(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        self.subscribed_users.add(user_id)
        update.message.reply_text(
            "💎 *Professional Scalping Bot Activated* 💎\n\n"
            "Features:\n"
            "- Multi-timeframe analysis\n"
            "- Circuit breaker protection\n"
            "- MT5 execution templates\n"
            "- Real-time performance tracking\n\n"
            "Execute signals immediately for optimal results!"
        )

    def subscribe(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        self.subscribed_users.add(user_id)
        update.message.reply_text("✅ You're now receiving professional scalping signals!")
        
    def bot_status(self, update: Update, context: CallbackContext):
        """Show bot status"""
        status = (
            f"🏦 *Market Sessions (UTC)*\n"
            f"Tokyo: {'✅ OPEN' if self.tokyo_open else '❌ CLOSED'}\n"
            f"London: {'✅ OPEN' if self.london_open else '❌ CLOSED'}\n"
            f"New York: {'✅ OPEN' if self.new_york_open else '❌ CLOSED'}\n"
            f"Overlap: {'✅ OPEN' if self.overlap_open else '❌ CLOSED'}\n\n"
            f"📶 *Trading Status*\n"
            f"{'⛔️ HALTED' if self.halted_until else '✅ ACTIVE'}\n"
            f"Consecutive Losses: {self.consecutive_losses}\n"
            f"Balance: ${self.current_balance:.2f}"
        )
        update.message.reply_text(status, parse_mode="Markdown")
        
    def performance_report(self, update: Update, context: CallbackContext):
        """Show performance report"""
        if not self.trade_history:
            update.message.reply_text("No trades recorded yet")
            return
            
        win_rate = self.calculate_win_rate()
        total_trades = len(self.trade_history)
        wins = sum(1 for t in self.trade_history if t['outcome'] == 'win')
        losses = total_trades - wins
        
        # Calculate profit factor
        if losses > 0:
            profit_factor = (wins * 1.0) / losses  # Simplified
        else:
            profit_factor = 99.9
            
        message = (
            f"📊 *Performance Report*\n"
            f"Trades: {total_trades}\n"
            f"Wins: {wins} | Losses: {losses}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Profit Factor: {profit_factor:.2f}\n"
            f"Balance: ${self.current_balance:.2f}\n\n"
            f"🔒 Circuit Breaker: {self.consecutive_losses}/3"
        )
        update.message.reply_text(message, parse_mode="Markdown")
        
    def resume_trading(self, update: Update, context: CallbackContext):
        """Resume trading after halt"""
        self.halted_until = None
        self.consecutive_losses = 0
        update.message.reply_text("✅ Trading resumed. Circuit breaker reset.")
        
    def cooldown_pair(self, update: Update, context: CallbackContext):
        """Manually cooldown a pair"""
        try:
            pair = context.args[0].upper()
            minutes = int(context.args[1]) if len(context.args) > 1 else 30
            
            if pair in PAIRS:
                self.pair_cooldowns[pair] = time.time() + (minutes * 60)
                update.message.reply_text(f"⏳ {pair} cooldown activated for {minutes} minutes")
            else:
                update.message.reply_text("Invalid pair. Available pairs: " + ", ".join(PAIRS))
        except:
            update.message.reply_text("Usage: /cooldown [PAIR] [MINUTES]")

    # ======================
    # BOT MANAGEMENT
    # ======================
    
    def start_services(self):
        """Start core services with resource awareness"""
        # Track start time for uptime calculation
        self.start_time = time.time()
        
        # Initialize market sessions
        now_utc = datetime.utcnow()
        hour = now_utc.hour
        self.tokyo_open = 0 <= hour < 6
        self.london_open = 7 <= hour < 16
        self.new_york_open = 12 <= hour < 20
        self.overlap_open = 12 <= hour < 16
        
        # Start Flask server in separate thread
        flask_thread = threading.Thread(target=self.start_flask_server, daemon=True)
        flask_thread.start()
        
        # Start health monitor
        health_thread = threading.Thread(target=self.health_monitor, daemon=True)
        health_thread.start()
        
        # Start trading services
        services = [
            self.market_session_manager,
            self.signal_generation_engine
        ]
        
        for service in services:
            t = threading.Thread(target=service, daemon=True)
            t.start()
            time.sleep(1)
            
    def run(self):
        """Main run loop with resource monitoring"""
        logger.info("Professional Scalping Bot Started")
        last_cleanup = time.time()
        
        while self.running:
            # Cleanup old cache hourly
            if time.time() - last_cleanup > 3600:
                self.cleanup_cache()
                last_cleanup = time.time()
                
            time.sleep(300)

    def cleanup_cache(self):
        """Clean up old cache entries"""
        now = time.time()
        keys_to_delete = []
        
        for key, entry in self.api_cache.items():
            if now - entry['timestamp'] > 600:  # 10 minutes
                keys_to_delete.append(key)
                
        for key in keys_to_delete:
            del self.api_cache[key]
            
        logger.info(f"Cache cleanup: Removed {len(keys_to_delete)} items")

# Start the bot
if __name__ == '__main__':
    bot = ProfessionalScalpingBot()
    bot.run()
