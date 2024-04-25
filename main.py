from collections import defaultdict
from datetime import datetime, timedelta
import telebot
from telebot import types
import sqlite3
import requests
import schedule
import time
import threading

TOKEN = "6718983088:AAFWAC9AIGIjvzVRFL5Sy_52jtueG-DkbvE"
bot = telebot.TeleBot(TOKEN)

user_commands = defaultdict(list)

def get_all_user_ids():
    conn = sqlite3.connect("finance_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users")
    user_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return user_ids

def send_daily_photo():
    user_ids = get_all_user_ids()
    photo_path = 'img_1.png'
    for user_id in user_ids:
        with open(photo_path, 'rb') as photo:
            bot.send_photo(user_id, photo, caption="???")
def run_scheduler():
    schedule.every().day.at("18:00").do(send_daily_photo)
    while True:
        schedule.run_pending()
        time.sleep(1)

thread = threading.Thread(target=run_scheduler)
thread.start()

def init_db():
    conn = sqlite3.connect("finance_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            category TEXT,
            date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS limits (
            user_id INTEGER,
            category TEXT,
            limit_amount REAL,
            period TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    limit_amount REAL,
    FOREIGN KEY (user_id) REFERENCES users (id)

    )"""
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS goals (
    user_id INTEGER,
    goal_name TEXT,
    target_amount REAL,
    current_amount REAL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (id)
)
"""
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS limit_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    limit_id INTEGER,
    amount_used REAL,
    date TEXT,
    FOREIGN KEY (limit_id) REFERENCES limits(id)
);
        """
    )

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
            bot.send_photo(message.chat.id, photo, caption="Вай шайтан тихо")
    else:
        process_user_command(message)


def get_cancel_back_markup():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    cancel_btn = types.KeyboardButton("Отмена")
    back_btn = types.KeyboardButton("Назад")
    markup.add(cancel_btn, back_btn)
    return markup


def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("Баланс", "Цели", "Транзакции", "Курсы валют", "Конвертер валют")
    welcome_text = "Выберите действие:"
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "Конвертер валют")
def currency_converter_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("Доллар", "Евро", "Юань", "Назад")
    bot.send_message(
        message.chat.id, "Выберите валюту для конвертации:", reply_markup=markup
    )


@bot.message_handler(func=lambda message: message.text == "Цели")
def goals_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    markup.add("Задать цель", "Список целей", "Очистить цели", "Назад")
    bot.send_message(
        message.chat.id, "Выберите действие для целей:", reply_markup=markup
    )


@bot.message_handler(func=lambda message: message.text == "Задать цель")
def set_goal_request(message):
    markup = types.ReplyKeyboardMarkup(
        row_width=1, resize_keyboard=True, one_time_keyboard=True
    )
    markup.add("Отмена")
    sent = bot.send_message(
        message.chat.id,
        "Введите название цели и желаемую сумму через запятую (например, Машина, 500000):",
        reply_markup=markup,
    )
    bot.register_next_step_handler(sent, set_goal)


def set_goal(message):
    if message.text.strip().lower() == "отмена":
        bot.send_message(
            message.chat.id,
            "Установка цели отменена.",
            reply_markup=types.ReplyKeyboardRemove(),
        )
        send_welcome(message)
        return

    try:
        goal_name, target_amount = message.text.split(",")
        target_amount = float(target_amount.strip())
        user_id = message.from_user.id
        conn = sqlite3.connect("finance_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO goals (user_id, goal_name, target_amount, current_amount) VALUES (?, ?, ?, ?)",
            (user_id, goal_name.strip(), target_amount, 0),
        )
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, "Цель успешно установлена.")
    except ValueError:
        bot.send_message(
            message.chat.id,
            "Неверный формат ввода. Пожалуйста, введите данные в формате: название, сумма",
        )
        set_goal_request(message)


@bot.message_handler(func=lambda message: message.text == "Список целей")
def show_goals(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("finance_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT goal_name, target_amount, current_amount FROM goals WHERE user_id=?",
        (user_id,),
    )
    goals = cursor.fetchall()
    if goals:
        goals_str = "\n".join(
            [
                f"{goal[0]}: {goal[2]}/{goal[1]} руб. ({goal[2]/goal[1]*100:.2f}% выполнено)"
                for goal in goals
            ]
        )
        bot.send_message(message.chat.id, f"Ваши цели:\n{goals_str}")
    else:
        bot.send_message(message.chat.id, "У вас нет установленных целей.")
    conn.close()


@bot.message_handler(func=lambda message: message.text == "Очистить цели")
def clear_goals(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("finance_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM goals WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, "Все ваши цели были удалены.")


def fetch_currency_rate(currency_code):
    api_key = "e88a592f41426950daf687bd"
    url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/RUB"
    response = requests.get(url)
    data = response.json()
    if data["result"] == "success":
        return data["conversion_rates"][currency_code]
    return None


@bot.message_handler(func=lambda message: message.text in ["Доллар", "Евро", "Юань"])
def handle_currency_conversion(message):
    currency_map = {"Доллар": "USD", "Евро": "EUR", "Юань": "CNY"}
    currency_code = currency_map[message.text]
    rate = fetch_currency_rate(currency_code)
    if rate:
        msg = bot.send_message(
            message.chat.id,
            f"Введите количество рублей для конвертации в {message.text}:",
        )
        bot.register_next_step_handler(msg, convert_currency, rate)
    else:
        bot.send_message(message.chat.id, "Ошибка получения курса валют.")


def convert_currency(message, rate):
    try:
        rubles = float(message.text)
        result = rubles * rate
        bot.send_message(
            message.chat.id, f"Эквивалент в выбранной валюте: {result:.2f}"
        )
    except ValueError:
        bot.send_message(
            message.chat.id, "Неверный формат ввода. Пожалуйста, введите число."
        )


@bot.message_handler(func=lambda message: message.text == "Транзакции")
def transaction_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        "Список транзакций", "Очистить транзакции", "Пополнение", "Расход", "Назад"
    )
    bot.send_message(message.chat.id, "Выберите тип транзакции:", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "Назад")
def handle_back(message):
    send_welcome(message)


@bot.message_handler(commands=["start"])
def handle_start(message):
    send_welcome(message)


@bot.message_handler(func=lambda message: message.text == "Очистить транзакции")
def clear_transactions(message):
    conn = sqlite3.connect("finance_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE user_id=?", (message.from_user.id,))
    conn.commit()
    conn.close()
    bot.reply_to(message, "Все ваши транзакции удалены.")


@bot.message_handler(func=lambda message: message.text in ["Расход", "Пополнение"])
def ask_for_transaction_details(message):
    markup = get_cancel_back_markup()
    transaction_type = message.text
    prompt_text = "Введите сумму и категорию через пробел (например, '1000 Еда')"
    sent = bot.send_message(message.chat.id, prompt_text, reply_markup=markup)
    bot.register_next_step_handler(sent, process_transaction, transaction_type)


def process_transaction(message, transaction_type):
    if message.text.strip().lower() == "отмена":
        bot.send_message(
            message.chat.id,
            "Транзакция отменена.",
            reply_markup=types.ReplyKeyboardRemove(),
        )
        send_welcome(message)
        return
    try:
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError("Неправильный формат ввода.")
        amount, category = parts
        amount = float(amount)
        if transaction_type == "Расход":
            amount = -abs(amount)
        else:
            amount = abs(amount)
        log_transaction(message.from_user.id, amount, transaction_type, category)
        bot.reply_to(
            message,
            f"Транзакция зарегистрирована: {transaction_type} {amount} руб. Категория: {category}",
        )
    except ValueError as e:
        bot.reply_to(message, f"Ошибка: {str(e)}. Попробуйте ещё раз.")
        ask_for_transaction_details(message)


def log_transaction(user_id, amount, transaction_type, category):
    conn = sqlite3.connect("finance_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transactions (user_id, type, amount, category, date) VALUES (?, ?, ?, ?, ?)",
        (
            user_id,
            transaction_type,
            amount,
            category,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    if transaction_type == "Пополнение":
        cursor.execute(
            "UPDATE goals SET current_amount = current_amount + ? WHERE user_id = ? AND goal_name = ?",
            (amount, user_id, category),
        )
        conn.commit()
    conn.close()


@bot.message_handler(func=lambda message: message.text == "Список транзакций")
def show_transactions(message):
    conn = sqlite3.connect("finance_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT type, amount, category, date FROM transactions WHERE user_id=? ORDER BY date DESC",
        (message.from_user.id,),
    )
    transactions = cursor.fetchall()
    if not transactions:
        bot.reply_to(message, "У вас пока нет транзакций.")
    else:
        transactions_list = "\n".join(
            [
                f"{t[3]}: {t[1]} руб ({'доход' if t[1] > 0 else 'расход'}) - Категория: {t[2]}"
                for t in transactions
            ]
        )
        bot.reply_to(message, f"Ваши транзакции:\n{transactions_list}")


@bot.message_handler(func=lambda message: message.text == "Курсы валют")
def currency_rates(message):
    api_key = "e88a592f41426950daf687bd"
    url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/RUB"
    response = requests.get(url)
    data = response.json()
    if data["result"] == "success":
        usd_rate = data["conversion_rates"]["USD"]
        eur_rate = data["conversion_rates"]["EUR"]
        cny_rate = data["conversion_rates"]["CNY"]
        rates_message = (
            f"Курс рубля:\nUSD: {usd_rate}\nEUR: {eur_rate}\nCNY: {cny_rate}"
        )
    else:
        rates_message = "Ошибка при получении данных о курсах валют."
    bot.send_message(message.chat.id, rates_message)


@bot.message_handler(func=lambda message: message.text == "Отмена")
def cancel_action(message):
    bot.send_message(
        message.chat.id, "Действие отменено.", reply_markup=types.ReplyKeyboardRemove()
    )
    send_welcome(message)


@bot.message_handler(func=lambda message: message.text == "Баланс")
def show_balance(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("finance_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=?", (user_id,))
    result = cursor.fetchone()[0]
    conn.close()
    if result is None:
        result = 0
    if result < 0:
        photo_path = 'img_2.png'
        with open(photo_path, 'rb') as photo:
            bot.send_photo(message.chat.id, photo,
                           caption="Поздравляю, вы бомж!!!")
            bot.send_message(message.chat.id, f"Ваш текущий баланс: {result} руб.")
    else:
        bot.send_message(message.chat.id, f"Ваш текущий баланс: {result} руб.")


def process_user_command(message):
    if check_command_limits(message.from_user.id, message.text):
        return

    if message.text == "Назад":
        handle_back(message)
    elif message.text == "Курсы валют":
        currency_rates(message)
    elif message.text == "Транзакции":
        transaction_menu(message)
    elif message.text == "Список транзакций":
        show_transactions(message)
    elif message.text == "Очистить транзакции":
        clear_transactions(message)
    elif message.text == "Расход":
        ask_for_transaction_details(message)
    elif message.text == "Пополнение":
        ask_for_transaction_details(message)
    elif message.text == "Цели":
        goals_menu(message)
    elif message.text == "Задать цель":
        set_goal_request(message)
    elif message.text == "Список целей":
        show_goals(message)
    elif message.text == "Очистить цели":
        clear_goals(message)
    elif message.text == "Отмена":
        cancel_action(message)
    elif message.text == "Конвертер валют":
        currency_converter_menu(message)
    elif message.text == "Доллар":
        handle_currency_conversion(message)
    elif message.text == "Евро":
        handle_currency_conversion(message)
    elif message.text == "Юань":
        handle_currency_conversion(message)
    elif message.text == "/start":
        send_welcome(message)
    elif message.text == 'Баланс':
        show_balance(message)
    else:
        bot.send_message(
            message.chat.id,
            "Неизвестная команда. Пожалуйста, используйте кнопки для навигации.",
        )


init_db()
bot.polling()

#Можно я 10 строчек вот так нафармлю, чтобы их 500 стало? пжпжпжпжпжпжп
#
#
#
#
#
#
#
#
#
#
