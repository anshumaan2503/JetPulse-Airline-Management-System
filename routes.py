from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from models import User, Flight, Aircraft, Passenger, Booking, CrewAssignment, SystemSetting
from extensions import db, bcrypt
from datetime import datetime, timedelta
from sqlalchemy import func, extract, text
import math
import razorpay
from flask import current_app

# Blueprints
main = Blueprint('main', __name__)
auth = Blueprint('auth', __name__)
admin_routes = Blueprint('admin', __name__, url_prefix='/admin')
staff_routes = Blueprint('staff', __name__, url_prefix='/staff')
passenger_routes = Blueprint('passenger', __name__, url_prefix='/passenger')

# --- Dynamic Pricing Utility ---
MEAL_SURCHARGE = {
    'Standard':   0,
    'Vegetarian': 350,
    'Vegan':      550,
    'Halal':      400,
}

CLASS_MULTIPLIER = {
    'Economy':    1.0,
    'Business':   2.8,
    'First Class': 8.0,
}

def get_dynamic_price(flight, seat_class='Economy', meal='Standard'):
    """Calculates a realistic dynamic price:
    - Base price from DB
    - Surge multiplier: closer departure = higher price (1.0x–2.2x)
    - Weekend surcharge (+12%)
    - Class multiplier
    - Meal add-on (FREE for First Class)
    """
    base = float(flight.price)
    now = datetime.utcnow()
    days_until = max(0, (flight.departure_time - now).days)

    # Surge: 0 days = 2.5x, 7 days = 1.8x, 30+ days = 1.0x (Increased for more rate)
    if days_until == 0:
        surge = 2.5
    elif days_until <= 3:
        surge = 2.2
    elif days_until <= 7:
        surge = 1.8
    elif days_until <= 14:
        surge = 1.5
    elif days_until <= 30:
        surge = 1.2
    else:
        surge = 1.0

    # Weekend surcharge (Friday=4, Saturday=5, Sunday=6)
    dow = flight.departure_time.weekday()
    weekend_mult = 1.15 if dow in (4, 5, 6) else 1.0

    class_mult = CLASS_MULTIPLIER.get(seat_class, 1.0)
    
    # First class includes all meals - set meal add-on to 0
    meal_add = 0 if seat_class == 'First Class' else MEAL_SURCHARGE.get(meal, 0)

    price = math.ceil((base * surge * weekend_mult * class_mult) + meal_add)
    return price

# --- Robust Date Parsing Utility ---
def parse_robust_dt(dt_str):
    """Parses a datetime string in multiple formats (CSV, Form, etc.)"""
    if not dt_str:
        return None
    dt_str = str(dt_str).strip().replace('T', ' ')
    
    # Try common formats
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
            
    # Try truncated version if it looks like it has extra data (e.g. milliseconds)
    if len(dt_str) > 19:
        try:
            return datetime.strptime(dt_str[:19], '%Y-%m-%d %H:%M:%S')
        except:
            pass
    elif len(dt_str) > 16:
        try:
            return datetime.strptime(dt_str[:16], '%Y-%m-%d %H:%M')
        except:
            pass
            
    raise ValueError(f"Unable to parse datetime: {dt_str}")

# --- Main Routes ---
@main.route('/')
def index():
    # Group flights by route (source/destination) and show only the soonest one for each on home page
    from sqlalchemy import func
    # Subquery to find the minimum departure_time per (source, destination)
    subquery = db.session.query(
        Flight.source, 
        Flight.destination, 
        func.min(Flight.departure_time).label('min_dep')
    ).group_by(Flight.source, Flight.destination).subquery()

    flights = Flight.query.join(
        subquery, 
        (Flight.source == subquery.c.source) & 
        (Flight.destination == subquery.c.destination) & 
        (Flight.departure_time == subquery.c.min_dep)
    ).all()

    # Compute dynamic economy prices for display on landing page
    dynamic_prices = {f.id: get_dynamic_price(f, 'Economy', 'Standard') for f in flights}
    return render_template('index.html', flights=flights, dynamic_prices=dynamic_prices)

@main.route('/overview')
def project_overview():
    return render_template('project_overview.html')

@main.route('/search_flights', methods=['POST'])
def search_flights():
    source = request.form.get('source', '').strip()
    destination = request.form.get('destination', '').strip()
    status = request.form.get('status')
    travel_date = request.form.get('travel_date')  # yyyy-mm-dd or empty

    from sqlalchemy import func
    query = Flight.query.filter(
        func.lower(Flight.source) == func.lower(source),
        func.lower(Flight.destination) == func.lower(destination)
    )
    if status and status != 'any':
        query = query.filter_by(status=status)
    if travel_date:
        try:
            from datetime import timedelta
            # Try to parse with time first, then fall back to date-only
            if ' ' in travel_date or 'T' in travel_date:
                # Handle both 'YYYY-MM-DD HH:MM' and ISO 'YYYY-MM-DDTHH:MM'
                clean_date = travel_date.replace('T', ' ').strip()
                # Determine how many parts the date has
                if clean_date.count(':') == 2:
                    dt = datetime.strptime(clean_date, '%Y-%m-%d %H:%M:%S')
                else:
                    dt = datetime.strptime(clean_date, '%Y-%m-%d %H:%M')
                
                # Filter: departure within ±2 hours of chosen time on the same date
                window_start = dt - timedelta(hours=2)
                window_end   = dt + timedelta(hours=2)
                query = query.filter(
                    Flight.departure_time >= window_start,
                    Flight.departure_time <= window_end
                )
            else:
                dt = datetime.strptime(travel_date.strip(), '%Y-%m-%d')
                query = query.filter(
                    func.date(Flight.departure_time) == dt.date()
                )
        except ValueError:
            pass

    # Get all flights for this route (regardless of date) to show alternatives
    all_flights_on_route = Flight.query.filter(
        func.lower(Flight.source) == func.lower(source),
        func.lower(Flight.destination) == func.lower(destination)
    ).order_by(Flight.departure_time.asc()).all()

    # Extract unique available dates (as strings for the template)
    available_dates = sorted(list(set([f.departure_time.strftime('%Y-%m-%d') for f in all_flights_on_route])))

    flights = query.all()
    dynamic_prices = {f.id: get_dynamic_price(f, 'Economy', 'Standard') for f in flights}
    return render_template('flights/search_results.html', 
                         flights=flights,
                         dynamic_prices=dynamic_prices, 
                         travel_date=travel_date,
                         source=source,
                         destination=destination,
                         all_available_dates=available_dates)

# --- Auth Routes ---
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'staff':
                return redirect(url_for('staff.dashboard'))
            else:
                return redirect(url_for('passenger.dashboard'))
        flash('Login unsuccessful. Please check email and password', 'danger')
        
    return render_template('auth/login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'passenger')

        # Check for duplicate email or username before inserting
        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists. Please log in or use a different email.', 'danger')
            return render_template('auth/register.html')
        if User.query.filter_by(username=username).first():
            flash('That username is already taken. Please choose a different one.', 'danger')
            return render_template('auth/register.html')

        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, email=email, password_hash=hashed_pw, role=role)
        db.session.add(user)
        db.session.commit()
        flash('Account created successfully! You can now login.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/register.html')

@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

# --- Admin Routes ---
@admin_routes.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
        
    total_users = User.query.count()
    total_flights = Flight.query.count()
    total_aircrafts = Aircraft.query.count()
    total_bookings = Booking.query.count()
    
    # Calculate total revenue
    total_revenue = db.session.query(db.func.sum(Flight.price)).join(Booking).filter(Booking.payment_status == 'paid').scalar() or 0
    
    recent_bookings = Booking.query.order_by(Booking.booking_date.desc()).limit(5).all()
    flights = Flight.query.all()
    
    # Check payment setting
    gateway_setting = SystemSetting.query.filter_by(key='payment_gateway_enabled').first()
    payment_enabled = gateway_setting.value if gateway_setting else 'true'

    return render_template('dashboards/admin.html', 
                         flights=flights,
                         total_revenue=total_revenue,
                         total_bookings=total_bookings,
                         total_flights=total_flights,
                         total_users=total_users,
                         recent_bookings=recent_bookings,
                         payment_enabled=payment_enabled)

@admin_routes.route('/flights/update_status/<int:flight_id>', methods=['POST'])
@login_required
def update_flight_status(flight_id):
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    
    flight = Flight.query.get_or_404(flight_id)
    status = request.form.get('status')
    if status in ['scheduled', 'delayed', 'cancelled', 'completed']:
        flight.status = status
        db.session.commit()
        flash(f'Flight {flight.flight_number} status updated to {status}.', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_routes.route('/flights/assign_crew', methods=['GET', 'POST'])
@login_required
def assign_crew():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    
    flights = Flight.query.all()
    staff_members = User.query.filter_by(role='staff').all()
    
    if request.method == 'POST':
        flight_id = request.form.get('flight_id')
        user_id = request.form.get('user_id')
        role = request.form.get('role')
        
        assignment = CrewAssignment(flight_id=flight_id, user_id=user_id, role=role)
        db.session.add(assignment)
        db.session.commit()
        flash('Crew member assigned successfully!', 'success')
        return redirect(url_for('admin.dashboard'))
        
    return render_template('admin/assign_crew.html', flights=flights, staff_members=staff_members)

@admin_routes.route('/flights/add', methods=['GET', 'POST'])
@login_required
def add_flight():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
        
    aircrafts = Aircraft.query.all()
    if request.method == 'POST':
        flight_num = request.form.get('flight_number')
        source = request.form.get('source')
        dest = request.form.get('destination')
        
        try:
            dep_time = parse_robust_dt(request.form.get('departure_time'))
            arr_time = parse_robust_dt(request.form.get('arrival_time'))
        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('admin.add_flight'))
            
        aircraft_id = request.form.get('aircraft_id')
        price = request.form.get('price')
        
        flight = Flight(flight_number=flight_num, source=source, destination=dest,
                       departure_time=dep_time, arrival_time=arr_time,
                       aircraft_id=aircraft_id, price=price)
        db.session.add(flight)
        db.session.commit()
        flash('Flight added successfully!', 'success')
        return redirect(url_for('admin.dashboard'))
        
    return render_template('flights/add_flight.html', aircrafts=aircrafts)

@admin_routes.route('/aircrafts/add', methods=['GET', 'POST'])
@login_required
def add_aircraft():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        model = request.form.get('model')
        reg_num = request.form.get('registration_number')
        capacity = request.form.get('capacity')
        
        aircraft = Aircraft(model=model, registration_number=reg_num, capacity=capacity)
        db.session.add(aircraft)
        db.session.commit()
        flash('Aircraft added successfully!', 'success')
        return redirect(url_for('admin.dashboard'))
        
    return render_template('admin/add_aircraft.html')

@admin_routes.route('/seed', methods=['POST'])
@login_required
def seed_db():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    
    from datetime import timedelta
    # Check if data already exists
    if Aircraft.query.first():
        flash('Database already contains data.', 'warning')
        return redirect(url_for('admin.dashboard'))
    
    # Add Aircrafts
    a1 = Aircraft(model="Boeing 787-9 Dreamliner", registration_number="JP-787A", capacity=290)
    a2 = Aircraft(model="Airbus A350-1000", registration_number="JP-A350", capacity=350)
    a3 = Aircraft(model="Gulfstream G650", registration_number="JP-G650", capacity=16)
    db.session.add_all([a1, a2, a3])
    db.session.commit()

    # Define common city routes with realistic high-end INR pricing
    routes = [
        ("Mumbai",    "New York",     145000.0, a1.id, "JP-101", 5),
        ("Delhi",     "London",       122000.0, a2.id, "JP-202", 12),
        ("Mumbai",    "Dubai",         45000.0, a1.id, "JP-303", 3),
        ("Delhi",     "Singapore",     58000.0, a3.id, "JP-404", 20),
        ("Bangalore", "London",        115000.0, a2.id, "JP-505", 8),
        ("Mumbai",    "Bangkok",        31000.0, a1.id, "JP-606", 1),
        ("Delhi",     "Tokyo",         85000.0, a3.id, "JP-707", 15),
    ]

    # Seed flights every 2 days for the next 30 days for each route
    for source, dest, base_price, ac_id, f_prefix, _ in routes:
        # We start from tomorrow and skip one day every time (1, 3, 5...)
        for i in range(1, 31, 2):
            f_num = f"{f_prefix}-{i}"
            # Normalize to 12PM for a clean schedule
            future_date = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=i)
            
            f = Flight(
                flight_number=f_num,
                source=source,
                destination=dest,
                departure_time=future_date,
                arrival_time=future_date + timedelta(hours=10),
                aircraft_id=ac_id,
                price=base_price
            )
            db.session.add(f)
    
    db.session.commit()
    flash('Database seeded: Flights repeating every 2 days for the next 30 days!', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_routes.route('/unseed', methods=['POST'])
@login_required
def unseed_db():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))

    # Delete in dependency order to avoid FK constraint errors
    CrewAssignment.query.delete()
    Booking.query.delete()
    Passenger.query.delete()
    Flight.query.delete()
    Aircraft.query.delete()
    db.session.commit()
    flash('✅ All flight data cleared successfully. User accounts preserved.', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_routes.route('/flights/download-template')
@login_required
def download_csv_template():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))

    import csv, io
    from flask import Response

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        'flight_number', 'source', 'destination',
        'departure_time', 'arrival_time',
        'price', 'aircraft_model', 'aircraft_registration', 'aircraft_capacity'
    ])
    # Sample rows
    sample_rows = [
        ['JP-101', 'Mumbai', 'Delhi',         '2026-05-01 08:00', '2026-05-01 10:00', 4500,  'Boeing 737',          'JP-737A', 180],
        ['JP-102', 'Delhi', 'Bangalore',      '2026-05-01 11:00', '2026-05-01 13:30', 3800,  'Airbus A320',         'JP-A320', 165],
        ['JP-103', 'Bangalore', 'Chennai',    '2026-05-02 06:00', '2026-05-02 07:00', 2200,  'ATR 72',              'JP-ATR1', 70 ],
        ['JP-104', 'Chennai', 'Hyderabad',    '2026-05-02 09:00', '2026-05-02 10:15', 2100,  'Boeing 737',          'JP-737B', 180],
        ['JP-105', 'Hyderabad', 'Mumbai',     '2026-05-03 14:00', '2026-05-03 16:00', 3600,  'Airbus A320',         'JP-A321', 165],
        ['JP-106', 'Mumbai', 'Kolkata',       '2026-05-03 07:30', '2026-05-03 10:30', 5200,  'Boeing 787 Dreamliner','JP-787A', 296],
        ['JP-107', 'Kolkata', 'Delhi',        '2026-05-04 12:00', '2026-05-04 14:30', 4100,  'Airbus A320',         'JP-A322', 165],
        ['JP-108', 'Delhi', 'Goa',            '2026-05-04 15:00', '2026-05-04 17:30', 5500,  'Boeing 737',          'JP-737C', 180],
        ['JP-109', 'Goa', 'Mumbai',           '2026-05-05 10:00', '2026-05-05 11:30', 3200,  'ATR 72',              'JP-ATR2', 70 ],
        ['JP-110', 'Mumbai', 'Dubai',         '2026-05-05 22:00', '2026-05-06 00:30', 12000, 'Boeing 787 Dreamliner','JP-787B', 296],
    ]
    for row in sample_rows:
        writer.writerow(row)

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=flights_template.csv'}
    )


@admin_routes.route('/flights/upload-csv', methods=['POST'])
@login_required
def upload_flights_csv():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))

    import csv, io

    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid .csv file.', 'danger')
        return redirect(url_for('admin.dashboard'))

    stream = io.StringIO(file.stream.read().decode('utf-8-sig'), newline=None)
    reader = csv.DictReader(stream)

    required_cols = {'flight_number', 'source', 'destination', 'departure_time',
                     'arrival_time', 'price', 'aircraft_model', 'aircraft_registration', 'aircraft_capacity'}

    if not required_cols.issubset(set(reader.fieldnames or [])):
        flash(f'CSV is missing required columns. Download the template to see the correct format.', 'danger')
        return redirect(url_for('admin.dashboard'))

    added, skipped = 0, 0
    errors = []

    for i, row in enumerate(reader, start=2):
        try:
            flight_number = row['flight_number'].strip()
            if Flight.query.filter_by(flight_number=flight_number).first():
                skipped += 1
                continue

            # Get or create aircraft
            reg = row['aircraft_registration'].strip()
            aircraft = Aircraft.query.filter_by(registration_number=reg).first()
            if not aircraft:
                aircraft = Aircraft(
                    model=row['aircraft_model'].strip(),
                    registration_number=reg,
                    capacity=int(row['aircraft_capacity'])
                )
                db.session.add(aircraft)
                db.session.flush()  # get the id without committing

            dep = parse_robust_dt(row['departure_time'])
            arr = parse_robust_dt(row['arrival_time'])

            flight = Flight(
                flight_number=flight_number,
                source=row['source'].strip(),
                destination=row['destination'].strip(),
                departure_time=dep,
                arrival_time=arr,
                price=float(row['price']),
                aircraft_id=aircraft.id
            )
            db.session.add(flight)
            added += 1

        except Exception as e:
            errors.append(f'Row {i}: {str(e)}')
            db.session.rollback()

    db.session.commit()

    if added:
        flash(f'✅ Successfully imported {added} flight(s).{f" Skipped {skipped} duplicate(s)." if skipped else ""}', 'success')
    if skipped and not added:
        flash(f'⚠️ All {skipped} flight(s) already exist in the database.', 'warning')
    for err in errors[:3]:
        flash(f'Error — {err}', 'danger')

    return redirect(url_for('admin.dashboard'))


@admin_routes.route('/bookings')
@login_required
def manage_bookings():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    
    bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
    return render_template('admin/manage_bookings.html', bookings=bookings)

@admin_routes.route('/bookings/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    
    booking = Booking.query.get_or_404(booking_id)
    booking.status = 'cancelled'
    db.session.commit()
    flash(f'Booking {booking.booking_reference} has been cancelled.', 'success')
    return redirect(url_for('admin.manage_bookings'))

@admin_routes.route('/bookings/update_seat/<int:booking_id>', methods=['POST'])
@login_required
def update_seat(booking_id):
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    
    booking = Booking.query.get_or_404(booking_id)
    new_seat = request.form.get('seat_number')
    if new_seat:
        booking.seat_number = new_seat
        db.session.commit()
        flash(f'Seat for booking {booking.booking_reference} updated to {new_seat}.', 'success')
    return redirect(url_for('admin.manage_bookings'))

# --- Passenger Routes ---
@passenger_routes.route('/dashboard')
@login_required
def dashboard():
    bookings = Booking.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboards/passenger.html', bookings=bookings)

@passenger_routes.route('/book/<int:flight_id>', methods=['GET', 'POST'])
@login_required
def book_flight(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    if request.method == 'POST':
        p_name = request.form.get('passenger_name')
        p_email = request.form.get('passenger_email')
        p_passport = request.form.get('passenger_passport')
        p_phone = request.form.get('passenger_phone')
        seat_class = request.form.get('seat_class', 'Economy')
        meal_pref = request.form.get('meal_pref', 'Standard')

        # Check if passenger exists or create new one
        passenger = Passenger.query.filter_by(passport_number=p_passport).first()
        if not passenger:
            passenger = Passenger(name=p_name, email=p_email, passport_number=p_passport, phone=p_phone)
            db.session.add(passenger)
            db.session.commit()

        # Generate unique booking reference
        import uuid, random
        booking_ref = str(uuid.uuid4())[:8].upper()

        # Smart seat assignment based on class
        existing_seats = [b.seat_number for b in Booking.query.filter_by(flight_id=flight.id).all()]
        if seat_class == 'Business':
            rows = range(1, 6)
            cols = ['A', 'B', 'C', 'D']
        elif seat_class == 'First Class':
            rows = range(1, 4)
            cols = ['A', 'B']
        else:
            rows = range(10, 40)
            cols = ['A', 'B', 'C', 'D', 'E', 'F']

        seat_number = None
        for row in rows:
            for col in cols:
                candidate = f"{row}{col}"
                if candidate not in existing_seats:
                    seat_number = candidate
                    break
            if seat_number:
                break
        if not seat_number:
            seat_number = f"{random.randint(40, 99)}{random.choice(['A','B','C'])}"

        # If passenger selected a specific seat in the new interactive map
        if request.form.get('selected_seat'):
            seat_number = request.form.get('selected_seat')

        booking = Booking(
            booking_reference=booking_ref,
            user_id=current_user.id,
            flight_id=flight.id,
            passenger_id=passenger.id,
            seat_number=seat_number,
            payment_status='pending',
            meal_preference=meal_pref,
            seat_class=seat_class
        )
        db.session.add(booking)
        db.session.commit()
        
        # CHECK IF PAYMENT GATEWAY IS ENABLED
        gateway_setting = SystemSetting.query.filter_by(key='payment_gateway_enabled').first()
        is_enabled = gateway_setting.value == 'true' if gateway_setting else True

        if is_enabled:
            # Redirect to external payment page
            return redirect(url_for('passenger.payment', booking_id=booking.id))
        else:
            # Skip payment, mark as paid immediately
            booking.payment_status = 'paid'
            db.session.commit()
            flash('🎟️ Booking confirmed automatically (Payment Gateway OFF).', 'success')
            return redirect(url_for('passenger.view_ticket', booking_id=booking.id))

    # Fetch occupied seats for the interactive map
    occupied_seats = [b.seat_number for b in Booking.query.filter_by(flight_id=flight.id).all()]

    # Precompute dynamic prices for all seat classes so JS can read them
    dynamic_prices = {
        cls: get_dynamic_price(flight, cls, 'Standard')
        for cls in ['Economy', 'Business', 'First Class']
    }
    
    # Fetch all available dates for this specific route for the calendar
    available_flights = Flight.query.filter_by(source=flight.source, destination=flight.destination).all()
    available_dates = [f.departure_time.strftime('%Y-%m-%d %H:%M') for f in available_flights]
    
    meal_surcharges = MEAL_SURCHARGE
    return render_template('flights/booking.html', flight=flight,
                           dynamic_prices=dynamic_prices,
                           meal_surcharges=meal_surcharges,
                           available_dates=available_dates,
                           occupied_seats=occupied_seats)


@passenger_routes.route('/ticket/<int:booking_id>')
@login_required
def view_ticket(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('passenger.dashboard'))
    return render_template('passenger/ticket.html', booking=booking)


@passenger_routes.route('/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('passenger.dashboard'))
    if booking.status == 'cancelled':
        flash('This booking is already cancelled.', 'warning')
        return redirect(url_for('passenger.dashboard'))
    booking.status = 'cancelled'
    db.session.commit()
    flash(f'Booking {booking.booking_reference} has been cancelled.', 'success')
    return redirect(url_for('passenger.dashboard'))


@passenger_routes.route('/delete/<int:booking_id>', methods=['POST'])
@login_required
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('passenger.dashboard'))
    
    if booking.status != 'cancelled':
        flash('Only cancelled bookings can be removed from history.', 'warning')
        return redirect(url_for('passenger.dashboard'))
    
    db.session.delete(booking)
    db.session.commit()
    flash(f'Booking record {booking.booking_reference} removed from history.', 'success')
    return redirect(url_for('passenger.dashboard'))

# --- Staff Routes ---
@staff_routes.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'staff':
        return redirect(url_for('main.index'))
        
    assignments = CrewAssignment.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboards/staff.html', assignments=assignments)

@passenger_routes.route('/baggage/add/<int:booking_id>', methods=['GET', 'POST'])
@login_required
def add_baggage(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        return redirect(url_for('passenger.dashboard'))
    
    if request.method == 'POST':
        weight = float(request.form.get('weight'))
        import uuid
        tag = "TAG-" + str(uuid.uuid4())[:12].upper()
        
        from models import Baggage
        bag = Baggage(booking_id=booking_id, weight=weight, tag_number=tag)
        db.session.add(bag)
        db.session.commit()
        flash('Baggage registered successfully!', 'success')
        return redirect(url_for('passenger.dashboard'))
        
    return render_template('passenger/add_baggage.html', booking=booking)


@admin_routes.route('/insights')
@login_required
def insights():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    
    from datetime import datetime
    year = datetime.now().year
    
    # 1. Monthly Revenue
    monthly_rev = db.session.query(
        extract('month', Flight.departure_time).label('month'),
        func.sum(Flight.price).label('revenue')
    ).join(Booking).filter(
        extract('year', Flight.departure_time) == year
    ).group_by('month').all()
    
    rev_data = [0] * 12
    for m, r in monthly_rev:
        try: rev_data[int(m)-1] = float(r)
        except: continue

    # 2. Top Routes
    top_routes = db.session.query(
        Flight.source, Flight.destination, 
        func.sum(Flight.price).label('total')
    ).join(Booking).group_by(
        Flight.source, Flight.destination
    ).order_by(
        text('total DESC')
    ).limit(5).all()
    
    route_labels = [f"{r[0][:3]} → {r[1][:3]}" for r in top_routes]
    route_values = [float(r[2]) for r in top_routes]

    # 3. Occupancy
    flights = Flight.query.all()
    occ_total = 0
    occ_count = 0
    for f in flights:
        if f.aircraft and f.aircraft.capacity > 0:
            occ_total += (len(f.bookings) / f.aircraft.capacity) * 100
            occ_count += 1
    
    avg_occ = round(occ_total / occ_count, 1) if occ_count > 0 else 0

    return render_template('admin/insights.html', 
                         rev_data=rev_data,
                         route_labels=route_labels,
                         route_values=route_values,
                         avg_occupancy=avg_occ)


@passenger_routes.route('/payment/<int:booking_id>')
@login_required
def payment(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        return redirect(url_for('main.index'))
    
    # Initialize Razorpay Client
    client = razorpay.Client(auth=(current_app.config['RAZORPAY_KEY_ID'], 
                                 current_app.config['RAZORPAY_KEY_SECRET']))
    
    # Create Razorpay Order (amount in paisa, so * 100)
    price = get_dynamic_price(booking.flight, booking.seat_class, booking.meal_preference)
    
    # Razorpay test mode has a limit of ₹50,000. 
    # We cap the payment at ₹10,000 just for testing to be safe.
    payment_amt = min(price, 10000)
    
    data = {
        "amount": int(payment_amt * 100),
        "currency": "INR",
        "receipt": f"receipt_{booking.booking_reference}",
        "payment_capture": 1
    }
    
    order = client.order.create(data=data)
    
    return render_template('passenger/payment.html', 
                         booking=booking, 
                         order=order,
                         key_id=current_app.config['RAZORPAY_KEY_ID'],
                         price=price)


@passenger_routes.route('/payment/verify', methods=['POST'])
@login_required
def verify_payment():
    data = request.json
    client = razorpay.Client(auth=(current_app.config['RAZORPAY_KEY_ID'], 
                                 current_app.config['RAZORPAY_KEY_SECRET']))
    
    try:
        # Verify the payment signature from Razorpay
        params_dict = {
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        }
        client.utility.verify_payment_signature(params_dict)
        
        # If verification succeeds, mark booking as paid
        booking_id = data.get('booking_id')
        booking = Booking.query.get(booking_id)
        if booking:
            booking.payment_status = 'paid'
            db.session.commit()
            return {"status": "success"}
    except:
        return {"status": "failure"}, 400
    
    return {"status": "failure"}, 400


@admin_routes.route('/toggle-payment', methods=['POST'])
@login_required
def toggle_payment():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    
    setting = SystemSetting.query.filter_by(key='payment_gateway_enabled').first()
    if setting:
        setting.value = 'false' if setting.value == 'true' else 'true'
        db.session.commit()
        flash(f'Payment Gateway turned {"ON" if setting.value == "true" else "OFF"}', 'success')
    
    return redirect(url_for('admin.dashboard'))
