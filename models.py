from extensions import db
from flask_login import UserMixin
from datetime import datetime

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='passenger') # admin, staff, passenger
    
    bookings = db.relationship('Booking', backref='user', lazy=True)
    crew_assignments = db.relationship('CrewAssignment', backref='user', lazy=True)

class Aircraft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(100), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    registration_number = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active') # active, maintenance
    
    flights = db.relationship('Flight', backref='aircraft', lazy=True)

class Flight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flight_number = db.Column(db.String(10), unique=True, nullable=False)
    source = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    departure_time = db.Column(db.DateTime, nullable=False)
    arrival_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='scheduled') # scheduled, delayed, cancelled, completed
    aircraft_id = db.Column(db.Integer, db.ForeignKey('aircraft.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    
    bookings = db.relationship('Booking', backref='flight', cascade='all, delete-orphan', lazy=True)
    crew_assignments = db.relationship('CrewAssignment', backref='flight', cascade='all, delete-orphan', lazy=True)

class Passenger(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    passport_number = db.Column(db.String(20), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    
    bookings = db.relationship('Booking', backref='passenger', lazy=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_reference = db.Column(db.String(10), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    flight_id = db.Column(db.Integer, db.ForeignKey('flight.id'), nullable=False)
    passenger_id = db.Column(db.Integer, db.ForeignKey('passenger.id'), nullable=False)
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='confirmed') # confirmed, cancelled
    seat_number = db.Column(db.String(5), nullable=False)
    payment_status = db.Column(db.String(20), default='pending') # pending, paid
    seat_class = db.Column(db.String(20), default='Economy')  # Economy, Business, First Class
    meal_preference = db.Column(db.String(50), default='Standard')  # Standard, Vegetarian, Vegan, Halal
    
    # Relationships with cascading delete
    baggages = db.relationship('Baggage', backref='booking', cascade='all, delete-orphan', lazy=True)

class CrewAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flight_id = db.Column(db.Integer, db.ForeignKey('flight.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(50), nullable=False) # Pilot, Cabine Crew, etc.

class Baggage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    tag_number = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.String(20), default='checked-in') # checked-in, in-transit, arrived, lost
    

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<SystemSetting {self.key}:{self.value}>'
