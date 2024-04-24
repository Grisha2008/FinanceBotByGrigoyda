from collections import defaultdict
from datetime import datetime, timedelta
import telebot
from telebot import types
import sqlite3
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from telebot import apihelper

session = Session()
retries = HTTPAdapter(max_retries=3)
session.mount('http://', retries)
session.mount('https://', retries)
apihelper._get_req_session = lambda: session

TOKEN = '6718983088:AAFWAC9AIGIjvzVRFL5Sy_52jtueG-DkbvE'
bot = telebot.TeleBot(TOKEN)

user_commands = defaultdict(list)


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

def check_command_limits(user_id, command):
    now = datetime.now()
    time_threshold = now - timedelta(seconds=20)
    recent_commands = [cmd for cmd in user_commands[user_id] if cmd[0] > time_threshold]
    user_commands[user_id] = recent_commands
    user_commands[user_id].append((now, command))
    command_count = len([cmd for cmd in user_commands[user_id] if cmd[1] == command])
    return command_count > 10

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    command = message.text
    if check_command_limits(user_id, command):
        with open("img.png", "rb") as photo:
            bot.send_photo(message.chat.id, photo, caption="Пожалуйста, остановитесь!")
    else:
        bot.send_message(message.chat.id, "Команда принята: " + command)


@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    transactions_btn = types.KeyboardButton('Транзакции')
    limits_btn = types.KeyboardButton('Лимиты')
    goals_btn = types.KeyboardButton('Цели')
    currency_rates_btn = types.KeyboardButton('Курсы валют')
    markup.add(transactions_btn, limits_btn, goals_btn, currency_rates_btn)
    welcome_text = "Добро пожаловать в вашего финансового помощника! Используйте кнопки ниже для управления вашими финансами."
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == 'Транзакции')
def transaction_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    expense_btn = types.KeyboardButton('Расход')
    income_btn = types.KeyboardButton('Пополнение')
    list_transactions_btn = types.KeyboardButton('Список транзакций')
    clear_transactions_btn = types.KeyboardButton('Очистить транзакции')
    back_btn = types.KeyboardButton('Назад')
    markup.add(expense_btn, income_btn, list_transactions_btn, clear_transactions_btn, back_btn)
    bot.send_message(message.chat.id, "Какое действие вы хотите совершить?", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == 'Очистить транзакции')
def clear_transactions(message):
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM transactions WHERE user_id=?', (message.from_user.id,))
    conn.commit()
    conn.close()
    bot.reply_to(message, "Все ваши транзакции удалены.")

@bot.message_handler(func=lambda message: message.text in ['Расход', 'Пополнение'])
def handle_transaction(message):
    transaction_type = message.text
    ask_for_transaction_details(message, transaction_type)

def ask_for_transaction_details(message, transaction_type):
    markup = get_cancel_back_markup()
    sent = bot.send_message(message.chat.id, "Введите транзакцию в формате: сумма категория", reply_markup=markup)
    bot.register_next_step_handler(sent, process_transaction, transaction_type)

@bot.message_handler(func=lambda message: message.text == 'Отмена')
def cancel_action(message):
    bot.send_message(message.chat.id, "Действие отменено.", reply_markup=types.ReplyKeyboardRemove())
    send_welcome(message)

@bot.message_handler(func=lambda message: message.text == 'Назад')
def go_back(message):
    send_welcome(message)


def process_transaction(message, transaction_type):
    try:
        amount, category = message.text.split(maxsplit=1)
        amount = float(amount)
        if transaction_type == 'Расход':
            amount = -amount
        log_transaction(message.from_user.id, amount, transaction_type.lower(), category)
        bot.reply_to(message, f"Транзакция зарегистрирована: {transaction_type} {amount} руб. Категория: {category}")
    except ValueError:
        bot.reply_to(message, "Ошибка ввода. Пожалуйста, введите данные в формате: сумма категория")

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

@bot.message_handler(func=lambda message: message.text == 'Список транзакций')
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

def get_cancel_back_markup():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    cancel_btn = types.KeyboardButton('Отмена')
    back_btn = types.KeyboardButton('Назад')
    markup.add(cancel_btn, back_btn)
    return markup


init_db()
bot.polling()
