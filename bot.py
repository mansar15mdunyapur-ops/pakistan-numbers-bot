# -*- coding: utf-8 -*-
import os
import logging
import json
import random
import string
import re
import requests
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, CallbackQueryHandler, ContextTypes,
    ConversationHandler
)

# ========== CONFIGURATION ==========
BOT_TOKEN = "8772281676:AAHVHo30d95hSpu8tot9OCmHgwNDWMdMQCI"
ADMIN_IDS = [8178162794]  # Aapka Telegram ID

# Payment Numbers
PAYMENT_NUMBERS = {
    'jazzcash': '03017178242',
    'easypaisa': '03424546056'
}

# Coin Plans
COIN_PLANS = {
    'daily': {'coins': 50, 'price': 100, 'desc': '50 coins - 100 Rs'},
    'weekly': {'coins': 350, 'price': 500, 'desc': '350 coins - 500 Rs'},
    'monthly': {'coins': 1600, 'price': 2000, 'desc': '1600 coins - 2000 Rs'}
}

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
SELECTING_SERVICE = 1
WAITING_PAYMENT_SS = 2

# ========== DATABASE ==========
class Database:
    def __init__(self):
        self.users = {}
        self.orders = {}
        self.payments = {}
        self.load_data()
    
    def load_data(self):
        try:
            if os.path.exists('users.json'):
                with open('users.json', 'r') as f:
                    data = json.load(f)
                    self.users = data.get('users', {})
                    self.orders = data.get('orders', {})
                    self.payments = data.get('payments', {})
        except Exception as e:
            logger.error(f"Error loading data: {e}")
    
    def save_data(self):
        try:
            with open('users.json', 'w') as f:
                json.dump({
                    'users': self.users,
                    'orders': self.orders,
                    'payments': self.payments
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def get_user(self, user_id):
        user_id = str(user_id)
        if user_id not in self.users:
            self.users[user_id] = {
                'user_id': user_id,
                'joined': str(datetime.now()),
                'coins': 10,
                'last_reset': str(datetime.now().date()),
                'numbers': [],
                'ads_watched': 0,
                'total_purchases': 0
            }
            self.save_data()
        return self.users[user_id]
    
    def add_coins(self, user_id, amount):
        user = self.get_user(user_id)
        user['coins'] += amount
        self.save_data()
    
    def remove_coins(self, user_id, amount):
        user_id = str(user_id)
        if int(user_id) in ADMIN_IDS:
            return True
        user = self.get_user(user_id)
        if user['coins'] >= amount:
            user['coins'] -= amount
            self.save_data()
            return True
        return False
    
    def add_payment(self, user_id, plan, amount, transaction_id):
        payment_id = f"PAY{len(self.payments)+1}"
        self.payments[payment_id] = {
            'user_id': user_id,
            'plan': plan,
            'coins': COIN_PLANS[plan]['coins'],
            'amount': amount,
            'transaction_id': transaction_id,
            'status': 'pending',
            'time': str(datetime.now())
        }
        self.save_data()
        return payment_id
    
    def approve_payment(self, payment_id, admin_id):
        if payment_id in self.payments:
            payment = self.payments[payment_id]
            if payment['status'] == 'pending':
                payment['status'] = 'approved'
                payment['approved_by'] = admin_id
                payment['approved_time'] = str(datetime.now())
                user_id = payment['user_id']
                self.add_coins(user_id, payment['coins'])
                self.save_data()
                return True
        return False
    
    def reject_payment(self, payment_id, reason):
        if payment_id in self.payments:
            self.payments[payment_id]['status'] = 'rejected'
            self.payments[payment_id]['reject_reason'] = reason
            self.save_data()
            return True
        return False
    
    def get_pending_payments(self):
        pending = []
        for pid, payment in self.payments.items():
            if payment['status'] == 'pending':
                pending.append((pid, payment))
        return pending
    
    def add_number(self, user_id, number, service):
        user = self.get_user(user_id)
        order_id = f"ORD{len(self.orders)+1}"
        self.orders[order_id] = {
            'user_id': user_id,
            'number': number,
            'service': service,
            'time': str(datetime.now()),
            'expires': str(datetime.now() + timedelta(minutes=20)),
            'otp': None
        }
        user['numbers'].append(order_id)
        self.save_data()
        return order_id
    
    def update_otp(self, order_id, otp):
        if order_id in self.orders:
            self.orders[order_id]['otp'] = otp
            self.save_data()
            return True
        return False
    
    def get_order(self, order_id):
        return self.orders.get(order_id)
    
    def reset_daily(self):
        today = str(datetime.now().date())
        for user_id in self.users:
            if self.users[user_id].get('last_reset') != today:
                if int(user_id) not in ADMIN_IDS:
                    self.users[user_id]['coins'] = 10
                    self.users[user_id]['last_reset'] = today
        self.save_data()
    
    def get_stats(self):
        total_users = len(self.users)
        total_orders = len(self.orders)
        total_coins = sum(u['coins'] for u in self.users.values())
        total_payments = len(self.payments)
        pending_payments = len([p for p in self.payments.values() if p['status'] == 'pending'])
        return {
            'total_users': total_users,
            'total_orders': total_orders,
            'total_coins': total_coins,
            'total_payments': total_payments,
            'pending_payments': pending_payments
        }

db = Database()

# ========== REAL OTP DETECTION ==========
class RealOTPService:
    """Real OTP detection from multiple free SMS websites"""
    
    @staticmethod
    def clean_number(number):
        """Clean phone number for websites"""
        number = number.replace('+92', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        return number
    
    @staticmethod
    def extract_otp(text):
        """Extract OTP from text using multiple patterns"""
        patterns = [
            r'OTP[:\s]*(\d{4,6})',
            r'code[:\s]*(\d{4,6})',
            r'verification[:\s]*(\d{4,6})',
            r'is[:\s]*(\d{4,6})',
            r'use[:\s]*(\d{4,6})',
            r'your[:\s]*(\d{4,6})',
            r'password[:\s]*(\d{4,6})',
            r'pin[:\s]*(\d{4,6})',
            r'\b\d{4,6}\b'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    if match and len(match) >= 4 and len(match) <= 6 and match.isdigit():
                        return match
        return None
    
    @staticmethod
    def check_otp(number):
        """Check OTP from multiple sources"""
        clean_num = RealOTPService.clean_number(number)
        
        # Browser headers to avoid blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
        # Multiple SMS websites
        sources = [
            {'url': f"https://receive-sms-online.info/{clean_num}", 'name': 'receive-sms-online'},
            {'url': f"https://sms-receive.net/{clean_num}", 'name': 'sms-receive'},
            {'url': f"https://receive-sms.cc/{clean_num}", 'name': 'receive-sms'},
            {'url': f"https://www.receivesmsonline.net/phone/{clean_num}/", 'name': 'receivesmsonline'},
            {'url': f"https://www.freeonlinephone.org/{clean_num}", 'name': 'freeonlinephone'},
        ]
        
        for source in sources:
            try:
                logger.info(f"🔍 Checking {source['name']} for number {clean_num}")
                
                response = requests.get(
                    source['url'], 
                    headers=headers, 
                    timeout=10
                )
                
                if response.status_code == 200:
                    otp = RealOTPService.extract_otp(response.text)
                    if otp:
                        logger.info(f"✅ OTP found: {otp} from {source['name']}")
                        return {
                            'otp': otp,
                            'from': source['name'],
                            'time': datetime.now()
                        }
                
                # Small delay to avoid rate limiting
                time.sleep(1)
                
            except requests.exceptions.Timeout:
                logger.warning(f"⏱️ Timeout for {source['name']}")
            except requests.exceptions.ConnectionError:
                logger.warning(f"🔌 Connection error for {source['name']}")
            except Exception as e:
                logger.error(f"❌ Error with {source['name']}: {e}")
        
        logger.info(f"❌ No OTP found for number {clean_num}")
        return None

# ========== FREE NUMBERS GENERATOR ==========
class FreeNumbers:
    PAKISTAN_PREFIXES = ['300', '301', '302', '303', '304', '305', '306', '307', '308', '309',
                         '310', '311', '312', '313', '314', '315', '316', '317', '318', '319',
                         '320', '321', '322', '323', '324', '325', '326', '327', '328', '329',
                         '330', '331', '332', '333', '334', '335', '336', '337', '338', '339',
                         '340', '341', '342', '343', '344', '345', '346', '347', '348', '349']
    
    @staticmethod
    def generate_pakistan_number():
        prefix = random.choice(FreeNumbers.PAKISTAN_PREFIXES)
        suffix = ''.join(random.choices(string.digits, k=7))
        return f"+92{prefix}{suffix}"
    
    @staticmethod
    def get_active_numbers(service='whatsapp'):
        numbers = []
        for _ in range(5):
            numbers.append({
                'number': FreeNumbers.generate_pakistan_number(),
                'service': service,
                'expires': datetime.now() + timedelta(minutes=20),
            })
        return numbers

# ========== KEYBOARDS ==========
def get_main_keyboard(user_id=None):
    keyboard = [
        [KeyboardButton("📱 Get Number"), KeyboardButton("💰 My Coins")],
        [KeyboardButton("🎥 Watch Ad"), KeyboardButton("💎 Buy Coins")],
        [KeyboardButton("📋 My Numbers"), KeyboardButton("❓ Help")]
    ]
    if user_id and user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton("👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_services_keyboard():
    keyboard = [
        [InlineKeyboardButton("📱 WhatsApp", callback_data="service_whatsapp"),
         InlineKeyboardButton("📘 Telegram", callback_data="service_telegram")],
        [InlineKeyboardButton("📘 Facebook", callback_data="service_facebook"),
         InlineKeyboardButton("📸 Instagram", callback_data="service_instagram")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_plans_keyboard():
    keyboard = [
        [InlineKeyboardButton(f"📅 Daily - {COIN_PLANS['daily']['desc']}", callback_data="plan_daily")],
        [InlineKeyboardButton(f"📆 Weekly - {COIN_PLANS['weekly']['desc']}", callback_data="plan_weekly")],
        [InlineKeyboardButton(f"📅 Monthly - {COIN_PLANS['monthly']['desc']}", callback_data="plan_monthly")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== BOT HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_user(user.id)
    db.reset_daily()
    user_data = db.get_user(user.id)
    
    welcome_msg = (
        f"👋 <b>Assalam-o-Alaikum {user.first_name}!</b>\n\n"
        f"📱 <b>🇵🇰 Pakistan Numbers Bot</b>\n\n"
        f"💰 <b>Your Coins:</b> {user_data['coins']}\n"
        f"🎁 <b>Daily Free:</b> 10 coins\n\n"
        f"<b>Payment Numbers:</b>\n"
        f"JazzCash: <code>{PAYMENT_NUMBERS['jazzcash']}</code>\n"
        f"EasyPaisa: <code>{PAYMENT_NUMBERS['easypaisa']}</code>\n\n"
        f"👇 <b>Choose option:</b>"
    )
    
    await update.message.reply_text(
        welcome_msg,
        reply_markup=get_main_keyboard(user.id),
        parse_mode='HTML'
    )

async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if user_id not in ADMIN_IDS and user_data['coins'] < 5:
        await update.message.reply_text(
            f"❌ Not enough coins! You have {user_data['coins']} coins. Need 5.",
            parse_mode='HTML'
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📋 <b>Select Service:</b>",
        reply_markup=get_services_keyboard(),
        parse_mode='HTML'
    )
    return SELECTING_SERVICE

async def service_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.message.delete()
        return ConversationHandler.END
    
    user_id = query.from_user.id
    service = query.data.replace('service_', '')
    
    if user_id not in ADMIN_IDS and not db.remove_coins(user_id, 5):
        await query.edit_message_text("❌ Not enough coins!")
        return ConversationHandler.END
    
    numbers = FreeNumbers.get_active_numbers(service)
    if not numbers:
        await query.edit_message_text("❌ No numbers available!")
        return ConversationHandler.END
    
    number_data = random.choice(numbers)
    phone = number_data['number']
    order_id = db.add_number(user_id, phone, service)
    
    message = f"✅ <b>Number Received!</b>\n\n📞 <code>{phone}</code>\n📱 Service: {service.title()}\n⏳ Expires: 20 minutes\n\n⏳ Waiting for OTP..."
    
    await query.edit_message_text(message, parse_mode='HTML')
    
    context.user_data['current_phone'] = phone
    context.user_data['current_order'] = order_id
    
    # Start OTP checking
    context.job_queue.run_once(check_otp_job, 10, data={
        'phone': phone,
        'order_id': order_id,
        'user_id': user_id,
        'attempt': 1
    })
    
    return ConversationHandler.END

async def check_otp_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    phone = data['phone']
    order_id = data['order_id']
    user_id = data['user_id']
    attempt = data.get('attempt', 1)
    
    logger.info(f"🔄 Checking OTP for {phone} (attempt {attempt})")
    
    otp_data = RealOTPService.check_otp(phone)
    
    if otp_data:
        db.update_otp(order_id, otp_data['otp'])
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📨 <b>✅ REAL OTP Received!</b>\n\n🔑 <code>{otp_data['otp']}</code>\n📱 From: {otp_data['from']}",
            parse_mode='HTML'
        )
        logger.info(f"✅ OTP sent to user {user_id}: {otp_data['otp']}")
    else:
        order = db.get_order(order_id)
        if order and datetime.now() < datetime.fromisoformat(order['expires']) and attempt < 40:
            context.job_queue.run_once(
                check_otp_job, 15, 
                data={'phone': phone, 'order_id': order_id, 'user_id': user_id, 'attempt': attempt + 1}
            )

async def buy_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 <b>Buy Coins</b>\n\nChoose plan:",
        reply_markup=get_plans_keyboard(),
        parse_mode='HTML'
    )

async def plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.message.delete()
        return
    
    plan = query.data.replace('plan_', '')
    context.user_data['selected_plan'] = plan
    plan_details = COIN_PLANS[plan]
    
    payment_info = (
        f"💎 <b>Payment Instructions</b>\n\n"
        f"Plan: {plan.title()}\nCoins: {plan_details['coins']}\nPrice: {plan_details['price']} Rs\n\n"
        f"Send payment to:\nJazzCash: {PAYMENT_NUMBERS['jazzcash']}\nEasyPaisa: {PAYMENT_NUMBERS['easypaisa']}\n\n"
        f"After payment, send transaction ID."
    )
    
    await query.edit_message_text(payment_info, parse_mode='HTML')
    await query.message.reply_text("📤 Send transaction ID:")
    return WAITING_PAYMENT_SS

async def handle_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    plan = context.user_data.get('selected_plan', 'daily')
    
    payment_id = db.add_payment(user_id, plan, COIN_PLANS[plan]['price'], text)
    
    await update.message.reply_text(f"✅ Payment request submitted!\nPayment ID: {payment_id}\nAdmin will approve soon.")
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"💰 New Payment\nUser: {user_id}\nPayment ID: {payment_id}\nPlan: {plan}\nTransaction: {text}\n/approve {payment_id}\n/reject {payment_id}"
            )
        except:
            pass
    
    context.user_data.pop('selected_plan', None)

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve PAYMENT_ID")
        return
    payment_id = context.args[0]
    if db.approve_payment(payment_id, update.effective_user.id):
        await update.message.reply_text(f"✅ Payment {payment_id} approved!")
    else:
        await update.message.reply_text("❌ Payment not found!")

async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /reject PAYMENT_ID [reason]")
        return
    payment_id = context.args[0]
    reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "No reason"
    if db.reject_payment(payment_id, reason):
        await update.message.reply_text(f"❌ Payment {payment_id} rejected!")
    else:
        await update.message.reply_text("❌ Payment not found!")

async def add_coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addcoins USER_ID AMOUNT")
        return
    target_id = context.args[0]
    amount = int(context.args[1])
    db.add_coins(target_id, amount)
    await update.message.reply_text(f"✅ Added {amount} coins to user {target_id}")

async def watch_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        await update.message.reply_text("👑 Admin doesn't need ads!")
        return
    
    keyboard = [[InlineKeyboardButton("✅ Verified", callback_data="ad_verified")]]
    await update.message.reply_text(
        "🎥 Watch Ad\n\nAfter watching, click verify:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def ad_verified(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id in ADMIN_IDS:
        await query.edit_message_text("👑 Admin doesn't need ads!")
        return
    
    db.add_coins(user_id, 5)
    user = db.get_user(user_id)
    await query.edit_message_text(f"✅ +5 Coins!\nNew balance: {user['coins']}")

async def my_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    await update.message.reply_text(f"💰 Balance: {user['coins']} coins")

async def my_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user['numbers']:
        await update.message.reply_text("📭 No numbers yet!")
        return
    
    msg = "📋 Recent Numbers:\n\n"
    for order_id in user['numbers'][-5:]:
        order = db.get_order(order_id)
        if order:
            otp = f"OTP: {order['otp']}" if order['otp'] else "Waiting..."
            msg += f"📞 {order['number']} - {otp}\n"
    await update.message.reply_text(msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "❓ Help\n\n"
        "1. Get Number (5 coins)\n"
        "2. Watch Ads (+5 coins)\n"
        "3. Buy Coins (No Ads)\n"
        "4. OTP auto appears\n\n"
        f"Contact: {ADMIN_USERNAME}"
    )
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard(update.effective_user.id))

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "📱 Get Number":
        await get_number(update, context)
    elif text == "💰 My Coins":
        await my_coins(update, context)
    elif text == "🎥 Watch Ad":
        await watch_ad(update, context)
    elif text == "💎 Buy Coins":
        await buy_coins(update, context)
    elif text == "📋 My Numbers":
        await my_numbers(update, context)
    elif text == "❓ Help":
        await help_command(update, context)
    elif text == "👑 Admin Panel" and user_id in ADMIN_IDS:
        stats = db.get_stats()
        await update.message.reply_text(f"👑 Admin Panel\n\nUsers: {stats['total_users']}\nPayments: {stats['total_payments']}")

# ========== MAIN FUNCTION ==========
def main():
    print("🚀 Starting Pakistan Numbers Bot with REAL OTP...")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("approve", approve_payment))
    app.add_handler(CommandHandler("reject", reject_payment))
    app.add_handler(CommandHandler("addcoins", add_coins_command))
    
    # Number flow conversation
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📱 Get Number$'), get_number)],
        states={SELECTING_SERVICE: [CallbackQueryHandler(service_selected, pattern='^(service_|cancel)')]},
        fallbacks=[CommandHandler('cancel', help_command)]
    )
    app.add_handler(conv_handler)
    
    # Payment flow conversation
    payment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(plan_selected, pattern='^plan_')],
        states={WAITING_PAYMENT_SS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transaction)]},
        fallbacks=[CommandHandler('cancel', help_command)]
    )
    app.add_handler(payment_conv)
    
    # Button and callback handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(CallbackQueryHandler(ad_verified, pattern='^ad_verified$'))
    app.add_handler(CallbackQueryHandler(plan_selected, pattern='^plan_'))
    
    # Daily reset job
    if app.job_queue:
        app.job_queue.run_daily(lambda _: db.reset_daily(), time=datetime.strptime("00:00", "%H:%M").time())
        print("✅ Daily reset job scheduled")
    
    print("✅ Bot is running with REAL OTP detection!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
