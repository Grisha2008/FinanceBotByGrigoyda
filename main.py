import telebot
from telebot import types
import sqlite3
from datetime import datetime

TOKEN = '6718983088:AAFWAC9AIGIjvzVRFL5Sy_52jtueG-DkbvE'
bot = telebot.TeleBot(TOKEN)

def init_db():
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            category TEXT,
            date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS limits (
                user_id INTEGER,
                category TEXT,
                limit_amount REAL,
                period TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
    conn.commit()
    conn.close()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('Расход')
    btn2 = types.KeyboardButton('Пополнение')
    btn3 = types.KeyboardButton('Баланс')
    btn4 = types.KeyboardButton('Транзакции')
    btn5 = types.KeyboardButton('Лимиты')
    markup.add(btn1, btn2, btn3, btn4, btn5)
    welcome_text = """Добро пожаловать в вашего финансового помощника! Используйте кнопки ниже для управления вашими финансами.
    Введите 'отмена' в любой момент, чтобы прервать текущее действие."""
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)


def ask_for_transaction_details(message):
    if message.text.lower() == 'отмена':
        bot.send_message(message.chat.id, "Действие отменено.")
        return
    sent = bot.send_message(message.chat.id, "Введите транзакцию в формате: сумма категория")
    bot.register_next_step_handler(sent, process_transaction, message.text)

def set_limit(message):
    if message.text.lower() == 'отмена':
        bot.send_message(message.chat.id, "Действие отменено.")
        return
    try:
        parts = message.text.split()
        category = parts[0]
        amount = float(parts[1])
        period = parts[2]
        conn = sqlite3.connect('finance_bot.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO limits (user_id, category, limit_amount, period) VALUES (?, ?, ?, ?)',
                       (message.from_user.id, category, amount, period))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"Установлен лимит {amount} рублей на {period} для категории {category}.")
    except Exception as e:
        bot.reply_to(message, "Ошибка ввода. Пожалуйста, убедитесь, что формат верен: Категория Сумма Период")



def log_transaction(user_id, amount, transaction_type, category):
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE id=?', (user_id,))
    if cursor.fetchone() is None:
        cursor.execute('INSERT INTO users (id, username) VALUES (?, ?)', (user_id, f'user_{user_id}'))
    cursor.execute('INSERT INTO transactions (user_id, type, amount, category, date) VALUES (?, ?, ?, ?, ?)',
                   (user_id, transaction_type, amount, category, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()


def process_transaction(message, transaction_type):
    try:
        amount, category = message.text.split(maxsplit=1)
        amount = float(amount)
        if transaction_type == 'Расход':
            amount = -amount
        log_transaction(message.from_user.id, amount, transaction_type.lower(), category)
        check_limits(message.from_user.id, category, abs(amount))
        bot.reply_to(message, f"Транзакция зарегистрирована: {transaction_type} {amount} руб. Категория: {category}")
    except ValueError:
        bot.reply_to(message, "Ошибка ввода. Пожалуйста, введите данные в формате: сумма категория")


@bot.message_handler(func=lambda message: message.text == 'Баланс')
def show_balance(message):
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id=?', (message.from_user.id,))
    result = cursor.fetchone()[0]
    balance = result if result is not None else 0
    if balance == 0:
        bot.reply_to(message, "У вас не было транзакций.")
    else:
        bot.reply_to(message, f"Ваш баланс: {balance} руб.")

@bot.message_handler(func=lambda message: message.text == 'Транзакции')
def show_transactions(message):
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT type, amount, category, date FROM transactions WHERE user_id=? ORDER BY date DESC', (message.from_user.id,))
    transactions = cursor.fetchall()
    if not transactions:
        bot.reply_to(message, "У вас пока нет транзакций.")
    else:
        transactions_list = '\n'.join([f"{index+1}) {t[0]}: {t[1]} руб, Категория: {t[2]}, Дата: {t[3]}" for index, t in enumerate(transactions)])
        bot.reply_to(message, f"Ваши транзакции:\n{transactions_list}")

@bot.message_handler(func=lambda message: message.text == 'Лимиты')
def limits_menu(message):
    sent = bot.send_message(message.chat.id, "Введите лимит в формате: Категория Сумма Период (неделя/месяц)")
    bot.register_next_step_handler(sent, set_limit)


def check_limits(user_id, category, amount):
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT limit_amount FROM limits WHERE user_id=? AND category=?', (user_id, category))
    limit = cursor.fetchone()
    if limit:
        limit_amount = limit[0]
        cursor.execute('''
            SELECT SUM(amount) FROM transactions 
            WHERE user_id=? AND category=? AND type='expense' AND date >= DATE('now', 'start of month')
        ''', (user_id, category))
        spent = cursor.fetchone()[0] or 0
        if spent + amount >= limit_amount * 0.95:
            remaining = limit_amount - spent - amount
            bot.send_message(user_id,
                             f"Внимание: Вы близки к лимиту по категории {category}. Осталось {remaining} руб.")
    conn.close()




init_db()
bot.polling()
