from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import logging
from datetime import datetime, timedelta
import re
import sqlite3
from collections import defaultdict, Counter
from threading import Lock
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from google import genai

GEMINI_AVAILABLE = False
gemini_client = None

api_key = os.environ.get("GEMINI_API_KEY")

if api_key:
    try:
        gemini_client = genai.Client(api_key=api_key)
        GEMINI_AVAILABLE = True
        logger.info("✅ Gemini AI is ENABLED (new SDK)")
    except Exception as e:
        logger.error(f"❌ Gemini init failed: {e}")


if gemini_client:
    logger.info("✅ Gemini AI is ENABLED and ready")
else:
    logger.warning("⚠️ Gemini AI is DISABLED — running in rule-only mode")

app = Flask(__name__)
CORS(app)


DATABASE = 'health_chatbot.db'
db_lock = Lock()

def html_to_text(html_response):
    """Convert HTML response to plain text for WhatsApp"""
    # Remove HTML tags and convert to plain text
    text = html_response.replace('<strong>', '**').replace('</strong>', '**')
    text = text.replace('<br><br>', '\n\n').replace('<br>', '\n')
    text = re.sub(r'<[^>]+>', '', text)  # Remove any remaining HTML tags
    return text

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_interactions (
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
        CREATE TABLE IF NOT EXISTS government_alerts (
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

init_db()

HEALTH_KNOWLEDGE = {
    'fever': {
        'en': {
            'symptoms': 'High temperature (>100.4°F), chills, sweating, headache, body aches',
            'treatment': 'Rest, drink plenty of fluids, take paracetamol. Consult doctor if fever persists >3 days or exceeds 102°F',
            'prevention': 'Maintain good hygiene, avoid crowded places, get adequate sleep'
        },
        'hi': {
            'symptoms': 'तेज बुखार (>100.4°F), कंपकंपी, पसीना, सिरदर्द, शरीर में दर्द',
            'treatment': 'आराम करें, खूब पानी पिएं, पैरासिटामोल लें। 3 दिन से ज्यादा या 102°F से ज्यादा बुखार हो तो डॉक्टर से मिलें',
            'prevention': 'स्वच्छता बनाए रखें, भीड़भाड़ से बचें, पर्याप्त नींद लें'
        }
    },
    'cough': {
        'en': {
            'symptoms': 'Persistent coughing, throat irritation, phlegm production, chest discomfort',
            'treatment': 'Warm water gargling, honey, steam inhalation, avoid cold drinks. See doctor if persistent >2 weeks',
            'prevention': 'Avoid smoking, wear mask in dusty areas, stay hydrated, avoid cold exposure'
        },
        'hi': {
            'symptoms': 'लगातार खांसी, गले में जलन, कफ निकलना, छाती में परेशानी',
            'treatment': 'गुनगुने पानी से गरारे करें, शहद लें, भाप लें, ठंडा न पिएं। 2 हफ्ते से ज्यादा हो तो डॉक्टर को दिखाएं',
            'prevention': 'धूम्रपान न करें, धूल भरी जगह मास्क पहनें, पानी पिएं, ठंड से बचें'
        }
    },
    'headache': {
        'en': {
            'symptoms': 'Head pain, sensitivity to light/sound, nausea, neck stiffness',
            'treatment': 'Rest in dark room, apply cold/warm compress, take paracetamol, stay hydrated',
            'prevention': 'Regular sleep schedule, avoid stress, limit screen time, stay hydrated'
        },
        'hi': {
            'symptoms': 'सिर में दर्द, रोशनी/आवाज से परेशानी, जी मिचलाना, गर्दन में अकड़न',
            'treatment': 'अंधेरे कमरे में आराम करें, ठंडी/गर्म पट्टी लगाएं, पैरासिटामोल लें, पानी पिएं',
            'prevention': 'नियमित नींद लें, तनाव से बचें, स्क्रीन टाइम कम करें, पानी पिएं'
        }
    },
    'vaccination': {
        'en': {
            'info': 'Visit nearest Primary Health Center (PHC) or Community Health Center (CHC) for vaccination. Carry Aadhar card and vaccination certificate.',
            'schedule': 'COVID-19: Available for age 18+, Polio: For children under 5 years, Hepatitis B: Birth to 6 months, DPT: 6 weeks to 5 years'
        },
        'hi': {
            'info': 'टीकाकरण के लिए नजदीकी प्राथमिक स्वास्थ्य केंद्र (PHC) या सामुदायिक स्वास्थ्य केंद्र (CHC) जाएं। आधार कार्ड और टीकाकरण प्रमाणपत्र साथ लें।',
            'schedule': 'कोविड-19: 18+ उम्र के लिए, पोलियो: 5 साल से कम बच्चों के लिए, हेपेटाइटिस बी: जन्म से 6 महीने तक, डीपीटी: 6 सप्ताह से 5 साल तक'
        }
    }
}

symptom_clusters = defaultdict(list)

class HealthChatbot:
    def detect_language(self, message):
        if re.search(r'[ऀ-ॿ]', message):
            return 'hi'
        return 'en'

    def extract_symptoms(self, message):
        msg = message.lower()
        symptoms = []

        # English symptoms
        if any(word in msg for word in ['fever', 'temperature', 'hot', 'burning']):
            symptoms.append('fever')
        if any(word in msg for word in ['cough', 'coughing', 'throat']):
            symptoms.append('cough')
        if any(word in msg for word in ['headache', 'head pain', 'migraine']):
            symptoms.append('headache')
        if any(word in msg for word in ['vaccine', 'vaccination', 'immunize']):
            symptoms.append('vaccination')
            
        # Hindi symptoms
        if any(word in msg for word in ['बुखार', 'तेज़ बुखार', 'तापमान']):
            symptoms.append('fever')
        if any(word in msg for word in ['खांसी', 'खाँसी', 'गला']):
            symptoms.append('cough')
        if any(word in msg for word in ['सिरदर्द', 'सर में दर्द', 'सिर दर्द']):
            symptoms.append('headache')
        if any(word in msg for word in ['टीका', 'टीकाकरण', 'वैक्सीन']):
            symptoms.append('vaccination')
            
        return symptoms

    def process_location_data(self, lat, lng, symptoms, user_phone):
        if lat is None or lng is None or not symptoms:

            return None
            
        location_key = f"{round(lat, 2)}_{round(lng, 2)}"
        timestamp = datetime.now()

        symptom_clusters[location_key].append({
            'symptoms': symptoms, 
            'timestamp': timestamp, 
            'user': user_phone
        })

        # Check for outbreak patterns (3+ cases in 24 hours)
        recent_symptoms = [s for s in symptom_clusters[location_key] 
                          if (timestamp - s['timestamp']).total_seconds() <= 86400]  # 24 hours

        if len(recent_symptoms) >= 3:
            symptom_counts = Counter()
            for case in recent_symptoms:
                for symptom in case['symptoms']:
                    symptom_counts[symptom] += 1
                    
            alert = {
                'location': location_key,
                'lat': lat,
                'lng': lng,
                'symptoms': dict(symptom_counts),
                'case_count': len(recent_symptoms),
                'timestamp': timestamp,
                'severity': 'HIGH' if len(recent_symptoms) >= 5 else 'MEDIUM'
            }
            self.send_government_alert(alert)
            return alert
        return None

    
    def send_government_alert(self, alert):
        with db_lock:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO government_alerts
                (alert_type, location, symptoms_count, severity) 
                VALUES (?, ?, ?, ?)
            """, (
                'OUTBREAK_DETECTED', 
                f"Lat: {alert['lat']:.4f}, Lng: {alert['lng']:.4f}", 
                alert['case_count'], 
                alert['severity']
            ))
            conn.commit()
            conn.close()
        logger.info(f"🚨 Government alert sent: {alert}")

    def get_health_response(self, message, language='en'):
        symptoms = self.extract_symptoms(message)
        
        if not symptoms:
            # STEP 6: Try Gemini fallback first
            gemini_response = self.gemini_fallback(message, language)
            if gemini_response:
                return gemini_response

            # Final fallback if Gemini is unavailable or fails
            if language == 'hi':
                return "मुझे आपकी समस्या समझने में मदद चाहिए। कृपया अपने लक्षण बताएं जैसे बुखार, खांसी, सिरदर्द आदि।"
            return "I need help understanding your concern. Please describe your symptoms like fever, cough, headache, etc."


        response_parts = []
        for symptom in symptoms:
            if symptom in HEALTH_KNOWLEDGE:
                data = HEALTH_KNOWLEDGE[symptom][language]
                if language == 'hi':
                    if symptom == 'vaccination':
                        response_parts.append(f"<strong>{symptom.title()} की जानकारी:</strong><br>")
                        response_parts.append(f"📍 कहाँ जाएं: {data['info']}<br>")
                        response_parts.append(f"📅 टीकाकरण शेड्यूल: {data['schedule']}<br>")
                    else:
                        response_parts.append(f"<strong>{symptom.title()} के बारे में:</strong><br>")
                        response_parts.append(f"🔸 लक्षण: {data['symptoms']}<br>")
                        response_parts.append(f"💊 इलाज: {data['treatment']}<br>")
                        if 'prevention' in data:
                            response_parts.append(f"🛡️ बचाव: {data['prevention']}<br>")
                else:
                    if symptom == 'vaccination':
                        response_parts.append(f"<strong>Vaccination Information:</strong><br>")
                        response_parts.append(f"📍 Where to go: {data['info']}<br>")
                        response_parts.append(f"📅 Schedule: {data['schedule']}<br>")
                    else:
                        response_parts.append(f"<strong>About {symptom.title()}:</strong><br>")
                        response_parts.append(f"🔸 Symptoms: {data['symptoms']}<br>")
                        response_parts.append(f"💊 Treatment: {data['treatment']}<br>")
                        if 'prevention' in data:
                            response_parts.append(f"🛡️ Prevention: {data['prevention']}<br>")

        # Add escalation message
        if language == 'hi':
            response_parts.append("<br>⚠️ <strong>महत्वपूर्ण:</strong> गंभीर लक्षण हों तो तुरंत डॉक्टर से मिलें। आपातकाल में 108 पर कॉल करें।")
        else:
            response_parts.append("<br>⚠️ <strong>Important:</strong> Consult a doctor immediately for severe symptoms. Call 108 for emergencies.")
            
        return "<br>".join(response_parts)
    
    def gemini_fallback(self, message, language):
        if not GEMINI_AVAILABLE or not gemini_client:
            return None

        logger.info("🤖 Gemini fallback triggered")

        try:
            prompt = (
                "You are vedura, a conservative health assistant for India.\n"
                "Do NOT diagnose.\n"
                "Do NOT prescribe medicines except paracetamol.\n"
                "Always suggest consulting a doctor.\n"
                "Use calm, supportive language.\n\n"
                f"User ({language}): {message}"
            )

            response = gemini_client.models.generate_content(
                             model="gemini-2.5-flash",
                            contents=[
                                {
                                    "role": "user",
                                    "parts": [
                                        {"text": prompt}
                                    ]
                                }
                                     ]
                )
            return response.text if response and hasattr(response, "text") else None

        except Exception as e:
            logger.error(f"❌ Gemini failed: {e}")
            return None



chatbot = HealthChatbot()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    with db_lock:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM government_alerts ORDER BY timestamp DESC LIMIT 10")
        alerts = cursor.fetchall()
        
        cursor.execute("""
            SELECT COUNT(*) as total, language, COUNT(DISTINCT user_phone) as unique_users
            FROM user_interactions 
            WHERE date(timestamp) = date('now')
            GROUP BY language
        """)
        stats = cursor.fetchall()
        
        conn.close()
    return render_template('admin.html', alerts=alerts, stats=stats)

@app.route('/whatsapp_webhook', methods=['POST'])
def whatsapp_webhook():
    try:
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
            
        logger.info(f"📱 Received webhook: {data}")

        message_body = data.get('Body', '').strip()
        from_number = data.get('From', '').replace('whatsapp:', '')

        if not message_body:
            twilio_resp = MessagingResponse()
            twilio_resp.message("Sorry, I did not receive any message.")
            return str(twilio_resp), 200, {'Content-Type': 'application/xml'}

        language = chatbot.detect_language(message_body)
        lat, lng = None, None

        # Handle location format: "loc:lat:lng:message"
        if message_body.startswith('loc:'):
            parts = message_body.split(':', 3)
            if len(parts) >= 4:
                try:
                    lat = float(parts[1])
                    lng = float(parts[2])
                    message_body = parts[3]
                except ValueError:
                    pass

        response_text = chatbot.get_health_response(message_body, language)
        response_text = html_to_text(response_text)  # Convert HTML to plain text for WhatsApp
        
        symptoms = chatbot.extract_symptoms(message_body)

        # Process location for outbreak detection
        alert = None
        if lat and lng and symptoms:
            alert = chatbot.process_location_data(lat, lng, symptoms, from_number)

        # Save interaction to database
        with db_lock:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_interactions
                (user_phone, message, response, language, location_lat, location_lng, symptoms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                from_number, message_body, response_text, language, 
                lat, lng, ','.join(symptoms) if symptoms else None
            ))
            conn.commit()
            conn.close()

        # Add alert notification to response
        if alert:
            if language == 'hi':
                response_text += f"\n\n📍 **स्थान आधारित अलर्ट:** आपके क्षेत्र में {alert['case_count']} मामले देखे गए हैं। स्वास्थ्य विभाग को सूचित कर दिया गया है।"
            else:
                response_text += f"\n\n📍 **Location Alert:** {alert['case_count']} cases detected in your area. Health authorities have been notified."

        # Create TwiML response for Twilio
        twilio_resp = MessagingResponse()
        twilio_resp.message(response_text)

        logger.info(f"📤 WhatsApp response sent: {response_text[:50]}...")
        
        return str(twilio_resp), 200, {'Content-Type': 'application/xml'}

    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}")
        twilio_resp = MessagingResponse()
        twilio_resp.message("Sorry, there was an error processing your request.")
        return str(twilio_resp), 500, {'Content-Type': 'application/xml'}

@app.route('/api/chat', methods=['POST'])
def chat_api():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        message = data.get('message', '').strip()
        language = data.get('language', 'en')
        lat = data.get('lat')
        lng = data.get('lng')
        user_id = data.get('user_id', f'web_demo_{datetime.now().strftime("%H%M%S")}')

        if not message:
            return jsonify({'error': 'No message provided'}), 400

        logger.info(f"💬 Processing message: {message} (lang: {language})")

        response = chatbot.get_health_response(message, language)
        symptoms = chatbot.extract_symptoms(message)

        # Process location data for outbreak detection
        alert = None
        if lat and lng and symptoms:
            alert = chatbot.process_location_data(lat, lng, symptoms, user_id)

        # Save interaction to database
        with db_lock:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_interactions
                (user_phone, message, response, language, location_lat, location_lng, symptoms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, message, response, language, 
                lat, lng, ','.join(symptoms) if symptoms else None
            ))
            conn.commit()
            conn.close()

        logger.info(f"✅ Response generated: {len(response)} chars, Alert: {alert is not None}")

        return jsonify({
            'response': response,
            'language_detected': chatbot.detect_language(message),
            'symptoms_detected': symptoms,
            'alert_generated': alert is not None,
            'alert_details': alert
        }), 200

    except Exception as e:
        logger.error(f"❌ Chat API error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/alerts')
def get_alerts():
    with db_lock:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM government_alerts ORDER BY timestamp DESC LIMIT 20")
        alerts = cursor.fetchall()
        conn.close()
    
    return jsonify([{
        'id': alert[0],
        'alert_type': alert[1],
        'location': alert[2],
        'symptoms_count': alert[3],
        'severity': alert[4],
        'timestamp': alert[5],
        'status': alert[6]
    } for alert in alerts])

@app.route('/api/stats')
def get_stats():
    with db_lock:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM user_interactions")
        total_interactions = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(DISTINCT user_phone) FROM user_interactions")
        unique_users = cursor.fetchone()[0] or 0

        cursor.execute("SELECT language, COUNT(*) FROM user_interactions GROUP BY language")
        language_stats = dict(cursor.fetchall())

        cursor.execute("SELECT COUNT(*) FROM government_alerts WHERE date(timestamp) = date('now')")
        today_alerts = cursor.fetchone()[0] or 0

        conn.close()

    return jsonify({
        'total_interactions': total_interactions,
        'unique_users': unique_users,
        'language_distribution': language_stats,
        'today_alerts': today_alerts
    })

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)

    print("=" * 50)
    print("🧠 ProtoMinds – Public Health Support System")
    print("=" * 50)
    print("🔗 Main Demo: http://localhost:5000/")
    print("📊 Admin Dashboard: http://localhost:5000/admin")
    print("🔌 WhatsApp Webhook: http://localhost:5000/whatsapp_webhook")
    print("👥 Team: ProtoMinds")
    print("🚀 Starting server...")
    print("=" * 50)

    app.run(debug=True, host='0.0.0.0', port=5000)
