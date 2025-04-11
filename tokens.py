from connection import web3
import json

token_addresses = {
   "USDT":  
          "0xdAC17F958D2ee523a2206206994597C13D831ec7"
}

# Загружаем ABI из файла
with open('usdt_abi.json') as f:
    usdt_abi = json.load(f)

usdt_address = web3.to_checksum_address(token_addresses["USDT"])
usdt_contract = web3.eth.contract(address=usdt_address, abi=usdt_abi)