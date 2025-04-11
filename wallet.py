from aiogram import types
from aiogram.types import Message
from web3._utils.events import get_event_data
from connection import web3
from tokens import usdt_contract, usdt_address
from database import save_wallet, get_wallet_address
from decimal import Decimal
import requests
import asyncio
import aiohttp
import time



async def create_wallet(message: Message, password):
  """Создание нового кошелька."""
  new_account = web3.eth.account.create()
  await save_wallet(message.from_user.id, web3.to_hex(new_account.key), password)
  account_details = [new_account.address, web3.to_hex(new_account.key)]
  return account_details



def import_wallet(private_key):
  """Импорт кошелька по приватному ключу."""
  try:
    account = web3.eth.account.from_key(private_key)
    return [account.address, web3.to_hex(account.key)]
  except Exception as e:
        raise ValueError("Некорректный приватный ключ")  # Исключение, если приватный ключ неверный
  


async def main_menu():
  """Главное меню"""
  keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="👛 Мой Кошелек", callback_data="wallet")]
    ])
  
  message_text = ("👋 *Добро пожаловать в Ethereum Wallet!*\n\n"
        " Это ваш универсальный крипто-помощник.\n"
        "Здесь вы можете управлять кошельком, обменивать и хранить валюту.\n\n"
        "Выберите, действие 👇")
  return {'message_text': message_text, 'keyboard': keyboard}

_eth_price_cache = {
    "price": None,
    "timestamp": 0
}

async def get_eth_price():
    """Получение курса Ethereum (ETH) к USD"""

    cache_duration = 60  # секунд
    # Если прошло меньше 60 сек с последнего запроса — возвращаем кэш
    if _eth_price_cache["price"] is not None and time.time() - _eth_price_cache["timestamp"] < cache_duration:
        return _eth_price_cache["price"]
    

    url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            
            if response.status == 200:
              data = await response.json()
              eth_price = data.get("ethereum", {}).get("usd", 0.0)
              _eth_price_cache["price"] = eth_price
              _eth_price_cache["timestamp"] = time.time()
              return eth_price



    # Если произошла ошибка — возвращаем старый кэш, если он есть
    if _eth_price_cache["price"] is not None:
        return _eth_price_cache["price"]
        


#Получение баланса токенов ERC-20
async def get_token_balance(token_contract, wallet_address):
  token_decimals = float(token_contract.functions.decimals().call())
  token_balance = float(token_contract.functions.balanceOf(wallet_address).call()) / 10 ** token_decimals
  return token_balance  



#Баланс токена в USD
async def token_balance_in_usd(token_balance, token_price):
  return token_balance * token_price



async def wallet_menu(user_id):

  wallet_address = await get_wallet_address(telegram_id=user_id)

  """Меню кошелька"""
  keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
      [types.InlineKeyboardButton(text="💸 Отправить", callback_data="send_crypto"),
       types.InlineKeyboardButton(text="💰 Получить", callback_data="receive_crypto")],  
      [types.InlineKeyboardButton(text="📜 История транзакций", url=f'https://sepolia.etherscan.io/address/{wallet_address}#txns')],
      [types.InlineKeyboardButton(text="🔄 Обновить", callback_data="update")],
      [types.InlineKeyboardButton(text="🔑 Приватный ключ", callback_data="show_private_key")],
      [types.InlineKeyboardButton(text="< Назад", callback_data="back_main_menu")]
   ])

  #Получаем балансы для кошелька
  if wallet_address is None:
    return None

  try:
    eth_price_usd = await get_eth_price()
  except requests.exceptions.RequestException as e:
    None


  #Баланс кошелька ETH
  balance_eth = float(web3.from_wei(web3.eth.get_balance(wallet_address), 'ether')) #Баланс в ETH
  balance_eth_in_usd = await token_balance_in_usd(balance_eth, eth_price_usd)

  #Баланс кошелька USDT
  balance_usdt = await get_token_balance(usdt_contract, wallet_address)

  #Общий баланс в USD
  wallet_balance_usd = (balance_eth * eth_price_usd) + balance_usdt

  # Используем Markdown для форматирования текста
  message_text = (
        "👛 *Ваш кошелёк*\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"💵 *Баланс:* ~ `${wallet_balance_usd:.2f}` USD\n\n"
        "📦 *Активы:*\n"
        f"   • ETH:    `{balance_eth:.6f}`   (`$ {balance_eth_in_usd:.2f}`)\n"
        f"   • USDT:   `{balance_usdt:.2f}`\n"
        "━━━━━━━━━━━━━━━━━\n"
        "Выберите действие ниже ⬇️"
    )
  
  return {'message_text': message_text, 'keyboard': keyboard}




async def handle_new_block(user_id, block_hash, wallet_address):
    block = web3.eth.get_block(block_hash, full_transactions=True)

    for tx in block.transactions:
        # ETH-перевод
        if tx.to and web3.to_checksum_address(tx.to) == web3.to_checksum_address(wallet_address):
            return {"tx": tx}

        # Проверяем USDT (или другой ERC-20)
        if tx.to and tx.to.lower() == usdt_address.lower():
            try:
                receipt = web3.eth.get_transaction_receipt(tx.hash)
                for log in receipt.logs:
                    if log['address'].lower() == usdt_contract.address.lower():
                        event_abi = next(x for x in usdt_contract.abi if x.get("name") == "Transfer")
                        event_data = get_event_data(web3.codec, event_abi, log)
                        if event_data['args']['to'].lower() == wallet_address.lower():
                            return {"tx": tx, "event": event_data['args']}
            except Exception as e:
              None
    return None