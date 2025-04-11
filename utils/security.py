from Crypto.Cipher import AES
import base64
import os

def generate_salt():
    return base64.b64encode(os.urandom(16)).decode()  # Создаем случайную соль

def encrypt_private_key(private_key: str, password: str, salt: str) -> str:
    key = (password + salt).ljust(32).encode()[:32]  # Генерируем ключ фиксированной длины
    cipher = AES.new(key, AES.MODE_GCM)
    encrypted_data, tag = cipher.encrypt_and_digest(private_key.encode())
    return base64.b64encode(cipher.nonce + tag + encrypted_data).decode()

def decrypt_private_key(encrypted_data: str, password: str, salt: str) -> str:
    data = base64.b64decode(encrypted_data)
    nonce, tag, encrypted_private_key = data[:16], data[16:32], data[32:]
    key = (password + salt).ljust(32).encode()[:32]
    cipher = AES.new(key, AES.MODE_GCM, nonce)
    return cipher.decrypt_and_verify(encrypted_private_key, tag).decode()
