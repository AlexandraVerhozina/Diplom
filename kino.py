from flask import Flask, render_template, request, redirect, session
from werkzeug.security import check_password_hash, generate_password_hash
import psycopg2
from psycopg2 import sql

app = Flask(__name__)
app.secret_key = '55555'


def dbConnect(): 
    conn = psycopg2.connect( 
        host="127.0.0.1", 
        database="kino", 
        user="aleksandra_kino", 
        password="12345"
    ) 
    return conn

def dbClose(cursor, connection): 
    cursor.close() 
    connection.close()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/movies', methods=['GET', 'POST'])
def movies():
    conn = dbConnect()
    cur = conn.cursor()

    # Получаем все фильмы из базы данных
    cur.execute("SELECT title, year, genre, tags FROM movies;")
    movies = cur.fetchall()

    # Получаем уникальные года, жанры и теги для фильтров
    cur.execute("SELECT DISTINCT year FROM movies;")
    years = [row[0] for row in cur.fetchall()]

    cur.execute("SELECT DISTINCT genre FROM movies;")
    genres = [row[0] for row in cur.fetchall()]

    cur.execute("SELECT DISTINCT unnest(tags) FROM movies;")
    tags = [row[0] for row in cur.fetchall()]

    # Фильтрация
    filtered_movies = movies
    if request.method == 'POST':
        selected_years = request.form.getlist('year')
        selected_genres = request.form.getlist('genre')
        selected_tags = request.form.getlist('tag')

        print("Selected Years:", selected_years)
        print("Movies:", [(movie[0], movie[1]) for movie in movies])  # Отладочная информация

        filtered_movies = [
            movie for movie in movies
            if (not selected_years or str(movie[1]) in selected_years) and
               (not selected_genres or movie[2] in selected_genres) and
               (not selected_tags or any(tag in selected_tags for tag in movie[3]))
        ]

    dbClose(cur, conn)
    return render_template('movies.html', movies=filtered_movies, years=years, genres=genres, tags=tags)


@app.route('/series')
def series():
    return render_template('series.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not (username and password):
            error = "Пожалуйста, заполните все поля"
            return render_template('login.html', error=error)

        conn = dbConnect()
        cur = conn.cursor()

        # Проверяем, существует ли пользователь
        cur.execute(sql.SQL("SELECT id, password FROM users WHERE username = %s;"), [username])
        result = cur.fetchone()

        if result is None:
            error = "Неправильный логин или пароль"
            dbClose(cur, conn)
            return render_template('login.html', error=error)
        
        userID, hashPassword = result
        if check_password_hash(hashPassword, password):
            session['id'] = userID
            session['username'] = username
            dbClose(cur, conn)
            return redirect("/")  # Перенаправление на главную страницу
        else:
            error = "Неправильный логин или пароль"
            dbClose(cur, conn)
            return render_template('login.html', error=error)

    # Если метод GET, просто отображаем страницу входа
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not (username and password):
            error = "Пожалуйста, заполните все поля"
            return render_template('register.html', error=error)

        hashPassword = generate_password_hash(password)

        conn = dbConnect()
        cur = conn.cursor()

        # Проверяем, существует ли пользователь
        cur.execute(sql.SQL("SELECT username FROM users WHERE username = %s;"), [username])
        if cur.fetchone() is not None:
            error = "Пользователь с данным именем уже существует"
            dbClose(cur, conn)
            return render_template('register.html', error=error)

        # Добавляем нового пользователя
        cur.execute(sql.SQL("INSERT INTO users (username, password) VALUES (%s, %s);"), [username, hashPassword])
        conn.commit()
        dbClose(cur, conn)

        return redirect("/login")  # Перенаправление на страницу входа

    return render_template('register.html')

if __name__ == '__main__':
    app.run(debug=True)
