from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import json
import datetime
import re
from typing import Dict, Any
from database_setup import DatabaseManager
from notification_system import notification_manager, admin_notifications

app = Flask(__name__)

# Twilio configuration (replace with your actual credentials)
TWILIO_ACCOUNT_SID = 'ACb82a7c4a7be7865d6246ad61508fc23f'
TWILIO_AUTH_TOKEN = '70056081d6a9045f227611b9c662ba11'
TWILIO_PHONE_NUMBER = 'whatsapp:+14155238886'  # Twilio Sandbox number

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Initialize database manager
db_manager = DatabaseManager()

# In-memory storage for temporary session data (database stores persistent data)
user_sessions = {}

# Available time slots for appointments
AVAILABLE_SLOTS = [
    "09:00 AM", "10:00 AM", "11:00 AM", "12:00 PM",
    "01:00 PM", "02:00 PM", "03:00 PM", "04:00 PM"
]

class ChatbotStates:
    WELCOME = "welcome"
    COLLECTING_NAME = "collecting_name"
    COLLECTING_PHONE = "collecting_phone"
    COLLECTING_EMAIL = "collecting_email"
    COLLECTING_ADDRESS = "collecting_address"
    COLLECTING_SERVICE_TYPE = "collecting_service_type"
    SELECTING_DATE = "selecting_date"
    SELECTING_TIME = "selecting_time"
    CONFIRMING_APPOINTMENT = "confirming_appointment"
    COMPLETED = "completed"

class InstallationChatbot:
    def __init__(self):
        self.service_types = {
            "1": "Solar Panel Installation",
            "2": "Air Conditioning Installation",
            "3": "Security System Installation",
            "4": "Home Theater Setup",
            "5": "Other (specify in notes)"
        }
    
    def get_user_session(self, phone_number: str) -> Dict[str, Any]:
        """Get or create user session - now with database persistence"""
        if phone_number not in user_sessions:
            # Try to load from database first
            db_session = db_manager.get_chat_session(phone_number)
            if db_session:
                user_sessions[phone_number] = {
                    "state": db_session["state"],
                    "user_info": db_session["data"].get("user_info", {}),
                    "appointment_info": db_session["data"].get("appointment_info", {}),
                    "phone_number": phone_number
                }
            else:
                # Create new session
                user_sessions[phone_number] = {
                    "state": ChatbotStates.WELCOME,
                    "user_info": {},
                    "appointment_info": {},
                    "phone_number": phone_number
                }
        return user_sessions[phone_number]
    
    def validate_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def validate_phone(self, phone: str) -> bool:
        """Validate phone number format"""
        # Remove spaces, dashes, and parentheses
        clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
        # Check if it's a valid length and contains only digits and +
        return re.match(r'^\+?[0-9]{10,15}$', clean_phone) is not None
    
    def get_available_dates(self) -> list:
        """Get next 7 available dates"""
        dates = []
        today = datetime.date.today()
        for i in range(1, 8):  # Next 7 days excluding today
            date = today + datetime.timedelta(days=i)
            # Skip Sundays (assuming business doesn't work on Sundays)
            if date.weekday() != 6:
                dates.append(date.strftime("%Y-%m-%d"))
        return dates
    
    def get_available_time_slots(self, date: str) -> list:
        """Get available time slots for a specific date from database"""
        return db_manager.get_available_time_slots(date, AVAILABLE_SLOTS)
    
    def process_message(self, phone_number: str, message: str) -> str:
        """Process incoming message and return response"""
        session = self.get_user_session(phone_number)
        state = session["state"]
        message = message.strip()
        
        # Save session state to database after each interaction
        def save_session_state():
            db_manager.save_chat_session(
                phone_number, 
                session["state"], 
                {
                    "user_info": session["user_info"],
                    "appointment_info": session["appointment_info"]
                }
            )
        
        if message.lower() in ['start', 'restart', 'begin']:
            response = self.handle_welcome(session)
            save_session_state()
            return response
        
        if state == ChatbotStates.WELCOME:
            response = self.handle_welcome(session)
        
        elif state == ChatbotStates.COLLECTING_NAME:
            response = self.handle_name_collection(session, message)
        
        elif state == ChatbotStates.COLLECTING_PHONE:
            response = self.handle_phone_collection(session, message)
        
        elif state == ChatbotStates.COLLECTING_EMAIL:
            response = self.handle_email_collection(session, message)
        
        elif state == ChatbotStates.COLLECTING_ADDRESS:
            response = self.handle_address_collection(session, message)
        
        elif state == ChatbotStates.COLLECTING_SERVICE_TYPE:
            response = self.handle_service_type_collection(session, message)
        
        elif state == ChatbotStates.SELECTING_DATE:
            response = self.handle_date_selection(session, message)
        
        elif state == ChatbotStates.SELECTING_TIME:
            response = self.handle_time_selection(session, message)
        
        elif state == ChatbotStates.CONFIRMING_APPOINTMENT:
            response = self.handle_appointment_confirmation(session, message)
        
        else:
            response = "I'm not sure how to help with that. Type 'start' to begin scheduling an appointment."
        
        # Save session state after processing
        save_session_state()
        return response
    
    def handle_welcome(self, session: Dict[str, Any]) -> str:
        session["state"] = ChatbotStates.COLLECTING_NAME
        return ("🔧 Welcome to our Installation Service!\n\n"
                "I'll help you schedule an installation appointment. "
                "Let's start by collecting some basic information.\n\n"
                "What's your full name?")
    
    def handle_name_collection(self, session: Dict[str, Any], message: str) -> str:
        if len(message) < 2:
            return "Please enter a valid name (at least 2 characters)."
        
        session["user_info"]["name"] = message
        session["state"] = ChatbotStates.COLLECTING_PHONE
        return f"Thanks {message}! 📱\n\nNow, please provide your phone number:"
    
    def handle_phone_collection(self, session: Dict[str, Any], message: str) -> str:
        if not self.validate_phone(message):
            return ("Please enter a valid phone number. "
                   "Examples: +1234567890, (123) 456-7890, or 123-456-7890")
        
        session["user_info"]["phone"] = message
        session["state"] = ChatbotStates.COLLECTING_EMAIL
        return "Great! 📧\n\nWhat's your email address?"
    
    def handle_email_collection(self, session: Dict[str, Any], message: str) -> str:
        if not self.validate_email(message):
            return "Please enter a valid email address (e.g., example@email.com)"
        
        session["user_info"]["email"] = message
        session["state"] = ChatbotStates.COLLECTING_ADDRESS
        return "Perfect! 🏠\n\nPlease provide your installation address:"
    
    def handle_address_collection(self, session: Dict[str, Any], message: str) -> str:
        if len(message) < 10:
            return "Please provide a complete address including street, city, and zip code."
        
        session["user_info"]["address"] = message
        session["state"] = ChatbotStates.COLLECTING_SERVICE_TYPE
        
        services_text = "What type of installation do you need? 🔧\n\n"
        for key, value in self.service_types.items():
            services_text += f"{key}. {value}\n"
        services_text += "\nPlease reply with the number (1-5):"
        
        return services_text
    
    def handle_service_type_collection(self, session: Dict[str, Any], message: str) -> str:
        if message not in self.service_types:
            return ("Please select a valid option (1-5):\n" + 
                   "\n".join([f"{k}. {v}" for k, v in self.service_types.items()]))
        
        session["user_info"]["service_type"] = self.service_types[message]
        session["state"] = ChatbotStates.SELECTING_DATE
        
        dates = self.get_available_dates()
        date_text = "Great choice! 📅\n\nPlease select your preferred date:\n\n"
        for i, date in enumerate(dates, 1):
            date_obj = datetime.datetime.strptime(date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            date_text += f"{i}. {formatted_date}\n"
        date_text += "\nReply with the number (1-{}):"
        
        session["available_dates"] = dates
        return date_text.format(len(dates))
    
    def handle_date_selection(self, session: Dict[str, Any], message: str) -> str:
        try:
            choice = int(message)
            available_dates = session.get("available_dates", [])
            
            if 1 <= choice <= len(available_dates):
                selected_date = available_dates[choice - 1]
                session["appointment_info"]["date"] = selected_date
                session["state"] = ChatbotStates.SELECTING_TIME
                
                time_text = "Perfect! ⏰\n\nPlease select your preferred time:\n\n"
                for i, time_slot in enumerate(AVAILABLE_SLOTS, 1):
                    time_text += f"{i}. {time_slot}\n"
                time_text += f"\nReply with the number (1-{len(AVAILABLE_SLOTS)}):"
                
                return time_text
            else:
                return f"Please select a valid option (1-{len(available_dates)})"
        
        except ValueError:
            return "Please enter a valid number."
    
    def handle_time_selection(self, session: Dict[str, Any], message: str) -> str:
        try:
            choice = int(message)
            selected_date = session["appointment_info"]["date"]
            
            # Get available time slots for the selected date
            available_slots = self.get_available_time_slots(selected_date)
            
            if not available_slots:
                return ("Sorry, no time slots are available for this date. "
                       "Please go back and select a different date by typing 'start'.")
            
            if 1 <= choice <= len(available_slots):
                selected_time = available_slots[choice - 1]
                session["appointment_info"]["time"] = selected_time
                session["state"] = ChatbotStates.CONFIRMING_APPOINTMENT
                
                # Format confirmation message
                user_info = session["user_info"]
                appointment_info = session["appointment_info"]
                
                date_obj = datetime.datetime.strptime(appointment_info["date"], "%Y-%m-%d")
                formatted_date = date_obj.strftime("%A, %B %d, %Y")
                
                confirmation = (
                    "📋 *APPOINTMENT SUMMARY*\n\n"
                    f"*Name:* {user_info['name']}\n"
                    f"*Phone:* {user_info['phone']}\n"
                    f"*Email:* {user_info['email']}\n"
                    f"*Address:* {user_info['address']}\n"
                    f"*Service:* {user_info['service_type']}\n"
                    f"*Date:* {formatted_date}\n"
                    f"*Time:* {selected_time}\n\n"
                    "Is this information correct?\n"
                    "Reply 'YES' to confirm or 'NO' to cancel."
                )
                
                return confirmation
            else:
                return f"Please select a valid time slot (1-{len(available_slots)})"
        
        except ValueError:
            return "Please enter a valid number."
    
    def handle_appointment_confirmation(self, session: Dict[str, Any], message: str) -> str:
        message_lower = message.lower()
        
        if message_lower in ['yes', 'y', 'confirm', 'correct']:
            # Save appointment to database
            appointment_id = self.save_appointment(session)
            
            if appointment_id:
                session["state"] = ChatbotStates.COMPLETED
                
                user_info = session["user_info"]
                appointment_info = session["appointment_info"]
                date_obj = datetime.datetime.strptime(appointment_info["date"], "%Y-%m-%d")
                formatted_date = date_obj.strftime("%A, %B %d, %Y")
                
                # Send confirmation notifications
                try:
                    notification_manager.send_all_notifications(
                        "appointment_confirmed",
                        user_info,
                        appointment_info,
                        appointment_id
                    )
                    print(f"📨 Notifications sent for appointment #{appointment_id}")
                except Exception as e:
                    print(f"⚠️ Notification sending failed: {e}")
                
                return (
                    "✅ *APPOINTMENT CONFIRMED!*\n\n"
                    f"Your {user_info['service_type']} appointment has been scheduled for "
                    f"{formatted_date} at {appointment_info['time']}.\n\n"
                    f"📋 Appointment ID: #{appointment_id}\n"
                    "📧 You'll receive a confirmation email shortly.\n"
                    "📱 We'll send you a reminder 24 hours before your appointment.\n\n"
                    "Thank you for choosing our service! 🔧\n\n"
                    "Type 'start' if you need to schedule another appointment."
                )
            else:
                return ("❌ Sorry, there was an error saving your appointment. "
                       "Please try again by typing 'start'.")
        
        elif message_lower in ['no', 'n', 'cancel']:
            # Reset session
            session["state"] = ChatbotStates.WELCOME
            session["user_info"] = {}
            session["appointment_info"] = {}
            
            return ("❌ Appointment cancelled.\n\n"
                   "No problem! Type 'start' when you're ready to schedule an appointment.")
        
        else:
            return "Please reply 'YES' to confirm the appointment or 'NO' to cancel."
    
    def save_appointment(self, session: Dict[str, Any]) -> int:
        """Save appointment to database with enhanced error handling"""
        try:
            phone_number = session.get("phone_number")
            user_info = session["user_info"]
            appointment_info = session["appointment_info"]
            
            # Debug logging
            print(f"🔍 Attempting to save appointment for {phone_number}")
            print(f"🔍 User info: {user_info}")
            print(f"🔍 Appointment info: {appointment_info}")
            
            # Validate required data
            if not phone_number:
                print("❌ Missing phone number")
                return None
                
            if not all(key in user_info for key in ['name', 'email', 'address', 'service_type']):
                print(f"❌ Missing user info. Have: {list(user_info.keys())}")
                return None
                
            if not all(key in appointment_info for key in ['date', 'time']):
                print(f"❌ Missing appointment info. Have: {list(appointment_info.keys())}")
                return None
            
            # Save to database using DatabaseManager
            appointment_id = db_manager.save_appointment(
                phone_number=phone_number,
                user_data=user_info,
                appointment_data={
                    'service_type': user_info['service_type'],  # Make sure service_type is in appointment_data
                    'date': appointment_info['date'],
                    'time': appointment_info['time']
                }
            )
            
            if appointment_id:
                print(f"✅ Appointment saved to database with ID: {appointment_id}")
                # Here you could also send confirmation emails, SMS, etc.
                # send_confirmation_email(user_info, appointment_info, appointment_id)
                return appointment_id
            else:
                print("❌ Failed to save appointment to database - db_manager returned None")
                return None
                
        except Exception as e:
            print(f"❌ Error saving appointment: {e}")
            import traceback
            traceback.print_exc()
            return None

# Initialize chatbot
chatbot = InstallationChatbot()

@app.route("/", methods=['POST'])
@app.route("/webhook", methods=['POST'])
def webhook():
    """Handle incoming WhatsApp messages"""
    try:
        incoming_msg = request.values.get('Body', '').strip()
        phone_number = request.values.get('From', '')
        
        print(f"📱 Received message from {phone_number}: {incoming_msg}")
        
        # Ensure phone number is stored in session for database operations
        if phone_number not in user_sessions:
            user_sessions[phone_number] = {
                "state": ChatbotStates.WELCOME,
                "user_info": {},
                "appointment_info": {},
                "phone_number": phone_number
            }
        else:
            # Make sure phone_number is always in session
            user_sessions[phone_number]["phone_number"] = phone_number
        
        # Process the message
        response_text = chatbot.process_message(phone_number, incoming_msg)
        
        print(f"🤖 Sending response: {response_text[:100]}...")
        
        # Create Twilio response
        resp = MessagingResponse()
        resp.message(response_text)
        
        return str(resp)
    
    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        resp = MessagingResponse()
        resp.message("Sorry, I'm experiencing technical difficulties. Please try again later.")
        return str(resp)

@app.route("/", methods=['GET'])
def home():
    """Home page with basic info"""
    return {
        "service": "WhatsApp Installation Chatbot",
        "status": "running",
        "endpoints": {
            "webhook": "/webhook (POST) - WhatsApp webhook",
            "health": "/health (GET) - Health check",
            "appointments": "/appointments/<date> (GET) - Daily appointments",
            "user_appointments": "/user/<phone>/appointments (GET) - User appointments"
        },
        "database_stats": db_manager.get_database_stats()
    }
def send_message():
    """Send a message to a WhatsApp number (for testing)"""
    data = request.get_json()
    to_number = data.get('to')
    message = data.get('message')
    
    try:
        message = client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=f'whatsapp:{to_number}'
        )
        return {"success": True, "message_sid": message.sid}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.route("/send_message", methods=['POST'])
def health():
    """Health check endpoint with database stats"""
    try:
        stats = db_manager.get_database_stats()
        return {
            "status": "healthy", 
            "active_sessions": len(user_sessions),
            "database_stats": stats
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route("/appointments/<date>")
def get_appointments_by_date(date):
    """Get all appointments for a specific date (YYYY-MM-DD format)"""
    try:
        appointments = db_manager.get_appointments_by_date(date)
        return {"date": date, "appointments": appointments}
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/debug/test_appointment", methods=['POST'])
def test_appointment():
    """Test endpoint to debug appointment saving"""
    try:
        # Test data
        test_phone = "+1234567890"
        test_user_data = {
            "name": "Test User",
            "email": "test@example.com",
            "address": "123 Test St, Test City, TS 12345",
            "service_type": "Solar Panel Installation"
        }
        test_appointment_data = {
            "service_type": "Solar Panel Installation",
            "date": "2025-08-01",
            "time": "10:00 AM"
        }
        
        print(f"🧪 Testing appointment save with:")
        print(f"   Phone: {test_phone}")
        print(f"   User: {test_user_data}")
        print(f"   Appointment: {test_appointment_data}")
        
        appointment_id = db_manager.save_appointment(
            phone_number=test_phone,
            user_data=test_user_data,
            appointment_data=test_appointment_data
        )
        
        if appointment_id:
            return {
                "success": True, 
                "appointment_id": appointment_id,
                "message": "Test appointment saved successfully"
            }
        else:
            return {
                "success": False,
                "message": "Failed to save test appointment"
            }, 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "message": "Exception occurred during test"
        }, 500

@app.route("/admin/schedule/<date>")
def send_daily_schedule(date):
    """Send daily schedule to admin email"""
    admin_email = request.args.get('email', 'admin@yourcompany.com')
    
    try:
        success = admin_notifications.send_daily_schedule_email(admin_email, date)
        if success:
            return {"success": True, "message": f"Daily schedule sent to {admin_email}"}
        else:
            return {"success": False, "message": "Failed to send schedule"}, 500
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/admin/test_notifications", methods=['POST'])
def test_notifications():
    """Test notification system"""
    data = request.get_json()
    phone = data.get('phone', '+1234567890')
    email = data.get('email', 'test@example.com')
    
    try:
        admin_notifications.send_test_notification(phone, email)
        return {"success": True, "message": "Test notifications sent"}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

@app.route("/admin/send_reminders", methods=['POST'])
def manual_send_reminders():
    """Manually trigger reminder check"""
    try:
        notification_manager.check_upcoming_appointments()
        return {"success": True, "message": "Reminder check completed"}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

@app.route("/admin/test_admin_whatsapp", methods=['POST'])
def test_admin_whatsapp():
    """Test admin WhatsApp notification"""
    try:
        admin_notifications.send_test_admin_notification()
        return {"success": True, "message": "Test admin WhatsApp notification sent"}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

@app.route("/admin/daily_summary", methods=['POST'])
def send_daily_summary_now():
    """Send daily summary to admin WhatsApp immediately"""
    try:
        success = admin_notifications.send_daily_summary_now()
        if success:
            return {"success": True, "message": "Daily summary sent to admin WhatsApp"}
        else:
            return {"success": False, "message": "Failed to send daily summary"}, 500
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

@app.route("/admin/cancel_appointment/<int:appointment_id>", methods=['POST'])
def cancel_appointment(appointment_id):
    """Cancel an appointment and notify admin"""
    try:
        # Update appointment status in database
        success = db_manager.update_appointment_status(appointment_id, "cancelled", "admin")
        
        if success:
            # Get appointment details for notification
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.service_type, a.appointment_date, a.appointment_time,
                       u.name, u.phone_number, u.email, u.address
                FROM appointments a
                JOIN users u ON a.user_id = u.id
                WHERE a.id = ?
            ''', (appointment_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                user_data = {
                    'name': result[3],
                    'phone': result[4],
                    'email': result[5],
                    'address': result[6]
                }
                
                appointment_data = {
                    'service_type': result[0],
                    'date': result[1],
                    'time': result[2]
                }
                
                # Send cancellation notification to admin
                notification_manager.send_admin_whatsapp_notification(
                    "appointment_cancelled",
                    user_data,
                    appointment_data,
                    appointment_id
                )
            
            return {"success": True, "message": f"Appointment {appointment_id} cancelled and admin notified"}
        else:
            return {"success": False, "message": "Failed to cancel appointment"}, 500
            
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

@app.route("/user/<phone_number>/appointments")
def get_user_appointments(phone_number):
    """Get all appointments for a specific user"""
    try:
        # Clean phone number format
        clean_phone = phone_number.replace(' ', '').replace('-', '')
        if not clean_phone.startswith('+'):
            clean_phone = '+' + clean_phone
            
        appointments = db_manager.get_user_appointments(clean_phone)
        return {"phone_number": clean_phone, "appointments": appointments}
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == '__main__':
    print("WhatsApp Installation Chatbot starting...")
    print("Make sure to:")
    print("1. Set your Twilio credentials")
    print("2. Configure your webhook URL in Twilio Console")
    print("3. Set up WhatsApp Sandbox or get approval for production")
    
    # Test database connection on startup
    try:
        print("🔍 Testing database connection...")
        stats = db_manager.get_database_stats()
        print(f"✅ Database connected! Stats: {stats}")
        
        # Clean up old sessions on startup
        db_manager.cleanup_old_sessions(days_old=7)
        print("✅ Database cleanup completed")
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("Please run 'python database_setup.py' first!")
        import traceback
        traceback.print_exc()
        exit(1)
    
    app.run(debug=True, host='0.0.0.0', port=10000)