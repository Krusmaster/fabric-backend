"""Synthetic manufacturing data, the 'mill' sample: a fictional Swedish workshop beside the shop of seed.py.

    %pip install git+https://github.com/Krusmaster/fabric-backend
    from fabric_backend.seed import seed
    seed(spark, schema="shop", mill=True)            # the shop as before, and the mill in its own schema 'mill'

Ystervik Mekaniska (fictional) makes conveyor rollers, pump units and gearbox housings for other manufacturers: it buys
steel, bearings and fasteners, machines and welds parts, assembles finished goods to order and delivers them. Sixteen
tables, about five thousand rows, two years of dates (November 2024 to October 2026), all generated from one seed with
`random.Random`, so the same seed gives the same rows on every run and every machine.

The table and column names are plain English words of our own; they do not copy or follow any ERP vendor's tables,
columns or codes. Company, customer, supplier and item names are invented.

A few problems are planted on purpose, at fixed places, so that a check has something to find and a test can say
exactly what (tests/fixtures/mill/planted_issues.json lists each one; docs/SAMPLE-MILL.md explains them):

  - orphan references: sales order lines and an inventory transaction that point at items that do not exist, and a
    production operation at a work center that does not exist;
  - a non-unique key in a staging-like table (stg_supplier_prices loads a price file twice for one row);
  - late deliveries: a fixed set of order lines delivered after the date promised to the customer;
  - a table without a key: machine_events, an event log.

Not a problem but a limit worth showing: customers.parent_customer_id points at customers itself (a group and its
sites). The engine's name rules never link a table to itself, so the plan leaves it out; the tests pin that.
"""
from __future__ import annotations

import datetime as _dt
import random
from datetime import date, datetime, timedelta

COMPANY = "Ystervik Mekaniska (fictional)"
START, END = date(2024, 11, 1), date(2026, 10, 31)          # two years of dates

# Spark DDL, one string per table, in the order the tables are written. Plain English names of our own.
SCHEMAS = {
    "customers": "customer_id INT, name STRING, country STRING, city STRING, parent_customer_id INT",
    "suppliers": "supplier_id INT, name STRING, country STRING, lead_time_days INT",
    "items": "item_id INT, item_number STRING, name STRING, item_type STRING, unit STRING, standard_cost DOUBLE, supplier_id INT",
    "bill_of_materials": "parent_item_id INT, component_item_id INT, quantity DOUBLE",
    "work_centers": "work_center_code STRING, name STRING, hourly_rate DOUBLE, hours_per_day DOUBLE",
    "sales_orders": "sales_order_id INT, order_date DATE, bill_to_customer_id INT, ship_to_customer_id INT, status STRING",
    "sales_order_lines": "sales_order_id INT, line_no INT, item_id INT, quantity DOUBLE, unit_price DOUBLE, promised_date DATE",
    "purchase_orders": "purchase_order_id INT, supplier_id INT, order_date DATE, expected_date DATE, status STRING",
    "purchase_order_lines": "purchase_order_id INT, line_no INT, item_id INT, quantity DOUBLE, unit_price DOUBLE, received_quantity DOUBLE",
    "production_orders": ("production_order_id INT, item_id INT, quantity DOUBLE, work_center_code STRING, sales_order_id INT, "
                          "planned_start DATE, planned_finish DATE, actual_start DATE, actual_finish DATE, status STRING"),
    "production_operations": ("production_operation_id INT, production_order_id INT, sequence_no INT, work_center_code STRING, "
                              "setup_hours DOUBLE, run_hours DOUBLE, finished_on DATE"),
    "inventory_transactions": ("inventory_transaction_id INT, item_id INT, transaction_type STRING, quantity DOUBLE, "
                               "transaction_date DATE, production_order_id INT, purchase_order_id INT"),
    "deliveries": "delivery_id INT, sales_order_id INT, line_no INT, delivered_quantity DOUBLE, delivery_date DATE",
    "item_prices": "item_price_id INT, item_id INT, valid_from DATE, valid_to DATE, unit_price DOUBLE, currency STRING",
    "stg_supplier_prices": "supplier_price_id INT, supplier_id INT, item_id INT, unit_price DOUBLE, loaded_at TIMESTAMP",
    "machine_events": "work_center_code STRING, event_type STRING, event_at TIMESTAMP, minutes INT",
}

# --------------------------------------------------------------- master data (fixed lists, no randomness) ----------

_CUSTOMERS = [  # (name, country, city); the first four are group parents, some later ones belong to them
    ("Northlake Machinery", "SE", "Västerås"), ("Fjordline Equipment", "NO", "Stavanger"), ("Baltic Conveyor Systems", "FI", "Turku"),
    ("Heathfield Processing", "DE", "Bremen"), ("Ridgeway Bulk Handling", "SE", "Gävle"), ("Saltmarsh Packaging", "DK", "Aarhus"),
    ("Granite Quarry Works", "SE", "Borlänge"), ("Pinewood Sawmills", "SE", "Härnösand"), ("Ironbridge Foundry", "DE", "Duisburg"),
    ("Lakeshore Dairy Plant", "FI", "Oulu"), ("Copperhill Mining", "SE", "Kiruna"), ("Seaport Grain Terminal", "DK", "Esbjerg"),
    ("Riverbend Paper", "SE", "Sundsvall"), ("Highmoor Recycling", "NO", "Trondheim"), ("Westgate Food Lines", "SE", "Jönköping"),
    ("Oakfield Brewery Supply", "DE", "Kassel"), ("Stonebrook Cement", "SE", "Skövde"), ("Clearwater Pumps Service", "NO", "Bergen"),
    ("Kestrel Automation", "SE", "Linköping"), ("Meadowvale Feed Mill", "SE", "Kristianstad"), ("Ashby Logistics Centre", "DE", "Hannover"),
    ("Frostvik Fish Processing", "NO", "Ålesund"), ("Elmstead Glassworks", "SE", "Växjö"), ("Brightwater Treatment", "FI", "Tampere"),
    ("Hollow Oak Timber", "SE", "Mora"), ("Northern Rail Workshops", "SE", "Luleå"), ("Silverdale Plastics", "DK", "Odense"),
    ("Cobalt Bay Shipyard", "FI", "Rauma"), ("Thornbury Textiles", "SE", "Borås"), ("Redcliff Asphalt", "NO", "Drammen"),
    ("Windmere Sugar", "SE", "Örtofta"), ("Larchwood Pallets", "SE", "Nässjö"),
]
_PARENTS = {7: 1, 11: 1, 13: 1, 9: 4, 16: 4, 14: 2, 22: 2, 24: 3, 28: 3}      # customer_id -> parent_customer_id (a group)

_SUPPLIERS = [  # (name, country, lead_time_days)
    ("Nordsteel Plate", "SE", 14), ("Ruhr Bar Stock", "DE", 21), ("Bothnia Bearings", "FI", 10), ("Fastline Fasteners", "SE", 5),
    ("Elbe Castings", "DE", 35), ("Coastal Paints", "DK", 7), ("Polar Seals", "NO", 12), ("Midland Motors", "DE", 28),
    ("Tarn Tube", "SE", 14), ("Glacier Gaskets", "FI", 9), ("Harrow Hydraulics", "DE", 20), ("Sound Springs", "DK", 8),
]

_WORK_CENTERS = [  # (code, name, hourly_rate, hours_per_day)
    ("SAW", "Saw line", 520.0, 16.0), ("CNC1", "CNC lathe 1", 780.0, 16.0), ("CNC2", "CNC machining centre 2", 860.0, 16.0),
    ("WELD", "Welding cell", 690.0, 8.0), ("PAINT", "Paint line", 610.0, 8.0), ("ASSY", "Assembly", 560.0, 16.0),
    ("TEST", "Test bench", 640.0, 8.0), ("PACK", "Packing", 450.0, 8.0),
]

# Raw materials, bought: (name, unit, standard_cost, supplier_id)
_RAW = [
    ("Steel bar 30 mm", "m", 92.0, 2), ("Steel bar 45 mm", "m", 168.0, 2), ("Steel bar 60 mm", "m", 290.0, 2),
    ("Steel tube 89 mm", "m", 214.0, 9), ("Steel tube 114 mm", "m", 286.0, 9), ("Steel tube 133 mm", "m", 341.0, 9),
    ("Sheet steel 3 mm", "kg", 18.5, 1), ("Sheet steel 6 mm", "kg", 19.2, 1), ("Plate steel 12 mm", "kg", 21.0, 1),
    ("Ball bearing 6205", "pcs", 64.0, 3), ("Ball bearing 6206", "pcs", 78.0, 3), ("Ball bearing 6308", "pcs", 142.0, 3),
    ("Hex bolt M8x30", "pcs", 1.4, 4), ("Hex bolt M10x40", "pcs", 2.1, 4), ("Hex bolt M12x50", "pcs", 3.3, 4),
    ("Lock nut M10", "pcs", 0.9, 4), ("Washer 10 mm", "pcs", 0.3, 4), ("Circlip 25 mm", "pcs", 1.1, 4),
    ("Grey cast blank, small", "pcs", 310.0, 5), ("Grey cast blank, large", "pcs", 640.0, 5),
    ("Primer, red oxide", "l", 96.0, 6), ("Top coat, grey", "l", 132.0, 6), ("Top coat, blue", "l", 138.0, 6),
    ("Lip seal 25 mm", "pcs", 12.0, 7), ("Lip seal 40 mm", "pcs", 17.0, 7), ("O-ring 60 mm", "pcs", 3.2, 10),
    ("Gasket, pump flange", "pcs", 9.5, 10), ("Electric motor 1.5 kW", "pcs", 2350.0, 8), ("Electric motor 3 kW", "pcs", 3480.0, 8),
    ("Electric motor 5.5 kW", "pcs", 5120.0, 8), ("Hydraulic hose 1 m", "pcs", 145.0, 11), ("Compression spring 20 mm", "pcs", 4.6, 12),
    ("Shaft key 8x7", "pcs", 2.2, 4), ("Grease cartridge", "pcs", 38.0, 3), ("Packing crate, small", "pcs", 120.0, 6),
    ("Packing crate, large", "pcs", 210.0, 6),
]
# Parts, made here from raw materials: (name, standard_cost, [(raw index, quantity)], work_center_code)
_PARTS = [
    ("Roller shaft 30x650", 0, [(0, 0.7)], "CNC1"), ("Roller shaft 45x850", 0, [(1, 0.9)], "CNC1"), ("Roller shaft 60x1050", 0, [(2, 1.1)], "CNC1"),
    ("Roller tube 89x600", 0, [(3, 0.6)], "SAW"), ("Roller tube 114x800", 0, [(4, 0.8)], "SAW"), ("Roller tube 133x1000", 0, [(5, 1.0)], "SAW"),
    ("End cap 89", 0, [(6, 0.4)], "CNC2"), ("End cap 114", 0, [(6, 0.6)], "CNC2"), ("End cap 133", 0, [(7, 0.8)], "CNC2"),
    ("Bearing housing 6205", 0, [(18, 1), (6, 0.3)], "CNC2"), ("Bearing housing 6206", 0, [(18, 1), (6, 0.4)], "CNC2"),
    ("Bearing housing 6308", 0, [(19, 1), (7, 0.5)], "CNC2"),
    ("Pump casing small", 0, [(18, 1)], "CNC2"), ("Pump casing large", 0, [(19, 1)], "CNC2"),
    ("Impeller 160", 0, [(8, 2.4)], "CNC2"), ("Impeller 220", 0, [(8, 3.6)], "CNC2"),
    ("Pump shaft 30", 0, [(0, 0.5), (32, 1)], "CNC1"), ("Pump shaft 45", 0, [(1, 0.6), (32, 1)], "CNC1"),
    ("Base frame small", 0, [(8, 14.0)], "WELD"), ("Base frame large", 0, [(8, 26.0)], "WELD"),
    ("Gearbox housing upper", 0, [(19, 1)], "CNC2"), ("Gearbox housing lower", 0, [(19, 1)], "CNC2"),
    ("Gear shaft 45", 0, [(1, 0.5), (32, 2)], "CNC1"), ("Gear shaft 60", 0, [(2, 0.6), (32, 2)], "CNC1"),
    ("Guard plate", 0, [(6, 3.5)], "WELD"), ("Mounting bracket", 0, [(7, 1.8)], "WELD"),
]
# Finished goods, sold: (name, [(part index, quantity)], [(raw index, quantity)], list price)
_FINISHED = [
    ("Conveyor roller CR-89/600", [(0, 1), (3, 1), (6, 2), (9, 2)], [(9, 2), (24, 2), (17, 2), (21, 0.1)], 1450.0),
    ("Conveyor roller CR-114/800", [(1, 1), (4, 1), (7, 2), (10, 2)], [(10, 2), (24, 2), (17, 2), (21, 0.15)], 2290.0),
    ("Conveyor roller CR-133/1000", [(2, 1), (5, 1), (8, 2), (11, 2)], [(11, 2), (24, 2), (21, 0.2)], 3380.0),
    ("Heavy roller HR-133/1000", [(2, 1), (5, 1), (8, 2), (11, 2), (25, 2)], [(11, 2), (14, 8), (22, 0.2)], 4150.0),
    ("Pump unit PU-160/1.5", [(12, 1), (14, 1), (16, 1), (18, 1), (24, 1)], [(27, 1), (23, 1), (26, 2), (13, 8), (20, 0.3), (21, 0.3)], 11800.0),
    ("Pump unit PU-160/3", [(12, 1), (14, 1), (16, 1), (18, 1), (24, 1)], [(28, 1), (23, 1), (26, 2), (13, 8), (20, 0.3), (21, 0.3)], 13900.0),
    ("Pump unit PU-220/5.5", [(13, 1), (15, 1), (17, 1), (19, 1), (24, 1)], [(29, 1), (24, 1), (26, 2), (14, 8), (20, 0.5), (21, 0.5)], 19400.0),
    ("Pump unit PU-220/5.5 blue", [(13, 1), (15, 1), (17, 1), (19, 1), (24, 1)], [(29, 1), (24, 1), (26, 2), (14, 8), (20, 0.5), (22, 0.5)], 19900.0),
    ("Gearbox housing set GH-45", [(20, 1), (21, 1), (22, 1), (25, 2)], [(10, 2), (23, 2), (13, 12), (33, 1)], 8600.0),
    ("Gearbox housing set GH-60", [(20, 1), (21, 1), (23, 1), (25, 2)], [(11, 2), (23, 2), (14, 12), (33, 1)], 10200.0),
    ("Hydraulic tensioner HT-20", [(25, 1), (16, 1)], [(30, 2), (31, 2), (15, 4), (16, 4)], 3900.0),
    ("Drive station DS-3", [(19, 1), (22, 1), (24, 2)], [(28, 1), (12, 1), (14, 12), (21, 0.6)], 24800.0),
]
_ROUTING = {  # finished good index -> the work centers its production order passes, in order
    "roller": ["SAW", "CNC1", "ASSY", "PAINT", "PACK"], "pump": ["CNC2", "WELD", "ASSY", "PAINT", "TEST", "PACK"],
    "gearbox": ["CNC2", "CNC1", "ASSY", "PACK"], "other": ["WELD", "ASSY", "TEST", "PACK"],
}

# --------------------------------------------------------------- the planted problems (fixed places) -----------------
# Every one is listed in tests/fixtures/mill/planted_issues.json; tests/test_mill.py asserts the check finds exactly these.
MISSING_ITEM_IDS = (9001, 9002)                 # items that do not exist
ORPHAN_ORDER_LINES = ((30005, 2, 9001), (30088, 1, 9002))       # (sales_order_id, line_no, item_id) set to a missing item
ORPHAN_INVENTORY_TRANSACTION = 70900            # inventory_transaction_id whose item_id is 9001
ORPHAN_OPERATION = (60040, "LASER")              # production_operation_id, a work_center_code that does not exist
DUPLICATE_SUPPLIER_PRICE_ID = 95012             # stg_supplier_prices: this id is loaded twice
LATE_EVERY = 37                                 # every 37th delivered order line arrives after its promised date
N_ORDERS = 200                                  # sales orders over the two years
# Each table numbers its rows in a range of its own, as an ERP's number series do, so an id of one table is never by
# chance a value of another: customers 10001-, suppliers 20001-, items 100-599, sales orders 30001-, purchase orders
# 40001-, production orders 50001-, operations 60001-, inventory transactions 70001-, deliveries 80001-, item prices
# 90001-, staged supplier prices 95001-.
CUSTOMER_BASE, SUPPLIER_BASE = 10000, 20000


def _round(x: float, n: int = 2) -> float:
    return float(round(x, n))


def _items() -> tuple[list[tuple], list[tuple]]:
    """items and bill_of_materials. Ids: raw 100+, parts 300+, finished 500+."""
    items, bom = [], []
    raw_id = {i: 100 + i for i in range(len(_RAW))}
    part_id = {i: 300 + i for i in range(len(_PARTS))}
    for i, (name, unit, cost, sup) in enumerate(_RAW):
        items.append((raw_id[i], f"RM-{raw_id[i]:04d}", name, "raw material", unit, cost, SUPPLIER_BASE + sup))
    part_cost = {}
    for i, (name, _c, comps, _wc) in enumerate(_PARTS):
        cost = sum(_RAW[r][2] * q for r, q in comps) * 1.35 + 40.0           # material plus machining
        part_cost[i] = _round(cost)
        items.append((part_id[i], f"PT-{part_id[i]:04d}", name, "part", "pcs", part_cost[i], None))
        bom += [(part_id[i], raw_id[r], float(q)) for r, q in comps]
    for i, (name, parts, raws, _price) in enumerate(_FINISHED):
        fid = 500 + i
        cost = sum(part_cost[p] * q for p, q in parts) + sum(_RAW[r][2] * q for r, q in raws) + 180.0
        items.append((fid, f"FG-{fid:04d}", name, "finished good", "pcs", _round(cost), None))
        bom += [(fid, part_id[p], float(q)) for p, q in parts] + [(fid, raw_id[r], float(q)) for r, q in raws]
    return items, bom


def _family(name: str) -> str:
    return ("roller" if "roller" in name.lower() else "pump" if "Pump" in name else "gearbox" if "Gearbox" in name else "other")


def rows(seed_value: int = 7) -> dict[str, list[tuple]]:
    """Every table's rows as tuples in SCHEMAS' column order. Deterministic: the same seed gives the same rows."""
    rnd = random.Random(seed_value)
    customers = [(CUSTOMER_BASE + i + 1, n, c, city, CUSTOMER_BASE + _PARENTS[i + 1] if i + 1 in _PARENTS else None)
                 for i, (n, c, city) in enumerate(_CUSTOMERS)]
    suppliers = [(SUPPLIER_BASE + i + 1, n, c, lt) for i, (n, c, lt) in enumerate(_SUPPLIERS)]
    items, bom = _items()
    work_centers = list(_WORK_CENTERS)
    finished = [it for it in items if it[3] == "finished good"]
    price_of = {500 + i: f[3] for i, f in enumerate(_FINISHED)}
    cost_of = {it[0]: it[5] for it in items}
    days = (END - START).days

    # item prices: a list price per finished good, raised once a year (valid_from / valid_to)
    item_prices, pid = [], 90001
    for fid, base in price_of.items():
        periods = [(START, date(2025, 3, 31)), (date(2025, 4, 1), date(2026, 3, 31)), (date(2026, 4, 1), None)]
        for k, (vf, vt) in enumerate(periods):
            item_prices.append((pid, fid, vf, vt, _round(base * (1.0 + 0.04 * k)), "SEK"))
            pid += 1

    def list_price(item_id: int, on: date) -> float:
        for _p, i, vf, vt, price, _cur in item_prices:
            if i == item_id and vf <= on and (vt is None or on <= vt):
                return price
        return price_of[item_id]

    # sales orders and lines; ship-to is the buyer or, for a group member, sometimes another site of the group
    sales_orders, lines = [], []
    groups: dict[int, list[int]] = {}
    for c in customers:
        groups.setdefault(c[4] or c[0], []).append(c[0])
    for n in range(N_ORDERS):
        so = 30001 + n
        od = START + timedelta(days=int(n * days / N_ORDERS) + rnd.randrange(0, 2))
        bill = rnd.choice([c[0] for c in customers if c[4] is None] * 2 + [c[0] for c in customers])
        group = groups.get(customers[bill - CUSTOMER_BASE - 1][4] or bill, [bill])
        ship = rnd.choice(group) if rnd.random() < 0.3 else bill
        sales_orders.append([so, od, bill, ship, "open"])
        for ln in range(1, rnd.choice([1, 2, 2, 3, 3, 4]) + 1):
            fg = rnd.choice(finished)
            qty = float(rnd.choice([1, 2, 2, 4, 5, 10, 20]) if "roller" in fg[2].lower() else rnd.choice([1, 1, 2, 3]))
            promised = od + timedelta(days=rnd.choice([14, 21, 28, 35, 42]))
            lines.append([so, ln, fg[0], qty, list_price(fg[0], od), promised])
    for so, ln, item in ORPHAN_ORDER_LINES:                         # planted: two lines point at items that do not exist
        line = next(x for x in lines if x[0] == so and x[1] == ln)
        line[2] = item

    # deliveries: each line delivered in one or two parts on or before the promised date, except the planted late ones;
    # lines promised after the data's end are still open (the order backlog)
    deliveries, did, k = [], 80001, 0
    delivered: dict[tuple, float] = {}
    for so, ln, item, qty, _price, promised in lines:
        if promised > END - timedelta(days=10):
            continue                                              # not delivered yet: backlog
        k += 1
        late = k % LATE_EVERY == 0
        parts = [qty] if qty < 4 or rnd.random() < 0.75 else [float(int(qty / 2)), qty - float(int(qty / 2))]
        for j, q in enumerate(parts):
            if late:
                when = promised + timedelta(days=rnd.choice([3, 5, 8, 12, 19]) + j)
            else:
                when = promised - timedelta(days=rnd.choice([0, 1, 2, 3, 5, 7]) - 0 * j)
            deliveries.append((did, so, ln, q, min(when, END)))
            did += 1
        delivered[(so, ln)] = qty
    for o in sales_orders:
        ls = [x for x in lines if x[0] == o[0]]
        done = sum(1 for x in ls if (x[0], x[1]) in delivered)
        o[4] = "closed" if done == len(ls) else "part delivered" if done else "open"

    # production orders: one per finished-good order line, started before the promised date, plus some for stock
    production, ops, prod_id, op_id = [], [], 50001, 60001
    wc_hours = {"roller": 0.6, "pump": 2.2, "gearbox": 1.8, "other": 1.5}
    for so, ln, item, qty, _price, promised in lines:
        if item in MISSING_ITEM_IDS or rnd.random() < 0.45:
            continue                                              # delivered from stock
        fam = _family(next(it[2] for it in items if it[0] == item))
        route = _ROUTING[fam]
        p_finish = promised - timedelta(days=rnd.choice([2, 3, 4]))
        p_start = p_finish - timedelta(days=len(route) + rnd.choice([1, 2, 3]))
        a_start = p_start + timedelta(days=rnd.choice([-1, 0, 0, 0, 1, 2]))
        a_finish = p_finish + timedelta(days=rnd.choice([-1, 0, 0, 0, 1, 2, 4]))
        finished_yet = a_finish <= END
        production.append((prod_id, item, qty, route[-2], so, p_start, p_finish,
                           a_start if a_start <= END else None, a_finish if finished_yet else None,
                           "finished" if finished_yet else "released" if a_start <= END else "planned"))
        for seq, wc in enumerate(route, start=1):
            run = _round(qty * wc_hours[fam] * rnd.uniform(0.3, 0.6), 2)
            day = a_start + timedelta(days=seq - 1)
            ops.append((op_id, prod_id, seq * 10, wc, _round(rnd.choice([0.25, 0.5, 0.75, 1.0])), run,
                        day if finished_yet else None))
            op_id += 1
        prod_id += 1
    for n in range(30):                                           # make-to-stock orders for the parts
        part = items[len(_RAW) + (n % len(_PARTS))]
        wc = _PARTS[n % len(_PARTS)][3]
        ps = START + timedelta(days=int(n * days / 30))
        qty = float(rnd.choice([20, 40, 50, 100]))
        production.append((prod_id, part[0], qty, wc, None, ps, ps + timedelta(days=3), ps, ps + timedelta(days=rnd.choice([3, 3, 4])), "finished"))
        ops.append((op_id, prod_id, 10, wc, 0.5, _round(qty * 0.08), ps + timedelta(days=2)))
        op_id += 1
        prod_id += 1
    ops = [list(o) for o in ops]
    for o in ops:                                                 # planted: one operation at a work center that does not exist
        if o[0] == ORPHAN_OPERATION[0]:
            o[3] = ORPHAN_OPERATION[1]
    ops = [tuple(o) for o in ops]

    # purchase orders for raw materials, by supplier, about every week
    purchase_orders, po_lines = [], []
    raws = [it for it in items if it[3] == "raw material"]
    for n in range(120):
        po = 40001 + n
        sup = suppliers[n % len(suppliers)]
        od = START + timedelta(days=int(n * days / 120))
        exp = od + timedelta(days=sup[3])
        bought = [r for r in raws if r[6] == sup[0]] or raws[:3]
        received_all = exp + timedelta(days=5) <= END
        purchase_orders.append((po, sup[0], od, exp, "received" if received_all else "open"))
        for ln, r in enumerate(rnd.sample(bought, min(len(bought), rnd.choice([1, 2, 3]))), start=1):
            qty = float(rnd.choice([10, 20, 50, 100, 200, 500]) if r[5] < 50 else rnd.choice([2, 4, 6, 10, 20]))
            got = qty if received_all else (0.0 if rnd.random() < 0.6 else float(int(qty / 2)))
            po_lines.append((po, ln, r[0], qty, _round(r[5] * rnd.uniform(0.95, 1.05)), got))

    # inventory transactions: receipts from purchase orders, receipts from and issues to production, adjustments
    inv, tid = [], 1
    po_date = {p[0]: p[3] for p in purchase_orders}
    for po, _ln, item, _qty, _price, got in po_lines:
        if got:
            inv.append([tid, item, "receipt", got, min(po_date[po] + timedelta(days=rnd.choice([0, 1, 2])), END), None, po]); tid += 1
    bom_of: dict[int, list[tuple]] = {}
    for parent, comp, q in bom:
        bom_of.setdefault(parent, []).append((comp, q))
    for p in production:
        if p[8] is None:
            continue
        for comp, q in bom_of.get(p[1], [])[:2]:
            inv.append([tid, comp, "issue", -_round(q * p[2]), p[7], p[0], None]); tid += 1
        inv.append([tid, p[1], "receipt", p[2], p[8], p[0], None]); tid += 1
    for n in range(60):                                           # stock counts: small corrections
        it = items[(n * 7) % len(items)]
        inv.append([tid, it[0], "adjustment", float(rnd.choice([-3, -2, -1, 1, 2])), START + timedelta(days=int(n * days / 60) + 3), None, None]); tid += 1
    inv.sort(key=lambda r: (r[4], r[0]))
    inv = [[70001 + i] + r[1:] for i, r in enumerate(inv)]
    for r in inv:                                                 # planted: one transaction for an item that does not exist
        if r[0] == ORPHAN_INVENTORY_TRANSACTION:
            r[1] = MISSING_ITEM_IDS[0]
    inv = [tuple(r) for r in inv]

    # a staging table loaded from suppliers' price files; one row is loaded twice (the same supplier_price_id)
    stg = []
    for n in range(48):
        r = raws[n % len(raws)]
        stg.append((95001 + n, r[6], r[0], _round(r[5] * rnd.uniform(0.9, 1.1)),
                    datetime(2026, 9, 1, 6, 0) + timedelta(days=n // 12, minutes=n)))
    dup = next(s for s in stg if s[0] == DUPLICATE_SUPPLIER_PRICE_ID)
    stg.append(dup[:4] + (dup[4] + timedelta(days=1),))           # planted: the same id loaded again a day later

    # machine events: an event log with no key (stops, starts, maintenance)
    events = []
    for n in range(110):                                          # logged on the hour, two work centers at a time
        at = datetime.combine(START, _dt.time(6, 0)) + timedelta(days=int(n * days / 110), hours=rnd.randrange(0, 10))
        for wc in rnd.sample([w[0] for w in work_centers], 2):
            events.append((wc, rnd.choice(["stop", "start", "maintenance", "tool change", "stop"]), at, rnd.choice([5, 10, 15, 30, 45, 90])))

    return {
        "customers": customers, "suppliers": suppliers, "items": items, "bill_of_materials": bom, "work_centers": work_centers,
        "sales_orders": [tuple(o) for o in sales_orders], "sales_order_lines": [tuple(x) for x in lines],
        "purchase_orders": purchase_orders, "purchase_order_lines": po_lines, "production_orders": production,
        "production_operations": ops, "inventory_transactions": inv, "deliveries": deliveries, "item_prices": item_prices,
        "stg_supplier_prices": stg, "machine_events": events,
    }


def schema(name: str = "mill"):
    """The sixteen tables as a `Schema` (no data), for planning offline."""
    from .schema import Column, Schema, Table
    s = Schema(schema=name)
    for table, cols in SCHEMAS.items():
        s.tables[table] = Table(table, [Column(c.split()[0], c.split()[1].lower()) for c in cols.split(", ")], schema=name)
    return s


def source(name: str = "mill", seed_value: int = 7):
    """The mill's rows in an in-memory SQLite database, as a local Source (what /check and the tests read)."""
    import sqlite3
    from .platforms.local import Source, _sqlite_execute
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS [{name}]")
    for table, data in rows(seed_value).items():
        con.execute(f"CREATE TABLE [{name}].[{table}] ({SCHEMAS[table]})")
        data = [tuple(v.isoformat() if isinstance(v, (date, datetime)) else v for v in r) for r in data]
        con.executemany(f"INSERT INTO [{name}].[{table}] VALUES ({','.join('?' * len(data[0]))})", data)
    return Source("folder", "Synthetic manufacturing data (fabric_backend.mill, sixteen tables, no real company)", schema(name),
                  _sqlite_execute(con), "sqlite",
                  [f"Synthetic rows from fabric_backend.mill: {COMPANY}, invented customers, suppliers and items."], con.close)


def seed(spark, schema: str = "mill", seed_value: int = 7) -> dict[str, int]:
    """Create (or replace) the sixteen tables in `schema` of the attached lakehouse (a lakehouse with schemas). Returns
    row counts. seed.seed(spark, mill=True) calls this after the shop."""
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    counts = {}
    for name, data in rows(seed_value).items():
        df = spark.createDataFrame(data, SCHEMAS[name])
        df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{schema}.{name}")
        counts[name] = len(data)
    return counts
