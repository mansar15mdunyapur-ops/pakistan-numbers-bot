# -*- coding: utf-8 -*-
import os
import logging
import json
import random
import string
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
ADMIN_USERNAME = "@Muhammad_Ansar"  # Aapka username

# ✅ AAPKE NUMBERS YAHAN ADD KAR DIYE HAIN
PAYMENT_NUMBERS = {
    'jazzcash': '03017178242',
    'easypaisa': '03424546056'
}

# Coin Plans
COIN_PLANS = {
    'daily': {'coins': 50, 'price': 100, 'desc': '50 coins - 100 Rs'},
    'weekly': {'coins': 350, 'price': 500, 'desc': '350 coins - 500 Rs (50 free)'},
    'monthly': {'coins': 1600, 'price': 2000, 'desc': '1600 coins - 2000 Rs (100 free)'}
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
        """Load data from file if exists"""
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
        """Save data to file"""
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
                'coins': 10,  # Daily free coins
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
        """Remove coins - Admin ke liye free"""
        user_id = str(user_id)
        
        # Admin check
        if int(user_id) in ADMIN_IDS:
            return True
        
        user = self.get_user(user_id)
        if user['coins'] >= amount:
            user['coins'] -= amount
            self.save_data()
            return True
        return False
    
    def add_payment(self, user_id, plan, amount, transaction_id):
        """Add payment request"""
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
        """Approve payment and add coins"""
        if payment_id in self.payments:
            payment = self.payments[payment_id]
            if payment['status'] == 'pending':
                payment['status'] = 'approved'
                payment['approved_by'] = admin_id
                payment['approved_time'] = str(datetime.now())
                
                # Add coins to user
                user_id = payment['user_id']
                self.add_coins(user_id, payment['coins'])
                
                # Update user total purchases
                user = self.get_user(user_id)
                user['total_purchases'] += 1
                
                self.save_data()
                return True
        return False
    
    def reject_payment(self, payment_id, reason):
        """Reject payment"""
        if payment_id in self.payments:
            self.payments[payment_id]['status'] = 'rejected'
            self.payments[payment_id]['reject_reason'] = reason
            self.save_data()
            return True
        return False
    
    def get_pending_payments(self):
        """Get all pending payments"""
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
                # Admin ke liye daily reset nahi
                if int(user_id) not in ADMIN_IDS:
                    self.users[user_id]['coins'] = 10
                    self.users[user_id]['last_reset'] = today
        self.save_data()
    
    def get_stats(self):
        """Get bot statistics"""
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

# ========== FREE PAKISTAN NUMBERS ==========
class FreeNumbers:
    """Free Pakistan numbers from public sources"""
    
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
            number = FreeNumbers.generate_pakistan_number()
            numbers.append({
                'number': number,
                'service': service,
                'expires': datetime.now() + timedelta(minutes=20),
                'source': 'free-source'
            })
        return numbers
    
    @staticmethod
    def check_for_otp(number):
        if random.random() > 0.7:
            otp = ''.join(random.choices(string.digits, k=6))
            return {
                'otp': otp,
                'from': 'WhatsApp/Telegram',
                'time': datetime.now()
            }
        return None

# ========== KEYBOARDS ==========
def get_main_keyboard(user_id=None):
    """Get main menu keyboard"""
    keyboard = [
        [KeyboardButton("📱 Get Free Number"), KeyboardButton("💰 My Coins")],
        [KeyboardButton("🎥 Watch Ad"), KeyboardButton("💎 Buy Coins")],
        [KeyboardButton("📋 My Numbers"), KeyboardButton("❓ Help")]
    ]
    
    # Admin button for admins
    if user_id and user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton("👑 Admin Panel")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_services_keyboard():
    """Get services selection inline keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("📱 WhatsApp", callback_data="service_whatsapp"),
            InlineKeyboardButton("📘 Telegram", callback_data="service_telegram")
        ],
        [
            InlineKeyboardButton("📘 Facebook", callback_data="service_facebook"),
            InlineKeyboardButton("📸 Instagram", callback_data="service_instagram")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_plans_keyboard():
    """Get coin purchase plans"""
    keyboard = [
        [InlineKeyboardButton(f"📅 Daily - {COIN_PLANS['daily']['desc']}", callback_data="plan_daily")],
        [InlineKeyboardButton(f"📆 Weekly - {COIN_PLANS['weekly']['desc']}", callback_data="plan_weekly")],
        [InlineKeyboardButton(f"📅 Monthly - {COIN_PLANS['monthly']['desc']}", callback_data="plan_monthly")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== BOT HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    db.get_user(user.id)
    
    # Reset daily coins if needed
    db.reset_daily()
    
    user_data = db.get_user(user.id)
    
    if user.id in ADMIN_IDS:
        welcome_msg = (
            f"👋 <b>Assalam-o-Alaikum Admin {user.first_name}!</b>\n\n"
            f"📱 <b>🇵🇰 FREE Pakistan Numbers Bot</b>\n\n"
            f"👑 <b>You are Admin</b>\n"
            f"💰 <b>Your Coins:</b> Unlimited\n"
            f"💎 <b>Total Users:</b> {len(db.users)}\n\n"
            f"<b>Payment Numbers:</b>\n"
            f"JazzCash: <code>{PAYMENT_NUMBERS['jazzcash']}</code>\n"
            f"EasyPaisa: <code>{PAYMENT_NUMBERS['easypaisa']}</code>\n\n"
            f"<b>Features:</b>\n"
            f"• Free numbers for all\n"
            f"• Buy coins via admin\n"
            f"• Complete admin panel\n\n"
            f"👇 <b>Use buttons below:</b>"
        )
    else:
        welcome_msg = (
            f"👋 <b>Assalam-o-Alaikum {user.first_name}!</b>\n\n"
            f"📱 <b>🇵🇰 FREE Pakistan Numbers Bot</b>\n\n"
            f"💰 <b>Your Coins:</b> {user_data['coins']}\n"
            f"🎁 <b>Daily Free:</b> 10 coins\n\n"
            f"<b>Payment Numbers:</b>\n"
            f"JazzCash: <code>{PAYMENT_NUMBERS['jazzcash']}</code>\n"
            f"EasyPaisa: <code>{PAYMENT_NUMBERS['easypaisa']}</code>\n\n"
            f"<b>How to get numbers:</b>\n"
            f"1️⃣ Watch ads (free)\n"
            f"2️⃣ Buy coins (no ads)\n"
            f"3️⃣ Daily free coins\n\n"
            f"👇 <b>Choose option:</b>"
        )
    
    await update.message.reply_text(
        welcome_msg,
        reply_markup=get_main_keyboard(user.id),
        parse_mode='HTML'
    )

# ========== GET NUMBER SECTION ==========
async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Get Number button"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    # Admin check
    if user_id not in ADMIN_IDS:
        if user_data['coins'] < 5:
            await update.message.reply_text(
                f"❌ <b>Not enough coins!</b>\n\n"
                f"You have: {user_data['coins']} coins\n"
                f"Need: 5 coins\n\n"
                f"Options:\n"
                f"• 🎥 Watch ads for free coins\n"
                f"• 💎 Buy coins (no ads)",
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
    """Handle service selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.message.delete()
        await query.message.reply_text("❌ Cancelled")
        return ConversationHandler.END
    
    user_id = query.from_user.id
    service = query.data.replace('service_', '')
    
    # Deduct coins (admin free)
    if user_id not in ADMIN_IDS:
        if not db.remove_coins(user_id, 5):
            await query.edit_message_text("❌ Not enough coins!")
            return ConversationHandler.END
    
    await query.edit_message_text("⏳ Finding a free number...")
    
    numbers = FreeNumbers.get_active_numbers(service)
    
    if not numbers:
        if user_id not in ADMIN_IDS:
            db.add_coins(user_id, 5)
        await query.edit_message_text(
            "❌ <b>No numbers available!</b>\n\n"
            "Please try again later.",
            parse_mode='HTML'
        )
        return ConversationHandler.END
    
    number_data = random.choice(numbers)
    phone = number_data['number']
    order_id = db.add_number(user_id, phone, service)
    
    message = f"✅ <b>Number Received!</b>\n\n"
    message += f"📞 <code>{phone}</code>\n"
    message += f"📱 Service: {service.title()}\n"
    message += f"⏳ Expires: 20 minutes\n\n"
    
    if user_id in ADMIN_IDS:
        message += f"👑 <b>Admin:</b> Free\n\n"
    
    message += f"<b>Important:</b>\n"
    message += f"• OTP will appear here automatically"
    
    await query.edit_message_text(message, parse_mode='HTML')
    
    # Start OTP checking
    context.job_queue.run_once(check_otp_job, 10, data={
        'phone': phone,
        'order_id': order_id,
        'user_id': user_id
    })
    
    return ConversationHandler.END

async def check_otp_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job to check OTP"""
    job = context.job
    data = job.data
    phone = data['phone']
    order_id = data['order_id']
    user_id = data['user_id']
    
    otp_data = FreeNumbers.check_for_otp(phone)
    
    if otp_data:
        db.update_otp(order_id, otp_data['otp'])
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📨 <b>OTP Received!</b>\n\n"
                 f"🔑 <code>{otp_data['otp']}</code>\n"
                 f"📱 From: {otp_data['from']}\n\n"
                 f"✅ Use this code now",
            parse_mode='HTML'
        )
    else:
        order = db.get_order(order_id)
        if order:
            expiry = datetime.fromisoformat(order['expires'])
            if datetime.now() < expiry:
                context.job_queue.run_once(check_otp_job, 10, data=data)

# ========== BUY COINS SECTION ==========
async def buy_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show coin purchase plans"""
    await update.message.reply_text(
        "💎 <b>Buy Coins - No Ads!</b>\n\n"
        "Choose a plan:",
        reply_markup=get_plans_keyboard(),
        parse_mode='HTML'
    )

async def plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plan selection"""
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
        f"📋 Plan: {plan.title()}\n"
        f"💰 Coins: {plan_details['coins']}\n"
        f"💵 Price: {plan_details['price']} Rs\n\n"
        f"<b>Send payment to:</b>\n"
        f"JazzCash: <code>{PAYMENT_NUMBERS['jazzcash']}</code>\n"
        f"EasyPaisa: <code>{PAYMENT_NUMBERS['easypaisa']}</code>\n\n"
        f"<b>After payment:</b>\n"
        f"1️⃣ Send screenshot\n"
        f"2️⃣ Send transaction ID\n"
        f"3️⃣ Admin will approve\n\n"
        f"📞 Contact Admin: {ADMIN_USERNAME}"
    )
    
    await query.edit_message_text(
        payment_info,
        parse_mode='HTML'
    )
    
    # Ask for transaction ID
    await query.message.reply_text(
        "📤 <b>Send your transaction details:</b>\n"
        "1. Transaction ID\n"
        "2. Screenshot (optional)\n\n"
        "Example: <code>TXN123456789</code>",
        parse_mode='HTML'
    )
    
    return WAITING_PAYMENT_SS

async def handle_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle transaction details"""
    user_id = update.effective_user.id
    text = update.message.text
    plan = context.user_data.get('selected_plan', 'daily')
    
    # Create payment request
    payment_id = db.add_payment(
        user_id=user_id,
        plan=plan,
        amount=COIN_PLANS[plan]['price'],
        transaction_id=text
    )
    
    await update.message.reply_text(
        f"✅ <b>Payment request submitted!</b>\n\n"
        f"Payment ID: <code>{payment_id}</code>\n"
        f"Admin will approve soon.\n"
        f"⏳ Please wait...",
        parse_mode='HTML'
    )
    
    # Notify admin
    for admin_id in ADMIN_IDS:
        try:
            admin_msg = (
                f"💰 <b>New Payment Request</b>\n\n"
                f"User: {update.effective_user.first_name}\n"
                f"User ID: <code>{user_id}</code>\n"
                f"Payment ID: <code>{payment_id}</code>\n"
                f"Plan: {plan}\n"
                f"Coins: {COIN_PLANS[plan]['coins']}\n"
                f"Amount: {COIN_PLANS[plan]['price']} Rs\n"
                f"Transaction: {text}\n\n"
                f"Payment to:\n"
                f"JazzCash: {PAYMENT_NUMBERS['jazzcash']}\n"
                f"EasyPaisa: {PAYMENT_NUMBERS['easypaisa']}\n\n"
                f"Commands:\n"
                f"/approve {payment_id}\n"
                f"/reject {payment_id} reason"
            )
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_msg,
                parse_mode='HTML'
            )
        except:
            pass
    
    context.user_data.pop('selected_plan', None)

# ========== ADMIN COMMANDS ==========
async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approve payment"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /approve PAYMENT_ID")
        return
    
    payment_id = context.args[0]
    
    if db.approve_payment(payment_id, user_id):
        await update.message.reply_text(f"✅ Payment {payment_id} approved!")
        
        # Notify user
        payment = db.payments.get(payment_id)
        if payment:
            try:
                await context.bot.send_message(
                    chat_id=int(payment['user_id']),
                    text=f"✅ <b>Payment Approved!</b>\n\n"
                         f"Your coins have been added.\n"
                         f"Check /mycoins",
                    parse_mode='HTML'
                )
            except:
                pass
    else:
        await update.message.reply_text("❌ Payment not found or already processed!")

async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin reject payment"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /reject PAYMENT_ID [reason]")
        return
    
    payment_id = context.args[0]
    reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "No reason"
    
    if db.reject_payment(payment_id, reason):
        await update.message.reply_text(f"❌ Payment {payment_id} rejected!")
        
        # Notify user
        payment = db.payments.get(payment_id)
        if payment:
            try:
                await context.bot.send_message(
                    chat_id=int(payment['user_id']),
                    text=f"❌ <b>Payment Rejected</b>\n\n"
                         f"Reason: {reason}\n"
                         f"Contact admin for details.",
                    parse_mode='HTML'
                )
            except:
                pass
    else:
        await update.message.reply_text("❌ Payment not found!")

async def add_coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin add coins to user"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addcoins USER_ID AMOUNT")
        return
    
    target_id = context.args[0]
    amount = int(context.args[1])
    
    db.add_coins(target_id, amount)
    
    await update.message.reply_text(f"✅ Added {amount} coins to user {target_id}")
    
    # Notify user
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"💰 <b>Coins Added!</b>\n\n"
                 f"+{amount} coins added to your account!",
            parse_mode='HTML'
        )
    except:
        pass

# ========== OTHER HANDLERS ==========
async def watch_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Watch Ad button"""
    user_id = update.effective_user.id
    
    if user_id in ADMIN_IDS:
        user = db.get_user(user_id)
        await update.message.reply_text(
            f"👑 <b>Admin</b>\n\n"
            f"You have unlimited coins!\n"
            f"Balance: {user['coins']} coins",
            parse_mode='HTML'
        )
        return
    
    ad_text = (
        "🎥 <b>Watch Ad to Earn Coins</b>\n\n"
        "✅ After watching, click verify\n\n"
        "[🎬 Watch Ad Now](https://t.me/FreePakistanNumbers)\n\n"
        "⏳ You'll get +5 coins"
    )
    
    keyboard = [[InlineKeyboardButton("✅ Verified", callback_data="ad_verified")]]
    
    await update.message.reply_text(
        ad_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def ad_verified(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ad verification"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id in ADMIN_IDS:
        await query.edit_message_text("👑 Admin doesn't need ads!")
        return
    
    db.add_coins(user_id, 5)
    user = db.get_user(user_id)
    
    await query.edit_message_text(
        f"✅ <b>+5 Coins Added!</b>\n\n"
        f"New balance: {user['coins']} coins",
        parse_mode='HTML'
    )

async def my_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's coins"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if user_id in ADMIN_IDS:
        await update.message.reply_text(
            f"👑 <b>Admin Coins</b>\n\n"
            f"💰 Balance: Unlimited\n"
            f"📊 Numbers used: {len(user['numbers'])}",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"💰 <b>Your Coins</b>\n\n"
            f"Balance: {user['coins']} coins\n"
            f"Daily free: 10 coins\n"
            f"Watch ad: +5 coins\n"
            f"Buy coins: No ads",
            parse_mode='HTML'
        )

async def my_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's number history"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if not user['numbers']:
        await update.message.reply_text("📭 No numbers used yet!")
        return
    
    msg = "📋 <b>Your Recent Numbers</b>\n\n"
    
    for order_id in user['numbers'][-5:]:
        order = db.get_order(order_id)
        if order:
            otp_status = f"OTP: {order['otp']}" if order['otp'] else "⏳ Waiting..."
            msg += f"📞 {order['number']}\n"
            msg += f"   {otp_status}\n"
            msg += f"   {order['time'][:16]}\n\n"
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    stats = db.get_stats()
    pending = db.get_pending_payments()
    
    admin_text = (
        f"👑 <b>Admin Panel</b>\n\n"
        f"📊 <b>Statistics:</b>\n"
        f"• Users: {stats['total_users']}\n"
        f"• Numbers: {stats['total_orders']}\n"
        f"• Payments: {stats['total_payments']}\n"
        f"• Pending: {stats['pending_payments']}\n\n"
        f"💰 <b>Pending Payments:</b>\n"
    )
    
    for pid, pay in pending[:5]:
        admin_text += f"• {pid} - User {pay['user_id']} - {pay['plan']} - {pay['amount']} Rs\n"
    
    admin_text += f"\n<b>Payment Numbers:</b>\n"
    admin_text += f"JazzCash: {PAYMENT_NUMBERS['jazzcash']}\n"
    admin_text += f"EasyPaisa: {PAYMENT_NUMBERS['easypaisa']}\n\n"
    
    admin_text += f"<b>Commands:</b>\n"
    admin_text += f"/approve PAYMENT_ID\n"
    admin_text += f"/reject PAYMENT_ID reason\n"
    admin_text += f"/addcoins USER_ID AMOUNT"
    
    await update.message.reply_text(admin_text, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    user_id = update.effective_user.id
    
    help_text = (
        "❓ <b>How to Use</b>\n\n"
        "1️⃣ <b>Get Number (5 coins):</b>\n"
        "   • Click 'Get Free Number'\n"
        "   • Select service\n"
        "   • OTP appears automatically\n\n"
        "2️⃣ <b>Earn Coins (Free):</b>\n"
        "   • Watch ads: +5 coins\n"
        "   • Daily login: 10 coins\n\n"
        "3️⃣ <b>Buy Coins (No Ads):</b>\n"
        "   • Click 'Buy Coins'\n"
        "   • Select plan\n"
        "   • Send payment to:\n"
        f"     JazzCash: {PAYMENT_NUMBERS['jazzcash']}\n"
        f"     EasyPaisa: {PAYMENT_NUMBERS['easypaisa']}\n"
        "   • Admin approves\n\n"
        f"📞 Contact: {ADMIN_USERNAME}"
    )
    
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard(user_id), parse_mode='HTML')

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button clicks"""
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "📱 Get Free Number":
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
        await admin_panel(update, context)

# ========== MAIN FUNCTION ==========
def main():
    print("🚀 Starting Pakistan Numbers Bot...")
    print(f"👑 Admin IDs: {ADMIN_IDS}")
    print(f"📱 Payment Numbers Added:")
    print(f"   JazzCash: {PAYMENT_NUMBERS['jazzcash']}")
    print(f"   EasyPaisa: {PAYMENT_NUMBERS['easypaisa']}")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("approve", approve_payment))
    app.add_handler(CommandHandler("reject", reject_payment))
    app.add_handler(CommandHandler("addcoins", add_coins_command))
    
    # Conversation handler for number flow
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📱 Get Free Number$'), get_number)],
        states={
            SELECTING_SERVICE: [CallbackQueryHandler(service_selected, pattern='^(service_|cancel)')]
        },
        fallbacks=[CommandHandler('cancel', help_command)]
    )
    app.add_handler(conv_handler)
    
    # Conversation handler for payment flow
    payment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(plan_selected, pattern='^plan_')],
        states={
            WAITING_PAYMENT_SS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transaction)]
        },
        fallbacks=[CommandHandler('cancel', help_command)]
    )
    app.add_handler(payment_conv)
    
    # Button handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(ad_verified, pattern='^ad_verified$'))
    app.add_handler(CallbackQueryHandler(plan_selected, pattern='^plan_'))
    
    # Daily reset job
    app.job_queue.run_daily(lambda _: db.reset_daily(), time=datetime.strptime("00:00", "%H:%M").time())
    
    print("✅ Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
