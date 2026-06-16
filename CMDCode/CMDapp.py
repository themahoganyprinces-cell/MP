import json
import os
import random
import shutil
import string
from datetime import datetime, timedelta, timezone

def _utcnow():
    return datetime.now(timezone.utc)
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message as MailMessage
from Inventory import get_inventory
from appointments import get_services, get_available_time_slots
from CMDemploy import register_employee_routes
from CMDmanage import register_manage_routes

DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////" + os.path.join(DATA_DIR, "cmd.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["MAIL_SERVER"]   = "smtp.gmail.com"
app.config["MAIL_PORT"]     = 587
app.config["MAIL_USE_TLS"]  = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_USERNAME")

db   = SQLAlchemy(app)
mail = Mail(app)


class Employee(db.Model):
    id            = db.Column(db.Integer, primary_key=True)       # auto-assigned row number, never reused
    employee_code = db.Column(db.String(20), unique=True, nullable=False)  # e.g. "cmd-01-001"
    email         = db.Column(db.String(120), unique=True, nullable=False) # generated login credential
    first_name    = db.Column(db.String(50), nullable=False)
    last_name     = db.Column(db.String(50), nullable=False)
    password      = db.Column(db.String(200), nullable=False)     # stored as a hash, never plain text
    city          = db.Column(db.String(100))
    state         = db.Column(db.String(2))
    headshot      = db.Column(db.String(200))
    avatar        = db.Column(db.String(200))
    position      = db.Column(db.String(50))   # e.g. Knight, Squire
    is_founder    = db.Column(db.Boolean, default=False)
    mp_access     = db.Column(db.Boolean, default=False)
    cmd_access    = db.Column(db.Boolean, default=False)
    mmm_access    = db.Column(db.Boolean, default=False)
    mce_access    = db.Column(db.Boolean, default=False)
    manage_access = db.Column(db.Boolean, default=False)


class PendingEmployee(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    branch          = db.Column(db.String(10), nullable=False)
    employee_number = db.Column(db.String(3), nullable=False)
    link            = db.Column(db.String(200), nullable=False)
    manage_access   = db.Column(db.Boolean, default=False)
    is_founder      = db.Column(db.Boolean, default=False)
    used            = db.Column(db.Boolean, default=False)


class Booking(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    appt_id         = db.Column(db.String(20), unique=True, nullable=False)
    customer_name   = db.Column(db.String(100))
    customer_email  = db.Column(db.String(120))
    customer_phone  = db.Column(db.String(20))
    car             = db.Column(db.String(50))
    service         = db.Column(db.String(200))
    date            = db.Column(db.String(10))
    start_time      = db.Column(db.String(5))
    date_type       = db.Column(db.String(20), default="available")
    status          = db.Column(db.String(20), default="Pending")
    email_sent      = db.Column(db.Boolean, default=False)
    service_address = db.Column(db.String(200))
    service_city    = db.Column(db.String(100))
    service_state   = db.Column(db.String(2))


class JobAssignment(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    appt_id       = db.Column(db.String(20), nullable=False)
    employee_code = db.Column(db.String(20), nullable=False)
    status        = db.Column(db.String(20), default='pending')  # pending, accepted, denied
    deny_reason   = db.Column(db.String(200))
    offered_at    = db.Column(db.DateTime, default=_utcnow)


class Notification(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(20), nullable=False)
    type          = db.Column(db.String(30))   # job_offer, mention, reminder_week, reminder_day
    message       = db.Column(db.String(500))
    related_id    = db.Column(db.String(50))   # appt_id or post_id
    read          = db.Column(db.Boolean, default=False)
    timestamp     = db.Column(db.DateTime, default=_utcnow)


class FeedPost(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(20), nullable=False)
    content       = db.Column(db.Text, nullable=False)
    timestamp     = db.Column(db.DateTime, default=_utcnow)


class EmployeeInventory(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(20), nullable=False)
    category      = db.Column(db.String(100), nullable=False)
    item          = db.Column(db.String(100), nullable=False)
    quantity      = db.Column(db.Integer, default=0)


class InventoryRequest(db.Model):
    id                 = db.Column(db.Integer, primary_key=True)
    employee_code      = db.Column(db.String(20), nullable=False)
    category           = db.Column(db.String(100), nullable=False)
    item               = db.Column(db.String(100), nullable=False)
    quantity_requested = db.Column(db.Integer, default=1)
    status             = db.Column(db.String(20), default='pending')  # pending, fulfilled, denied
    fulfilled_qty      = db.Column(db.Integer, default=0)
    note               = db.Column(db.String(300))
    requested_at       = db.Column(db.DateTime, default=_utcnow)


import re as _re
import markupsafe as _mu

@app.template_filter('replace_mentions')
def _replace_mentions(text):
    escaped = _mu.escape(text)
    highlighted = _re.sub(
        r'@(\S+)',
        r'<span class="mention">@\1</span>',
        str(escaped)
    )
    return _mu.Markup(highlighted)


register_employee_routes(app, db, Employee, PendingEmployee, JobAssignment, Notification, FeedPost, Booking,
                         EmployeeInventory, InventoryRequest)
register_manage_routes(app, db, Employee, PendingEmployee, Booking, JobAssignment, Notification,
                       EmployeeInventory, InventoryRequest)


def generate_appt_id():
    chars = string.ascii_uppercase + string.digits
    return 'CMD-' + ''.join(random.choices(chars, k=6))


def get_car_types():
    with open(os.path.join(DATA_DIR, 'CrownMahoganyDetailingCartypes.json')) as f:
        data = json.load(f)
    return [
        {"name": name, **info}
        for name, info in data.get("car_sizes", {}).items()
    ]

def get_service_context():
    services_data = get_services()
    return {
        "services": [
            {"name": name, **info, "price": info.get("solo_price", info.get("duo_price", 0))}
            for name, info in services_data.get("services", {}).items()
        ],
        "packages": [
            {"name": name, **info, "price": info.get("solo_price", info.get("duo_price", 0))}
            for name, info in services_data.get("packages", {}).items()
        ],
        "add_ons": [
            {"name": name, "description": info.get("description", ""), "price": info.get("price", 0)}
            for name, info in services_data.get("add_ons", {}).items()
        ],
        "cars": get_car_types()
    }

def get_formula_context():
    inventory = get_inventory()
    return {
        "foundations": [
            {"name": name, "Quantity": data.get("Quantity", 0), "Reserved": data.get("Reserved", 0)}
            for name, data in inventory.get("Royal Foundations", {}).items()
        ],
        "scents":           list(inventory.get("Royal Scents", {}).keys()),
        "majesties_scents": [{"name": name} for name in inventory.get("Majestys Scents", {})],
        "sig_blends":       [{"name": name} for name in inventory.get("Signature Blends", {})],
    }


@app.route('/static/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(os.path.join(DATA_DIR, 'uploads'), filename)


@app.route('/')
def home():
    return render_template('CMDHomePage.html')

@app.route('/formula')
def formula():
    inventory_data = get_inventory()
    for item in inventory_data:
        if "Reserved" not in inventory_data[item][list(inventory_data[item].keys())[0]]:
            for subitem in inventory_data[item]:
                inventory_data[item][subitem]["Reserved"] = 0
    return render_template('CMDFormula.html', inventory=inventory_data)

@app.route('/services')
def services():
    return render_template('CMDServices.html', **get_service_context())

@app.route('/contact')
def contact():
    return render_template('CMDContact.html')

@app.route('/book')
def book():
    return render_template('CMDBook.html', **get_service_context(), **get_formula_context())

def _service_fits(slots, slots_needed):
    """Return True if any contiguous block of slots_needed 30-min slots exists before 7 PM."""
    if slots_needed <= 0:
        return True
    if not slots:
        return False
    CLOSING_MINS = 19 * 60
    slot_set = set(slots)
    for slot in slots:
        h, m = map(int, slot.split(':'))
        start = h * 60 + m
        if start + slots_needed * 30 > CLOSING_MINS:
            continue
        needed = [f"{(start + i*30)//60:02d}:{(start + i*30)%60:02d}" for i in range(slots_needed)]
        if all(s in slot_set for s in needed):
            return True
    return False

@app.route('/available-dates')
def available_dates():
    import calendar as cal
    from datetime import date as date_cls
    year         = request.args.get('year',  type=int)
    month        = request.args.get('month', type=int)
    service_name = request.args.get('service', '')
    service_type = request.args.get('type', 'solo')
    addon_names  = [a for a in request.args.get('addons', '').split(',') if a]
    if not year or not month:
        return jsonify({'available': [], 'request': [], 'request_with_slots': []})

    services_data = get_services()
    all_items     = {**services_data.get('services', {}), **services_data.get('packages', {})}
    duration      = 60
    if service_name and service_name in all_items:
        item     = all_items[service_name]
        dur_key  = f"{service_type}_duration"
        duration = item.get(dur_key, item.get('solo_duration', item.get('duo_duration', 60)))
    addon_duration = sum(
        services_data.get('add_ons', {}).get(a, {}).get('duration', 0)
        for a in addon_names
    )
    slots_needed  = -(-( duration + addon_duration) // 30)  # ceiling division

    today         = date_cls.today()
    days_in_month = cal.monthrange(year, month)[1]
    available, request_dates, request_with_slots = [], [], []

    for day in range(1, days_in_month + 1):
        this_date = date_cls(year, month, day)
        if this_date < today:
            continue
        date_str  = f"{year}-{month:02d}-{day:02d}"
        is_far    = (this_date - today).days >= 14
        raw_slots = get_available_time_slots(date_str)
        fits      = _service_fits(raw_slots, slots_needed)

        if is_far:
            if raw_slots:
                request_with_slots.append(date_str)
            else:
                request_dates.append(date_str)
        elif fits:
            available.append(date_str)

    return jsonify({'available': available, 'request': request_dates, 'request_with_slots': request_with_slots})

@app.route('/available-slots')
def available_slots():
    date         = request.args.get('date')
    service_name = request.args.get('service', '')
    service_type = request.args.get('type', 'solo')
    addon_names  = [a for a in request.args.get('addons', '').split(',') if a]

    if not date:
        return jsonify([])

    services_data = get_services()
    all_items     = {**services_data.get('services', {}), **services_data.get('packages', {})}

    duration = 60  # default
    if service_name and service_name in all_items:
        item     = all_items[service_name]
        dur_key  = f"{service_type}_duration"
        duration = item.get(dur_key, item.get('solo_duration', item.get('duo_duration', 60)))

    addon_duration = sum(
        services_data.get('add_ons', {}).get(a, {}).get('duration', 0)
        for a in addon_names
    )
    total_duration = duration + addon_duration

    raw_slots = get_available_time_slots(date)
    if not raw_slots:
        return jsonify({'available': [], 'duration': total_duration})

    return jsonify({'available': raw_slots, 'duration': total_duration})

@app.route('/submit-booking', methods=['POST'])
def submit_booking():
    data     = request.get_json()
    cars     = data.get('cars', [])
    customer = data.get('customer', {})
    results  = []

    for car_booking in cars:
        appt_id  = generate_appt_id()
        services = car_booking.get('services', [])
        service_str = ', '.join(
            f"{s['name']} ({s['type']})" if s.get('type') else s['name']
            for s in services
        )
        booking = Booking(
            appt_id=appt_id,
            customer_name=customer.get('name'),
            customer_email=customer.get('email'),
            customer_phone=customer.get('phone'),
            car=car_booking.get('car'),
            service=service_str,
            date=car_booking.get('date'),
            start_time=car_booking.get('start_time'),
            date_type=car_booking.get('date_type', 'available'),
            status='Pending',
            email_sent=False,
            service_address=customer.get('service_address', ''),
            service_city=customer.get('service_city', ''),
            service_state=(customer.get('service_state', '') or '').upper()[:2],
        )
        db.session.add(booking)
        results.append({
            'appt_id': appt_id,
            'car': car_booking.get('car'),
            'date': car_booking.get('date'),
            'start_time': car_booking.get('start_time'),
            'services': services,
            'addons': car_booking.get('addons', []),
            'formula': car_booking.get('formula', {}),
        })

    db.session.commit()
    _send_confirmation_email(customer, results)
    for r in results:
        _offer_job_to_employees(r['appt_id'], r['date'], r['start_time'])
    return jsonify({'appointments': results})


def _send_confirmation_email(customer, appointments):
    email = customer.get('email')
    name  = customer.get('name', 'Valued Customer')
    if not email or not app.config.get('MAIL_USERNAME'):
        return

    lines = [f"Hi {name},\n\nThank you for booking with Crown Mahogany Detailing!\n"]
    for i, appt in enumerate(appointments, 1):
        lines.append(f"Car {i} — {appt.get('car', '')}")
        lines.append(f"  Appointment ID : {appt['appt_id']}")
        lines.append(f"  Service        : {', '.join(s['name'] for s in appt.get('services', []))}")
        lines.append(f"  Date           : {appt.get('date', '—')}")
        lines.append(f"  Time           : {appt.get('start_time', '—')}\n")

    lines.append("No payment is required at time of booking.")
    lines.append("We accept cash, Venmo, Apple Pay, or PayPal upon completion.\n")
    lines.append("We'll be in touch to confirm your appointment!\n\n— Crown Mahogany Detailing")

    try:
        msg = MailMessage(
            subject="Your Crown Mahogany Detailing Booking Confirmation",
            recipients=[email],
            body='\n'.join(lines)
        )
        mail.send(msg)
        Booking.query.filter(
            Booking.appt_id.in_([a['appt_id'] for a in appointments])
        ).update({'email_sent': True}, synchronize_session=False)
        db.session.commit()
    except Exception:
        pass


def _offer_job_to_employees(appt_id, date, start_time):
    """Match a new booking to available employees in the same zone, then create job offers."""
    from CMDemploy import _get_employees, _get_location_code
    try:
        employees_json = _get_employees()
    except Exception:
        return

    booking   = Booking.query.filter_by(appt_id=appt_id).first()
    svc_city  = (booking.service_city  or '') if booking else ''
    svc_state = (booking.service_state or '').upper() if booking else ''

    # Resolve the booking's district zone (first digit of 2-digit code, e.g. "01" → "0")
    book_zone = None
    if svc_city and svc_state:
        district = _get_location_code(svc_city, svc_state)
        book_zone = district[0] if district and district != "00" else None

    h, m      = map(int, start_time.split(':'))
    book_mins = h * 60 + m

    for emp_code, emp_data in employees_json.get('employees', {}).items():
        avail_slots = emp_data.get('availability', {}).get(date, [])
        if not avail_slots:
            continue

        # Zone filter: state + first digit of location code must match when address is provided
        if svc_state:
            emp_obj = Employee.query.filter_by(employee_code=emp_code).first()
            if not emp_obj or (emp_obj.state or '').upper() != svc_state:
                continue
            if book_zone:
                parts    = emp_code.split('-')
                emp_loc  = parts[1] if len(parts) >= 3 else "00"
                emp_zone = emp_loc[0] if emp_loc else None
                if emp_zone and emp_zone != book_zone:
                    continue

        # Offer if booking time is within ±2 hours of any available slot
        in_range = any(
            abs((int(s.split(':')[0]) * 60 + int(s.split(':')[1])) - book_mins) <= 120
            for s in avail_slots
        )
        if not in_range:
            continue

        # Skip if already offered
        if JobAssignment.query.filter_by(appt_id=appt_id, employee_code=emp_code).first():
            continue

        db.session.add(JobAssignment(appt_id=appt_id, employee_code=emp_code))
        msg = (f"New job offer: {booking.service if booking else appt_id} "
               f"on {date} at {start_time}"
               + (f" in {svc_city}, {svc_state}" if svc_city else ""))
        db.session.add(Notification(
            employee_code=emp_code,
            type='job_offer',
            message=msg,
            related_id=appt_id
        ))

    db.session.commit()


_SEED_DIR = os.path.dirname(os.path.abspath(__file__))
_SEED_FILES = [
    "CrownMahoganyDetailingEmployees.json",
    "CrownMahoganyDetailingInventory.json",
    "CrownMahoganyDetailingServices.json",
    "CrownMahoganyDetailingCartypes.json",
    "CrownMahoganyDetailingAppointments.json",
]

os.makedirs(DATA_DIR, exist_ok=True)
for _fname in _SEED_FILES:
    _dest = os.path.join(DATA_DIR, _fname)
    if not os.path.exists(_dest):
        shutil.copy(os.path.join(_SEED_DIR, _fname), _dest)

with app.app_context():
    db.create_all()
    # Add new Booking columns if this is an existing database
    with db.engine.connect() as _conn:
        for _col, _defn in [
            ("service_address", "VARCHAR(200)"),
            ("service_city",    "VARCHAR(100)"),
            ("service_state",   "VARCHAR(2)"),
        ]:
            try:
                _conn.execute(db.text(f"ALTER TABLE booking ADD COLUMN {_col} {_defn}"))
                _conn.commit()
            except Exception:
                pass

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug)
