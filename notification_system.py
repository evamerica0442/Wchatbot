import smtplib
import schedule
import time
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from twilio.rest import Client
import requests
import json
from typing import Dict, Any, List
from database_setup import DatabaseManager

class NotificationManager:
    def __init__(self):
        # Email configuration (Gmail example)
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email_username = "elmar.america@gmail.com"  # Replace with your email
        self.email_password = "hbpr poqs fcas jjyo"     # Replace with your app password
        self.from_email = "elmar.america@gmail.com"
        
        # Twilio configuration for SMS
        self.twilio_account_sid = 'ACb82a7c4a7be7865d6246ad61508fc23f'  # Replace with your Twilio SID
        self.twilio_auth_token = '70056081d6a9045f227611b9c662ba11'    # Replace with your Twilio token
        self.twilio_phone = '+18777804236'             # Replace with your Twilio phone number
        
        # WhatsApp configuration
        self.whatsapp_phone = 'whatsapp:+14155238886' # Twilio WhatsApp number
        
        # Admin WhatsApp numbers for forwarding notifications
        self.admin_whatsapp_numbers = [
            "+27812507572",  # Replace with admin/manager WhatsApp number
            "+27610337902",  # Add multiple admin numbers if needed
        ]
        
        # Webhook for external notifications (optional)
        self.webhook_url = "https://21b19b54b711.ngrok-free.app/appointment-notification"
        
        # Initialize Twilio client
        try:
            self.twilio_client = Client(self.twilio_account_sid, self.twilio_auth_token)
        except Exception as e:
            print(f"❌ Twilio initialization failed: {e}")
            self.twilio_client = None
        
        # Initialize database
        self.db_manager = DatabaseManager()
        
        # Start scheduler in background
        self.start_scheduler()
    
    def send_admin_whatsapp_notification(self, event_type: str, user_data: Dict[str, str], appointment_data: Dict[str, str], appointment_id: int) -> bool:
        """Send WhatsApp notification to admin numbers"""
        try:
            if not self.twilio_client or not self.admin_whatsapp_numbers:
                print("❌ Twilio client not initialized or no admin numbers configured")
                return False
            
            # Format appointment date
            date_obj = datetime.strptime(appointment_data['date'], "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            
            # Create different messages based on event type
            if event_type == "appointment_confirmed":
                message_body = f"""
🆕 *NEW APPOINTMENT BOOKED*

📋 *Appointment Details:*
• ID: #{appointment_id}
• Service: {appointment_data['service_type']}
• Date: {formatted_date}
• Time: {appointment_data['time']}

👤 *Customer Details:*
• Name: {user_data['name']}
• Phone: {user_data.get('phone', 'N/A')}
• Email: {user_data['email']}
• Address: {user_data['address']}

✅ Confirmation email sent to customer
⏰ Reminder will be sent 24h before appointment

_Booked via WhatsApp Bot at {datetime.now().strftime('%I:%M %p')}_
                """.strip()
                
            elif event_type == "appointment_reminder":
                message_body = f"""
⏰ *REMINDER SENT TO CUSTOMER*

📋 *Tomorrow's Appointment:*
• ID: #{appointment_id}
• Customer: {user_data['name']}
• Service: {appointment_data['service_type']}
• Time: {appointment_data['time']}
• Phone: {user_data.get('phone', 'N/A')}
• Address: {user_data['address']}

📱 SMS & WhatsApp reminder sent to customer

_Reminder sent at {datetime.now().strftime('%I:%M %p')}_
                """.strip()
                
            elif event_type == "appointment_cancelled":
                message_body = f"""
❌ *APPOINTMENT CANCELLED*

📋 *Cancelled Appointment:*
• ID: #{appointment_id}
• Customer: {user_data['name']}
• Service: {appointment_data['service_type']}
• Date: {formatted_date}
• Time: {appointment_data['time']}
• Phone: {user_data.get('phone', 'N/A')}

_Cancelled at {datetime.now().strftime('%I:%M %p')}_
                """.strip()
                
            else:
                message_body = f"""
📋 *APPOINTMENT UPDATE*

Event: {event_type}
ID: #{appointment_id}
Customer: {user_data['name']}
Service: {appointment_data['service_type']}
Date: {formatted_date}
Time: {appointment_data['time']}
                """.strip()
            
            # Send to all admin numbers
            success_count = 0
            for admin_number in self.admin_whatsapp_numbers:
                try:
                    # Ensure WhatsApp format
                    if not admin_number.startswith('whatsapp:'):
                        formatted_number = f"whatsapp:{admin_number}"
                    else:
                        formatted_number = admin_number
                    
                    message = self.twilio_client.messages.create(
                        body=message_body,
                        from_=self.whatsapp_phone,
                        to=formatted_number
                    )
                    
                    print(f"✅ Admin WhatsApp notification sent to {admin_number}: {message.sid}")
                    success_count += 1
                    
                except Exception as e:
                    print(f"❌ Failed to send admin WhatsApp to {admin_number}: {e}")
            
            return success_count > 0
            
        except Exception as e:
            print(f"❌ Failed to send admin WhatsApp notifications: {e}")
            return False
    
    def send_daily_summary_to_admin(self) -> bool:
        """Send daily appointment summary to admin WhatsApp"""
        try:
            if not self.twilio_client or not self.admin_whatsapp_numbers:
                return False
            
            # Get today's and tomorrow's appointments
            today = datetime.now().strftime('%Y-%m-%d')
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            
            today_appointments = self.db_manager.get_appointments_by_date(today)
            tomorrow_appointments = self.db_manager.get_appointments_by_date(tomorrow)
            
            # Create summary message
            message_body = f"""
📊 *DAILY APPOINTMENT SUMMARY*
_{datetime.now().strftime('%A, %B %d, %Y')}_

📅 *TODAY ({len(today_appointments)} appointments):*
"""
            
            if today_appointments:
                for apt in today_appointments:
                    status_emoji = "✅" if apt['status'] == 'confirmed' else "❌" if apt['status'] == 'cancelled' else "⏳"
                    message_body += f"\n{status_emoji} {apt['appointment_time']} - {apt['user_name']} ({apt['service_type']})"
            else:
                message_body += "\n_No appointments today_"
            
            message_body += f"\n\n📅 *TOMORROW ({len(tomorrow_appointments)} appointments):*"
            
            if tomorrow_appointments:
                for apt in tomorrow_appointments:
                    status_emoji = "✅" if apt['status'] == 'confirmed' else "❌" if apt['status'] == 'cancelled' else "⏳"
                    message_body += f"\n{status_emoji} {apt['appointment_time']} - {apt['user_name']} ({apt['service_type']})"
            else:
                message_body += "\n_No appointments tomorrow_"
            
            # Add statistics
            total_stats = self.db_manager.get_database_stats()
            message_body += f"""

📈 *QUICK STATS:*
• Total appointments: {total_stats.get('total_appointments', 0)}
• Confirmed: {total_stats.get('confirmed_appointments', 0)}
• Active chat sessions: {total_stats.get('active_sessions', 0)}

_Summary sent at {datetime.now().strftime('%I:%M %p')}_
            """.strip()
            
            # Send to all admin numbers
            success_count = 0
            for admin_number in self.admin_whatsapp_numbers:
                try:
                    formatted_number = f"whatsapp:{admin_number}" if not admin_number.startswith('whatsapp:') else admin_number
                    
                    message = self.twilio_client.messages.create(
                        body=message_body,
                        from_=self.whatsapp_phone,
                        to=formatted_number
                    )
                    
                    print(f"✅ Daily summary sent to admin {admin_number}: {message.sid}")
                    success_count += 1
                    
                except Exception as e:
                    print(f"❌ Failed to send daily summary to {admin_number}: {e}")
            
            return success_count > 0
            
        except Exception as e:
            print(f"❌ Failed to send daily summary: {e}")
            return False

    def send_confirmation_email(self, user_data: Dict[str, str], appointment_data: Dict[str, str], appointment_id: int) -> bool:
        """Send appointment confirmation email"""
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = user_data['email']
            msg['Subject'] = f"Appointment Confirmation - #{appointment_id}"
            
            # Format appointment date
            date_obj = datetime.strptime(appointment_data['date'], "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            
            # Email body
            body = f"""
            Dear {user_data['name']},

            Thank you for scheduling an appointment with us! Here are your appointment details:

            📋 APPOINTMENT DETAILS:
            • Appointment ID: #{appointment_id}
            • Service: {appointment_data['service_type']}
            • Date: {formatted_date}
            • Time: {appointment_data['time']}
            • Location: {user_data['address']}

            📞 CONTACT INFORMATION:
            • Name: {user_data['name']}
            • Phone: {user_data.get('phone', 'N/A')}
            • Email: {user_data['email']}

            ⏰ IMPORTANT REMINDERS:
            • Please be available at the scheduled time
            • Ensure easy access to the installation area
            • Someone 18+ should be present during installation
            • You'll receive a reminder 24 hours before your appointment

            If you need to reschedule or cancel, please contact us as soon as possible.

            Thank you for choosing our services!

            Best regards,
            Installation Services Team
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email_username, self.email_password)
            text = msg.as_string()
            server.sendmail(self.from_email, user_data['email'], text)
            server.quit()
            
            print(f"✅ Confirmation email sent to {user_data['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send confirmation email: {e}")
            return False
    
    def send_reminder_sms(self, user_data: Dict[str, str], appointment_data: Dict[str, str], appointment_id: int) -> bool:
        """Send SMS reminder"""
        try:
            if not self.twilio_client:
                print("❌ Twilio client not initialized")
                return False
            
            # Format appointment date
            date_obj = datetime.strptime(appointment_data['date'], "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            
            # SMS message
            message_body = f"""
🔧 APPOINTMENT REMINDER

Hi {user_data['name']}, this is a reminder for your appointment tomorrow:

📅 {formatted_date} at {appointment_data['time']}
🏠 Service: {appointment_data['service_type']}
📍 Location: {user_data['address']}
🆔 Appointment ID: #{appointment_id}

Please ensure someone 18+ is available at the scheduled time.

Need to reschedule? Contact us immediately.

Thank you!
            """.strip()
            
            # Send SMS
            message = self.twilio_client.messages.create(
                body=message_body,
                from_=self.twilio_phone,
                to=user_data.get('phone', '')
            )
            
            print(f"✅ SMS reminder sent to {user_data.get('phone', 'N/A')}: {message.sid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send SMS reminder: {e}")
            return False
    
    def send_whatsapp_reminder(self, user_data: Dict[str, str], appointment_data: Dict[str, str], appointment_id: int) -> bool:
        """Send WhatsApp reminder"""
        try:
            if not self.twilio_client:
                print("❌ Twilio client not initialized")
                return False
            
            # Format appointment date
            date_obj = datetime.strptime(appointment_data['date'], "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            
            # WhatsApp message
            message_body = f"""
🔧 *APPOINTMENT REMINDER*

Hi {user_data['name']}! 👋

This is a friendly reminder for your appointment *tomorrow*:

📅 *Date:* {formatted_date}
⏰ *Time:* {appointment_data['time']}
🔧 *Service:* {appointment_data['service_type']}
📍 *Location:* {user_data['address']}
🆔 *ID:* #{appointment_id}

*Please ensure:*
• Someone 18+ is available
• Easy access to installation area
• All necessary permissions ready

Need to reschedule? Reply to this message!

Thank you for choosing our services! 🙏
            """.strip()
            
            # Send WhatsApp message
            phone_number = user_data.get('phone', '')
            if phone_number:
                # Ensure WhatsApp format
                if not phone_number.startswith('whatsapp:'):
                    phone_number = f"whatsapp:{phone_number}"
                
                message = self.twilio_client.messages.create(
                    body=message_body,
                    from_=self.whatsapp_phone,
                    to=phone_number
                )
                
                print(f"✅ WhatsApp reminder sent: {message.sid}")
                return True
            else:
                print("❌ No phone number available for WhatsApp reminder")
                return False
            
        except Exception as e:
            print(f"❌ Failed to send WhatsApp reminder: {e}")
            return False
    
    def send_webhook_notification(self, event_type: str, user_data: Dict[str, str], appointment_data: Dict[str, str], appointment_id: int) -> bool:
        """Send webhook notification to external system"""
        try:
            if not self.webhook_url:
                return True  # Skip if no webhook configured
            
            payload = {
                "event_type": event_type,
                "appointment_id": appointment_id,
                "timestamp": datetime.now().isoformat(),
                "user_data": user_data,
                "appointment_data": appointment_data
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"✅ Webhook notification sent: {event_type}")
                return True
            else:
                print(f"❌ Webhook failed with status {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Webhook notification failed: {e}")
            return False
    
    def send_all_notifications(self, event_type: str, user_data: Dict[str, str], appointment_data: Dict[str, str], appointment_id: int):
        """Send all types of notifications including admin WhatsApp"""
        print(f"📨 Sending {event_type} notifications for appointment #{appointment_id}")
        
        # Send customer notifications
        if event_type == "appointment_confirmed":
            self.send_confirmation_email(user_data, appointment_data, appointment_id)
            self.send_webhook_notification(event_type, user_data, appointment_data, appointment_id)
        
        elif event_type == "appointment_reminder":
            self.send_reminder_sms(user_data, appointment_data, appointment_id)
            self.send_whatsapp_reminder(user_data, appointment_data, appointment_id)
            self.send_webhook_notification(event_type, user_data, appointment_data, appointment_id)
        
        # Always send admin WhatsApp notification
        self.send_admin_whatsapp_notification(event_type, user_data, appointment_data, appointment_id)
    
    def check_upcoming_appointments(self):
        """Check for appointments that need reminders (24 hours before)"""
        try:
            # Get tomorrow's date
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            
            # Get appointments for tomorrow
            appointments = self.db_manager.get_appointments_by_date(tomorrow)
            
            print(f"🔍 Checking reminders for {tomorrow}: Found {len(appointments)} appointments")
            
            for appointment in appointments:
                if appointment['status'] == 'confirmed':
                    # Get user data
                    user_data = {
                        'name': appointment['user_name'],
                        'phone': appointment['user_phone'],
                        'email': appointment['user_email'],
                        'address': appointment['user_address']
                    }
                    
                    appointment_data = {
                        'service_type': appointment['service_type'],
                        'date': tomorrow,
                        'time': appointment['appointment_time']
                    }
                    
                    # Send reminder notifications
                    self.send_all_notifications(
                        "appointment_reminder",
                        user_data,
                        appointment_data,
                        appointment['id']
                    )
                    
                    # Mark as reminded (you could add a 'reminded' field to the database)
                    print(f"✅ Reminder sent for appointment #{appointment['id']}")
        
        except Exception as e:
            print(f"❌ Error checking upcoming appointments: {e}")
    
    def start_scheduler(self):
        """Start the background scheduler for reminders and daily summaries"""
        def run_scheduler():
            # Schedule reminder check daily at 9 AM
            schedule.every().day.at("09:00").do(self.check_upcoming_appointments)
            
            # Schedule daily summary to admin at 8 AM
            schedule.every().day.at("08:00").do(self.send_daily_summary_to_admin)
            
            # Keep scheduler running
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        
        # Run scheduler in background thread
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        print("⏰ Notification scheduler started:")
        print("   • Daily summary to admin: 8:00 AM")
        print("   • Customer reminders: 9:00 AM")
        print(f"   • Admin WhatsApp numbers: {', '.join(self.admin_whatsapp_numbers)}")

# Admin notification functions for immediate testing
class AdminNotifications:
    def __init__(self, notification_manager: NotificationManager):
        self.notification_manager = notification_manager
        self.db_manager = DatabaseManager()
    
    def send_daily_schedule_email(self, admin_email: str, date: str = None):
        """Send daily appointment schedule to admin"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
        
        try:
            appointments = self.db_manager.get_appointments_by_date(date)
            
            # Create email
            msg = MIMEMultipart()
            msg['From'] = self.notification_manager.from_email
            msg['To'] = admin_email
            msg['Subject'] = f"Daily Appointment Schedule - {date}"
            
            # Format date
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            
            if appointments:
                schedule_html = f"""
                <h2>📅 Appointment Schedule for {formatted_date}</h2>
                <p><strong>Total Appointments:</strong> {len(appointments)}</p>
                <table border="1" style="border-collapse: collapse; width: 100%;">
                    <tr style="background-color: #f2f2f2;">
                        <th>Time</th>
                        <th>Customer</th>
                        <th>Service</th>
                        <th>Phone</th>
                        <th>Address</th>
                        <th>Status</th>
                    </tr>
                """
                
                for apt in appointments:
                    schedule_html += f"""
                    <tr>
                        <td>{apt['appointment_time']}</td>
                        <td>{apt['user_name']}</td>
                        <td>{apt['service_type']}</td>
                        <td>{apt['user_phone']}</td>
                        <td>{apt['user_address']}</td>
                        <td>{apt['status']}</td>
                    </tr>
                    """
                
                schedule_html += "</table>"
            else:
                schedule_html = f"""
                <h2>📅 Appointment Schedule for {formatted_date}</h2>
                <p><strong>No appointments scheduled for this date.</strong></p>
                """
            
            msg.attach(MIMEText(schedule_html, 'html'))
            
            # Send email
            server = smtplib.SMTP(self.notification_manager.smtp_server, self.notification_manager.smtp_port)
            server.starttls()
            server.login(self.notification_manager.email_username, self.notification_manager.email_password)
            server.sendmail(self.notification_manager.from_email, admin_email, msg.as_string())
            server.quit()
            
            print(f"✅ Daily schedule sent to {admin_email}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send daily schedule: {e}")
            return False
    
    def send_test_notification(self, phone_number: str, email: str):
        """Send test notification to verify setup"""
        test_user_data = {
            'name': 'Test Customer',
            'phone': phone_number,
            'email': email,
            'address': '123 Test Street, Test City'
        }
        
        test_appointment_data = {
            'service_type': 'Test Installation',
            'date': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'time': '10:00 AM'
        }
        
        # Send test notifications
        self.notification_manager.send_all_notifications(
            "appointment_confirmed",
            test_user_data,
            test_appointment_data,
            999  # Test appointment ID
        )
    
    def send_test_admin_notification(self):
        """Send test notification to admin WhatsApp"""
        test_user_data = {
            'name': 'Test Customer',
            'phone': '+1234567890',
            'email': 'test@example.com',
            'address': '123 Test Street, Test City'
        }
        
        test_appointment_data = {
            'service_type': 'Test Installation',
            'date': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'time': '10:00 AM'
        }
        
        # Send test admin notification
        self.notification_manager.send_admin_whatsapp_notification(
            "appointment_confirmed",
            test_user_data,
            test_appointment_data,
            999
        )
    
    def send_daily_summary_now(self):
        """Send daily summary immediately (for testing)"""
        return self.notification_manager.send_daily_summary_to_admin()

# Initialize notification system
notification_manager = NotificationManager()
admin_notifications = AdminNotifications(notification_manager)