🚀 Ethereum Telegram Wallet Bot
Telegram-бот, который позволяет пользователям безопасно создавать, импортировать, получать и отправлять Ethereum (ETH) и USDT прямо в Telegram.

🔐 Функциональность
👛 Создание и импорт кошельков

🔐 Хранение приватных ключей с шифрованием (AES + соль)

💸 Отправка и получение ETH и USDT (ERC-20)

📈 Получение актуального курса ETH

📥 Генерация QR-кода для адреса

🧾 Ссылки на транзакции в Etherscan

🔔 Автоматическое отслеживание входящих транзакций

## Установка

1. Клонируйте репозиторий:
`git clone https://github.com/your_username/ethereum-telegram-wallet-bot.git`
`cd ethereum-telegram-wallet-bot`

2. Установить зависимости

`pip install -r requirements.txt`

3. Настрой .env
   
Создай .env файл в корне проекта:

`INFURA_API_KEY=your_infura_project_id
BOT_TOKEN=your_telegram_bot_token`


4. Убедись, что у тебя есть файл ABI:

Помести ABI от USDT в файл usdt_abi.json в корень проекта:

`usdt_abi.json`

ABI можно получить на Etherscan в разделе "Contract" → "Contract ABI"

5. Запусти бота

`python main.py`


📁 Структура проекта

├── main.py                # Основной бот
├── wallet.py             # Логика кошелька
├── transaction.py        # Отправка/прием, QR
├── connection.py         # Web3 подключение
├── tokens.py             # Контракты
├── database.py           # SQLite и ключи
├── utils/
│   └── security.py       # Шифрование ключей
├── usdt_abi.json         # ABI контракта USDT
├── requirements.txt
└── .env


⚠️ Безопасность
Приватные ключи шифруются с помощью пароля пользователя.
Пароль не хранится в открытом виде.
Telegram ID используется как идентификатор.
Никогда не рассылайте свой приватный ключ!


📸 Примеры
Главное меню:
`👋 Добро пожаловать в Ethereum Wallet!
...`

QR-код и адрес:
`📥 Пополнение кошелька
💳 Адрес: 0x...`


📄 Лицензия
Этот проект распространяется под лицензией MIT. Свободен к использованию и модификации.

🤝 Автор
web3-vorker
