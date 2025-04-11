from web3 import Web3
from dotenv import load_dotenv
import os

load_dotenv()  # Загружает переменные из .env


INFURA_API = os.getenv("INFURA_API_KEY")
INFURA_URL = f"wss://mainnet.infura.io/ws/v3/{INFURA_API}"

web3 = Web3(Web3.LegacyWebSocketProvider(INFURA_URL))
