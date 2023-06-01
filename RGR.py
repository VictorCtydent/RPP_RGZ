import requests
import json
import os
import threading
import numpy as np
import psycopg2 as pg
from datetime import date, timedelta

from aiogram import Bot, Dispatcher, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message

ALPHAVANTAGE_API_KEY = '1U1WM0T5XFIEOIPY'
# Токен бота
API_TOKEN = 'TELEGRAM_BOT_TOKEN'
# Таймер для перерасчета показателей акций (24 часа)
WAIT_TIME_SECONDS = 10
# Конфиг для локальной БД
conn = pg.connect(user='postgres', password='postgres', host='localhost', port='5432', database='RGR_10')
cursor = conn.cursor()


class Form(StatesGroup):
    save = State()
    show = State()


bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
bot = Bot(token=bot_token)
dp = Dispatcher(bot, storage=MemoryStorage())


# Раз в WAIT_TIME_SECONDS секунд пересчитываем показатели для всех бумаг
def periodically_recalculate_stocks():
    ticker = threading.Event()
    while not ticker.wait(WAIT_TIME_SECONDS):
        print("asd")
        recalculate_stocks()

# получаем информацию о ценной бумаге с помощью API
async def add_stock_bd(user_id, stock_name):
    data = get_values(stock_name)
    cursor.execute(
        f"""SELECT * FROM stock
        WHERE user_id = {user_id}
        AND stock_name = '{stock_name}'"""
    )
    users = cursor.fetchall()
    if len(users) == 0:
        cursor.execute(
            f"""INSERT INTO stock (user_id, stock_name,position_size)
             VALUES ({user_id}, '{stock_name}', '{data}')"""
        )
        conn.commit()
        return f'Ценная бумага {stock_name} добавлена к отслеживаемым'
    else:
        cursor.execute(
            f"""UPDATE stock
            SET position_size = '{data}'
            WHERE user_id = {user_id}
            AND stock_name = '{stock_name}'"""
        )
        conn.commit()
        return f'Ценная бумага {stock_name} обновлена'

# принимаеv название ценной бумаги
def get_stocks_by_name(name):
    cursor.execute(
        f"""SELECT stock_name, position_size FROM stock
        WHERE stock_name = '{name}'"""
    )
    stocks = cursor.fetchall()
    msg = ''
    for stock_name, position_size in stocks:
        if position_size == 'null':
            msg += f'Для ценной бумаги {stock_name} не найдено значений\n\n'
        else:
            msg += f'Акция {stock_name} имеет\n' \
                   f'Оптимальный размер позиции {position_size}\n\n'
    return msg

# пересчитываем размер позиции для всех ценных бумаг
def recalculate_stocks():
    cursor.execute(
        f"""SELECT * FROM stock """
    )
    stocks = cursor.fetchall()
    for _, user_id, stock_name, position_size in stocks:
        data = get_values(stock_name)
        cursor.execute(
            f"""UPDATE stock
            SET position_size = '{data}'
            WHERE user_id = {user_id} AND stock_name = '{stock_name}'"""
        )


@dp.message_handler(commands=['start'])
async def start_command(message: Message):
    kb = ReplyKeyboardMarkup(is_persistent=True, resize_keyboard=True, row_width=1)
    kb.add(KeyboardButton('/Add'))
    kb.add(KeyboardButton('/Show'))

    await message.answer(text='Добро пожаловать в чат бот!', reply_markup=kb)


@dp.message_handler(commands=['Add'])
async def add_stock(message: Message):
    await message.answer('Введите имя ценной бумаги')
    await Form.save.set()


@dp.message_handler(state=Form.save)
async def save_stock(message: Message, state: FSMContext):
    ide = message.from_id
    test = message.text
    msg = await add_stock_bd(ide, test)
    await message.answer(msg)
    await state.finish()


@dp.message_handler(commands=['Show'])
async def stock_get(message: Message):
    await message.answer('Введите название ценной валюты')
    await Form.show.set()


@dp.message_handler(state=Form.show)
async def save_stock(message: Message, state: FSMContext):
    msg = get_stocks_by_name(message.text)
    await message.answer(msg)
    await state.finish()


def fetch_data(company_symbol):
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={company_symbol}&apikey={ALPHAVANTAGE_API_KEY}"
    response = requests.get(url)
    return json.loads(response.text)


def get_values(company_symbol):
    data = fetch_data(company_symbol)

    # Если компания не найдена, возвращаем налы
    if data.get('Error Message'):
        return 'null'

    # Длина периода для рассчета среднего
    n = 30
    # Счетчик отступа дней от сегодня
    day_offset = 0
    # Здесь храним средние значения по периодам длиной n
    income = []
    val = []

    while day_offset < n:
        day = (date.today() - timedelta(days=day_offset)).isoformat()
        day_info = data['Time Series (Daily)'].get(day)
        day_offset += 1
        # Пропускаем день, если по нему нет данных
        if day_info is None:
            continue

        # Достаем значение ценности бумаги
        val.append(float(day_info['4. close']))
    print(val)
    for i in range(len(val)-1):
        res = (val[i] - val[i + 1]) / val[i + 1]
        income.append(res)
        i += 1
    res = np.std(income)
    result = 0.03 / (res - 0.05)

    return result


if __name__ == '__main__':
    thread = threading.Thread(target=periodically_recalculate_stocks)
    thread.start()
    executor.start_polling(dp, skip_updates=True)
