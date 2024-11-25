# pylint: disable=missing-function-docstring
import sqlite3
import math
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from geopy.distance import geodesic

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # To handle sessions securely

# Function to connect to database
def get_db():
    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row  # This helps us get dictionary-like access to rows
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Drop the users table if it already exists (if needed)
    cursor.execute('DROP TABLE IF EXISTS users')
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    """)

    # Create users table with the 'role' column
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL  -- 'teacher' or 'student'
        )
    ''')

    # Create attendance table with the 'status' column
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL  -- 'Present' or 'Absent'
        )
    ''')

    # Create location table for teacher GPS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_email TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL
        )
    ''')

    conn.commit()
    conn.close()

def haversine(lat1, lon1, lat2, lon2):
    """Calculate the distance between two lat/long points"""
    R = 6371  # Radius of the Earth in kilometers
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c * 1000  # Distance in meters
    return distance

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if 'username' not in session:
        return redirect(url_for('login'))  # Ensure the user is logged in

    data = request.get_json()
    latitude = data['latitude']
    longitude = data['longitude']
    student_name = session['username']

    conn = get_db()
    cursor = conn.cursor()

    # Fetch the teacher's location from the database
    cursor.execute('SELECT latitude, longitude FROM locations ORDER BY id DESC LIMIT 1')
    teacher_location = cursor.fetchone()

    if teacher_location:
        teacher_lat = teacher_location[0]
        teacher_lon = teacher_location[1]

        # Debug print the teacher's and student's locations
        print(f"Teacher's Location: ({teacher_lat}, {teacher_lon})")
        print(f"Student's Location: ({latitude}, {longitude})")

        # Calculate the distance between the teacher and student's location
        distance = haversine(latitude, longitude, teacher_lat, teacher_lon)

        # Debug print the calculated distance
        print(f"Calculated Distance: {distance} meters")

        # If within 100 meters, mark attendance as Present, otherwise mark as Absent
        if distance <= 100:
            status = 'Present'
        else:
            status = 'Absent'  # Explicitly mark the student as Absent if the distance is greater than 100 meters

        # Insert the attendance record into the database
        cursor.execute('''
            INSERT INTO attendance (student_name, latitude, longitude, timestamp, status)
            VALUES (?, ?, ?, datetime('now'), ?)
        ''', (student_name, latitude, longitude, status))

        conn.commit()

    conn.close()

    return {'message': 'Attendance marked successfully!'}

# Home route
@app.route('/')
def index():
    return render_template('index.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Query the database for the user
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (username,))
        user = cursor.fetchone()  # Fetch the first matching user
        conn.close()
        
        if user and check_password_hash(user['password'], password):  # Check password hash
            session['username'] = username  # Store username in session
            if user['role'] == 'student':
                return redirect(url_for('student_dashboard'))
            elif user['role'] == 'teacher':
                return redirect(url_for('teacher_dashboard'))
        else:
            flash('Invalid credentials!', 'danger')
            return redirect(url_for('login'))
    
    return render_template('login.html')

# Register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        
        # Check if the user already exists in the database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (username,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            flash('User already exists!', 'danger')
            return redirect(url_for('register'))
        
        # Hash the password before storing it
        hashed_password = generate_password_hash(password)
        
        # Insert new user into the database
        cursor.execute('''
            INSERT INTO users (email, password, role) VALUES (?, ?, ?)
        ''', (username, hashed_password, role))
        conn.commit()
        conn.close()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Student Dashboard route
@app.route('/student_dashboard')
def student_dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('student_dashboard.html')

# Teacher Dashboard route
@app.route('/teacher_dashboard')
def teacher_dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    # Fetch all attendance records from the database
    cursor.execute('SELECT student_name, latitude, longitude, timestamp, status FROM attendance')
    attendance_records = cursor.fetchall()

    conn.close()

    return render_template('teacher_dashboard.html', attendance_records=attendance_records)

@app.route('/set_location', methods=['POST'])
def set_location():
    latitude = request.form['latitude']
    longitude = request.form['longitude']

    conn = get_db()
    cursor = conn.cursor()

    # Insert teacher's location into the locations table
    cursor.execute('''
        INSERT INTO locations (teacher_email, latitude, longitude)
        VALUES (?, ?, ?)
    ''', (session['username'], latitude, longitude))

    conn.commit()
    conn.close()

    return redirect(url_for('teacher_dashboard'))

# Logout route
@app.route('/logout')
def logout():
    session.pop('username', None)  # Remove the user from the session
    return redirect(url_for('index'))  # Redirect to home page

if __name__ == '__main__':
    # Initialize the database tables (if not already initialized)
    init_db()
    app.run(debug=True)
