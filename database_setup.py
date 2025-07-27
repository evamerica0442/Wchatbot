import sqlite3
import datetime
import json
from typing import Dict, Any, List, Optional
import os

class DatabaseManager:
    def __init__(self, db_path: str = "chatbot_appointments.db"):
        """Initialize database manager with SQLite database"""
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Initialize database with required tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    address TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create appointments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    phone_number TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    appointment_date DATE NOT NULL,
                    appointment_time TEXT NOT NULL,
                    status TEXT DEFAULT 'confirmed',
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # Create chat_sessions table to track conversation state
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number TEXT UNIQUE NOT NULL,
                    current_state TEXT NOT NULL,
                    session_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create service_types lookup table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS service_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_code TEXT UNIQUE NOT NULL,
                    service_name TEXT NOT NULL,
                    description TEXT,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Create appointment_history table for tracking changes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS appointment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appointment_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    old_values TEXT,
                    new_values TEXT,
                    changed_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (appointment_id) REFERENCES appointments (id)
                )
            ''')
            
            # Insert default service types
            self.insert_default_service_types(cursor)
            
            conn.commit()
            print("✅ Database initialized successfully!")
            
        except sqlite3.Error as e:
            print(f"❌ Error initializing database: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def insert_default_service_types(self, cursor):
        """Insert default service types"""
        default_services = [
            ("1", "Solar Panel Installation", "Complete solar panel system installation"),
            ("2", "Air Conditioning Installation", "AC unit installation and setup"),
            ("3", "Security System Installation", "Home security system setup"),
            ("4", "Home Theater Setup", "Entertainment system installation"),
            ("5", "Other", "Custom installation service")
        ]
        
        cursor.execute("SELECT COUNT(*) FROM service_types")
        if cursor.fetchone()[0] == 0:  # Only insert if table is empty
            cursor.executemany(
                "INSERT INTO service_types (service_code, service_name, description) VALUES (?, ?, ?)",
                default_services
            )
    
    def save_or_update_user(self, phone_number: str, user_data: Dict[str, str]) -> int:
        """Save or update user information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE phone_number = ?", (phone_number,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                # Update existing user
                user_id = existing_user[0]
                cursor.execute('''
                    UPDATE users 
                    SET name = ?, email = ?, address = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE phone_number = ?
                ''', (user_data['name'], user_data['email'], user_data['address'], phone_number))
            else:
                # Insert new user
                cursor.execute('''
                    INSERT INTO users (phone_number, name, email, address)
                    VALUES (?, ?, ?, ?)
                ''', (phone_number, user_data['name'], user_data['email'], user_data['address']))
                user_id = cursor.lastrowid
            
            conn.commit()
            return user_id
            
        except sqlite3.Error as e:
            print(f"❌ Error saving user: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def save_appointment(self, phone_number: str, user_data: Dict[str, str], appointment_data: Dict[str, str]) -> Optional[int]:
        """Save appointment with user information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Save or update user first
            user_id = self.save_or_update_user(phone_number, user_data)
            if not user_id:
                return None
            
            # Save appointment
            cursor.execute('''
                INSERT INTO appointments (user_id, phone_number, service_type, appointment_date, appointment_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                user_id,
                phone_number,
                appointment_data['service_type'],
                appointment_data['date'],
                appointment_data['time']
            ))
            
            appointment_id = cursor.lastrowid
            
            # Log appointment creation
            self.log_appointment_history(
                cursor, appointment_id, "CREATED", None, appointment_data, "chatbot"
            )
            
            conn.commit()
            print(f"✅ Appointment saved with ID: {appointment_id}")
            return appointment_id
            
        except sqlite3.Error as e:
            print(f"❌ Error saving appointment: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def log_appointment_history(self, cursor, appointment_id: int, action: str, old_values: Dict = None, new_values: Dict = None, changed_by: str = "system"):
        """Log appointment changes to history table"""
        cursor.execute('''
            INSERT INTO appointment_history (appointment_id, action, old_values, new_values, changed_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            appointment_id,
            action,
            json.dumps(old_values) if old_values else None,
            json.dumps(new_values) if new_values else None,
            changed_by
        ))
    
    def save_chat_session(self, phone_number: str, state: str, session_data: Dict[str, Any]):
        """Save or update chat session state"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO chat_sessions (phone_number, current_state, session_data, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (phone_number, state, json.dumps(session_data)))
            
            conn.commit()
            
        except sqlite3.Error as e:
            print(f"❌ Error saving chat session: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def get_chat_session(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Retrieve chat session state"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT current_state, session_data 
                FROM chat_sessions 
                WHERE phone_number = ?
            ''', (phone_number,))
            
            result = cursor.fetchone()
            if result:
                return {
                    "state": result[0],
                    "data": json.loads(result[1]) if result[1] else {}
                }
            return None
            
        except sqlite3.Error as e:
            print(f"❌ Error retrieving chat session: {e}")
            return None
        finally:
            conn.close()
    
    def get_user_appointments(self, phone_number: str) -> List[Dict[str, Any]]:
        """Get all appointments for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT a.id, a.service_type, a.appointment_date, a.appointment_time, 
                       a.status, a.created_at, u.name, u.email
                FROM appointments a
                JOIN users u ON a.user_id = u.id
                WHERE a.phone_number = ?
                ORDER BY a.appointment_date DESC, a.appointment_time DESC
            ''', (phone_number,))
            
            appointments = []
            for row in cursor.fetchall():
                appointments.append({
                    "id": row[0],
                    "service_type": row[1],
                    "appointment_date": row[2],
                    "appointment_time": row[3],
                    "status": row[4],
                    "created_at": row[5],
                    "user_name": row[6],
                    "user_email": row[7]
                })
            
            return appointments
            
        except sqlite3.Error as e:
            print(f"❌ Error retrieving appointments: {e}")
            return []
        finally:
            conn.close()
    
    def update_appointment_status(self, appointment_id: int, new_status: str, changed_by: str = "system") -> bool:
        """Update appointment status"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get current appointment data
            cursor.execute('''
                SELECT service_type, appointment_date, appointment_time, status
                FROM appointments WHERE id = ?
            ''', (appointment_id,))
            
            current_data = cursor.fetchone()
            if not current_data:
                return False
            
            old_values = {
                "status": current_data[3]
            }
            new_values = {
                "status": new_status
            }
            
            # Update status
            cursor.execute('''
                UPDATE appointments 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_status, appointment_id))
            
            # Log the change
            self.log_appointment_history(
                cursor, appointment_id, "STATUS_CHANGED", old_values, new_values, changed_by
            )
            
            conn.commit()
            return True
            
        except sqlite3.Error as e:
            print(f"❌ Error updating appointment status: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_appointments_by_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all appointments for a specific date"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT a.id, a.service_type, a.appointment_time, a.status,
                       u.name, u.phone_number, u.email, u.address
                FROM appointments a
                JOIN users u ON a.user_id = u.id
                WHERE a.appointment_date = ?
                ORDER BY a.appointment_time
            ''', (date,))
            
            appointments = []
            for row in cursor.fetchall():
                appointments.append({
                    "id": row[0],
                    "service_type": row[1],
                    "appointment_time": row[2],
                    "status": row[3],
                    "user_name": row[4],
                    "user_phone": row[5],
                    "user_email": row[6],
                    "user_address": row[7]
                })
            
            return appointments
            
        except sqlite3.Error as e:
            print(f"❌ Error retrieving appointments by date: {e}")
            return []
        finally:
            conn.close()
    
    def get_available_time_slots(self, date: str, all_slots: List[str]) -> List[str]:
        """Get available time slots for a specific date"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT appointment_time 
                FROM appointments 
                WHERE appointment_date = ? AND status != 'cancelled'
            ''', (date,))
            
            booked_slots = [row[0] for row in cursor.fetchall()]
            available_slots = [slot for slot in all_slots if slot not in booked_slots]
            
            return available_slots
            
        except sqlite3.Error as e:
            print(f"❌ Error checking available slots: {e}")
            return all_slots
        finally:
            conn.close()
    
    def get_database_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            stats = {}
            
            # Count users
            cursor.execute("SELECT COUNT(*) FROM users")
            stats['total_users'] = cursor.fetchone()[0]
            
            # Count appointments
            cursor.execute("SELECT COUNT(*) FROM appointments")
            stats['total_appointments'] = cursor.fetchone()[0]
            
            # Count confirmed appointments
            cursor.execute("SELECT COUNT(*) FROM appointments WHERE status = 'confirmed'")
            stats['confirmed_appointments'] = cursor.fetchone()[0]
            
            # Count appointments today
            today = datetime.date.today().strftime('%Y-%m-%d')
            cursor.execute("SELECT COUNT(*) FROM appointments WHERE appointment_date = ?", (today,))
            stats['appointments_today'] = cursor.fetchone()[0]
            
            # Count active chat sessions
            cursor.execute("SELECT COUNT(*) FROM chat_sessions")
            stats['active_sessions'] = cursor.fetchone()[0]
            
            return stats
            
        except sqlite3.Error as e:
            print(f"❌ Error getting database stats: {e}")
            return {}
        finally:
            conn.close()
    
    def cleanup_old_sessions(self, days_old: int = 7):
        """Clean up old chat sessions"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_old)
            cursor.execute('''
                DELETE FROM chat_sessions 
                WHERE updated_at < ?
            ''', (cutoff_date.strftime('%Y-%m-%d %H:%M:%S'),))
            
            deleted_count = cursor.rowcount
            conn.commit()
            print(f"✅ Cleaned up {deleted_count} old chat sessions")
            
        except sqlite3.Error as e:
            print(f"❌ Error cleaning up sessions: {e}")
            conn.rollback()
        finally:
            conn.close()

def setup_database():
    """Initialize the database - run this once to set up everything"""
    print("🔧 Setting up WhatsApp Chatbot Database...")
    
    # Create database manager instance
    db_manager = DatabaseManager()
    
    # Display stats
    stats = db_manager.get_database_stats()
    print("\n📊 Database Statistics:")
    print(f"   Total Users: {stats.get('total_users', 0)}")
    print(f"   Total Appointments: {stats.get('total_appointments', 0)}")
    print(f"   Confirmed Appointments: {stats.get('confirmed_appointments', 0)}")
    print(f"   Appointments Today: {stats.get('appointments_today', 0)}")
    print(f"   Active Chat Sessions: {stats.get('active_sessions', 0)}")
    
    print("\n✅ Database setup complete!")
    print(f"📁 Database file: {db_manager.db_path}")
    
    return db_manager

if __name__ == "__main__":
    # Run database setup
    db_manager = setup_database()
    
    # Example usage:
    print("\n🧪 Testing database operations...")
    
    # Test saving a sample appointment
    sample_user_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "address": "123 Main St, City, State 12345"
    }
    
    sample_appointment_data = {
        "service_type": "Solar Panel Installation",
        "date": "2025-08-01",
        "time": "10:00 AM"
    }
    
    # Save test appointment
    appointment_id = db_manager.save_appointment(
        phone_number="+1234567890",
        user_data=sample_user_data,
        appointment_data=sample_appointment_data
    )
    
    if appointment_id:
        print(f"✅ Test appointment created with ID: {appointment_id}")
        
        # Test retrieving appointments
        appointments = db_manager.get_user_appointments("+1234567890")
        print(f"📅 Found {len(appointments)} appointments for test user")
        
        # Test updating appointment status
        success = db_manager.update_appointment_status(appointment_id, "completed", "test_admin")
        if success:
            print("✅ Appointment status updated successfully")
    
    print("\n🎉 Database setup and testing complete!")