from flask_sqlalchemy import SQLAlchemy
from app import sqlitedb, UserMixin, secrets, hashlib
from datetime import datetime

class Changes(sqlitedb.Model):
    change_id = sqlitedb.Column(sqlitedb.Integer, primary_key=True)
    agent_name = sqlitedb.Column(sqlitedb.String(100), nullable=False)
    old_text = sqlitedb.Column(sqlitedb.String(5000), nullable=False)
    new_text = sqlitedb.Column(sqlitedb.String(5000), nullable=False)
    validated = sqlitedb.Column(sqlitedb.Boolean(), nullable=False)
    user_id = sqlitedb.Column(sqlitedb.Integer, sqlitedb.ForeignKey('user.id'), nullable=False)
    @staticmethod
    def get_changes():
        return Changes.query.all()

    @staticmethod
    def save_changes(agent_name, old_text, new_text, validated, user_id):
        changes = Changes.query.filter_by(old_text=old_text).first()
        if changes is None:
            changes = Changes(agent_name=agent_name, old_text=old_text, new_text = new_text, validated = validated, user_id = user_id)
            sqlitedb.session.add(changes)
        else:
            changes.user_id = user_id
        sqlitedb.session.commit()

class User(UserMixin, sqlitedb.Model):
    id = sqlitedb.Column(sqlitedb.Integer, primary_key=True)
    username = sqlitedb.Column(sqlitedb.String(100), unique=True, nullable=False)
    password_hash = sqlitedb.Column(sqlitedb.String(200), nullable=False)
    role = sqlitedb.Column(sqlitedb.String(50), default='user')
    chat_history = sqlitedb.relationship('ChatHistory', back_populates='user', lazy=True)

    def set_password(self, password):
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        self.password_hash = f"{salt}${pwd_hash.hex()}"

    def check_password(self, password):
        if not self.password_hash or '$' not in self.password_hash:
            return False
        salt, stored_hash = self.password_hash.split('$')
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return pwd_hash.hex() == stored_hash

class Settings(sqlitedb.Model):
    id = sqlitedb.Column(sqlitedb.Integer, primary_key=True)
    key = sqlitedb.Column(sqlitedb.String(100), unique=True, nullable=False)
    value = sqlitedb.Column(sqlitedb.Text, nullable=True)

    @staticmethod
    def get_setting(key):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else None

    @staticmethod
    def save_setting(key, value):
        setting = Settings.query.filter_by(key=key).first()
        if setting is None:
            setting = Settings(key=key, value=value)
            sqlitedb.session.add(setting)
        else:
            setting.value = value
        sqlitedb.session.commit()

class Residents(sqlitedb.Model):
    resident_id = sqlitedb.Column(sqlitedb.Integer, primary_key=True)
    name = sqlitedb.Column(sqlitedb.String(100), nullable=False)
    type = sqlitedb.Column(sqlitedb.String(50), nullable=False) 
    room = sqlitedb.Column(sqlitedb.String(50), nullable=False)
    voucher = sqlitedb.Column(sqlitedb.String(50), nullable=False)

    @staticmethod
    def get_all_residents():
        return Residents.query.all()
    
    @staticmethod
    def get_residents_by_room(room):
        return Residents.query.filter_by(room=room).all()
    
    @staticmethod
    def save_resident(name, resident_type, room, voucher):
        resident = Residents.query.filter_by(name=name, room=room).first()
        
        if resident is None:
            resident = Residents(
                name=name,
                type=resident_type,
                room=room,
                voucher = voucher
            )
            sqlitedb.session.add(resident)
        
        sqlitedb.session.commit()
        return resident
    
class ChatHistory(sqlitedb.Model):
    id = sqlitedb.Column(sqlitedb.Integer, primary_key=True)
    user_id = sqlitedb.Column(sqlitedb.Integer, sqlitedb.ForeignKey('user.id'), nullable=False)
    message = sqlitedb.Column(sqlitedb.Text, nullable=False)
    response = sqlitedb.Column(sqlitedb.Text, nullable=False)
    message_type = sqlitedb.Column(sqlitedb.String(20), nullable=False)  
    timestamp = sqlitedb.Column(sqlitedb.DateTime, default=datetime.utcnow)
    
    user = sqlitedb.relationship('User', back_populates='chat_history')
    
    @staticmethod
    def save_chat_message(user_id, message, response, message_type='ai_chat'):
        chat_entry = ChatHistory(
            user_id=user_id,
            message=message,
            response=response,
            message_type=message_type
        )
        sqlitedb.session.add(chat_entry)
        sqlitedb.session.commit()
        return chat_entry
    
    @staticmethod
    def get_user_chat_history(user_id, limit=50):
        return ChatHistory.query.filter_by(user_id=user_id)\
                               .order_by(ChatHistory.timestamp.desc())\
                               .limit(limit)\
                               .all()
    
    @staticmethod
    def get_recent_chat_history(user_id, limit=10):
        return ChatHistory.query.filter_by(user_id=user_id)\
                               .order_by(ChatHistory.timestamp.asc())\
                               .limit(limit)\
                               .all()
    
    @staticmethod
    def clear_user_history(user_id):
        ChatHistory.query.filter_by(user_id=user_id).delete()
        sqlitedb.session.commit()
    
    @staticmethod
    def get_all_chat_stats():
        from sqlalchemy import func
        return sqlitedb.session.query(
            ChatHistory.message_type,
            func.count(ChatHistory.id).label('count')
        ).group_by(ChatHistory.message_type).all()