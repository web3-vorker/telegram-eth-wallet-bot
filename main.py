import logging
import asyncio
import time
import sqlite3
import requests
from connection import web3
from utils.config import MyUSDT_ABI
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.filters import CommandStart, Command
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from wallet import create_wallet, import_wallet, main_menu, wallet_menu, handle_new_block, get_eth_price, get_token_balance
from database import save_wallet, get_wallet_address, get_private_key, get_all_wallets
from transaction import receive_crypto, send_transaction_eth, send_transaction_usdt
from tokens import usdt_contract
from web3.exceptions import TransactionNotFound
import re
import threading
from dotenv import load_dotenv
import os

load_dotenv()  # Загружает переменные из .env



INFURA_API = os.getenv("INFURA_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")



bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


web3 = web3

if web3.is_connected():
  print('✅ Успешно подключено к Ethereum\n')
else:
  print('❌ Ошибка подключения')


user_wallet_addresses = {}


# Функция обработки команды /start
@dp.message(CommandStart())
async def start(message: Message):
    telegram_id = message.from_user.id
    
    conn = sqlite3.connect("wallets.db")
    cursor = conn.cursor()

    # Выполняем запрос, чтобы получить информацию по конкретному telegram_id
    cursor.execute("SELECT telegram_id, wallet_address FROM users WHERE telegram_id = ?", (telegram_id,))
    result = cursor.fetchone()
    conn.close()

    #Проверяем наличие адреса кошелька пользователя в списке адресов 
    wallet_address = await get_wallet_address(telegram_id)
    if wallet_address:
        user_wallet_addresses[wallet_address] = telegram_id
        await start_tracking(message)

    if result:
        main_menu_data = await main_menu()
        await message.answer(main_menu_data['message_text'], reply_markup=main_menu_data['keyboard'], parse_mode=ParseMode.MARKDOWN)

    else:
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text="👛 Создать", callback_data='create_wallet'),
            types.InlineKeyboardButton(text="🔗 Импортировать", callback_data='import_wallet')
        ]]
    )

        await message.answer("💰 Добро пожаловать в Wallet!\n\nОтправляй, получай, храни и обменивай криптовалюту в Wallet\n\nДля начала создай кошелек или импортируй существующий", reply_markup=keyboard)



@dp.message(Command('menu'))
async def Menu(message: Message):
    telegram_id = message.from_user.id

    wallet_address = await get_wallet_address(telegram_id)
    if wallet_address:
        user_wallet_addresses[wallet_address] = telegram_id
        await start_tracking(message)

    
    main_menu_data = await main_menu()
    await message.answer(main_menu_data['message_text'], reply_markup=main_menu_data['keyboard'], parse_mode=ParseMode.MARKDOWN)



@dp.message(Command('wallet'))
async def Wallet(message: Message):
    telegram_id = message.from_user.id

    wallet_address = await get_wallet_address(telegram_id)
    if wallet_address:
        user_wallet_addresses[wallet_address] = telegram_id
        await start_tracking(message)


    wallet_menu_data = await wallet_menu(telegram_id)
    await message.answer(wallet_menu_data['message_text'], reply_markup=wallet_menu_data['keyboard'], parse_mode=ParseMode.MARKDOWN)



class AuthState(StatesGroup):
    setting_password = State()
    waiting_for_password = State()
    import_wallet = State()
    setting_password_2 = State()
    waiting_for_password_2 = State()
    get_password_eth = State()
    get_password_usdt = State()
    get_transaction_data_eth = State()
    get_transaction_data_usdt = State()
    confirm_private_key_access = State()


@dp.callback_query()
async def callback_handler(callback: CallbackQuery, state: FSMContext):
    
    await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)

    if callback.data == 'create_wallet':
        msg = await callback.message.answer('🔐 Придумайте пароль для кошелька')
        await state.set_state(AuthState.setting_password)

        await state.update_data(last_bot_message_id=msg.message_id)


    elif callback.data == 'import_wallet': 
        msg = await callback.message.answer('🔑 Вставьте приватный ключ от кошелька')
        await state.set_state(AuthState.import_wallet)

        await state.update_data(last_bot_message_id=msg.message_id)


    elif callback.data == 'wallet':
        user_id = callback.from_user.id
        data = await wallet_menu(user_id)

        if data is None:
            await callback.message.answer("Кошелек не найден!")
        else:
            await callback.message.answer(data['message_text'], reply_markup=data['keyboard'], parse_mode=ParseMode.MARKDOWN)        


    elif callback.data == 'back_main_menu':
        main_menu_data = await main_menu()
        await callback.message.answer(main_menu_data['message_text'], reply_markup=main_menu_data['keyboard'], parse_mode=ParseMode.MARKDOWN)


    elif callback.data == 'back_wallet_menu':
      user_id = callback.from_user.id
      menu_data = await wallet_menu(user_id)
      await callback.message.answer(menu_data['message_text'], reply_markup=menu_data['keyboard'], parse_mode=ParseMode.MARKDOWN)


    elif callback.data == 'update':
      user_id = callback.from_user.id
      menu_data = await wallet_menu(user_id)
      await callback.message.answer(menu_data['message_text'], reply_markup=menu_data['keyboard'], parse_mode=ParseMode.MARKDOWN)        


    elif callback.data == 'show_private_key':
        msg = await callback.message.answer("⚠️ Для просмотра приватного ключа необходимо подтвердить действие. Введите код-пароль:")
        await state.set_state(AuthState.confirm_private_key_access)
        await state.update_data(last_bot_message_id=msg.message_id)



    elif callback.data == 'receive_crypto':
        user_id = callback.from_user.id
        receive_data = await receive_crypto(user_id)
        await callback.message.answer(receive_data['message_text'], reply_markup=receive_data['keyboard'], parse_mode=ParseMode.MARKDOWN)


    elif callback.data == 'send_crypto':
        user_id = callback.from_user.id
        #Получаем балансы валют
        wallet_address = await get_wallet_address(user_id)
        eth_balance = web3.from_wei((web3.eth.get_balance(wallet_address)), 'ether')
        usdt_balance = await get_token_balance(usdt_contract, wallet_address)


        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="ETH", callback_data='eth')],
            [types.InlineKeyboardButton(text="USDT", callback_data='usdt')],
            [types.InlineKeyboardButton(text="< Назад", callback_data="back_wallet_menu")]
            ])
        
        msg = await callback.message.answer("🔸 *Выберите криптовалюту для отправки* 🔸\n\n"
    "💰 *Доступные варианты:* \n\n"
    "━━━━━━━━━━━━━━━━━\n"
    f"⚪ *Ethereum (ETH)*:\n   `{eth_balance}`\n"
    f"💵 *Tether (USDT)*:\n    `{usdt_balance}`\n\n"
    "━━━━━━━━━━━━━━━━━\n"
    "⬇️ Нажмите на нужную валюту ниже ⬇️", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        
        await state.update_data(last_bot_message_id=msg.message_id)
        


    elif callback.data == 'show_qr':
        user_id = callback.from_user.id
        receive_data = await receive_crypto(user_id)
        qr_code = receive_data['qr']

        markup = types.InlineKeyboardMarkup(inline_keyboard=[
           [types.InlineKeyboardButton(text="< Назад", callback_data="back_wallet_menu")]
        ])
        try:
            await callback.message.answer_photo(qr_code, caption='❗ Отправляйте по этому адресу только ETH и токены в сети Ethereum ❗', reply_markup=markup)
        except Exception as e:
            None
            await callback.message.answer("Ошибка при отправке QR-кода. Попробуйте позже.")


    elif callback.data == 'eth':
        msg = await callback.message.answer('🔐 Введите пароль для отправки транзакции')
        await state.set_state(AuthState.get_password_eth)
        await state.update_data(last_bot_message_id=msg.message_id)


    elif callback.data == 'usdt':
        msg = await callback.message.answer('🔐 Введите пароль для отправки транзакции')
        await state.set_state(AuthState.get_password_usdt)
        await state.update_data(last_bot_message_id=msg.message_id)


    elif callback.data == 'confirm_transaction_eth':
        user_data = await state.get_data()
        private_key = user_data.get('private_key')
        receiver = user_data.get('receiver')
        value_eth = user_data.get('value_eth')

        if not private_key or not receiver or not value_eth:
            await callback.message.answer("Ошибка: Не удалось получить данные транзакции. Попробуйте снова.")
            return
        
        waiting_message = await callback.message.answer("⏳ Ожидайте, транзакция в процессе...")

        transaction_data = await send_transaction_eth(private_key, receiver, value_eth)
        if "Error Address" in transaction_data:
            await callback.message.answer(f"❌ Ошибка: Неверный адрес кошелька. Попробуйте ввести снова")
            await state.set_state(AuthState.get_transaction_data_eth)
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="< Назад в меню", callback_data='back_wallet_menu')]
        ])
        
        await state.clear()
        await waiting_message.delete()        

        tx_link = f'<a href="https://sepolia.etherscan.io/tx/{transaction_data["tx_hash"]}">🔍 Проверить в Etherscan</a>'

        await callback.message.answer(
                f"✅ <b>Транзакция отправлена!</b>\n\n"
                f"🔹 <b>Сумма:</b> {value_eth} ETH\n"
                f"🔸 <b>Получатель:\n</b> <code>{receiver}</code>\n"
                f"⛽ <b>Комиссия:</b> {transaction_data['transaction_fee']} ETH\n\n"
                f"{tx_link}\n\n"
                f"💼 <b>Новый баланс:</b> {transaction_data['new_balance_eth']:.4f} ETH ", reply_markup=keyboard, parse_mode=ParseMode.HTML)



    elif callback.data == 'confirm_transaction_usdt':
        user_data = await state.get_data()
        private_key = user_data.get('private_key')
        receiver = user_data.get('receiver')
        value_usdt = user_data.get('value_usdt')

        if not private_key or not receiver or not value_usdt:
            await callback.message.answer("Ошибка: Не удалось получить данные транзакции. Попробуйте снова.")
            return
        
        waiting_message = await callback.message.answer("⏳ Ожидайте, транзакция в процессе...")

        transaction_data = await send_transaction_usdt(private_key, receiver, value_usdt)
        if not transaction_data or "error" in transaction_data:
            await callback.message.answer("❌ Ошибка при отправке USDT. Подробнее в логах сервера.")
            await state.clear()
            return

        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="< Назад в меню", callback_data='back_wallet_menu')]
        ])
        
        await state.clear()
        await waiting_message.delete()        

        tx_link = f'<a href="https://sepolia.etherscan.io/tx/{transaction_data["tx_hash"]}">🔍 Проверить в Etherscan</a>'

        await callback.message.answer(
                f"✅ <b>Транзакция отправлена!</b>\n\n"
                f"🔹 <b>Сумма:</b> {value_usdt} USDT\n"
                f"🔸 <b>Получатель:\n</b> <code>{receiver}</code>\n"
                f"⛽ <b>Комиссия:</b> {transaction_data['transaction_fee']} ETH\n\n"
                f"{tx_link}\n\n"
                f"💼 <b>Новый баланс:</b> {transaction_data['new_balance_token']:.2f} USDT ", reply_markup=keyboard, parse_mode=ParseMode.HTML)



@dp.message(AuthState.import_wallet)
async def get_user_private_key(message: Message, state: FSMContext):
    user_data = await state.get_data()

    # Удаляем предыдущее сообщение бота
    if "last_bot_message_id" in user_data:
        await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])

    # Удаляем сообщение пользователя с приватным ключом
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)


    private_key = message.text[2:] if message.text.startswith('0x') else message.text
    if not private_key or not (len(private_key) == 64):
        await message.answer('❗ Неверный приватный ключ. Проверьте приватный ключ на корректность')
        await state.set_state(AuthState.import_wallet)
        return

    await state.update_data(private_key=private_key)
    msg = await message.answer('🔐 Придумайте пароль для кошелька (не менее 5 символов)')

    await state.update_data(last_bot_message_id=msg.message_id)    
    await state.set_state(AuthState.setting_password_2)



@dp.message(AuthState.setting_password)
async def set_password(message: Message, state: FSMContext):

    user_data = await state.get_data()

    # Удаляем предыдущее сообщение бота
    if "last_bot_message_id" in user_data:
        await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])

    # Удаляем сообщение пользователя с приватным ключом
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)


    password = message.text.strip()
    if len(password) < 5:
        msg = await message.answer('⚠ Пароль должен содержать не менее 5 символов ⚠')
        await state.update_data(last_bot_message_id=msg.message_id)
        await state.set_state(AuthState.setting_password)
        return


    await state.update_data(password=password)  # Сохраняем пароль в состоянии
    msg = await message.answer('🔐 Подтвердите пароль для кошелька')

    await state.update_data(last_bot_message_id=msg.message_id)
    await state.set_state(AuthState.waiting_for_password)



@dp.message(AuthState.setting_password_2)
async def set_password(message: Message, state: FSMContext):
    user_data = await state.get_data()

    # Удаляем предыдущее сообщение бота
    if "last_bot_message_id" in user_data:
        await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])

    # Удаляем сообщение пользователя
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    

    password = message.text.strip()
    if len(password) < 5:
        msg = await message.answer('⚠ Пароль должен содержать не менее 5 символов ⚠')
        await state.update_data(last_bot_message_id=msg.message_id)
        await state.set_state(AuthState.setting_password)
        return

    await state.update_data(password=password)  # Сохраняем пароль в состоянии
    msg = await message.answer('🔐 Подтвердите пароль для кошелька')
    await state.update_data(last_bot_message_id=msg.message_id)
    await state.set_state(AuthState.waiting_for_password_2)


@dp.message(AuthState.waiting_for_password)
async def confirm_password(message: Message, state: FSMContext):
    user_data = await state.get_data()

    # Удаляем предыдущее сообщение бота
    if "last_bot_message_id" in user_data:
        await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])

    # Удаляем сообщение пользователя
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    # Получаем пароль из состояния
    user_data = await state.get_data()
    password = user_data.get('password')
    
    # Проверяем, что пароли совпадают
    if message.text.strip() == password:
        telegram_id = message.from_user.id
        # Если пароли совпали, создаем кошелек
        new_wallet = await create_wallet(message, password)
        await save_wallet(telegram_id, new_wallet[1], password)
        wallet_address = await get_wallet_address(telegram_id)
        user_wallet_addresses[wallet_address] = telegram_id
        await start_tracking(message)


        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text='Открыть кошелек', callback_data='wallet')]
        ])

        await message.answer(f"✅ *Кошелек создан!*\n\n💳 *Ваш адрес:* `{new_wallet[0]}`\n\n⚠️ **Важно:** сохраните пароль, без него доступ к кошельку будет потерян!", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

        await state.clear()  # Очищаем состояние
    else:
        msg = await message.answer("❌ Пароли не совпадают. Пожалуйста, попробуйте еще раз.")
        await state.set_state(AuthState.waiting_for_password)  # Если пароли не совпали, снова просим ввести пароль
        await state.update_data(last_bot_message_id=msg.message_id)



@dp.message(AuthState.waiting_for_password_2)
async def confirm_password(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    user_data = await state.get_data()

    # Удаляем предыдущее сообщение бота
    if "last_bot_message_id" in user_data:
        await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])

    # Удаляем сообщение пользователя с приватным ключом
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)    
    
    # Получаем пароль из состояния
    user_data = await state.get_data()
    password = user_data.get('password')

    user_data = await state.get_data()
    private_key = user_data.get('private_key')
    wallet_address = import_wallet(private_key)

    if message.text.strip() == password:

        await save_wallet(telegram_id, private_key, password)
        user_wallet_addresses[wallet_address[0]] = telegram_id
        await start_tracking(message)

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text='Открыть кошелек', callback_data='wallet')]
        ])
        
        await message.answer(f"✅ *Кошелек импортирован!*\n\n💳 *Ваш адрес:* `{wallet_address[0]}`\n\n⚠️ **Важно:** сохраните пароль, без него доступ к кошельку будет потерян!", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
              
        await state.clear()  # Очищаем состояние  
    else:
        msg = await message.answer("❌ Пароли не совпадают. Пожалуйста, попробуйте еще раз.")
        await state.set_state(AuthState.waiting_for_password_2)  # Если пароли не совпали, снова просим ввести пароль
        await state.update_data(last_bot_message_id=msg.message_id)



async def get_password(message: Message, state: FSMContext):
    user_data = await state.get_data()
    user_id = message.from_user.id
    password = message.text.strip()

    if "last_bot_message_id" in user_data:
        await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])
    # Удаляем сообщение пользователя с паролем
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    private_key = await get_private_key(telegram_id=user_id, password=password)

    if not private_key:
        msg = await message.answer("❌ Неверный пароль. Попробуйте еще раз.")
        await state.update_data(last_bot_message_id=msg.message_id)
        await state.set_state(AuthState.get_password_eth)
        return
        

    await state.update_data(private_key=private_key)  # Сохраняем пароль в состоянии
    msg = await message.answer("*Введите адрес кошелька и количество валюты для отправки*\n\n" \
    "*Пример*: `Адрес`, `сумма (0.1)`", parse_mode=ParseMode.MARKDOWN)

    await state.update_data(last_bot_message_id=msg.message_id)
    await state.set_state(AuthState.get_transaction_data_eth) 
    private_key = await get_private_key


@dp.message(AuthState.get_password_eth)
async def get_password_eth(message: Message, state: FSMContext):
    user_data = await state.get_data()
    user_id = message.from_user.id
    password = message.text.strip()

    if "last_bot_message_id" in user_data:
        await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])
    # Удаляем сообщение пользователя 
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    private_key = await get_private_key(telegram_id=user_id, password=password)
    if private_key is None:
        msg = await message.answer("❌ Неверный пароль. Попробуйте еще раз.")
        await state.update_data(last_bot_message_id=msg.message_id)
        await state.set_state(AuthState.get_password_eth)
        return
    
    await state.update_data(private_key=private_key)  # Сохраняем приватный ключ в состоянии
    msg = await message.answer("*Введите адрес кошелька и количество валюты для отправки*\n\n" \
    "*Пример*: `Адрес`, `сумма (0.1)`", parse_mode=ParseMode.MARKDOWN)
    
    await state.update_data(last_bot_message_id=msg.message_id)
    await state.set_state(AuthState.get_transaction_data_eth)


@dp.message(AuthState.get_password_usdt)
async def get_password_usdt(message: Message, state: FSMContext):
    user_data = await state.get_data()
    user_id = message.from_user.id
    password = message.text.strip()

    if "last_bot_message_id" in user_data:
        await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])
    # Удаляем сообщение пользователя 
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    private_key = await get_private_key(telegram_id=user_id, password=password)
    if private_key is None:
        msg = await message.answer("❌ Неверный пароль. Попробуйте еще раз.")
        await state.update_data(last_bot_message_id=msg.message_id)
        await state.set_state(AuthState.get_password_usdt)
        return
    
    await state.update_data(private_key=private_key)  # Сохраняем приватный ключ в состоянии
    msg = await message.answer("*Введите адрес кошелька и количество валюты для отправки*\n\n" \
    "*Пример*: `Адрес`, `сумма (100)`", parse_mode=ParseMode.MARKDOWN)
    
    await state.update_data(last_bot_message_id=msg.message_id)
    await state.set_state(AuthState.get_transaction_data_usdt)


@dp.message(AuthState.get_transaction_data_eth)
async def get_transaction_data_eth(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = await state.get_data()
    transaction_data = message.text.strip()
    private_key = user_data.get('private_key')
    wallet_sender =  web3.to_checksum_address(await get_wallet_address(user_id))
    wallet_sender_balance = web3.from_wei(web3.eth.get_balance(wallet_sender), 'ether')


    if "last_bot_message_id" in user_data:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])
        except Exception as e: 
            None
        
        try:
            # Удаляем сообщение пользователя 
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception as e: 
            None
    

    # Регулярное выражение для поиска Ethereum-адреса и числа
    pattern = r"(\b0x[a-fA-F0-9]{40}\b),\s*([0-9]+(?:\.[0-9]+)?)"

    # Ищем совпадения
    match = re.match(pattern, transaction_data)

    if match:
        try:
            # Получаем адрес кошелька и количество эфира
            receiver = web3.to_checksum_address(match.group(1))
        except ValueError:
            msg = await message.answer("⚠ Неверный адрес кошелька! Перепроверьте и введите заново")
            await state.update_data(last_bot_message_id=msg.message_id)
            await state.set_state(AuthState.get_transaction_data_eth)
            return    
        
        value_eth = match.group(2)

        if float(value_eth) > float(wallet_sender_balance):
            msg = await message.answer("❗ Недостаточно ETH на балансе для отправки ❗\n\n"
                                 
                                 f"💰 Ваш текущий баланс: `{wallet_sender_balance:.6f}` ETH\n"
                                 f"Попробуйте еще раз ввести данные для отправки", parse_mode=ParseMode.MARKDOWN)
            await state.update_data(last_bot_message_id=msg.message_id)
            await state.set_state(AuthState.get_transaction_data_eth)
            return

        if private_key is None:
            None
        sender_balance = web3.from_wei(web3.eth.get_balance(web3.eth.account.from_key(private_key).address), 'ether')

    else:
        msg = await message.answer("⚠ Неверный формат ввода!\nВведите в формате:\n`0xАдрес, сумма`", parse_mode="Markdown")
        await state.update_data(last_bot_message_id=msg.message_id)
        await state.set_state(AuthState.get_transaction_data_eth)
        return
    
    gas = 21000
    gasPrice = web3.eth.gas_price
    transaction_fee = web3.from_wei(gas * gasPrice, 'ether')

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [types.InlineKeyboardButton(text="✔ Подтвердить отправку", callback_data="confirm_transaction_eth")], 
    [types.InlineKeyboardButton(text="< Назад", callback_data="back_wallet_menu")]
  ])
    
    await message.answer(    "📤 *Детали транзакции* 📤\n\n"
    f"🔹 *Отправка:* `{value_eth} ETH`\n"
    f"🔸 *Получатель:* \n`{receiver}`\n"
    f"⚡ *Сеть:* *Ethereum (ERC-20)*\n"
    f"⛽ *Комиссия (Gas):* `{transaction_fee} ETH`\n\n"
    "✅ *Проверьте данные перед подтверждением!*\n"
    "🔽 Нажмите «Подтвердить» для отправки: 🔽", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    await state.update_data(receiver=receiver, value_eth=value_eth)  
    return private_key, receiver, value_eth
    

@dp.message(AuthState.get_transaction_data_usdt)
async def get_transaction_data_usdt(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = await state.get_data()
    transaction_data = message.text.strip()
    private_key = user_data.get('private_key')
    token_decimals = usdt_contract.functions.decimals().call()
    wallet_sender =  web3.to_checksum_address(await get_wallet_address(user_id))
    wallet_sender_balance = (usdt_contract.functions.balanceOf(wallet_sender).call()) / 10 ** token_decimals


    if "last_bot_message_id" in user_data:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])
        except Exception as e: 
            None
        
        try:
            # Удаляем сообщение пользователя 
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception as e: 
            None
    

    # Регулярное выражение для поиска Ethereum-адреса и числа
    pattern = r"(\b0x[a-fA-F0-9]{40}\b),\s*([0-9]+(?:\.[0-9]+)?)"

    # Ищем совпадения
    match = re.match(pattern, transaction_data)

    if match:
        try:
            # Получаем адрес кошелька и количество USDT
            receiver = web3.to_checksum_address(match.group(1))
        except ValueError:
            msg = await message.answer("⚠ Неверный адрес кошелька! Перепроверьте и введите заново")
            await state.update_data(last_bot_message_id=msg.message_id)
            await state.set_state(AuthState.get_transaction_data_usdt)
            return    
        
        value_usdt = match.group(2)

        if float(value_usdt) > float(wallet_sender_balance):
            msg = await message.answer("❗ Недостаточно USDT на балансе для отправки ❗\n\n"
                                 
                                 f"💰 Ваш текущий баланс: `{wallet_sender_balance:.6f}` ETH\n"
                                 f"Попробуйте еще раз ввести данные для отправки", parse_mode=ParseMode.MARKDOWN)
            await state.update_data(last_bot_message_id=msg.message_id)
            await state.set_state(AuthState.get_transaction_data_usdt)
            return

        if private_key is None:
            None

    else:
        msg = await message.answer("⚠ Неверный формат ввода!\nВведите в формате:\n`0xАдрес, сумма`", parse_mode="Markdown")
        await state.update_data(last_bot_message_id=msg.message_id)
        await state.set_state(AuthState.get_transaction_data_usdt)
        return


    gas = 70000
    gasPrice = web3.eth.gas_price
    transaction_fee = web3.from_wei(gas * gasPrice, 'ether')


    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [types.InlineKeyboardButton(text="✔ Подтвердить отправку", callback_data="confirm_transaction_usdt")], 
    [types.InlineKeyboardButton(text="< Назад", callback_data="back_wallet_menu")]
  ])
    
    await message.answer(    "📤 *Детали транзакции* 📤\n\n"
    f"🔹 *Отправка:* `{value_usdt} USDT`\n"
    f"🔸 *Получатель:* \n`{receiver}`\n"
    f"⚡ *Сеть:* *Ethereum (ERC-20)*\n"
    f"⛽ *Комиссия (Gas):* `{transaction_fee} ETH`\n\n"
    "✅ *Проверьте данные перед подтверждением!*\n"
    "🔽 Нажмите «Подтвердить» для отправки: 🔽", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    await state.update_data(receiver=receiver, value_usdt=value_usdt)  
    return private_key, receiver, value_usdt



@dp.message(AuthState.confirm_private_key_access)
async def show_private_key(message: Message, state: FSMContext):
    user_data = await state.get_data()
    user_id = message.from_user.id
    password = message.text.strip()

    if "last_bot_message_id" in user_data:
        await bot.delete_message(chat_id=message.chat.id, message_id=user_data["last_bot_message_id"])
    # Удаляем сообщение пользователя 
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    private_key = await get_private_key(telegram_id=user_id, password=password)
    if private_key is None:
        msg = await message.answer("❌ Неверный пароль. Попробуйте еще раз.")
        await state.update_data(last_bot_message_id=msg.message_id)
        await state.set_state(AuthState.confirm_private_key_access)
        await state.clear()
        private_key = await get_private_key
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='< Назад', callback_data='back_wallet_menu')]
    ])

    msg = await message.answer(f"🔐 *Ваш приватный ключ:*\n`{private_key}`\n\n⚠️ *Никогда не делитесь этим ключом ни с кем. Он даёт полный доступ к вашему кошельку. Мы **не рекомендуем** просматривать его без острой необходимости*", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    await state.update_data(last_bot_message_id=msg.message_id)



async def handle_incoming_transaction(user_id, tx_data, wallet_address):
    if not tx_data:
        return  # ничего не пришло
    
    # Если транзакция это объект, а не вложенный словарь с ключом 'tx', работаем с ним напрямую
    if isinstance(tx_data, dict) and 'tx' in tx_data:
        tx = tx_data['tx']
    else:
        # Если 'tx' нет, значит, это просто данные транзакции
        tx = tx_data

    tx_hash = web3.to_hex(tx.hash)
    msg = ''  # Инициализация переменной для сообщения

    # Проверка на наличие события (например, для USDT)
    if "event" in tx_data:  # USDT-транзакция
        event = tx_data['event']
        value = int(event['value']) / 10**18  # предполагаем, что это USDT (6 знаков после запятой)
        sender = event['from']

        msg = (
            f"💸 <b>Получено USDT!</b>\n\n"
            f"🔹 <b>Сумма:</b> {value:.2f} USDT\n"
            f"👤 <b>Отправитель:</b> <code>{sender}</code>\n"
            f"<a href='https://etherscan.io/tx/{tx_hash}'>🔍 Проверить в Etherscan</a>"
        )
    elif tx.get("value", 0) > 0:  # ETH-транзакция (проверка на значение 'value')
        eth_price = await get_eth_price()
        receive_value = web3.from_wei(tx.value, 'ether')
        receive_value_usd = float(receive_value) * eth_price

        msg = (
            f"💰 <b>Монеты успешно получены!</b>\n\n"
            f"Вы получили <b>{receive_value:.6f} ETH</b> (${receive_value_usd:.2f})\n"
            f"👤 От: <code>{tx['from']}</code>\n"
            f"<a href='https://etherscan.io/tx/{tx_hash}'>🔍 Проверить в Etherscan</a>"
        )
    else:
        msg = (
            f"⚠️ <b>Неизвестная транзакция!</b>\n\n"
            f"Не удалось распознать тип транзакции для адреса: <code>{tx['from']}</code>\n"
            f"🔹 <b>Хэш транзакции:</b> <code>{tx_hash}</code>\n"
            f"<a href='https://etherscan.io/tx/{tx_hash}'>🔍 Проверить в Etherscan</a>"
        )

    # Отправка сообщения
    await bot.send_message(user_id, msg, parse_mode=ParseMode.HTML)





async def track_wallet(message: Message, user_id, wallet_address):
    # Добавляем кошелек в словарь
    user_wallet_addresses[wallet_address] = user_id

    # Подписываемся на новые блоки
    last_block = web3.eth.block_number

    # Запуск бесконечного цикла, чтобы WebSocket оставался активным
    while True:
        try:
            current_block = web3.eth.block_number
            current_block_hash = web3.eth.get_block(current_block)['hash']
            if current_block > last_block:
                block_data = await handle_new_block(user_id, current_block_hash, wallet_address)
                last_block = current_block

                if block_data:
                    tx = block_data.get('tx')  # Получаем транзакцию
                    if tx:
                        await handle_incoming_transaction(user_id, block_data, wallet_address)  # Передаем block_data
                    else:
                        None
                
        except TransactionNotFound as e:
            None
        await asyncio.sleep(5)



async def start_tracking(message: Message):
    user_id = message.from_user.id
    wallet_address = await get_wallet_address(user_id)

    if wallet_address not in user_wallet_addresses:
        user_wallet_addresses[wallet_address] = user_id
    asyncio.create_task(track_wallet(message, user_id, wallet_address))
    


async def main():   
    print('✅ Бот запущен!')
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
