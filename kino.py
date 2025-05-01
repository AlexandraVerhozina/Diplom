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
    sort_order = request.form.get('sort', 'desc')  # По умолчанию сортировка по убыванию
    search_query = request.form.get('search', '')  # Получаем запрос на поиск

    # Убедитесь, что значение сортировки безопасно
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'  # По умолчанию

    # Изменяем SQL-запрос для поиска по названию
    if search_query:
        cur.execute(f"SELECT title, year, genre, tags, rating FROM movies WHERE title ILIKE %s ORDER BY rating {sort_order}", ['%' + search_query + '%'])
    else:
        cur.execute(f"SELECT title, year, genre, tags, rating FROM movies ORDER BY rating {sort_order};")

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
    selected_years = request.form.getlist('year')
    selected_genres = request.form.getlist('genre')
    selected_tags = request.form.getlist('tag')

    if request.method == 'POST':
        filtered_movies = [
            movie for movie in movies
            if (not selected_years or str(movie[1]) in selected_years) and
               (not selected_genres or movie[2] in selected_genres) and
               (not selected_tags or any(tag in selected_tags for tag in movie[3]))
        ]

    dbClose(cur, conn)
    return render_template('movies.html', movies=filtered_movies, years=years, genres=genres, tags=tags,
                           selected_years=selected_years, selected_genres=selected_genres, selected_tags=selected_tags)


@app.route('/add_favorite/<string:title>')
def add_favorite(title):
    if 'id' not in session:  # Проверяем, авторизован ли пользователь
        return redirect('/login')  # Перенаправляем на страницу входа, если не авторизован

    conn = dbConnect()
    cur = conn.cursor()

    # Добавляем фильм в избранное
    cur.execute("UPDATE movies SET is_favorite = TRUE WHERE title = %s;", (title,))
    conn.commit()

    dbClose(cur, conn)
    return redirect('/movies')

@app.route('/mark_watched/<string:title>')
def mark_watched(title):
    conn = dbConnect()
    cur = conn.cursor()

    # Помечаем фильм как просмотренный
    cur.execute("UPDATE movies SET is_watched = TRUE WHERE title = %s;", (title,))
    conn.commit()

    dbClose(cur, conn)
    return redirect('/izbr')

@app.route('/remove_favorite/<string:title>')
def remove_favorite(title):
    conn = dbConnect()
    cur = conn.cursor()

    # Удаляем фильм из избранного
    cur.execute("UPDATE movies SET is_favorite = FALSE WHERE title = %s;", (title,))
    conn.commit()

    dbClose(cur, conn)
    return redirect('/izbr')

@app.route('/izbr', methods=['GET', 'POST'])
def izbr():
    conn = dbConnect()
    cur = conn.cursor()

    # Получаем избранные фильмы для текущего пользователя
    cur.execute("SELECT title, year, genre, tags, rating, description, is_watched FROM movies WHERE is_favorite = TRUE;")
    favorites = cur.fetchall()

    dbClose(cur, conn)
    return render_template('izbr.html', favorites=favorites)

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
            return redirect("/")  
        else:
            error = "Неправильный логин или пароль"
            dbClose(cur, conn)
            return render_template('login.html', error=error)

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

@app.route('/user', methods=['GET', 'POST'])
def user():
    if 'id' not in session:
        return redirect('/login')  # Перенаправляем на страницу входа, если не авторизован

    conn = dbConnect()
    cur = conn.cursor()

    # Получаем информацию о пользователе
    cur.execute("SELECT username,  preferred_genres FROM users WHERE id = %s;", (session['id'],))
    user = cur.fetchone()

    if request.method == 'POST':
        preferred_genres = request.form.getlist('genres')
        # Сохраняем предпочтительные жанры
        cur.execute("UPDATE users SET preferred_genres = %s WHERE id = %s;", (preferred_genres, session['id']))
        conn.commit()

    dbClose(cur, conn)

    return render_template('user.html', user=user)


@app.route('/logout')
def logout():
    session.pop('id', None)  # Удаляем пользователя из сессии
    session.pop('username', None)
    return redirect('/')  # Перенаправление на главную страницу

if __name__ == '__main__':
    app.run(debug=True)

