import json
import os
import re
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import render_template, request, redirect, url_for, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
)
EMPLOYEES_FILE = os.path.join(DATA_DIR, 'CrownMahoganyDetailingEmployees.json')
DISTRICT_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DistrictCodes.json')
UPLOAD_FOLDER  = os.path.join(DATA_DIR, 'uploads', 'employees')
SERVICES_FILE  = os.path.join(DATA_DIR, 'CrownMahoganyDetailingServices.json')

DENY_REASONS = [
    "Already have a prior commitment",
    "No longer available at this time",
    "Outside service area",
    "Equipment not available",
    "Personal conflict",
]


def _get_employees():
    with open(EMPLOYEES_FILE, 'r') as f:
        return json.load(f)

def _save_employees(data):
    with open(EMPLOYEES_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def _get_location_code(city, state):
    with open(DISTRICT_FILE) as f:
        data = json.load(f)
    for state_data in data["District Codes"].values():
        if state_data.get("State Abbreviation", "").upper() != state.upper():
            continue
        for county_data in state_data.values():
            if not isinstance(county_data, dict) or "Districts" not in county_data:
                continue
            for district_data in county_data["Districts"].values():
                if city in district_data.get("Towns", []):
                    return f"{district_data['District code']:02d}"
    return "00"


def register_employee_routes(app, db, Employee, PendingEmployee,
                             JobAssignment, Notification, FeedPost, Booking,
                             EmployeeInventory=None, InventoryRequest=None):

    def _get_current_employee():
        code = session.get('employee_code')
        if not code:
            return None
        return Employee.query.filter_by(employee_code=code).first()

    def _get_notifications(employee_code):
        return (Notification.query
                .filter_by(employee_code=employee_code)
                .order_by(Notification.timestamp.desc())
                .limit(20)
                .all())

    def _check_job_reminders(employee_code):
        """Create Sunday-of-week and day-before notifications for accepted jobs."""
        today = datetime.now(timezone.utc).date()
        accepted = JobAssignment.query.filter_by(employee_code=employee_code, status='accepted').all()
        for ja in accepted:
            b = Booking.query.filter_by(appt_id=ja.appt_id).first()
            if not b or not b.date:
                continue
            try:
                job_date = datetime.strptime(b.date, "%Y-%m-%d").date()
            except ValueError:
                continue
            days_away = (job_date - today).days
            if days_away < 0:
                continue

            # Sunday of the job's week
            sunday = job_date - timedelta(days=job_date.weekday() + 1)
            if today == sunday:
                exists = Notification.query.filter_by(
                    employee_code=employee_code, type='reminder_week', related_id=b.appt_id
                ).first()
                if not exists:
                    db.session.add(Notification(
                        employee_code=employee_code,
                        type='reminder_week',
                        message=f"Reminder: You have a job this week on {b.date} at {b.start_time}.",
                        related_id=b.appt_id
                    ))
                    db.session.commit()

            # Day before
            if days_away == 1:
                exists = Notification.query.filter_by(
                    employee_code=employee_code, type='reminder_day', related_id=b.appt_id
                ).first()
                if not exists:
                    db.session.add(Notification(
                        employee_code=employee_code,
                        type='reminder_day',
                        message=(f"Tomorrow: {b.service} — {b.date} at {b.start_time}."
                                 f" Customer: {b.customer_name}."),
                        related_id=b.appt_id
                    ))
                    db.session.commit()

    def _employee_context():
        employee = _get_current_employee()
        if not employee:
            return {"employee_name": "Employee", "employee_avatar": None, "notifications": []}
        _check_job_reminders(employee.employee_code)
        return {
            "employee": employee,
            "employee_name": f"{employee.first_name} {employee.last_name}",
            "employee_code": employee.employee_code,
            "employee_avatar": employee.avatar,
            "employee_headshot": employee.headshot,
            "notifications": _get_notifications(employee.employee_code),
        }

    def _login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'employee_code' not in session:
                return redirect(url_for('employee_signin'))
            return f(*args, **kwargs)
        return decorated

    # ── Auth ────────────────────────────────────────────────────────────────

    @app.route("/employ/signin", methods=["GET", "POST"])
    def employee_signin():
        if 'employee_code' in session:
            emp = Employee.query.filter_by(employee_code=session['employee_code']).first()
            if emp and emp.manage_access:
                return redirect(url_for('employee_choose_mode'))
            return redirect(url_for('employee_dashboard'))
        error = None
        if request.method == "POST":
            email    = request.form["email"]
            password = request.form["password"]
            employee = Employee.query.filter_by(email=email).first()
            if employee and check_password_hash(employee.password, password):
                session['employee_code'] = employee.employee_code
                if employee.manage_access:
                    return redirect(url_for('employee_choose_mode'))
                return redirect(url_for('employee_dashboard'))
            error = "Invalid email or password."
        return render_template("CMDemploysignin.html", error=error)

    @app.route("/employ/choose")
    def employee_choose_mode():
        if 'employee_code' not in session:
            return redirect(url_for('employee_signin'))
        emp = Employee.query.filter_by(employee_code=session['employee_code']).first()
        if not emp or not emp.manage_access:
            return redirect(url_for('employee_dashboard'))
        return render_template("CMDemployChooseMode.html", employee=emp)

    @app.route("/employ/signout")
    def employee_signout():
        session.pop('employee_code', None)
        return redirect(url_for('employee_signin'))

    @app.route("/employ/signup/<branch>/<employee_number>", methods=["GET", "POST"])
    def employee_signup(branch, employee_number):
        pending = PendingEmployee.query.filter_by(
            branch=branch, employee_number=employee_number, used=False
        ).first()
        if not pending:
            return render_template("CMDemploysignup.html",
                                   error="This signup link is invalid or has already been used.")

        if request.method == "POST":
            first_name = request.form["name"]
            last_name  = request.form["lastname"]
            password   = generate_password_hash(request.form["password"])
            city       = request.form["Town/City"]
            state      = request.form["state"]

            location_code = _get_location_code(city, state)
            employee_code = f"{branch.upper()}-{location_code}-{employee_number}"
            email = f"{first_name.lower()}{last_name.lower()}{branch.lower()}@themahoganyprinces.com"

            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

            def _save_file(field):
                file = request.files.get(field)
                if file and file.filename:
                    filename = secure_filename(f"{employee_code}_{field}_{file.filename}")
                    file.save(os.path.join(UPLOAD_FOLDER, filename))
                    return f"uploads/employees/{filename}"
                return None

            b       = branch.lower()
            founder = pending.is_founder
            employee = Employee(
                employee_code=employee_code,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password,
                city=city,
                state=state,
                headshot=_save_file("professional"),
                avatar=_save_file("avatar"),
                is_founder=founder,
                mp_access=founder  or (b == "mp"),
                cmd_access=founder or (b == "cmd"),
                mmm_access=founder or (b == "mmm"),
                mce_access=founder or (b == "mce"),
                manage_access=founder or pending.manage_access
            )
            db.session.add(employee)
            pending.used = True
            db.session.commit()
            return redirect(url_for("employee_signin"))

        return render_template("CMDemploysignup.html",
                               branch=branch, employee_number=employee_number)

    # ── Dashboard ───────────────────────────────────────────────────────────

    @app.route("/employ")
    @app.route("/employ/dashboard")
    @_login_required
    def employee_dashboard():
        emp_code = session['employee_code']
        pending_assignments = (JobAssignment.query
                               .filter_by(employee_code=emp_code, status='pending')
                               .order_by(JobAssignment.offered_at.desc())
                               .all())
        offers = []
        for ja in pending_assignments:
            b = Booking.query.filter_by(appt_id=ja.appt_id).first()
            if b:
                offers.append({"assignment": ja, "booking": b})
        return render_template("CMDemployDashboard.html",
                               offers=offers,
                               deny_reasons=DENY_REASONS,
                               **_employee_context())

    @app.route("/employ/jobs/accept/<appt_id>", methods=["POST"])
    @_login_required
    def employee_job_accept(appt_id):
        emp_code = session['employee_code']
        ja = JobAssignment.query.filter_by(appt_id=appt_id, employee_code=emp_code).first()
        if ja:
            ja.status = 'accepted'
            b = Booking.query.filter_by(appt_id=appt_id).first()
            acceptor = Employee.query.filter_by(employee_code=emp_code).first()
            acceptor_name = f"{acceptor.first_name} {acceptor.last_name}" if acceptor else emp_code
            others = JobAssignment.query.filter(
                JobAssignment.appt_id == appt_id,
                JobAssignment.employee_code != emp_code,
                JobAssignment.status == 'pending'
            ).all()
            for o in others:
                o.status = 'denied'
                o.deny_reason = 'Job accepted by another employee'
                db.session.add(Notification(
                    employee_code=o.employee_code,
                    type='job_offer',
                    message=(f"The job offer for {b.service if b else appt_id} "
                             f"on {b.date if b else '—'} was accepted by {acceptor_name}."),
                    related_id=appt_id
                ))
            db.session.commit()
        return redirect(url_for('employee_dashboard'))

    @app.route("/employ/jobs/deny/<appt_id>", methods=["POST"])
    @_login_required
    def employee_job_deny(appt_id):
        emp_code = session['employee_code']
        ja = JobAssignment.query.filter_by(appt_id=appt_id, employee_code=emp_code).first()
        if ja:
            ja.status = 'denied'
            ja.deny_reason = request.form.get('reason', '')
            db.session.commit()
        return redirect(url_for('employee_dashboard'))

    # ── Upcoming Jobs ───────────────────────────────────────────────────────

    @app.route("/employ/upcoming")
    @_login_required
    def employee_upcoming_jobs():
        emp_code  = session['employee_code']
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        accepted  = JobAssignment.query.filter_by(employee_code=emp_code, status='accepted').all()
        upcoming, past = [], []
        for ja in accepted:
            b = Booking.query.filter_by(appt_id=ja.appt_id).first()
            if not b:
                continue
            if b.date and b.date >= today_str:
                upcoming.append(b)
            else:
                past.append(b)
        upcoming.sort(key=lambda x: (x.date or '', x.start_time or ''))
        past.sort(key=lambda x: (x.date or '', x.start_time or ''), reverse=True)
        return render_template("CMDemployUpcoming.html",
                               upcoming=upcoming, past=past,
                               **_employee_context())

    # ── Availability ────────────────────────────────────────────────────────

    @app.route("/employ/avail")
    @_login_required
    def employee_availability():
        return render_template("CMDemployAvail.html", **_employee_context())

    @app.route("/employ/avail/data")
    @_login_required
    def employee_availability_data():
        date          = request.args.get("date")
        employee_code = session.get('employee_code')
        employees_json = _get_employees()
        emp_json      = employees_json["employees"].get(employee_code, {})
        availability  = emp_json.get("availability", {})
        if date:
            return jsonify({"slots": availability.get(date, [])})
        return jsonify({"dates": list(availability.keys())})

    @app.route("/employ/avail/save", methods=["POST"])
    @_login_required
    def employee_availability_save():
        data          = request.get_json()
        date          = data.get("date")
        slots         = data.get("slots", [])
        employee_code = session.get('employee_code')
        if not date:
            return jsonify({"error": "date required"}), 400
        employees = _get_employees()
        employees["employees"].setdefault(employee_code, {}).setdefault("availability", {})[date] = slots
        _save_employees(employees)
        return jsonify({"success": True})

    # ── Stay in Contact ─────────────────────────────────────────────────────

    @app.route("/employ/contact")
    @_login_required
    def employee_contact():
        posts     = FeedPost.query.order_by(FeedPost.timestamp.desc()).limit(50).all()
        employees = {e.employee_code: e for e in Employee.query.all()}
        return render_template("CMDemployContact.html",
                               posts=posts, employees=employees,
                               **_employee_context())

    @app.route("/employ/contact/post", methods=["POST"])
    @_login_required
    def employee_contact_post():
        emp_code = session['employee_code']
        content  = request.form.get("content", "").strip()
        if not content:
            return redirect(url_for('employee_contact'))

        post = FeedPost(employee_code=emp_code, content=content)
        db.session.add(post)
        db.session.flush()

        mentions = re.findall(r'@(\S+)', content)
        for mention in mentions:
            mentioned = (Employee.query.filter(
                Employee.employee_code.ilike(f"%{mention}%")
            ).first() or Employee.query.filter(
                Employee.first_name.ilike(mention)
            ).first())
            if mentioned and mentioned.employee_code != emp_code:
                sender = Employee.query.filter_by(employee_code=emp_code).first()
                sender_name = f"{sender.first_name} {sender.last_name}" if sender else emp_code
                db.session.add(Notification(
                    employee_code=mentioned.employee_code,
                    type='mention',
                    message=f"{sender_name} mentioned you in the feed.",
                    related_id=str(post.id)
                ))

        db.session.commit()
        return redirect(url_for('employee_contact'))

    @app.route("/employ/contact/posts")
    @_login_required
    def employee_contact_posts_api():
        since_id  = request.args.get("since", 0, type=int)
        posts     = (FeedPost.query
                     .filter(FeedPost.id > since_id)
                     .order_by(FeedPost.timestamp.asc())
                     .all())
        emp_map   = {e.employee_code: {"name": f"{e.first_name} {e.last_name}", "avatar": e.avatar}
                     for e in Employee.query.all()}
        return jsonify([{
            "id": p.id,
            "employee_code": p.employee_code,
            "author": emp_map.get(p.employee_code, {}).get("name", p.employee_code),
            "avatar": emp_map.get(p.employee_code, {}).get("avatar"),
            "content": p.content,
            "timestamp": p.timestamp.strftime("%b %d %I:%M %p")
        } for p in posts])

    # ── Notifications ───────────────────────────────────────────────────────

    @app.route("/employ/notifications")
    @_login_required
    def employee_notifications():
        emp_code = session['employee_code']
        notifs   = (Notification.query
                    .filter_by(employee_code=emp_code)
                    .order_by(Notification.timestamp.desc())
                    .all())
        return render_template("CMDemployNotifications.html",
                               all_notifications=notifs,
                               **_employee_context())

    @app.route("/employ/notifications/<int:notif_id>/read", methods=["POST"])
    @_login_required
    def employee_notification_read(notif_id):
        emp_code = session['employee_code']
        n = Notification.query.filter_by(id=notif_id, employee_code=emp_code).first()
        if n:
            n.read = True
            db.session.commit()
        return jsonify({"ok": True})

    # ── Pay ─────────────────────────────────────────────────────────────────

    @app.route("/employ/pay")
    @_login_required
    def employee_pay_details():
        emp_code = session['employee_code']
        employee = _get_current_employee()
        position = None
        if employee and employee.position:
            try:
                pos_data = json.loads(employee.position)
                position = pos_data.get("cmd", "") if isinstance(pos_data, dict) else employee.position
            except (json.JSONDecodeError, ValueError):
                position = employee.position
        accepted = JobAssignment.query.filter_by(employee_code=emp_code, status='accepted').all()
        completed, total = [], 0.0
        with open(SERVICES_FILE) as f:
            svc_config = json.load(f)
        all_items = {
            **svc_config.get("services", {}),
            **svc_config.get("packages", {}),
        }
        positions = svc_config.get("positions", [])
        for ja in accepted:
            b = Booking.query.filter_by(appt_id=ja.appt_id, status='Completed').first()
            if not b:
                continue
            pay = 0.0
            for part in (b.service or '').split(', '):
                m = re.match(r'^(.+?) \((solo|duo)\)$', part.strip())
                if m:
                    svc_name, svc_type = m.group(1), m.group(2)
                else:
                    svc_name, svc_type = part.strip(), 'solo'
                item = all_items.get(svc_name) or next(
                    (v for k, v in all_items.items() if k.lower() == svc_name.lower()), None
                )
                if item and position:
                    hourly   = float(item.get("pay_rates", {}).get(position, 0))
                    dur_key  = f"{svc_type}_duration"
                    duration = item.get(dur_key, item.get('solo_duration', item.get('duo_duration', 0)))
                    pay += hourly * (duration / 60)
            completed.append({"booking": b, "pay": round(pay, 2)})
            total += pay
        return render_template("CMDemployPay.html",
                               completed=completed, total=round(total, 2),
                               all_items=all_items, positions=positions,
                               position=position,
                               **_employee_context())

    # ── Profile & Settings ──────────────────────────────────────────────────

    @app.route("/employ/profile")
    @_login_required
    def employee_profile():
        return render_template("CMDemployProfile.html", **_employee_context())

    @app.route("/employ/settings", methods=["GET", "POST"])
    @_login_required
    def employee_settings():
        employee = _get_current_employee()
        error, success = None, None
        if request.method == "POST":
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            emp_code = employee.employee_code

            def _save_file(field):
                file = request.files.get(field)
                if file and file.filename:
                    filename = secure_filename(f"{emp_code}_{field}_{file.filename}")
                    file.save(os.path.join(UPLOAD_FOLDER, filename))
                    return f"uploads/employees/{filename}"
                return None

            new_avatar   = _save_file("avatar")
            new_headshot = _save_file("professional")
            new_password = request.form.get("new_password", "").strip()
            confirm_pass = request.form.get("confirm_password", "").strip()

            if new_avatar:
                employee.avatar = new_avatar
            if new_headshot:
                employee.headshot = new_headshot
            if new_password:
                if new_password != confirm_pass:
                    error = "Passwords do not match."
                elif len(new_password) < 6:
                    error = "Password must be at least 6 characters."
                else:
                    employee.password = generate_password_hash(new_password)
            if not error:
                db.session.commit()
                success = "Settings updated."

        return render_template("CMDemploySettings.html",
                               error=error, success=success,
                               **_employee_context())

    # ── Personal Inventory ──────────────────────────────────────────────────

    @app.route("/employ/inventory")
    @_login_required
    def employee_inventory():
        from Inventory import get_inventory, get_category_meta
        emp_code  = session['employee_code']
        inventory = get_inventory()
        meta      = get_category_meta()

        all_categories = {cat: list(items.keys()) for cat, items in inventory.items()}

        personal     = EmployeeInventory.query.filter_by(employee_code=emp_code).all()
        pending_reqs = (InventoryRequest.query
                        .filter_by(employee_code=emp_code, status='pending')
                        .order_by(InventoryRequest.requested_at.desc()).all())
        past_reqs    = (InventoryRequest.query
                        .filter_by(employee_code=emp_code)
                        .filter(InventoryRequest.status != 'pending')
                        .order_by(InventoryRequest.requested_at.desc())
                        .limit(20).all())

        return render_template("CMDemployInventory.html",
                               all_categories=all_categories,
                               personal=personal,
                               pending_reqs=pending_reqs,
                               past_reqs=past_reqs,
                               **_employee_context())

    @app.route("/employ/inventory/request", methods=["POST"])
    @_login_required
    def employee_inventory_request():
        from Inventory import get_inventory
        emp_code = session['employee_code']
        category = request.form.get("category", "").strip()
        item     = request.form.get("item", "").strip()
        raw_qty  = request.form.get("quantity", "1").strip()
        note     = request.form.get("note", "").strip()
        qty      = int(raw_qty) if raw_qty.isdigit() and int(raw_qty) >= 1 else 1

        inventory = get_inventory()
        if category in inventory and item in inventory[category]:
            db.session.add(InventoryRequest(
                employee_code=emp_code,
                category=category,
                item=item,
                quantity_requested=qty,
                note=note or None
            ))
            db.session.commit()

        return redirect(url_for('employee_inventory'))

    @app.route("/employ/inventory/update", methods=["POST"])
    @_login_required
    def employee_inventory_update():
        emp_code = session['employee_code']
        inv_id   = request.form.get("inv_id", "").strip()
        raw_qty  = request.form.get("quantity", "0").strip()
        new_qty  = int(raw_qty) if raw_qty.isdigit() else 0

        if inv_id.isdigit():
            entry = EmployeeInventory.query.filter_by(
                id=int(inv_id), employee_code=emp_code
            ).first()
            if entry:
                entry.quantity = new_qty
                db.session.commit()

        return redirect(url_for('employee_inventory'))
