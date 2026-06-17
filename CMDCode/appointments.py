import json
import os
from datetime import datetime

DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
)

def get_services():
    with open(os.path.join(DATA_DIR, 'CrownMahoganyDetailingServices.json'), 'r') as f:
        services = json.load(f)
    return services

def calculate_total_price(service_type, add_ons, car_type):
    services = get_services()
    total = 0

    # Base service price
    if service_type in services['services']:
        total += services['services'][service_type]['base_price']

    # Add-on prices
    for add_on in add_ons:
        if add_on in services['add_ons']:
            total += services['add_ons'][add_on]['price']

    # Car type multiplier
    if car_type in services['car_type_multipliers']:
        total *= services['car_type_multipliers'][car_type]

    return round(total, 2)

def add_appointment(date, time, service_data, knight_data, customer_data, inventory_data):
    appointments = get_appointments()
    apptid = f"{date},{time}"

    # Calculate pricing
    total_price = calculate_total_price(
        service_data['type'],
        service_data.get('add_ons', []),
        customer_data['car_type']
    )

    appointment = {
        "appointment_id": apptid,
        "created_at": datetime.now().isoformat(),
        "scheduled_date": date,
        "scheduled_time": time,
        "status": "Pending",
        "service": service_data,
        "knight": knight_data,
        "customer": customer_data,
        "inventory": inventory_data,
        "pricing": {
            "base_price": total_price,
            "commission_rate": 0.15,  # 15% commission
            "commission_amount": round(total_price * 0.15, 2),
            "total_price": total_price
        },
        "notes": "",
        "last_updated": datetime.now().isoformat()
    }

    appointments["Pending"][apptid] = appointment
    update_appointment_file(appointments)
    return apptid

def update_appointment_file(appointments):
    with open(os.path.join(DATA_DIR, 'CrownMahoganyDetailingAppointments.json'), 'w') as f:
        json.dump(appointments, f, indent=4)

def get_appointments():
    with open(os.path.join(DATA_DIR, 'CrownMahoganyDetailingAppointments.json'), 'r') as f:
        appointments = json.load(f)
    return appointments

def remove_appointment(apptid):
    appointments=get_appointments()
    if apptid in appointments["Pending"]:
        del appointments["Pending"][apptid]
    elif apptid in appointments["Accepted"]:    
        del appointments["Accepted"][apptid]
    update_appointment_file(appointments)

def change_appointment(status, apptid, category, change):
    appointments = get_appointments()
    if apptid in appointments[status]:
        if '.' in category:
            # Handle nested updates like "customer.name" or "service.type"
            keys = category.split('.')
            target = appointments[status][apptid]
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = change
        else:
            appointments[status][apptid][category] = change

        appointments[status][apptid]["last_updated"] = datetime.now().isoformat()
        update_appointment_file(appointments)

def accept_appointment(apptid):
    appointments = get_appointments()
    if apptid in appointments["Pending"]:
        appointment = appointments["Pending"][apptid]
        appointment["status"] = "Accepted"
        appointment["accepted_at"] = datetime.now().isoformat()
        appointment["last_updated"] = datetime.now().isoformat()

        appointments["Accepted"][apptid] = appointment
        del appointments["Pending"][apptid]
        update_appointment_file(appointments)

def cancel_appointment(apptid, reason):
    appointments = get_appointments()
    if apptid in appointments["Accepted"]:
        appointment = appointments["Accepted"][apptid]
        appointment["status"] = "Cancelled"
        appointment["cancelled_at"] = datetime.now().isoformat()
        appointment["cancellation_reason"] = reason
        appointment["last_updated"] = datetime.now().isoformat()

        appointments["Cancelled"][apptid] = appointment
        del appointments["Accepted"][apptid]
    elif apptid in appointments["Pending"]:
        appointment = appointments["Pending"][apptid]
        appointment["status"] = "Cancelled"
        appointment["cancelled_at"] = datetime.now().isoformat()
        appointment["cancellation_reason"] = reason
        appointment["last_updated"] = datetime.now().isoformat()

        appointments["Cancelled"][apptid] = appointment
        del appointments["Pending"][apptid]

    update_appointment_file(appointments)
    
def complete_appointment(apptid):
    appointments = get_appointments()
    if apptid in appointments["Accepted"]:
        appointments["Completed"][apptid] = appointments["Accepted"][apptid]
        del appointments["Accepted"][apptid]
        update_appointment_file(appointments)

def appointment_unresolved(apptid):
    from datetime import datetime
    appointments = get_appointments()
    if apptid in appointments["Accepted"]:
        appt_datetime = datetime.strptime(f"{appointments['Accepted'][apptid]['Date']} {appointments['Accepted'][apptid]['Time']}", "%Y-%m-%d %H:%M")
        if appt_datetime < datetime.now():
            appointments["Unresolved"][apptid] = appointments["Accepted"][apptid]
            del appointments["Accepted"][apptid]
            update_appointment_file(appointments)

def get_appointment_status(apptid):
    appointments = get_appointments()
    for status in ["Pending", "Accepted", "Cancelled", "Completed", "Unresolved"]:
        if apptid in appointments[status]:
            return appointments[status][apptid]["status"]
    return "Not Found"

def get_employee_appointments(employee_id, status_filter=None):
    """Get all appointments for a specific employee"""
    appointments = get_appointments()
    employee_appts = {}

    for status in appointments:
        if status_filter and status != status_filter:
            continue
        for apptid, appt in appointments[status].items():
            if appt["knight"]["id"] == employee_id:
                employee_appts[apptid] = appt

    return employee_appts

def get_employee_commission(employee_id):
    """Calculate total commission for an employee"""
    employee_appts = get_employee_appointments(employee_id, "Completed")
    total_commission = 0

    for appt in employee_appts.values():
        total_commission += appt["pricing"]["commission_amount"]

    return round(total_commission, 2)

def get_available_time_slots(date, employee_id=None, district_code=None):
    """Get available time slots for a given date.

    Filters by employee if employee_id is provided.
    Filters by district/county when district_code is provided — falls back to
    county-level (first 3 chars of district_code) and then to all employees if
    no matches exist at the tighter level.
    """
    employees_file = os.path.join(DATA_DIR, 'CrownMahoganyDetailingEmployees.json')
    with open(employees_file, 'r') as f:
        employees_data = json.load(f)

    all_employees = employees_data.get("employees", {})

    if employee_id and employee_id in all_employees:
        emp_availability = all_employees[employee_id].get("availability", {})
        time_slots = emp_availability.get(date, [])
    else:
        # Determine which employees to aggregate
        pool = all_employees
        if district_code and len(district_code) == 5:
            county_prefix = district_code[:3]  # state + 2-digit county
            # Try district-exact match first (employee_code segment == district_code)
            district_pool = {
                k: v for k, v in all_employees.items()
                if len(k.split('-')) >= 2 and k.split('-')[1] == district_code
            }
            # Fall back to county-level match
            county_pool = {
                k: v for k, v in all_employees.items()
                if len(k.split('-')) >= 2 and k.split('-')[1].startswith(county_prefix)
            }
            pool = district_pool or county_pool or all_employees

        time_slots_set = set()
        for emp_data in pool.values():
            emp_avail = emp_data.get("availability", {})
            if date in emp_avail:
                time_slots_set.update(emp_avail[date])
        time_slots = sorted(time_slots_set)

    # Remove already-booked slots
    appointments = get_appointments()
    booked_slots = set()
    for status in ["Pending", "Accepted"]:
        for appt in appointments[status].values():
            if appt["scheduled_date"] == date:
                if employee_id is None or appt["knight"]["id"] == employee_id:
                    booked_slots.add(appt["scheduled_time"])

    return [slot for slot in time_slots if slot not in booked_slots]

def get_appointment_summary():
    """Get summary statistics for all appointments"""
    appointments = get_appointments()
    summary = {
        "total_appointments": 0,
        "pending": 0,
        "accepted": 0,
        "completed": 0,
        "cancelled": 0,
        "unresolved": 0,
        "total_revenue": 0,
        "monthly_revenue": 0
    }

    current_month = datetime.now().strftime("%Y-%m")

    for status, appts in appointments.items():
        count = len(appts)
        summary["total_appointments"] += count
        summary[status.lower()] = count

        if status == "Completed":
            for appt in appts.values():
                summary["total_revenue"] += appt["pricing"]["total_price"]
                if appt["scheduled_date"].startswith(current_month):
                    summary["monthly_revenue"] += appt["pricing"]["total_price"]

    summary["total_revenue"] = round(summary["total_revenue"], 2)
    summary["monthly_revenue"] = round(summary["monthly_revenue"], 2)

    return summary