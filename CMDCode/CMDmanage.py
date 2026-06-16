import json
import os
import calendar as cal_mod
from datetime import datetime, timezone
from functools import wraps
from flask import render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash

DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
)
SERVICES_FILE  = os.path.join(DATA_DIR, 'CrownMahoganyDetailingServices.json')
EMPLOYEES_FILE = os.path.join(DATA_DIR, 'CrownMahoganyDetailingEmployees.json')

BRANCH_POSITIONS = {
    "mp":  ["Staff"],
    "cmd": ["Knight", "Squire"],
    "mmm": ["Staff"],
    "mce": ["Staff"],
}

BRANCH_FULL = {
    "mp":  "The Mahogany Princes",
    "cmd": "Crown Mahogany Detailing",
    "mmm": "Mahogany Multimedia Management",
    "mce": "Mahogany Crown Estates",
}


def _load_employees_json():
    with open(EMPLOYEES_FILE, 'r') as f:
        return json.load(f)

def _load_services():
    with open(SERVICES_FILE) as f:
        return json.load(f)

def _save_services(data):
    with open(SERVICES_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def register_manage_routes(app, db, Employee, PendingEmployee, Booking=None,
                           JobAssignment=None, Notification=None,
                           EmployeeInventory=None, InventoryRequest=None):

    def _manage_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if Employee.query.count() == 0:
                return f(*args, **kwargs)
            code = session.get('employee_code')
            if not code:
                return redirect(url_for('employee_signin'))
            emp = Employee.query.filter_by(employee_code=code).first()
            if not emp or not emp.manage_access:
                return redirect(url_for('employee_dashboard'))
            return f(*args, **kwargs)
        return decorated

    def _current_employee():
        code = session.get('employee_code')
        if not code:
            return None
        return Employee.query.filter_by(employee_code=code).first()

    def _current_is_founder():
        if Employee.query.count() == 0:
            return True
        emp = _current_employee()
        return emp.is_founder if emp else False

    def _parse_branch_positions(emp):
        """Return the position dict {branch: role} for an employee, handling plain strings."""
        raw = emp.position or ""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        if raw:
            branch = emp.employee_code.split('-')[0].lower()
            return {branch: raw}
        return {}

    def _manage_context(active_tab):
        emp = _current_employee()
        return {
            "active_tab": active_tab,
            "manager": emp,
            "is_founder": _current_is_founder(),
        }

    def _next_employee_number(branch):
        pending_nums = [
            int(p.employee_number)
            for p in PendingEmployee.query.filter_by(branch=branch).all()
        ]
        active_nums = [
            int(e.employee_code.split('-')[-1])
            for e in Employee.query.filter(
                Employee.employee_code.like(f"{branch.upper()}-%")
            ).all()
        ]
        all_nums = pending_nums + active_nums
        return max(all_nums) + 1 if all_nums else 1

    # ── Redirect root → employees tab ───────────────────────────────────────

    @app.route("/manage")
    @app.route("/manage/dashboard")
    @_manage_required
    def manage_dashboard():
        return redirect(url_for('manage_employees'))

    # ── Employees ────────────────────────────────────────────────────────────

    def _employees_with_cmd_pos():
        emps = Employee.query.filter_by(cmd_access=True).order_by(Employee.last_name).all()
        return emps, {e.employee_code: _parse_branch_positions(e).get("cmd", "") for e in emps}

    @app.route("/manage/employees")
    @_manage_required
    def manage_employees():
        svc_config    = _load_services()
        cmd_positions = svc_config.get("positions", ["Knight", "Squire"])
        branch_pos    = {**BRANCH_POSITIONS, "cmd": cmd_positions}
        emps, emp_cmd_pos = _employees_with_cmd_pos()
        return render_template(
            "CMDmanageEmployees.html",
            employees=emps,
            emp_cmd_pos=emp_cmd_pos,
            pending=PendingEmployee.query.filter_by(used=False).all(),
            branch_positions=branch_pos,
            cmd_positions=cmd_positions,
            branch_full=BRANCH_FULL,
            **_manage_context("employees"),
        )

    @app.route("/manage/employees/preview", methods=["POST"])
    @_manage_required
    def generate_employee_preview():
        founder       = _current_is_founder()
        branch        = request.form["branch"]
        manage_access = founder and ("manage_access" in request.form)
        is_founder    = founder and ("is_founder" in request.form)
        position      = request.form.get("position", "")
        num           = _next_employee_number(branch)
        svc_config    = _load_services()
        cmd_positions = svc_config.get("positions", ["Knight", "Squire"])
        branch_pos    = {**BRANCH_POSITIONS, "cmd": cmd_positions}
        emps, emp_cmd_pos = _employees_with_cmd_pos()
        return render_template(
            "CMDmanageEmployees.html",
            employees=emps,
            emp_cmd_pos=emp_cmd_pos,
            pending=PendingEmployee.query.filter_by(used=False).all(),
            branch_positions=branch_pos,
            cmd_positions=cmd_positions,
            branch_full=BRANCH_FULL,
            new_number=f"{num:03d}",
            branch=branch,
            position=position,
            manage_access=manage_access,
            grant_founder=is_founder,
            **_manage_context("employees"),
        )

    @app.route("/manage/employees/generate-link", methods=["POST"])
    @_manage_required
    def generate_employee_link():
        founder         = _current_is_founder()
        branch          = request.form["branch"]
        employee_number = request.form["employee_number"]
        position        = request.form.get("position", "")
        manage_access   = founder and (request.form.get("manage_access") == "true")
        is_founder_flag = founder and (request.form.get("is_founder") == "true")
        link = f"{request.host_url}employ/signup/{branch}/{employee_number}"
        db.session.add(PendingEmployee(
            branch=branch,
            employee_number=employee_number,
            link=link,
            manage_access=manage_access,
            is_founder=is_founder_flag,
            used=False
        ))
        db.session.commit()
        # Store position hint so signup can pre-fill — saved to PendingEmployee.notes if needed
        # For now pass it through the template
        svc_config    = _load_services()
        cmd_positions = svc_config.get("positions", ["Knight", "Squire"])
        branch_pos    = {**BRANCH_POSITIONS, "cmd": cmd_positions}
        emps, emp_cmd_pos = _employees_with_cmd_pos()
        return render_template(
            "CMDmanageEmployees.html",
            employees=emps,
            emp_cmd_pos=emp_cmd_pos,
            pending=PendingEmployee.query.filter_by(used=False).all(),
            branch_positions=branch_pos,
            cmd_positions=cmd_positions,
            branch_full=BRANCH_FULL,
            generated_link=link,
            **_manage_context("employees"),
        )

    @app.route("/manage/employees/<emp_code>/edit", methods=["POST"])
    @_manage_required
    def manage_employee_edit(emp_code):
        emp = Employee.query.filter_by(employee_code=emp_code).first()
        if emp:
            pos_dict = _parse_branch_positions(emp)
            new_pos  = request.form.get("position", "").strip()
            if new_pos:
                pos_dict["cmd"] = new_pos
            else:
                pos_dict.pop("cmd", None)
            emp.position = json.dumps(pos_dict)
            if _current_is_founder():
                emp.manage_access = "manage_access" in request.form
                emp.is_founder    = "is_founder" in request.form
            emp.cmd_access = "cmd_access" in request.form
            emp.mmm_access = "mmm_access" in request.form
            emp.mce_access = "mce_access" in request.form
            emp.mp_access  = "mp_access"  in request.form
            new_pw = request.form.get("reset_password", "").strip()
            if new_pw and len(new_pw) >= 6:
                emp.password = generate_password_hash(new_pw)
            db.session.commit()
        return redirect(url_for('manage_employees'))

    @app.route("/manage/employees/<emp_code>/remove", methods=["POST"])
    @_manage_required
    def manage_employee_remove(emp_code):
        emp = Employee.query.filter_by(employee_code=emp_code).first()
        if emp:
            db.session.delete(emp)
            db.session.commit()
        return redirect(url_for('manage_employees'))

    # ── Services ─────────────────────────────────────────────────────────────

    def _parse_pay_rows(positions):
        """Read pos_0/pay_0 … pairs from the current POST form."""
        pay_rates = {}
        i = 0
        while True:
            pos = request.form.get(f"pos_{i}", "").strip()
            pay = request.form.get(f"pay_{i}", "").strip()
            if not pos:
                break
            if pay.replace('.', '', 1).isdigit():
                pay_rates[pos] = float(pay)
            i += 1
        return pay_rates

    def _parse_service_entry(existing, positions):
        """Build a service dict from POST form data, preserving unknown keys."""
        entry = dict(existing)
        entry["description"] = request.form.get("description", entry.get("description", ""))
        entry["category"]    = request.form.get("category",    entry.get("category", ""))
        entry["duo_only"]    = "duo_only" in request.form
        for field, cast in (("solo_price", float), ("duo_price", float)):
            val = request.form.get(field, "").strip()
            if val.replace('.', '', 1).isdigit():
                entry[field] = cast(val)
            elif field in entry and entry["duo_only"] and field == "solo_price":
                entry.pop(field, None)
        for field in ("solo_duration", "duo_duration"):
            val = request.form.get(field, "").strip()
            if val.isdigit():
                entry[field] = int(val)
            elif field in entry and entry["duo_only"] and field == "solo_duration":
                entry.pop(field, None)
        entry["pay_rates"] = _parse_pay_rows(positions)
        return entry

    @app.route("/manage/services", methods=["GET", "POST"])
    @_manage_required
    def manage_services():
        config    = _load_services()
        positions = config.get("positions", ["Knight", "Squire"])
        saved, msg = False, None

        if request.method == "POST":
            action = request.form.get("action")

            # ── Categories (founder only) ─────────────────────────
            if action == "add_category":
                if _current_is_founder():
                    new_cat = request.form.get("new_category", "").strip().title()
                    categories = config.get("categories", [])
                    if new_cat and new_cat not in categories:
                        categories.append(new_cat)
                        config["categories"] = categories
                        _save_services(config)
                        msg = f"Category '{new_cat}' added."
                else:
                    msg = "Only founders can manage categories."

            elif action == "rename_category":
                if _current_is_founder():
                    old = request.form.get("old_category", "").strip()
                    new = request.form.get("renamed_category", "").strip().title()
                    categories = config.get("categories", [])
                    if old in categories and new and new != old:
                        config["categories"] = [new if c == old else c for c in categories]
                        for section in ("services", "packages"):
                            for item in config.get(section, {}).values():
                                if item.get("category") == old:
                                    item["category"] = new
                        _save_services(config)
                        msg = f"Renamed '{old}' → '{new}'."
                else:
                    msg = "Only founders can manage categories."

            elif action == "delete_category":
                if _current_is_founder():
                    del_cat = request.form.get("category")
                    categories = config.get("categories", [])
                    if del_cat and del_cat in categories:
                        categories.remove(del_cat)
                        config["categories"] = categories
                        _save_services(config)
                        msg = f"Category '{del_cat}' removed."
                else:
                    msg = "Only founders can manage categories."

            # ── Positions ────────────────────────────────────────
            elif action == "add_position":
                new_pos = request.form.get("new_position", "").strip().title()
                if new_pos and new_pos not in positions:
                    positions.append(new_pos)
                    config["positions"] = positions
                    _save_services(config)
                    msg = f"Position '{new_pos}' added."

            elif action == "rename_position":
                old = request.form.get("old_position", "").strip()
                new = request.form.get("renamed_position", "").strip().title()
                if old in positions and new and new != old:
                    config["positions"] = [new if p == old else p for p in positions]
                    for section in ("services", "packages"):
                        for item in config.get(section, {}).values():
                            pr = item.get("pay_rates", {})
                            if old in pr:
                                pr[new] = pr.pop(old)
                    _save_services(config)
                    msg = f"Renamed '{old}' → '{new}'."

            elif action == "delete_position":
                del_pos = request.form.get("position")
                if del_pos and del_pos in positions and len(positions) > 1:
                    positions.remove(del_pos)
                    config["positions"] = positions
                    for section in ("services", "packages"):
                        for item in config.get(section, {}).values():
                            item.get("pay_rates", {}).pop(del_pos, None)
                    _save_services(config)
                    msg = f"Position '{del_pos}' removed."

            # ── Service CRUD ─────────────────────────────────────
            elif action in ("update_service", "update_package"):
                section   = "services" if action == "update_service" else "packages"
                orig_name = request.form.get("orig_name", "").strip()
                new_name  = request.form.get("name", orig_name).strip()
                if orig_name and orig_name in config.get(section, {}):
                    entry = _parse_service_entry(config[section][orig_name], positions)
                    del config[section][orig_name]
                    config[section][new_name or orig_name] = entry
                    _save_services(config)
                    saved = True

            elif action in ("add_service", "add_package"):
                section = "services" if action == "add_service" else "packages"
                name    = request.form.get("name", "").strip()
                if name:
                    entry = _parse_service_entry({}, positions)
                    config.setdefault(section, {})[name] = entry
                    _save_services(config)
                    saved = True

            elif action in ("delete_service", "delete_package"):
                section = "services" if action == "delete_service" else "packages"
                name    = request.form.get("name", "").strip()
                if name and name in config.get(section, {}):
                    del config[section][name]
                    _save_services(config)
                    msg = f"'{name}' removed."

            # ── Add-on CRUD ──────────────────────────────────────
            elif action == "update_addon":
                orig  = request.form.get("orig_name", "").strip()
                new   = request.form.get("name", orig).strip()
                if orig and orig in config.get("add_ons", {}):
                    entry = dict(config["add_ons"][orig])
                    val = request.form.get("price", "").strip()
                    if val.replace('.', '', 1).isdigit():
                        entry["price"] = float(val)
                    val = request.form.get("duration", "").strip()
                    if val.isdigit():
                        entry["duration"] = int(val)
                    del config["add_ons"][orig]
                    config["add_ons"][new or orig] = entry
                    _save_services(config)
                    saved = True

            elif action == "add_addon":
                name = request.form.get("name", "").strip()
                if name:
                    entry = {}
                    val = request.form.get("price", "").strip()
                    if val.replace('.', '', 1).isdigit():
                        entry["price"] = float(val)
                    val = request.form.get("duration", "").strip()
                    if val.isdigit():
                        entry["duration"] = int(val)
                    config.setdefault("add_ons", {})[name] = entry
                    _save_services(config)
                    saved = True

            elif action == "delete_addon":
                name = request.form.get("name", "").strip()
                if name and name in config.get("add_ons", {}):
                    del config["add_ons"][name]
                    _save_services(config)
                    msg = f"Add-on '{name}' removed."

            config     = _load_services()
            positions  = config.get("positions", ["Knight", "Squire"])

        return render_template(
            "CMDmanageServices.html",
            services=config.get("services", {}),
            packages=config.get("packages", {}),
            addons=config.get("add_ons", {}),
            positions=positions,
            categories=config.get("categories", []),
            saved=saved,
            msg=msg,
            **_manage_context("services"),
        )

    # ── Inventory ────────────────────────────────────────────────────────────

    @app.route("/manage/inventory", methods=["GET", "POST"])
    @_manage_required
    def manage_inventory():
        from Inventory import (get_inventory, update_JSON,
                               get_category_meta, update_category_meta)
        inventory = get_inventory()
        meta      = get_category_meta()
        msg       = None

        if request.method == "POST":
            action   = request.form.get("action")
            category = request.form.get("category", "")
            item     = request.form.get("item", "")

            if action == "update_qty":
                qty = request.form.get("quantity", "0")
                if category in inventory and item in inventory[category]:
                    inventory[category][item]["Quantity"] = int(qty)
                    update_JSON(inventory)
                    msg = f"Updated {item} quantity."

            elif action == "update_reserved":
                res = request.form.get("reserved", "0")
                if category in inventory and item in inventory[category]:
                    inventory[category][item]["Reserved"] = int(res)
                    update_JSON(inventory)
                    msg = f"Updated {item} reserved."

            elif action == "update_category_meta":
                client_visible  = "client_visible"  in request.form
                employee_stock  = "employee_stock"  in request.form
                if category:
                    meta.setdefault(category, {})
                    meta[category]["client_visible"] = client_visible
                    meta[category]["employee_stock"] = employee_stock
                    update_category_meta(meta)
                    msg = f"Updated settings for '{category}'."

            elif action == "add_category":
                if _current_is_founder():
                    new_cat = request.form.get("category_name", "").strip()
                    if new_cat and new_cat not in inventory:
                        inventory[new_cat] = {}
                        update_JSON(inventory)
                        meta[new_cat] = {"client_visible": True, "employee_stock": False}
                        update_category_meta(meta)
                        msg = f"Category '{new_cat}' added."
                else:
                    msg = "Only founders can add categories."

            elif action == "add_item":
                if _current_is_founder():
                    item_name = request.form.get("item_name", "").strip()
                    qty       = request.form.get("quantity", "0").strip()
                    qty       = int(qty) if qty.isdigit() else 0
                    if category in inventory and item_name and item_name not in inventory[category]:
                        inventory[category][item_name] = {"Quantity": qty, "Reserved": 0}
                        update_JSON(inventory)
                        msg = f"'{item_name}' added to {category}."
                else:
                    msg = "Only founders can add items."

            elif action == "remove_item":
                if _current_is_founder():
                    if category in inventory and item in inventory[category]:
                        del inventory[category][item]
                        update_JSON(inventory)
                        msg = f"'{item}' removed."
                else:
                    msg = "Only founders can remove items."

            elif action == "remove_category":
                if _current_is_founder():
                    if category in inventory:
                        del inventory[category]
                        update_JSON(inventory)
                        meta.pop(category, None)
                        update_category_meta(meta)
                        msg = f"Category '{category}' removed."
                else:
                    msg = "Only founders can remove categories."

            elif action == "fulfill_request" and InventoryRequest and EmployeeInventory:
                req_id   = request.form.get("request_id", "")
                raw_give = request.form.get("give_qty", "0").strip()
                give_qty = int(raw_give) if raw_give.isdigit() else 0
                inv_req  = InventoryRequest.query.get(int(req_id)) if req_id.isdigit() else None
                if inv_req and inv_req.status == 'pending' and give_qty > 0:
                    cat, itm = inv_req.category, inv_req.item
                    if cat in inventory and itm in inventory[cat]:
                        available   = inventory[cat][itm].get("Quantity", 0)
                        actual_give = min(give_qty, available)
                        if actual_give > 0:
                            inventory[cat][itm]["Quantity"] -= actual_give
                            update_JSON(inventory)
                            emp_inv = EmployeeInventory.query.filter_by(
                                employee_code=inv_req.employee_code,
                                category=cat, item=itm
                            ).first()
                            if emp_inv:
                                emp_inv.quantity += actual_give
                            else:
                                db.session.add(EmployeeInventory(
                                    employee_code=inv_req.employee_code,
                                    category=cat, item=itm, quantity=actual_give
                                ))
                            inv_req.status        = 'fulfilled'
                            inv_req.fulfilled_qty = actual_give
                            if Notification:
                                db.session.add(Notification(
                                    employee_code=inv_req.employee_code,
                                    type='inventory',
                                    message=(f"Your request for {actual_give}x {itm} "
                                             f"has been fulfilled.")
                                ))
                            db.session.commit()
                            msg = f"Gave {actual_give}x {itm} to employee."
                        else:
                            msg = f"Not enough {itm} in stock to fulfill."

            elif action == "deny_request" and InventoryRequest:
                req_id  = request.form.get("request_id", "")
                inv_req = InventoryRequest.query.get(int(req_id)) if req_id.isdigit() else None
                if inv_req and inv_req.status == 'pending':
                    inv_req.status = 'denied'
                    if Notification:
                        db.session.add(Notification(
                            employee_code=inv_req.employee_code,
                            type='inventory',
                            message=(f"Your request for {inv_req.quantity_requested}x "
                                     f"{inv_req.item} was denied.")
                        ))
                    db.session.commit()
                    msg = "Request denied."

            inventory = get_inventory()
            meta      = get_category_meta()

        pending_requests = []
        if InventoryRequest:
            reqs = (InventoryRequest.query
                    .filter_by(status='pending')
                    .order_by(InventoryRequest.requested_at.asc())
                    .all())
            for r in reqs:
                emp = Employee.query.filter_by(employee_code=r.employee_code).first()
                pending_requests.append({"req": r, "emp": emp})

        return render_template(
            "CMDmanageInventory.html",
            inventory=inventory,
            category_meta=meta,
            pending_requests=pending_requests,
            msg=msg,
            **_manage_context("inventory"),
        )

    # ── Jobs ─────────────────────────────────────────────────────────────────

    @app.route("/manage/jobs", methods=["GET", "POST"])
    @_manage_required
    def manage_jobs():
        if Booking is None:
            return redirect(url_for('manage_employees'))

        status_filter = request.args.get("status", "all")

        if request.method == "POST":
            action  = request.form.get("action")
            appt_id = request.form.get("appt_id")
            booking = Booking.query.filter_by(appt_id=appt_id).first()
            if booking and action == "update":
                old_status           = booking.status
                new_status           = request.form.get("status", booking.status)
                booking.status       = new_status
                booking.date         = request.form.get("date", booking.date)
                booking.start_time   = request.form.get("start_time", booking.start_time)
                booking.customer_name  = request.form.get("customer_name", booking.customer_name)
                booking.customer_email = request.form.get("customer_email", booking.customer_email)
                booking.customer_phone = request.form.get("customer_phone", booking.customer_phone)
                db.session.commit()
                if (Notification and JobAssignment
                        and new_status != old_status
                        and new_status.lower() in ('completed', 'cancelled')):
                    accepted = JobAssignment.query.filter_by(
                        appt_id=appt_id, status='accepted'
                    ).all()
                    verb = "completed" if new_status.lower() == "completed" else "cancelled"
                    for ja in accepted:
                        db.session.add(Notification(
                            employee_code=ja.employee_code,
                            type='job_offer',
                            message=(f"Job {booking.service} on {booking.date} "
                                     f"has been marked {verb}."),
                            related_id=appt_id
                        ))
                    db.session.commit()
            elif booking and action == "assign":
                if JobAssignment:
                    emp_code = request.form.get("employee_code")
                    existing = JobAssignment.query.filter_by(
                        appt_id=appt_id, employee_code=emp_code
                    ).first()
                    if not existing:
                        db.session.add(JobAssignment(
                            appt_id=appt_id,
                            employee_code=emp_code,
                            status='pending'
                        ))
                        if Notification:
                            emp = Employee.query.filter_by(employee_code=emp_code).first()
                            db.session.add(Notification(
                                employee_code=emp_code,
                                type='job_offer',
                                message=f"New job assigned to you: {booking.service} on {booking.date} at {booking.start_time}.",
                                related_id=appt_id
                            ))
                        db.session.commit()
            return redirect(url_for('manage_jobs', status=status_filter))

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_bookings = Booking.query.order_by(Booking.date.desc(), Booking.start_time).all()

        # Enrich with assignment info
        jobs = []
        for b in all_bookings:
            if status_filter != "all" and b.status.lower() != status_filter.lower():
                continue
            assigned = []
            no_detailer = True
            if JobAssignment:
                assignments = JobAssignment.query.filter_by(appt_id=b.appt_id).all()
                for ja in assignments:
                    if ja.status == 'accepted':
                        no_detailer = False
                    emp = Employee.query.filter_by(employee_code=ja.employee_code).first()
                    if emp:
                        assigned.append({"emp": emp, "status": ja.status})
            danger = (no_detailer and b.date and b.date >= today
                      and b.status.lower() != 'cancelled')
            jobs.append({"booking": b, "assigned": assigned, "danger": danger})

        employees = Employee.query.order_by(Employee.last_name).all()
        return render_template(
            "CMDmanageJobs.html",
            jobs=jobs,
            employees=employees,
            status_filter=status_filter,
            **_manage_context("jobs"),
        )

    # ── Availability Calendar ────────────────────────────────────────────────

    @app.route("/manage/availability")
    @_manage_required
    def manage_availability():
        year  = request.args.get("year",  datetime.now(timezone.utc).year,  type=int)
        month = request.args.get("month", datetime.now(timezone.utc).month, type=int)

        # Load all employee availability
        emp_json   = _load_employees_json()
        employees  = {e.employee_code: e for e in Employee.query.all()}

        # Build: date_str → list of employee objects
        avail_map = {}
        for emp_code, data in emp_json.get("employees", {}).items():
            for date_str, slots in data.get("availability", {}).items():
                if not slots:
                    continue
                if date_str[:7] != f"{year}-{month:02d}":
                    continue
                avail_map.setdefault(date_str, [])
                emp_obj = employees.get(emp_code)
                if emp_obj:
                    avail_map[date_str].append({
                        "emp": emp_obj,
                        "slots": slots
                    })

        # Build calendar grid
        first_weekday, days_in_month = cal_mod.monthrange(year, month)
        month_name = cal_mod.month_name[month]
        prev_month = (month - 2) % 12 + 1
        prev_year  = year - 1 if month == 1 else year
        next_month = month % 12 + 1
        next_year  = year + 1 if month == 12 else year

        return render_template(
            "CMDmanageAvailability.html",
            year=year, month=month,
            month_name=month_name,
            first_weekday=first_weekday,
            days_in_month=days_in_month,
            avail_map=avail_map,
            prev_year=prev_year, prev_month=prev_month,
            next_year=next_year, next_month=next_month,
            **_manage_context("availability"),
        )
