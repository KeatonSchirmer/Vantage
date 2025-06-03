from database.db import db
from datetime import datetime


class SearchResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job = db.Column(db.String(250))
    company = db.Column(db.String(250))
    location = db.Column(db.String(250))
    description = db.Column(db.Text)
    url = db.Column(db.String(350))
    posted = db.Column(db.String(50))
    requirements = db.Column(db.Text)
    ideal_path = db.Column(db.Text)

def save_results_to_db(results):
    for result in results:
        exists = SearchResult.query.filter_by(
            job = result.get('job'),
            company = result.get('company'),
            url = result.get('url')
        ).first()
        if not exists:
            entry = SearchResult(
                job = result.get('job'),
                company = result.get('company'),
                location = result.get('location'),
                url = result.get('url'),
                posted = result.get('posted')
            )
            db.session.add(entry)
        db.session.commit()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    degree = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    resume_filename = db.Column(db.String(200))
    profile_pic = db.Column(db.String(120), nullable=True)
    
    def __repr__(self):
        return f'<User {self.username}>'
    
class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('search_result.id'), nullable=False)
    status = db.Column(db.String(50), default='Applied')
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

    user = db.relationship('User', backref='applications')
    job = db.relationship('SearchResult', backref='applications')    
    
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    job_id = db.Column(db.Integer, db.ForeignKey('search_result.id'), nullable=True)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='received_messages')    

class SavedListing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    job_id = db.Column(db.Integer, db.ForeignKey('search_result.id'))
    