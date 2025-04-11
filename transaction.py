import asyncio
import qrcode
import time
import requests
from io import BytesIO
from aiogram import types
from aiogram.types import Message, FSInputFile
from connection import web3
from database import get_wallet_address
from wallet import get_eth_price, get_token_balance
from tokens import usdt_contract
from decimal import Decimal



async def receive_crypto(user_id):
  telegram_id = user_id
  wallet_address = await get_wallet_address(telegram_id)

  if wallet_address is None:
    return '🚫 Адрес кошелька не найден!' 

  qr = qrcode.make(wallet_address)
  qr.save("qr_code.png")
  
  try:
    qr_code = FSInputFile("qr_code.png")
  except Exception as e:
    None
  network = 'Ethereum' 
  min_deposit = 0.001

  keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [types.InlineKeyboardButton(text="📷 QR-код", callback_data="show_qr"),
     types.InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=wallet_address)], 
    [types.InlineKeyboardButton(text="< Назад", callback_data="back_wallet_menu")]
  ])

  message_text = (
        "*📥 Пополнение кошелька*\n\n"
        "*🔗 Сеть:* `{}`\n\n"
        "*💳 Адрес для пополнения:*\n"
        "`{}`   (Нажмите, чтобы скопировать)\n\n"
        "*⚠️ Минимальная сумма пополнения:* `{:.4f}` ETH\n\n"
        "⏳ Зачисление может занять до *10-15 минут*, в зависимости от загруженности сети.\n\n"
        "Вы можете *скопировать адрес* или воспользоваться *QR-кодом* для быстрого перевода.\n\n"
        "❗❗ *Внимание!* Отправляйте на этот адрес только *ETH* или токены стандарта ERC-20 в сети Ethereum. Все остальные активы, отправленные на этот адрес, будут утеряны ❗❗"
    ).format(network, wallet_address, min_deposit)


  return {'message_text': message_text, 'qr': qr_code, 'keyboard': keyboard}


async def send_transaction_eth(private_key, receiver, value_eth):

    wallet_sender = web3.eth.account.from_key(private_key).address
    wallet_sender_balance = web3.from_wei((web3.eth.get_balance(wallet_sender)), 'ether')


    value = web3.to_wei(value_eth, 'ether')
    nonce = web3.eth.get_transaction_count(wallet_sender)
    gas = 21000
    gasPrice = web3.eth.gas_price
    transaction_fee = web3.from_wei((gas * gasPrice), 'ether')

      #Создание транзакции 
    tx = {
          'nonce' : nonce,
          'to' : receiver,
          'value' : value,
          'gas' : gas,
          'gasPrice' : gasPrice
        }

      #Подписание транзакции
    signed_tx = web3.eth.account.sign_transaction(tx, private_key)

      # Очистка приватного ключа после использования
    private_key = None
    del private_key

      #Получение хэша транзакции
    send_tx = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash = web3.to_hex(send_tx)
    value_eth = value / 10**18
      
    try:
      eth_price = await get_eth_price()
    except requests.exceptions.RequestException as e:
      None
    return await wait_for_transaction_receipt(tx_hash, wallet_sender, eth_price, transaction_fee)



async def send_transaction_usdt(private_key, receiver, value_usdt):

    wallet_sender = web3.eth.account.from_key(private_key).address
    wallet_sender_balance = await get_token_balance(usdt_contract, wallet_sender)


    token_decimals = int(usdt_contract.functions.decimals().call())
    value = int(Decimal(str(value_usdt)) * Decimal(10) ** token_decimals)
    nonce = web3.eth.get_transaction_count(wallet_sender)
    gas = 70000
    gasPrice = web3.eth.gas_price
    transaction_fee = web3.from_wei((gas * gasPrice), 'ether')

      #Создание транзакции 
    tx = usdt_contract.functions.transfer(
       receiver,
       value
    ).build_transaction({
          'from' : wallet_sender,
          'gas' : gas,
          'gasPrice' : gasPrice,
          'nonce' : nonce
      })

      #Подписание транзакции
    signed_tx = web3.eth.account.sign_transaction(tx, private_key)

      # Очистка приватного ключа после использования
    private_key = None
    del private_key

      #Получение хэша транзакции
    send_tx = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash = web3.to_hex(send_tx)
    try:
      eth_price = await get_eth_price()
    except requests.exceptions.RequestException as e:
      None

    return await wait_for_transaction_receipt(tx_hash, wallet_sender, eth_price, transaction_fee)



      #Запускаем отслеживание статуса транзакции
async def wait_for_transaction_receipt(tx_hash, wallet_sender, eth_price, transaction_fee):
      while True:    
        try:
          tx_data = web3.eth.get_transaction_receipt(tx_hash)
          
          if tx_data:
            tx_status = tx_data['status']    
            
            if tx_status == 1:
              new_balance_eth = web3.from_wei(web3.eth.get_balance(wallet_sender), 'ether')
              new_balance_token = await get_token_balance(usdt_contract, wallet_sender)
                
              return {"tx_hash": tx_hash, "transaction_fee": transaction_fee, "new_balance_eth": new_balance_eth, "new_balance_token": new_balance_token}

          
            else:
              None
              break           

        except Exception as e:
          None
          await asyncio.sleep(5)
