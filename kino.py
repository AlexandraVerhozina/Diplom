from flask import Flask, render_template, request, redirect, session, flash, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import psycopg2
from datetime import datetime
from werkzeug.utils import secure_filename
import os


ALLOWED_EXTENSIONS = {'jpg'}  

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



app = Flask(__name__)
app.secret_key = '55555'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')

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

def get_unread_notifications_count(user_id):
    conn = dbConnect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = %s AND is_read = FALSE;", (user_id,))
    count = cur.fetchone()[0]
    dbClose(cur, conn)
    return count

@app.route('/')
def index():
    return redirect('/movies')

@app.route('/movies', methods=['GET', 'POST'])
def movies():
    conn = dbConnect()
    cur = conn.cursor()

    # Получаем параметры
    sort_order = request.form.get('sort', 'desc')
    search_query = request.form.get('search', '')
    
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'

    unread_notifications_count = get_unread_notifications_count(session['id']) if 'id' in session else 0
    # Подсчет непрочитанных уведомлений


    # Основной запрос
    query = """
    SELECT m.id, m.title, m.year, m.rating, m.description, m.image_path,
        (
            SELECT STRING_AGG(g.name, ', ')
            FROM movie_genres mg
            JOIN genres g ON mg.genre_id = g.id
            WHERE mg.movie_id = m.id
        ) AS genres,
        (
            SELECT STRING_AGG(c.name, ', ')
            FROM movie_countries mc
            JOIN countries c ON mc.country_id = c.id
            WHERE mc.movie_id = m.id
        ) AS countries,
        (
            SELECT STRING_AGG(a.name, ', ')
            FROM movie_actors ma
            JOIN actors a ON ma.actor_id = a.id
            WHERE ma.movie_id = m.id
        ) AS actors,
        (
            SELECT STRING_AGG(t.trailer_url, ', ')
            FROM trailers t
            WHERE t.movie_id = m.id
        ) AS trailers
    FROM movies m
    """
    
    params = []
    where_clauses = []
    
    if search_query:
        where_clauses.append("m.title ILIKE %s")
        params.append(f'%{search_query}%')
    
    # Учет предпочтений пользователя
    if 'id' in session:
        user_id = session['id']
        
        # Минимальный рейтинг
        cur.execute("SELECT min_rating FROM users WHERE id = %s;", (user_id,))
        min_rating = cur.fetchone()[0]
        if min_rating:
            where_clauses.append("m.rating >= %s")
            params.append(min_rating)
        
        # Получаем любимые и нелюбимые элементы
        cur.execute("SELECT genre FROM user_genres WHERE user_id = %s AND is_favorite = TRUE;", (user_id,))
        favorite_genres = [row[0] for row in cur.fetchall()]
        
        cur.execute("SELECT genre FROM user_genres WHERE user_id = %s AND is_favorite = FALSE;", (user_id,))
        disliked_genres = [row[0] for row in cur.fetchall()]
        
        cur.execute("SELECT country FROM user_countries WHERE user_id = %s AND is_favorite = TRUE;", (user_id,))
        favorite_countries = [row[0] for row in cur.fetchall()]
        
        cur.execute("SELECT country FROM user_countries WHERE user_id = %s AND is_favorite = FALSE;", (user_id,))
        disliked_countries = [row[0] for row in cur.fetchall()]
        
        cur.execute("SELECT actor FROM user_actors WHERE user_id = %s AND is_favorite = TRUE;", (user_id,))
        favorite_actors = [row[0] for row in cur.fetchall()]
        
        cur.execute("SELECT actor FROM user_actors WHERE user_id = %s AND is_favorite = FALSE;", (user_id,))
        disliked_actors = [row[0] for row in cur.fetchall()]
        
        # Условия для показа фильмов:
        # Фильм должен иметь хотя бы один любимый жанр, страну или актера
        # И не должен иметь ни одного нелюбимого жанра, страны или актера
        
        # Собираем условия для любимых элементов
        favorite_conditions = []
        if favorite_genres:
            favorite_conditions.append("""
            EXISTS (
                SELECT 1 FROM movie_genres mg 
                JOIN genres g ON mg.genre_id = g.id
                WHERE mg.movie_id = m.id AND g.name IN %s
            )
            """)
            params.append(tuple(favorite_genres))
        
        if favorite_countries:
            favorite_conditions.append("""
            EXISTS (
                SELECT 1 FROM movie_countries mc 
                JOIN countries c ON mc.country_id = c.id
                WHERE mc.movie_id = m.id AND c.name IN %s
            )
            """)
            params.append(tuple(favorite_countries))
        
        if favorite_actors:
            favorite_conditions.append("""
            EXISTS (
                SELECT 1 FROM movie_actors ma 
                JOIN actors a ON ma.actor_id = a.id
                WHERE ma.movie_id = m.id AND a.name IN %s
            )
            """)
            params.append(tuple(favorite_actors))
        
        # Если есть хотя бы одно условие для любимых элементов
        if favorite_conditions:
            where_clauses.append("(" + " OR ".join(favorite_conditions) + ")")
        
        # Условия для исключения нелюбимых элементов
        if disliked_genres:
            where_clauses.append("""
            NOT EXISTS (
                SELECT 1 FROM movie_genres mg 
                JOIN genres g ON mg.genre_id = g.id
                WHERE mg.movie_id = m.id AND g.name IN %s
            )
            """)
            params.append(tuple(disliked_genres))
        
        if disliked_countries:
            where_clauses.append("""
            NOT EXISTS (
                SELECT 1 FROM movie_countries mc 
                JOIN countries c ON mc.country_id = c.id
                WHERE mc.movie_id = m.id AND c.name IN %s
            )
            """)
            params.append(tuple(disliked_countries))
        
        if disliked_actors:
            where_clauses.append("""
            NOT EXISTS (
                SELECT 1 FROM movie_actors ma 
                JOIN actors a ON ma.actor_id = a.id
                WHERE ma.movie_id = m.id AND a.name IN %s
            )
            """)
            params.append(tuple(disliked_actors))
    
    # Добавляем условия фильтрации
    selected_years = request.form.getlist('year')
    selected_genres = request.form.getlist('genre')
    selected_countries = request.form.getlist('country')
    selected_actors = request.form.getlist('actor')

    if selected_genres:
        genre_ids = []
        for genre in selected_genres:
            cur.execute("SELECT id FROM genres WHERE name = %s;", (genre,))
            result = cur.fetchone()
            if result:
                genre_ids.append(result[0])

        if genre_ids:
            where_clauses.append("""
            EXISTS (
                SELECT 1 FROM movie_genres mg 
                WHERE mg.movie_id = m.id AND mg.genre_id IN %s
            )
            """)
            params.append(tuple(genre_ids))

    
    if selected_years:
        where_clauses.append("m.year IN %s")
        params.append(tuple(selected_years))
    
    
    if selected_countries:
        country_ids = []
        for country in selected_countries:
            cur.execute("SELECT id FROM countries WHERE name = %s;", (country,))
            result = cur.fetchone()
            if result:
                country_ids.append(result[0])

        if country_ids:
            where_clauses.append("""
            EXISTS (
                SELECT 1 FROM movie_countries mc 
                WHERE mc.movie_id = m.id AND mc.country_id IN %s
            )
            """)
            params.append(tuple(country_ids))
    
    if selected_actors:
        where_clauses.append("""
        EXISTS (
            SELECT 1 FROM movie_actors ma 
            JOIN actors a ON ma.actor_id = a.id 
            WHERE ma.movie_id = m.id AND a.id IN %s
        )
        """)
        params.append(tuple(selected_actors))
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
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

    # Проверяем избранное
    favorites = []
    if 'id' in session:
        cur.execute("SELECT movie_id FROM favorites WHERE user_id = %s;", (session['id'],))
        favorites = [row[0] for row in cur.fetchall()]

    dbClose(cur, conn)
    
    return render_template('movies.html', 
                         movies=movies, 
                         years=years, 
                         genres=genres, 
                         countries=countries,
                         actors=actors,
                         selected_years=selected_years,
                         selected_genres=selected_genres,
                         selected_countries=selected_countries,
                         selected_actors=selected_actors,
                         favorites=favorites,
                         unread_notifications_count=unread_notifications_count)

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

    unread_notifications_count = get_unread_notifications_count(session['id']) if 'id' in session else 0
    # Подсчет непрочитанных уведомлений

    query = """
    SELECT m.id, m.title, m.year, m.rating, m.description, m.image_path,
        (
            SELECT STRING_AGG(g.name, ', ')
            FROM movie_genres mg
            JOIN genres g ON mg.genre_id = g.id
            WHERE mg.movie_id = m.id
        ) AS genres,
        (
            SELECT STRING_AGG(c.name, ', ')
            FROM movie_countries mc
            JOIN countries c ON mc.country_id = c.id
            WHERE mc.movie_id = m.id
        ) AS countries,
        (
            SELECT STRING_AGG(a.name, ', ')
            FROM movie_actors ma
            JOIN actors a ON ma.actor_id = a.id
            WHERE ma.movie_id = m.id
        ) AS actors,
        (
            SELECT STRING_AGG(t.trailer_url, ', ')
            FROM trailers t
            WHERE t.movie_id = m.id
        ) AS trailers
    FROM movies m
    JOIN favorites f ON m.id = f.movie_id
    WHERE f.user_id = %s
    ORDER BY m.title;
    """
    
    cur.execute(query, (session['id'],))
    favorites = cur.fetchall()

    dbClose(cur, conn)
    return render_template('izbr.html', favorites=favorites, unread_notifications_count=unread_notifications_count)


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

@app.route('/user', methods=['GET', 'POST'])
def user():
    if 'id' not in session:
        return redirect('/login')

    conn = dbConnect()
    cur = conn.cursor()

    unread_notifications_count = get_unread_notifications_count(session['id']) if 'id' in session else 0
    # Подсчет непрочитанных уведомлений

    if request.method == 'POST':
        try:
            user_id = session['id']
            
            # Обработка предпочтений
            favorite_genres = request.form.getlist('favorite_genres')
            disliked_genres = request.form.getlist('disliked_genres')
            favorite_countries = request.form.getlist('favorite_countries')
            disliked_countries = request.form.getlist('disliked_countries')
            favorite_actors = request.form.getlist('favorite_actors')
            disliked_actors = request.form.getlist('disliked_actors')
            min_rating = request.form.get('min_rating')

            # Обновляем предпочтения по жанрам
            cur.execute("DELETE FROM user_genres WHERE user_id = %s;", (user_id,))
            for genre in favorite_genres:
                cur.execute("INSERT INTO user_genres (user_id, genre, is_favorite) VALUES (%s, %s, TRUE);", 
                          (user_id, genre))
            for genre in disliked_genres:
                cur.execute("INSERT INTO user_genres (user_id, genre, is_favorite) VALUES (%s, %s, FALSE);", 
                          (user_id, genre))

            # Обновляем предпочтения по странам
            cur.execute("DELETE FROM user_countries WHERE user_id = %s;", (user_id,))
            for country in favorite_countries:
                cur.execute("INSERT INTO user_countries (user_id, country, is_favorite) VALUES (%s, %s, TRUE);", 
                          (user_id, country))
            for country in disliked_countries:
                cur.execute("INSERT INTO user_countries (user_id, country, is_favorite) VALUES (%s, %s, FALSE);", 
                          (user_id, country))

            # Обновляем предпочтения по актерам
            cur.execute("DELETE FROM user_actors WHERE user_id = %s;", (user_id,))
            for actor in favorite_actors:
                cur.execute("INSERT INTO user_actors (user_id, actor, is_favorite) VALUES (%s, %s, TRUE);", 
                          (user_id, actor))
            for actor in disliked_actors:
                cur.execute("INSERT INTO user_actors (user_id, actor, is_favorite) VALUES (%s, %s, FALSE);", 
                          (user_id, actor))

            # Обновляем минимальный рейтинг
            cur.execute("UPDATE users SET min_rating = %s WHERE id = %s;", (min_rating, user_id))

            conn.commit()
            flash('Ваши предпочтения успешно сохранены!', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Ошибка при сохранении предпочтений: {str(e)}', 'danger')
        finally:
            dbClose(cur, conn)
            return redirect(url_for('user'))

    # Получаем данные пользователя
    cur.execute("SELECT id, username, min_rating FROM users WHERE id = %s;", (session['id'],))
    user = cur.fetchone()

    # Получаем все доступные жанры, страны и актеров
    cur.execute("SELECT name FROM genres ORDER BY name;")
    genres = [row[0] for row in cur.fetchall()]

    cur.execute("SELECT name FROM countries ORDER BY name;")
    countries = [row[0] for row in cur.fetchall()]

    cur.execute("SELECT name FROM actors ORDER BY name;")
    actors = [row[0] for row in cur.fetchall()]

    # Получаем текущие предпочтения пользователя
    cur.execute("SELECT genre, is_favorite FROM user_genres WHERE user_id = %s;", (session['id'],))
    genre_prefs = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("SELECT country, is_favorite FROM user_countries WHERE user_id = %s;", (session['id'],))
    country_prefs = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("SELECT actor, is_favorite FROM user_actors WHERE user_id = %s;", (session['id'],))
    actor_prefs = {row[0]: row[1] for row in cur.fetchall()}

    dbClose(cur, conn)

    return render_template('user.html', 
                         user=user,
                         genres=genres,
                         countries=countries,
                         actors=actors,
                         genre_prefs=genre_prefs,
                         country_prefs=country_prefs,
                         actor_prefs=actor_prefs,
                        unread_notifications_count=unread_notifications_count)

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

    # Получаем существующие данные для выпадающих списков
    cur.execute("SELECT id, name FROM genres ORDER BY name;")
    existing_genres = cur.fetchall()

    cur.execute("SELECT id, name FROM countries ORDER BY name;")
    existing_countries = cur.fetchall()

    cur.execute("SELECT id, name FROM actors ORDER BY name;")
    existing_actors = cur.fetchall()

    movie_id = None

    if request.method == 'POST':
        try:
            title = request.form.get('title')
            year = request.form.get('year')
            rating = request.form.get('rating')
            description = request.form.get('description')
            trailer_url = request.form.get('trailer_url')

            image_path = None
            if 'image' in request.files:
                file = request.files['image']
                if file and allowed_file(file.filename):
                    # Получаем расширение файла
                    file_extension = os.path.splitext(secure_filename(file.filename))[1].lower()
                    
                    # Проверяем, что расширение файла - только .jpg
                    if file_extension != '.jpg':
                        flash('Файл должен быть в формате .jpg', 'danger')
                        return redirect(request.referrer or url_for('add_movie'))

                    # Создаем уникальное имя файла
                    unique_filename = f"{int(datetime.now().timestamp())}.jpg"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    
                    # Сохраняем файл
                    file.save(save_path)
                    image_path = os.path.join('uploads', unique_filename)

                    # Проверяем, что файл действительно сохранён
                    if not os.path.exists(save_path):
                        flash('Ошибка при сохранении файла', 'danger')
                        return redirect(request.referrer or url_for('add_movie'))

            # Новые жанры, страны и актеры
            new_genres = [g.strip() for g in request.form.get('new_genres', '').split(',') if g.strip()]
            new_countries = [c.strip() for c in request.form.get('new_countries', '').split(',') if c.strip()]
            new_actors = [a.strip() for a in request.form.getlist('new_actors') if a.strip()]
            
            # Выбранные существующие элементы
            selected_genres = request.form.getlist('genres')
            selected_countries = request.form.getlist('countries')
            selected_actors = request.form.getlist('actors')

            # Добавляем новые жанры
            genre_ids = []
            for genre in new_genres:
                cur.execute("SELECT id FROM genres WHERE name = %s;", (genre,))
                if res := cur.fetchone():
                    genre_ids.append(res[0])
                else:
                    cur.execute("INSERT INTO genres (name) VALUES (%s) RETURNING id;", (genre,))
                    genre_ids.append(cur.fetchone()[0])

            # Добавляем новые страны
            country_ids = []
            for country in new_countries:
                cur.execute("SELECT id FROM countries WHERE name = %s;", (country,))
                if res := cur.fetchone():
                    country_ids.append(res[0])
                else:
                    cur.execute("INSERT INTO countries (name) VALUES (%s) RETURNING id;", (country,))
                    country_ids.append(cur.fetchone()[0])

            # Добавляем новых актеров
            actor_ids = []
            for actor in new_actors:
                cur.execute("SELECT id FROM actors WHERE name = %s;", (actor,))
                if res := cur.fetchone():
                    actor_ids.append(res[0])
                else:
                    cur.execute("INSERT INTO actors (name) VALUES (%s) RETURNING id;", (actor,))
                    actor_ids.append(cur.fetchone()[0])

            # Добавляем фильм с изображением
            cur.execute("""
                INSERT INTO movies 
                (title, year, rating, description, image_path) 
                VALUES (%s, %s, %s, %s, %s) 
                RETURNING id;
            """, (title, year, rating or None, description or None, image_path))
            movie_id = cur.fetchone()[0]

            # Добавляем трейлер в новую таблицу
            if trailer_url:
                cur.execute("""
                    INSERT INTO trailers (movie_id, trailer_url) 
                    VALUES (%s, %s);
                """, (movie_id, trailer_url))

            # Связываем фильм с жанрами
            for genre_id in genre_ids + selected_genres:
                try:
                    cur.execute("""
                        INSERT INTO movie_genres (movie_id, genre_id) 
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING;
                    """, (movie_id, genre_id))
                except Exception as e:
                    conn.rollback()
                    app.logger.error(f"Error adding genre: {e}")


            # Связываем фильм со странами
            for country_id in country_ids + selected_countries:
                try:
                    cur.execute("""
                        INSERT INTO movie_countries (movie_id, country_id) 
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING;
                    """, (movie_id, country_id))
                except Exception as e:
                    conn.rollback()
                    app.logger.error(f"Error adding country: {e}")

            # Связываем фильм с актерами
            for actor_id in actor_ids + selected_actors:
                try:
                    cur.execute("""
                        INSERT INTO movie_actors (movie_id, actor_id) 
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING;
                    """, (movie_id, actor_id))
                except Exception as e:
                    conn.rollback()
                    app.logger.error(f"Error adding actor: {e}")

            conn.commit()
            flash('Фильм успешно добавлен', 'success')
            

     
           # После добавления фильма
            cur.execute("SELECT id FROM users;")
            users = cur.fetchall()

            for user in users:
                user_id = user[0]
                
                # Извлекаем любимые жанры пользователя
                cur.execute("SELECT genre FROM user_genres WHERE user_id = %s AND is_favorite = TRUE;", (user_id,))
                favorite_genres = [row[0] for row in cur.fetchall()]

                # Извлекаем любимые страны пользователя
                cur.execute("SELECT country FROM user_countries WHERE user_id = %s AND is_favorite = TRUE;", (user_id,))
                favorite_countries = [row[0] for row in cur.fetchall()]

                # Извлекаем любимых актеров пользователя
                cur.execute("SELECT actor FROM user_actors WHERE user_id = %s AND is_favorite = TRUE;", (user_id,))
                favorite_actors = [row[0] for row in cur.fetchall()]

                # Извлекаем жанры нового фильма
                cur.execute("SELECT genre_id FROM movie_genres WHERE movie_id = %s;", (movie_id,))
                genre_ids = [row[0] for row in cur.fetchall()]

                # Извлекаем страны нового фильма
                cur.execute("SELECT country_id FROM movie_countries WHERE movie_id = %s;", (movie_id,))
                country_ids = [row[0] for row in cur.fetchall()]

                # Извлекаем актеров нового фильма
                cur.execute("SELECT actor_id FROM movie_actors WHERE movie_id = %s;", (movie_id,))
                actor_ids = [row[0] for row in cur.fetchall()]

                # Преобразуем ID в названия для логирования
                genre_names = []
                for gid in genre_ids:
                    cur.execute("SELECT name FROM genres WHERE id = %s;", (gid,))
                    result = cur.fetchone()
                    if result:
                        genre_names.append(result[0])

                country_names = []
                for cid in country_ids:
                    cur.execute("SELECT name FROM countries WHERE id = %s;", (cid,))
                    result = cur.fetchone()
                    if result:
                        country_names.append(result[0])

                actor_names = []
                for aid in actor_ids:
                    cur.execute("SELECT name FROM actors WHERE id = %s;", (aid,))
                    result = cur.fetchone()
                    if result:
                        actor_names.append(result[0])

                app.logger.info(f"Пользователь ID: {user_id}, Любимые жанры: {favorite_genres}, Жанры фильма: {genre_names}")
                app.logger.info(f"Пользователь ID: {user_id}, Любимые страны: {favorite_countries}, Страны фильма: {country_names}")
                app.logger.info(f"Пользователь ID: {user_id}, Любимые актеры: {favorite_actors}, Актеры фильма: {actor_names}")

                # Проверяем соответствие хотя бы одному критерию
                if (any(genre in favorite_genres for genre in genre_names) or
                    any(country in favorite_countries for country in country_names) or
                    any(actor in favorite_actors for actor in actor_names)):
                    
                    app.logger.info(f"Уведомление добавлено для пользователя ID: {user_id} о фильме ID: {movie_id}")
                    cur.execute("""
                        INSERT INTO notifications (user_id, movie_id, message) 
                        VALUES (%s, %s, %s);
                    """, (user_id, movie_id, 'Вышел новый фильм, соответствующий вашим предпочтениям'))
                    conn.commit()  
                else:
                    app.logger.info(f"Уведомление не добавлено для пользователя ID: {user_id} - нет соответствия.")



  


            return redirect(url_for('movies'))

        except Exception as e:
            conn.rollback()
            flash(f'Ошибка при добавлении фильма: {str(e)}', 'danger')
            app.logger.error(f"Error in add_movie: {str(e)}")
        finally:
            dbClose(cur, conn)

    return render_template('add_movie.html',
                         genres=existing_genres,
                         countries=existing_countries,
                         actors=existing_actors,
                         current_year=datetime.now().year)

@app.route('/notifications')
def notifications():
    if 'id' not in session:
        return redirect('/login')

    conn = dbConnect()
    cur = conn.cursor()

    # Получаем уведомления для пользователя
    cur.execute("SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC;", (session['id'],))
    notifications = cur.fetchall()

    # Обновляем статус уведомлений на прочитанные
    cur.execute("UPDATE notifications SET is_read = TRUE WHERE user_id = %s;", (session['id'],))

    conn.commit()

    dbClose(cur, conn)
    return render_template('notifications.html', notifications=notifications)

def get_unread_notifications_count(user_id):
    conn = dbConnect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = %s AND is_read = FALSE;", (user_id,))
    count = cur.fetchone()[0]
    dbClose(cur, conn)
    return count

if __name__ == '__main__':
    app.run(debug=True)