import sqlite3
from utils.security import generate_salt, encrypt_private_key, decrypt_private_key
from connection import web3


def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect("wallets.db")
    cursor = conn.cursor()
    # Создаем новую таблицу с добавленным столбцом wallet_address
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER UNIQUE,
                        wallet_address TEXT NOT NULL,
                        encrypted_private_key TEXT NOT NULL,
                        salt TEXT)''')
    conn.commit()
    conn.close()

# Инициализируем базу данных с новой таблицей
init_db()



def clear_database():
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users')
    conn.commit()
    conn.close()

# clear_database()



async def save_wallet(telegram_id: int, private_key: str, password: str) -> bool:
    """Сохранение кошелька пользователя (без перезаписи, если уже есть)"""
    try:
        conn = sqlite3.connect("wallets.db")
        cursor = conn.cursor()
        # Проверяем, есть ли уже кошелек у пользователя
        cursor.execute("SELECT 1 FROM users WHERE telegram_id = ?", (telegram_id,))
        if cursor.fetchone():  # Если нашли запись, возвращаем False (уже есть кошелек)
            return False  

        # Если кошелька нет, создаем его
        salt = generate_salt()
        encrypted_key = encrypt_private_key(private_key, password, salt)

        if private_key is None:
            raise ValueError("Ошибка: приватный ключ не найден!")
        wallet_address = web3.to_checksum_address(web3.eth.account.from_key(private_key).address)

        cursor.execute("""
            INSERT INTO users (telegram_id, wallet_address, encrypted_private_key, salt)
            VALUES (?, ?, ?, ?)
        """, (telegram_id, wallet_address, encrypted_key, salt))

        conn.commit()

    except sqlite3.DatabaseError as e:
        None
    except ValueError as e:
        None
    except Exception as e:
        None
    finally:
        conn.close()  # Закрываем соединение



async def get_wallet_address(telegram_id: int) -> str | None:
    try:
        """Получение публичного адреса пользователя"""
        conn = sqlite3.connect("wallets.db")
        cursor = conn.cursor()

        cursor.execute("SELECT wallet_address FROM users WHERE telegram_id = ?", (telegram_id,))
        result = cursor.fetchone()

        if result:
            wallet_address = result[0]   
            return result[0] if result else None


        conn.close()
    
    except sqlite3.DatabaseError as e:
        None
    finally:
        conn.close()



async def get_private_key(telegram_id: int, password: str) -> str | None:
    """Дешифровка приватного ключа (используется только при отправке транзакций)"""
    conn = sqlite3.connect("wallets.db")
    cursor = conn.cursor()

    cursor.execute("SELECT encrypted_private_key, salt FROM users WHERE telegram_id = ?", (telegram_id,))
    result = cursor.fetchone()
    
    conn.close()

    if result:
        encrypted_key, salt = result
        try:
            return decrypt_private_key(encrypted_key, password, salt)
        except:
            return None  # Неверный пароль

    return None  # Кошелек не найден



def get_all_wallets():
    conn = sqlite3.connect("wallets.db")
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id, wallet_address FROM users")
    result = cursor.fetchall()
    conn.close()
    return result
