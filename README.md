# 🛫 JetPulse Airline Management System

![JetPulse Banner](https://images.unsplash.com/photo-1436491865332-7a61a109c0f3?auto=format&fit=crop&q=80&w=1200)

**JetPulse** is a high-fidelity, premium web application designed to revolutionize the airline booking experience. Built with a focus on modern aesthetics, secure transactions, and intuitive administrative control, JetPulse offers a complete end-to-end solution for flight management and passenger bookings.

---

## ✨ Key Features

### 💎 Premium Passenger Experience
- **Interactive Seat Map**: A stunning, glassmorphic 3D-styled cabin layout allowing passengers to select their preferred seats (First Class, Business, or Economy) with real-time availability.
- **Dynamic Pricing**: Intelligent fare calculation based on seat class and meal preferences.
- **Secure Payments**: Integrated **Razorpay Payment Gateway** for safe and seamless UPI/Card transactions.
- **Personalized Dashboard**: Passengers can manage bookings, view digital tickets, and track their travel history.

### 🛡️ Powerful Administrative Controls
- **System Settings Toggle**: A unique "Test Mode" switch that allows admins to enable or disable the real payment gateway for development and demonstration purposes.
- **Advanced Analytics**: Real-time revenue tracking and route popularity insights using **Chart.js**.
- **Bulk Operations**: Rapid flight scheduling and passenger manifest management.
- **Crew Management**: Automated and manual crew assignment tools for flight operations.

---

## 🚀 Technology Stack

- **Backend**: Python 3.x, Flask (Full-stack Framework)
- **Database**: SQLAlchemy (ORM for SQLite/PostgreSQL)
- **Frontend**: Vanilla CSS3 (Custom Design System), Jinja2 Templating
- **Security**: Flask-Login, Bcrypt Password Hashing, CSRF Protection
- **Integrations**: Razorpay SDK (Payments), Lucide Icons, Chart.js (Analytics)
- **Aesthetics**: Glassmorphism, CSS Micro-animations, Google Fonts (Inter/Outfit)

---

## 🛠️ Installation & Setup

1. **Clone the Project**
   ```bash
   git clone https://github.com/your-username/jetpulse-airline.git
   cd jetpulse-airline
   ```

2. **Set up Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   *   Create a `.env` file or update `app.py` with your Razorpay API keys:
   ```python
   RAZORPAY_KEY_ID = 'your_key_id'
   RAZORPAY_KEY_SECRET = 'your_key_secret'
   ```

5. **Run the Application**
   ```bash
   python app.py
   ```
   The app will be live at `http://127.0.0.1:5000`

---

## 🕹️ Admin Access
| Role | Username | Password |
|------|----------|----------|
| **Administrator** | admin@jetpulse.com | admin123 |
| **Staff** | staff@jetpulse.com | staff123 |

---

## 🎨 Design Philosophy
JetPulse adheres to a **"Dark-Premium"** design language, utilizing:
- **Depth**: Multi-layered glassmorphism for a sophisticated look.
- **Clarity**: High-contrast typography for readability in dashboards.
- **Engagement**: Subtle hover states and transitions that make the interface feel "alive".

---

## 📈 Future Roadmap
- [ ] **Round-Trip Booking**: Enable multi-leg flight selection.
- [ ] **Email Automation**: PDF boarding passes sent directly to passenger emails.
- [ ] **Real-time Weather**: Destination weather integration on route cards.
- [ ] **Mobile App**: React Native companion app for check-ins.

---

## 📄 License
This project is for educational and portfolio demonstration purposes. 🛡️🛫✨
