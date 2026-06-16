import json
import os

DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
)
INVENTORY_FILE = os.path.join(DATA_DIR, 'CrownMahoganyDetailingInventory.json')

def _load_raw():
    with open(INVENTORY_FILE, 'r') as f:
        return json.load(f)

def get_inventory():
    raw = _load_raw()
    return {k: v for k, v in raw.items() if k != '_category_meta'}

def get_category_meta():
    return _load_raw().get('_category_meta', {})

def update_JSON(inventory):
    raw  = _load_raw()
    meta = raw.get('_category_meta', {})
    result = {}
    if meta:
        result['_category_meta'] = meta
    result.update(inventory)
    with open(INVENTORY_FILE, 'w') as f:
        json.dump(result, f, indent=4)

def update_category_meta(meta):
    raw = _load_raw()
    raw['_category_meta'] = meta
    with open(INVENTORY_FILE, 'w') as f:
        json.dump(raw, f, indent=4)

def specific_item_info(category, item):
    return get_inventory()[category][item]

def add_to_quantity(category, item, amount):
    inventory = get_inventory()
    inventory[category][item]["Quantity"] += amount
    update_JSON(inventory)

def subtract_from_quantity(category, item, amount):
    inventory = get_inventory()
    if amount <= inventory[category][item]["Quantity"]:
        inventory[category][item]["Quantity"] -= amount
    update_JSON(inventory)

def get_quantity(category, item):
    return get_inventory()[category][item]["Quantity"]

def reserve_item(category, item, amount):
    inventory = get_inventory()
    if amount <= inventory[category][item]["Quantity"]:
        inventory[category][item]["Reserved"] += amount
        inventory[category][item]["Quantity"] -= amount
        update_JSON(inventory)

def unreserve_item(category, item, amount, purchased):
    inventory = get_inventory()
    if amount <= inventory[category][item]["Reserved"]:
        inventory[category][item]["Reserved"] -= amount
        if not purchased:
            inventory[category][item]["Quantity"] += amount
    update_JSON(inventory)

def available_quantity():
    inventory = get_inventory()
    available    = []
    out_of_stock = []
    for cat in inventory:
        for itm in inventory[cat]:
            if inventory[cat][itm]["Quantity"] > 0:
                available.append(itm)
            else:
                out_of_stock.append(itm)
    return available, out_of_stock

def add_new_item(category, item, quantity):
    inventory = get_inventory()
    if item not in inventory[category]:
        existing = list(inventory[category].values())
        if existing and "Reserved" in existing[0]:
            inventory[category][item] = {"Quantity": quantity, "Reserved": 0}
        else:
            inventory[category][item] = {"Quantity": quantity}
        update_JSON(inventory)

def remove_item(category, item):
    inventory = get_inventory()
    del inventory[category][item]
    update_JSON(inventory)
