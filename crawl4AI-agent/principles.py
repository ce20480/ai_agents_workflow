import hashlib
from datetime import datetime

class UserManager:
    def __init__(self, db_connection):
        self.db = db_connection
        
    def create_user(self, username, email, password):
        # Hash password
        hashed_password = self._hash_password(password)
        
        # Save to database
        self.db.execute("INSERT INTO users VALUES (?, ?, ?)", 
                        [username, email, hashed_password])
    
        # Send welcome email
        self._send_welcome_email(email)
        
        # Log activity
        print(f"User {username} created at {datetime.now()}")
        
    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
        
    def _send_welcome_email(self, email):
        # Code to send email
        print(f"Welcome email sent to {email}")

class UserDatabase:
    def __init__(self, database_path):
        self.database_path = database_path

    def create_user(self, username, email, password):
        # Hash password
        hashed_password = self.password_hasher.hash_password(password)

        # Save to database
        self.db.execute("INSERT INTO users VALUES (?, ?, ?)", 
                        [username, email, hashed_password])
        
        # Send welcome email
        self.email_sender.send_email(email, "Welcome to our service", "Welcome to our service")

        # Log activity
        self.logger.log(f"User {username} created at {datetime.now()}")

    
class EmailSender:
    def __init__(self, email_provider):
        self.email_provider = email_provider

    def send_email(self, email, subject, body):
        # Code to send email
        print(f"Email sent to {email} with subject {subject}")

class PasswordHasher:
    def __init__(self):
        pass

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

class Logger:
    def __init__(self):
        pass

    def log(self, message):
        print(f"Logged: {message}")