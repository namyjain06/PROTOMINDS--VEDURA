import sqlite3
from datetime import datetime, timedelta
import random
import os

def init_db():
    print("🗄️ Initializing database...")
    conn = sqlite3.connect('health_chatbot.db')
    cursor = conn.cursor()

    # Drop existing tables to ensure clean setup
    cursor.execute("DROP TABLE IF EXISTS user_interactions")
    cursor.execute("DROP TABLE IF EXISTS government_alerts")

    cursor.execute("""
        CREATE TABLE user_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_phone TEXT,
            message TEXT,
            response TEXT,
            language TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            location_lat REAL,
            location_lng REAL,
            symptoms TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE government_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT,
            location TEXT,
            symptoms_count INTEGER,
            severity TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'ACTIVE'
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database tables initialized")

def insert_demo_data():
    print("🎭 Inserting demo data...")
    conn = sqlite3.connect('health_chatbot.db')
    cursor = conn.cursor()

    # Sample user interactions with realistic data
    now = datetime.now()
    interactions = [
        ("whatsapp:+919876543210", "I have fever and cough", "Fever response", "en", 28.6139, 77.2090, "fever,cough", now - timedelta(hours=2)),
        ("whatsapp:+919876543211", "मुझे सिरदर्द है", "Headache response", "hi", 28.6140, 77.2091, "headache", now - timedelta(hours=4)),
        ("whatsapp:+919876543212", "Vaccination schedule", "Vaccination info", "en", 28.6141, 77.2092, "vaccination", now - timedelta(hours=6)),
        ("whatsapp:+919876543213", "मुझे बुखार है", "Fever response", "hi", 28.6142, 77.2093, "fever", now - timedelta(hours=8)),
        ("whatsapp:+919876543214", "I have headache and fever", "Combined response", "en", 28.6143, 77.2094, "headache,fever", now - timedelta(hours=1)),
        ("web_demo_123", "Cough and throat pain", "Cough response", "en", 19.0760, 72.8777, "cough", now - timedelta(hours=3)),
        ("web_demo_456", "खांसी और गले में दर्द", "Cough response Hindi", "hi", 19.0761, 72.8778, "cough", now - timedelta(hours=5)),
    ]

    for interaction in interactions:
        cursor.execute("""
            INSERT INTO user_interactions 
            (user_phone, message, response, language, location_lat, location_lng, symptoms, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, interaction)

    # Sample government alerts
    alerts = [
        ("OUTBREAK_DETECTED", "Lat: 28.6141, Lng: 77.2092", 5, "HIGH", now - timedelta(hours=2), "ACTIVE"),
        ("OUTBREAK_DETECTED", "Lat: 19.0760, Lng: 72.8777", 3, "MEDIUM", now - timedelta(hours=6), "ACTIVE"),
        ("SYMPTOM_CLUSTER", "Lat: 12.9716, Lng: 77.5946", 4, "HIGH", now - timedelta(hours=12), "RESOLVED"),
    ]

    for alert in alerts:
        cursor.execute("""
            INSERT INTO government_alerts 
            (alert_type, location, symptoms_count, severity, timestamp, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, alert)

    conn.commit()
    conn.close()
    print("✅ Demo data inserted")

if __name__ == "__main__":
    print("=" * 50)
    print("🏥 ProtoMinds Health Chatbot Setup")
    print("=" * 50)

    # Create templates directory if it doesn't exist
    if not os.path.exists("templates"):
        os.makedirs("templates")
        print("📁 Created templates directory")

    # Initialize database and insert demo data
    init_db()
    insert_demo_data()

    print("=" * 50)
    print("🎉 Setup complete!")
    print("You can now run: python app.py")
    print("Or run: python start_demo.py (to auto-open browser)")
    print("=" * 50)