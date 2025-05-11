import psycopg2
from werkzeug.security import generate_password_hash

# Данные подключения (как в вашем приложении)
conn = psycopg2.connect(
    host="127.0.0.1",
    database="kino",
    user="aleksandra_kino",
    password="12345"
)

# Создаем администратора
username = "admin"
password = "123"  # Вы можете изменить этот пароль
hashed_password = generate_password_hash(password)

try:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (%s, %s, %s)",
            (username, hashed_password, True)
        )
        conn.commit()
    print(f"Администратор создан: {username}/{password}")
except psycopg2.IntegrityError:
    print("Пользователь 'admin' уже существует")
finally:
    conn.close()