from flask import Flask, render_template, request, redirect, session, flash, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import psycopg2
from psycopg2 import sql
from datetime import datetime



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
def index():
    return redirect('/movies')

@app.route('/movies', methods=['GET', 'POST'])
def movies():
    conn = dbConnect()
    cur = conn.cursor()

    # Получаем параметры сортировки и поиска
    sort_order = request.form.get('sort', 'desc')
    search_query = request.form.get('search', '')

    # Безопасная проверка сортировки
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'

    # Основной запрос для фильмов
    query = """
    SELECT m.id, m.title, m.year, m.rating, m.description, 
           STRING_AGG(g.name, ', ') AS genres,
           STRING_AGG(c.name, ', ') AS countries,
           STRING_AGG(a.name, ', ') AS actors
    FROM movies m
    LEFT JOIN movie_genres mg ON m.id = mg.movie_id
    LEFT JOIN genres g ON mg.genre_id = g.id
    LEFT JOIN movie_countries mc ON m.id = mc.movie_id
    LEFT JOIN countries c ON mc.country_id = c.id
    LEFT JOIN movie_actors ma ON m.id = ma.movie_id
    LEFT JOIN actors a ON ma.actor_id = a.id
    """
    
    # Добавляем условие поиска
    if search_query:
        query += " WHERE m.title ILIKE %s"
        params = ['%' + search_query + '%']
    else:
        params = []
    
    query += " GROUP BY m.id, m.title, m.year, m.rating, m.description"
    query += f" ORDER BY m.rating {sort_order};"
    
    cur.execute(query, params)
    movies = cur.fetchall()

    # Получаем данные для фильтров
    cur.execute("SELECT DISTINCT year FROM movies ORDER BY year;")
    years = [row[0] for row in cur.fetchall()]

    cur.execute("SELECT id, name FROM genres ORDER BY name;")
    genres = cur.fetchall()

    cur.execute("SELECT id, name FROM countries ORDER BY name;")
    countries = cur.fetchall()

    cur.execute("SELECT id, name FROM actors ORDER BY name;")
    actors = cur.fetchall()

    # Применяем фильтры
    filtered_movies = movies
    selected_years = request.form.getlist('year')
    selected_genres = request.form.getlist('genre')
    selected_countries = request.form.getlist('country')

    if request.method == 'POST':
        filtered_movies = []
        for movie in movies:
            # Получаем жанры и страны для текущего фильма
            movie_genres = movie[5].split(', ') if movie[5] else []
            movie_countries = movie[6].split(', ') if movie[6] else []
            
            # Проверяем соответствие фильтров
            year_match = not selected_years or str(movie[2]) in selected_years
            genre_match = not selected_genres or any(g in movie_genres for g in selected_genres)
            country_match = not selected_countries or any(c in movie_countries for c in selected_countries)
            
            if year_match and genre_match and country_match:
                filtered_movies.append(movie)

    # Проверяем, есть ли у пользователя избранные фильмы
    favorites = []
    if 'id' in session:
        cur.execute("SELECT movie_id FROM favorites WHERE user_id = %s;", (session['id'],))
        favorites = [row[0] for row in cur.fetchall()]

    dbClose(cur, conn)
    return render_template('movies.html', 
                         movies=filtered_movies, 
                         years=years, 
                         genres=genres, 
                         countries=countries,
                         actors=actors,
                         selected_years=selected_years, 
                         selected_genres=selected_genres, 
                         selected_countries=selected_countries,
                         favorites=favorites)

@app.route('/add_favorite/<int:movie_id>')
def add_favorite(movie_id):
    if 'id' not in session:
        return redirect('/login')

    conn = dbConnect()
    cur = conn.cursor()

    try:
        cur.execute("INSERT INTO favorites (user_id, movie_id) VALUES (%s, %s);", 
                   (session['id'], movie_id))
        conn.commit()
        flash('Фильм добавлен в избранное', 'success')
    except psycopg2.IntegrityError:
        conn.rollback()
        flash('Этот фильм уже в избранном', 'warning')

    dbClose(cur, conn)
    return redirect(request.referrer or url_for('movies'))

@app.route('/remove_favorite/<int:movie_id>')
def remove_favorite(movie_id):
    if 'id' not in session:
        return redirect('/login')

    conn = dbConnect()
    cur = conn.cursor()

    cur.execute("DELETE FROM favorites WHERE user_id = %s AND movie_id = %s;", 
               (session['id'], movie_id))
    conn.commit()
    flash('Фильм удален из избранного', 'info')

    dbClose(cur, conn)
    return redirect(request.referrer or url_for('izbr'))

@app.route('/izbr')
def izbr():
    if 'id' not in session:
        return redirect('/login')

    conn = dbConnect()
    cur = conn.cursor()

    query = """
    SELECT m.id, m.title, m.year, m.rating, m.description, 
           STRING_AGG(g.name, ', ') AS genres,
           STRING_AGG(c.name, ', ') AS countries
    FROM movies m
    JOIN favorites f ON m.id = f.movie_id
    LEFT JOIN movie_genres mg ON m.id = mg.movie_id
    LEFT JOIN genres g ON mg.genre_id = g.id
    LEFT JOIN movie_countries mc ON m.id = mc.movie_id
    LEFT JOIN countries c ON mc.country_id = c.id
    WHERE f.user_id = %s
    GROUP BY m.id, m.title, m.year, m.rating, m.description
    ORDER BY m.title;
    """
    
    cur.execute(query, (session['id'],))
    favorites = cur.fetchall()

    dbClose(cur, conn)
    return render_template('izbr.html', favorites=favorites)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'id' in session:
        return redirect('/')

    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not (username and password):
            error = "Пожалуйста, заполните все поля"
            return render_template('login.html', error=error)

        conn = dbConnect()
        cur = conn.cursor()

        cur.execute("SELECT id, password, is_admin FROM users WHERE username = %s;", (username,))
        result = cur.fetchone()

        if result is None:
            error = "Неправильный логин или пароль"
        else:
            user_id, hash_password, is_admin = result
            if check_password_hash(hash_password, password):
                session['id'] = user_id
                session['username'] = username
                session['is_admin'] = is_admin
                dbClose(cur, conn)
                return redirect("/")
            else:
                error = "Неправильный логин или пароль"

        dbClose(cur, conn)

    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'id' in session:
        return redirect('/')

    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not (username and password ):
            error = "Пожалуйста, заполните все поля"
        else:
            conn = dbConnect()
            cur = conn.cursor()

            try:
                hash_password = generate_password_hash(password)
                cur.execute("INSERT INTO users (username, password) VALUES (%s, %s);", 
                           (username, hash_password))
                conn.commit()
                dbClose(cur, conn)
                flash('Регистрация успешна. Теперь вы можете войти.', 'success')
                return redirect('/login')
            except psycopg2.IntegrityError:
                error = "Пользователь с таким именем уже существует"
            finally:
                dbClose(cur, conn)

    return render_template('register.html', error=error)

@app.route('/user')
def user():
    if 'id' not in session:
        return redirect('/login')

    conn = dbConnect()
    cur = conn.cursor()

    cur.execute("SELECT username FROM users WHERE id = %s;", (session['id'],))
    user = cur.fetchone()

    dbClose(cur, conn)
    return render_template('user.html', user=user)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# Админские функции
@app.route('/admin/add_movie', methods=['GET', 'POST'])
def add_movie():
    if 'id' not in session or not session.get('is_admin'):
        return redirect('/login')

    conn = dbConnect()
    cur = conn.cursor()

    # Инициализация переменных
    existing_genres = []
    existing_countries = []
    existing_actors = []

    try:
        # Получаем существующие данные
        cur.execute("SELECT id, name FROM genres ORDER BY name;")
        existing_genres = cur.fetchall()

        cur.execute("SELECT id, name FROM countries ORDER BY name;")
        existing_countries = cur.fetchall()

        cur.execute("SELECT id, name FROM actors ORDER BY name;")
        existing_actors = cur.fetchall()

        if request.method == 'POST':
            title = request.form.get('title')
            year = request.form.get('year')
            rating = request.form.get('rating')
            description = request.form.get('description')

            new_genres = [g.strip() for g in request.form.get('new_genres', '').split(',') if g.strip()]
            new_countries = [c.strip() for c in request.form.get('new_countries', '').split(',') if c.strip()]
            new_actors = [a.strip() for a in request.form.getlist('new_actors') if a.strip()]

            selected_genres = request.form.getlist('genres')
            selected_countries = request.form.getlist('countries')
            selected_actors = request.form.getlist('actors')

            # Добавляем новые элементы
            genre_ids = []
            for genre in new_genres:
                cur.execute("SELECT id FROM genres WHERE name = %s;", (genre,))
                if res := cur.fetchone():
                    genre_ids.append(res[0])
                else:
                    cur.execute("INSERT INTO genres (name) VALUES (%s) RETURNING id;", (genre,))
                    genre_ids.append(cur.fetchone()[0])

            country_ids = []
            for country in new_countries:
                cur.execute("SELECT id FROM countries WHERE name = %s;", (country,))
                if res := cur.fetchone():
                    country_ids.append(res[0])
                else:
                    cur.execute("INSERT INTO countries (name) VALUES (%s) RETURNING id;", (country,))
                    country_ids.append(cur.fetchone()[0])

            actor_ids = []
            for actor in new_actors:
                cur.execute("SELECT id FROM actors WHERE name = %s;", (actor,))
                if res := cur.fetchone():
                    actor_ids.append(res[0])
                else:
                    cur.execute("INSERT INTO actors (name) VALUES (%s) RETURNING id;", (actor,))
                    actor_ids.append(cur.fetchone()[0])

            # Добавляем фильм
            cur.execute("""
                INSERT INTO movies (title, year, rating, description) 
                VALUES (%s, %s, %s, %s) 
                RETURNING id;
            """, (title, year, rating or None, description or None))
            movie_id = cur.fetchone()[0]

            # Связываем фильм с элементами
            for genre_id in genre_ids + selected_genres:
                try:
                    cur.execute("INSERT INTO movie_genres (movie_id, genre_id) VALUES (%s, %s);",
                               (movie_id, genre_id))
                except psycopg2.IntegrityError:
                    conn.rollback()

            for country_id in country_ids + selected_countries:
                try:
                    cur.execute("INSERT INTO movie_countries (movie_id, country_id) VALUES (%s, %s);",
                               (movie_id, country_id))
                except psycopg2.IntegrityError:
                    conn.rollback()

            for actor_id in actor_ids + selected_actors:
                try:
                    cur.execute("INSERT INTO movie_actors (movie_id, actor_id) VALUES (%s, %s);",
                               (movie_id, actor_id))
                except psycopg2.IntegrityError:
                    conn.rollback()

            conn.commit()
            flash('Фильм и связанные данные успешно добавлены', 'success')
            return redirect('/movies')

    except Exception as e:
        conn.rollback()
        flash(f'Ошибка при добавлении: {str(e)}', 'danger')
    finally:
        dbClose(cur, conn)

    return render_template('add_movie.html',
                           genres=existing_genres,
                           countries=existing_countries,
                           actors=existing_actors,
                           current_year=datetime.now().year)

if __name__ == '__main__':
    app.run(debug=True)