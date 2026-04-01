import os
from flask import Flask
from extensions import db, bcrypt, login_manager
from models import User, SystemSetting

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'jetpulse_secret_key_123'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///jetpulse.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Razorpay Test Keys (Replace with your actual keys from dashboard.razorpay.com)
    app.config['RAZORPAY_KEY_ID'] = 'rzp_test_SYBkAdW6l2Djt4'
    app.config['RAZORPAY_KEY_SECRET'] = 'zjODBQ7iwjL9jnj4eGMhSAc1'

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Import and register blueprints
    from routes import main, auth, admin_routes, staff_routes, passenger_routes
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(admin_routes)
    app.register_blueprint(staff_routes)
    app.register_blueprint(passenger_routes)

    with app.app_context():
        db.create_all()
        # Seed an admin user if none exists
        if not User.query.filter_by(role='admin').first():
            hashed_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin = User(username='admin', email='admin@jetpulse.com', password_hash=hashed_pw, role='admin')
            db.session.add(admin)
            db.session.commit()
        
        # Seed Payment Gateway Setting if missing
        gateway_setting = SystemSetting.query.filter_by(key='payment_gateway_enabled').first()
        if not gateway_setting:
            new_setting = SystemSetting(key='payment_gateway_enabled', value='true')
            db.session.add(new_setting)
            db.session.commit()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
