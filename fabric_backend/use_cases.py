"""The /use-cases page: the same engine on typical table designs from ten industries.

Each scenario is a small synthetic schema (generic names, no customer data). The schema sketches on the page are
drawn from the real `infer.plan()` and `evidence.suggest_composite_keys()` on these tables, and every claim the text
makes about a key, a link, a rule or a suggestion is listed in `checks` and verified by `tests/test_use_cases.py`.
If the engine changes, the tests say which sentence is no longer true.

Text fields use `backticks` for code; everything is HTML-escaped when rendered.
"""
from __future__ import annotations

import html
import re
from functools import lru_cache

from .tool_status import task_status

FOOTNOTE = "The schemas are illustrative examples, not customer projects."

COLORS = ("coral", "sage", "lav", "mustard")
NUMBER_WORDS = {7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve"}

INDUSTRIES: list[dict] = [
    {
        "slug": "retail", "name": "Retail & e-commerce", "color": "coral",
        "lead": "Follow a return back to the right order line.",
        "summary": ("A returned product belongs to an order line, not just an order. In this example, the plan uses "
                    "`order_id` and `line_no` together so you can review that relationship before creating the API. An "
                    "app can then read the order, its products and its returns through the same model."),
        "tables": {
            "customers": "customer_id email country created_at",
            "orders": "order_id customer_id order_date status",
            "order_lines": "order_id line_no product_id quantity unit_price",
            "products": "product_id sku category_id list_price",
            "categories": "category_id parent_category_id name",
            "returns": "return_id order_id line_no reason",
        },
        "finds": [
            ("R1", "`orders.customer_id` → `customers`: the column is named after the table. The same rule links "
                   "`order_lines.product_id` → `products` and `products.category_id` → `categories`."),
            ("K5", "`order_lines` has no key column of its own. The line rule (K5) takes the reference to its "
                   "header plus the line number, `order_id + line_no`, and `returns.order_id + line_no` → "
                   "`order_lines` follows by R3."),
            ("confirm", "`categories.parent_category_id` points back at its own table, and no rule links a table to "
                        "itself by name. Confirm it once and the API gets a `parent_category` field."),
        ],
        "build": [
            "A returns desk in Lovable over the GraphQL API: an order, its lines and products, and what came back, "
            "in one nested query.",
            "Questions in Claude through `query_graphql`, such as which categories see the most returns.",
            "A Power BI semantic model draft from the same keys.",
        ],
        "value": [
            "The line-level key is stated once, so a return is joined to its order line, not to the whole order.",
        ],
        "checks": {
            "keys": [("order_lines", "order_id+line_no", "K5")],
            "links": [("orders", "customer_id", "customers", "R1"), ("order_lines", "product_id", "products", "R1"),
                      ("products", "category_id", "categories", "R1"), ("returns", "order_id+line_no", "order_lines", "R3")],
            "keyless": [],
            "roles": [("categories", "parent_category_id", "categories", "category_id", "parent_category")],
        },
    },
    {
        "slug": "manufacturing", "name": "Manufacturing", "color": "sage",
        "lead": "Keep the parent item and the component apart.",
        "summary": ("A bill of materials can refer to the same item table twice. The plan shows both roles so you can "
                    "check which column means the parent and which means the component. This example covers one level of "
                    "the bill of materials; a full recursive breakdown is separate work."),
        "tables": {
            "items": "item_no description unit item_type",
            "bill_of_materials": "parent_item_no component_item_no quantity",
            "work_orders": "work_order_id item_no machine_id planned_start status",
            "machines": "machine_id line_name model",
            "quality_checks": "quality_check_id work_order_id checked_at result",
        },
        "finds": [
            ("R1", "`items` gets `item_no` as its key (K2 also reads `_no`), and `work_orders.item_no` → `items` "
                   "follows. `work_orders.machine_id` → `machines` and `quality_checks.work_order_id` → "
                   "`work_orders` the same way."),
            ("R4", "`bill_of_materials` points at `items` twice, through `parent_item_no` and `component_item_no`. "
                   "Both are linked by R4, the weaker rule for a role in front of a table's name, as `parent_item` and "
                   "`component_item` fields. Check them before you build."),
            ("K4", "`bill_of_materials` has no key column and starts with those two references, so the junction rule "
                   "(K4) makes `parent_item_no + component_item_no` its key. `validate_plan` counts duplicates and "
                   "NULLs in it before anything is built."),
        ],
        "build": [
            "A shop-floor app over GraphQL: a work order with its item, machine and quality checks.",
            "One level of a bill of materials per query. A full explosion is recursive, and that stays a SQL job.",
            "Questions in Claude, such as which machines had failed checks last week.",
        ],
        "value": [
            "The two-way bill of materials is a classic wrong join. Both roles carry the weaker rule, so they get reviewed instead of assumed.",
        ],
        "checks": {
            "keys": [("items", "item_no", "K2"), ("bill_of_materials", "parent_item_no+component_item_no", "K4")],
            "links": [("work_orders", "item_no", "items", "R1"), ("work_orders", "machine_id", "machines", "R1"),
                      ("quality_checks", "work_order_id", "work_orders", "R1")],
            "fields": [("bill_of_materials", "parent_item_no", "items", "R4", "parent_item"),
                       ("bill_of_materials", "component_item_no", "items", "R4", "component_item")],
            "keyless": [],
        },
    },
    {
        "slug": "saas", "name": "SaaS & subscriptions", "color": "lav",
        "lead": "Which account uses the service, and which one pays?",
        "summary": "Accounts on plans, invoices with lines, and a stream of usage events.",
        "tables": {
            "accounts": "account_id name owner_email created_at",
            "plans": "plan_id name monthly_price",
            "subscriptions": "subscription_id account_id plan_id billing_account_id started_at",
            "invoices": "invoice_id account_id subscription_id issued_at total",
            "invoice_lines": "invoice_id line_no description amount",
            "usage_events": "event_id subscription_id event_type occurred_at",
        },
        "finds": [
            ("R1", "`subscriptions.account_id` → `accounts` and `subscriptions.plan_id` → `plans`; "
                   "`invoices.subscription_id` → `subscriptions` as well."),
            ("R4", "`subscriptions.billing_account_id` → `accounts` by R4, the weaker rule for a role in front of a "
                   "table's name, as a `billing_account` field. Probably right, for example a parent company paying "
                   "for a subsidiary, but only you know: check it, or confirm another target."),
            ("K5", "`invoice_lines` gets `invoice_id + line_no` by the line rule (K5). `usage_events` has `event_id`, "
                   "which is not named after the table, so it gets no key (K3). It still points at `subscriptions`, "
                   "but nothing can point at it until you give the key (K1)."),
        ],
        "build": [
            "A self-service billing page in Lovable: an account, its subscriptions, invoices and invoice lines.",
            "Usage per plan, asked in Claude and answered through the API without writing SQL.",
            "A semantic model draft for revenue reporting from the same keys.",
        ],
        "value": [
            "The using account and the paying account are kept apart from the start, not discovered in a wrong revenue figure later.",
        ],
        "checks": {
            "keys": [("invoice_lines", "invoice_id+line_no", "K5")],
            "links": [("subscriptions", "account_id", "accounts", "R1"), ("subscriptions", "plan_id", "plans", "R1"),
                      ("invoices", "subscription_id", "subscriptions", "R1"),
                      ("usage_events", "subscription_id", "subscriptions", "R1")],
            "fields": [("subscriptions", "billing_account_id", "accounts", "R4", "billing_account")],
            "keyless": ["usage_events"],
        },
    },
    {
        "slug": "professional-services", "name": "Professional services", "color": "mustard",
        "lead": "See which project hours are still unbilled.",
        "summary": ("Start with clients, projects, consultants and time entries. Review how an entry connects to its "
                    "project and invoice, including entries with no invoice yet. The resulting API gives an internal tool"
                    " a way to read those records together."),
        "tables": {
            "clients": "client_id name sector",
            "consultants": "consultant_id name grade manager_id",
            "projects": "project_id client_id lead_consultant_id name",
            "time_entries": "time_entry_id consultant_id project_id work_date hours invoice_id",
            "invoices": "invoice_id client_id issued_at amount",
        },
        "finds": [
            ("R1", "`time_entries.project_id` → `projects`, `time_entries.consultant_id` → `consultants` and "
                   "`time_entries.invoice_id` → `invoices`. An empty `invoice_id` is an unbilled hour: "
                   "`validate_plan` counts rows with a value and orphans separately."),
            ("R4", "`projects.lead_consultant_id` → `consultants` by R4, a role in front of the table's name, as a "
                   "`lead_consultant` field. `consultants.manager_id` names no table at all, so it stays unlinked "
                   "until you confirm it; then it is `manager`."),
            ("K2", "Every table here has a key by name (`client_id`, `project_id`, `time_entry_id`, …), so the API "
                   "can fetch any single row by its key."),
        ],
        "build": [
            "A utilisation app: hours per consultant and project, with the client one level up.",
            "Questions in Claude, such as which projects have hours that are not invoiced yet.",
            "A Fabric IQ ontology draft (preview) with Client, Project, Consultant and Time entry entity types.",
        ],
        "value": [
            "Hours to invoices is the join that decides revenue. Its rule and its orphan count are visible before anything is built.",
        ],
        "checks": {
            "keys": [("clients", "client_id", "K2"), ("projects", "project_id", "K2"), ("time_entries", "time_entry_id", "K2")],
            "links": [("time_entries", "project_id", "projects", "R1"), ("time_entries", "consultant_id", "consultants", "R1"),
                      ("time_entries", "invoice_id", "invoices", "R1")],
            "keyless": [],
            "fields": [("projects", "lead_consultant_id", "consultants", "R4", "lead_consultant")],
            "roles": [("consultants", "manager_id", "consultants", "consultant_id", "manager")],
        },
    },
    {
        "slug": "aml", "name": "Financial services: AML", "color": "coral",
        "lead": "Trace a transaction through its account holders.",
        "summary": ("Anti-money laundering: customers, the accounts they hold, transactions, counterparties, alerts and "
                    "KYC reviews."),
        "tables": {
            "customers": "customer_id name country risk_rating",
            "accounts": "account_id product_type opened_at status",
            "account_holders": "customer_id account_id holder_role since",
            "transactions": "transaction_id account_id counterparty_id beneficiary_account_id amount booked_at",
            "counterparties": "counterparty_id name country bank_code",
            "alerts": "alert_id transaction_id customer_id scenario raised_at",
            "kyc_reviews": "kyc_review_id customer_id reviewed_at outcome",
        },
        "finds": [
            ("R1", "`transactions.account_id` → `accounts`, `transactions.counterparty_id` → `counterparties` and "
                   "`alerts.transaction_id` → `transactions`."),
            ("K4", "`account_holders` is a bridge with two outgoing references: `account_holders.customer_id` → "
                   "`customers` and `account_holders.account_id` → `accounts`, both R1. The junction rule (K4) makes "
                   "`customer_id + account_id` its key: one row per holding."),
            ("R4", "`transactions.beneficiary_account_id` → `accounts` by R4, the weaker rule for a role in front of "
                   "a table's name, as a `beneficiary_account` field. The plan says which rule made it, so it is "
                   "checked rather than trusted."),
        ],
        "build": [
            "One explained model that investigators and an agent in Claude query the same way.",
            "Questions such as all transactions between accounts held by the same customer in the last 90 days: one "
            "nested GraphQL query from customer through `account_holders`, accounts and transactions to the "
            "beneficiary account, with the rule or confirmation behind each step.",
            "A read-only investigation app in Lovable over the same API.",
        ],
        "value": [
            "The bridge and the beneficiary account are each stated once with their rules, and `validate_plan` counts orphans before anyone relies on them.",
            "This shows the joins an investigation tool needs. {{PRODUCT}} is not an investigation system: alert logic, scoring "
            "and the organisation's own regulatory validation are separate work.",
        ],
        "note": ("The next layer",
                 "{{PRODUCT}} works on how the tables connect. Finding rings among individual customers and accounts "
                 "(communities, shared addresses or phones, money moving in cycles) is row-level graph analysis, built "
                 "on top of that model, for example with graph tools in Fabric. The explained model makes it possible; "
                 "it is not a {{PRODUCT}} feature today."),
        "checks": {
            "keys": [("account_holders", "customer_id+account_id", "K4")],
            "links": [("transactions", "account_id", "accounts", "R1"), ("transactions", "counterparty_id", "counterparties", "R1"),
                      ("alerts", "transaction_id", "transactions", "R1"), ("account_holders", "customer_id", "customers", "R1"),
                      ("account_holders", "account_id", "accounts", "R1")],
            "fields": [("transactions", "beneficiary_account_id", "accounts", "R4", "beneficiary_account")],
            "keyless": [],
        },
    },
    {
        "slug": "financial-crime", "name": "Financial crime prevention", "color": "sage",
        "lead": "Bring a customer’s cases and screening hits into one view.",
        "summary": "Fraud, sanctions screening and KYC: alerts and cases from teams that usually keep separate tables.",
        "tables": {
            "customers": "customer_id name onboarded_at",
            "cases": "case_id customer_id linked_case_id case_type status",
            "alerts": "alert_id case_id customer_id source_system raised_at",
            "screening_hits": "screening_hit_id customer_id list_entry_id match_score",
            "sanctions_lists": "list_entry_id list_name entry_name published_at",
            "devices": "device_id fingerprint first_seen",
            "logins": "login_id customer_id device_id ip_address logged_in_at",
        },
        "finds": [
            ("R1", "`logins.device_id` → `devices`, `logins.customer_id` → `customers` and `alerts.case_id` → "
                   "`cases`: fraud signals, alerts and cases meet at the customer."),
            ("R2", "`sanctions_lists` has one row per list entry, keyed by `list_entry_id`, which no key rule reads "
                   "(K3). Give it as the key (K1) and `screening_hits.list_entry_id` → `sanctions_lists` follows by R2."),
            ("confirm", "`cases.linked_case_id` ties a case to an earlier one. It points back at its own table, which "
                        "no rule links by name, so you confirm it; then each case has a `linked_case` field."),
        ],
        "build": [
            "One connected view for fraud, sanctions and AML analysts: a customer with cases, alerts, screening hits "
            "and logins.",
            "Questions in Claude, such as which customers with an open screening hit also have a fraud alert this month.",
            "A Fabric IQ ontology draft (preview) as a shared vocabulary across the teams.",
        ],
        "value": [
            "Each relationship includes its rule or confirmation, so a reviewer can inspect why it was added.",
        ],
        "note": ("The next layer",
                 "Several customers sharing one device is a row-level question this model can answer (device, its "
                 "logins, their customers). Scoring, network analysis and screening logic on top are separate work; "
                 "{{PRODUCT}} supplies the explained joins."),
        "checks": {
            "keys_given": {"sanctions_lists": ["list_entry_id"]},
            "links": [("logins", "device_id", "devices", "R1"), ("logins", "customer_id", "customers", "R1"),
                      ("alerts", "case_id", "cases", "R1"), ("screening_hits", "customer_id", "customers", "R1")],
            "links_after_keys": [("screening_hits", "list_entry_id", "sanctions_lists", "R2")],
            "keyless": ["sanctions_lists"],
            "roles": [("cases", "linked_case_id", "cases", "case_id", "linked_case")],
        },
    },
    {
        "slug": "pharma-research", "name": "Pharmaceutical research", "color": "lav",
        "lead": "A visit number is not always a unique key.",
        "summary": ("Clinical studies and lab work: subjects at sites, visits, adverse events, compounds and assay "
                    "results."),
        "tables": {
            "studies": "study_id compound_id phase start_date",
            "sites": "site_id country investigator",
            "subjects": "subject_id study_id site_id arm_code enrolled_at",
            "visits": "subject_id visit_no visit_date visit_type",
            "adverse_events": "adverse_event_id subject_id visit_no severity_code meddra_code",
            "compounds": "compound_id code_name modality",
            "assays": "assay_id assay_type unit",
            "results": "result_id assay_id subject_id visit_no value",
        },
        "finds": [
            ("R1", "`visits.subject_id` → `subjects`, `results.assay_id` → `assays`, `subjects.site_id` → `sites` "
                   "and `studies.compound_id` → `compounds`."),
            ("K1", "From names alone, `visits` gets `visit_no` as its key (K2) and `results.visit_no` → `visits` "
                   "(R1). Both are wrong: visit numbers repeat per subject, and `validate_plan` shows the duplicates. "
                   "The engine does not suggest the fix here; you give `subject_id + visit_no` (K1). The single-column "
                   "links go, and `results` and `adverse_events` reach `visits` by R3 on both columns."),
            ("confirm", "Coded columns such as `adverse_events.severity_code`, `adverse_events.meddra_code` and "
                        "`subjects.arm_code` point at code lists. No rule links them and nothing is guessed: add the "
                        "code-list tables, or confirm each link."),
        ],
        "build": [
            "An agent in Claude that answers research questions through the explained plan, such as which compounds "
            "had adverse events at more than one site.",
            "A study overview app: a subject with visits, results and adverse events.",
            "A semantic model draft for study reporting.",
        ],
        "value": [
            "The visit key above is a confident-but-wrong join, caught before an answer depends on it.",
            "Regulated use, such as GxP work, needs the organisation's own validation; {{PRODUCT}} does not provide it.",
        ],
        "note": ("Better answers",
                 "Asked which compounds had adverse events at more than one site, Claude goes from adverse events to "
                 "subjects, then to sites and to studies and compounds, through joins that were planned, explained and "
                 "checked. The answer can show its path and the rule behind every step, and `validate_plan` has "
                 "already shown whether rows go missing on the way."),
        "checks": {
            "keys_given": {"visits": ["subject_id", "visit_no"]},
            "keys": [("visits", "visit_no", "K2")],
            "links": [("visits", "subject_id", "subjects", "R1"), ("results", "assay_id", "assays", "R1"),
                      ("subjects", "site_id", "sites", "R1"), ("studies", "compound_id", "compounds", "R1"),
                      ("results", "visit_no", "visits", "R1")],
            "links_after_keys": [("results", "subject_id+visit_no", "visits", "R3"),
                                 ("adverse_events", "subject_id+visit_no", "visits", "R3")],
            "gone_after_keys": [("results", "visit_no", "visits"), ("adverse_events", "visit_no", "visits")],
            "keyless": [],
            "suggested": [],
            "not_linked": [("adverse_events", "severity_code"), ("adverse_events", "meddra_code"), ("subjects", "arm_code")],
        },
    },
    {
        "slug": "environment", "name": "Environment & sustainability", "color": "mustard",
        "lead": "See which emission factor an activity refers to.",
        "summary": ("Sites, energy meters and readings, activities with emission factors, and purchases from suppliers "
                    "(Scope 3)."),
        "tables": {
            "sites": "site_id name region",
            "meters": "meter_id site_id energy_type",
            "meter_readings": "meter_id read_at value_kwh",
            "activities": "activity_id site_id emission_factor_id activity_type quantity period_start",
            "emission_factors": "emission_factor_id activity_type valid_from kg_co2e_per_unit",
            "suppliers": "supplier_id name country",
            "purchases": "purchase_id supplier_id site_id spend_category amount purchased_at",
        },
        "finds": [
            ("R1", "`activities.emission_factor_id` → `emission_factors`: the factor behind each activity is an "
                   "explained join. `meters.site_id` → `sites` and `meter_readings.meter_id` → `meters` as well."),
            ("R1", "`purchases.supplier_id` → `suppliers` and `purchases.site_id` → `sites`, for spend-based Scope 3 "
                   "per site and supplier."),
            ("K3", "`meter_readings` has no key, which is fine for rows that are read, not pointed at. Where a factor "
                   "is picked by activity type and date range instead of an id, that is not a key relationship: "
                   "{{PRODUCT}} does not infer it, and it belongs in a SQL view."),
        ],
        "build": [
            "A site app over GraphQL: a site with its meters, activities and purchases.",
            "Questions in Claude, such as emissions per site and quarter with the factor behind each figure.",
            "Factor matching by date range is not a key relationship; write it as a SQL view by hand.",
        ],
        "value": [
            "Each activity points at the factor row it used, so a changed factor shows up as a changed relationship.",
            "It documents joins. It does not make a report meet any reporting standard.",
        ],
        "checks": {
            "links": [("activities", "emission_factor_id", "emission_factors", "R1"), ("meters", "site_id", "sites", "R1"),
                      ("meter_readings", "meter_id", "meters", "R1"), ("purchases", "supplier_id", "suppliers", "R1"),
                      ("purchases", "site_id", "sites", "R1")],
            "keyless": ["meter_readings"],
            "not_linked": [("emission_factors", "activity_type")],
        },
    },
    {
        "slug": "property", "name": "Property & real estate", "color": "coral",
        "lead": "Which unit does this maintenance request belong to?",
        "summary": "Properties split into units, leased to tenants, with maintenance requests.",
        "tables": {
            "properties": "property_id address city",
            "units": "unit_id property_id floor area_m2",
            "tenants": "tenant_id name contact_email",
            "leases": "lease_id unit_id tenant_id start_date monthly_rent",
            "maintenance_requests": "maintenance_request_id unit_id reported_by_tenant_id status opened_at",
        },
        "finds": [
            ("R1", "`units.property_id` → `properties` (the plural is understood), `leases.unit_id` → `units` and "
                   "`leases.tenant_id` → `tenants`."),
            ("R4", "`maintenance_requests.reported_by_tenant_id` → `tenants` by R4, a role in front of the table's "
                   "name, as a `reported_by_tenant` field. Check it before you build."),
            ("K2", "All five tables have a key by name, so the API can fetch any unit, lease or request by its key."),
        ],
        "build": [
            "A caretaker app in Lovable: a unit with its lease, tenant and open requests. Creating requests from "
            "the app needs a warehouse or SQL database source; lakehouse sources are read-only through the API.",
            "Questions in Claude, such as which properties have the most open requests per unit.",
            "A Fabric IQ ontology draft (preview) with Property, Unit, Lease and Tenant entity types.",
        ],
        "value": [
            "Tenant, lease and unit are joined once, so a report does not have to guess which tenant belongs to which unit.",
        ],
        "checks": {
            "keys": [("properties", "property_id", "K2"), ("units", "unit_id", "K2"), ("leases", "lease_id", "K2"),
                     ("maintenance_requests", "maintenance_request_id", "K2")],
            "links": [("units", "property_id", "properties", "R1"), ("leases", "unit_id", "units", "R1"),
                      ("leases", "tenant_id", "tenants", "R1")],
            "keyless": [],
            "fields": [("maintenance_requests", "reported_by_tenant_id", "tenants", "R4", "reported_by_tenant")],
        },
    },
    {
        "slug": "education", "name": "Education", "color": "sage",
        "lead": "What happens when a student takes the same course twice?",
        "summary": "Students enrolled in courses each term, taught by teachers, with grades.",
        "tables": {
            "students": "student_id name cohort",
            "teachers": "teacher_id name department",
            "courses": "course_id teacher_id title credits",
            "enrolments": "student_id course_id term enrolled_at",
            "grades": "grade_id student_id course_id term grade",
        },
        "finds": [
            ("R1", "`courses.teacher_id` → `teachers`, `enrolments.student_id` → `students` and "
                   "`enrolments.course_id` → `courses`."),
            ("K4", "`enrolments` has no key column and starts with two references, so the junction rule (K4) makes "
                   "`student_id + course_id` its key, and `grades` reaches it by R3. If a student can retake a course "
                   "in another term, that key is wrong, and `validate_plan` shows the duplicates."),
            ("K1", "Give `student_id + course_id + term` (K1). Then `grades.student_id + course_id + term` → "
                   "`enrolments` follows by R3 on all three columns."),
        ],
        "build": [
            "A course overview app: a course, its teacher and the students enrolled this term.",
            "Questions in Claude, such as grades per course and term.",
            "A semantic model draft for term reports from the same keys.",
        ],
        "value": [
            "A three-column key is easy to half-write in a join and then double-count. Stating it once avoids that.",
        ],
        "checks": {
            "keys_given": {"enrolments": ["student_id", "course_id", "term"]},
            "keys": [("enrolments", "student_id+course_id", "K4"), ("grades", "grade_id", "K2")],
            "links": [("courses", "teacher_id", "teachers", "R1"), ("enrolments", "student_id", "students", "R1"),
                      ("enrolments", "course_id", "courses", "R1"), ("grades", "student_id+course_id", "enrolments", "R3")],
            "links_after_keys": [("grades", "student_id+course_id+term", "enrolments", "R3")],
            "gone_after_keys": [("grades", "student_id+course_id", "enrolments")],
            "suggested": [],
            "keyless": [],
        },
    },
]

RULE_LEGEND = [
    ("K2", "key", "a key found by name: `id`, `<table>_id`, `<table>_no`, …"),
    ("K1", "key", "a key you give, for example a composite one"),
    ("K4", "key", "a junction: the leading reference columns together, such as `customer_id + account_id`"),
    ("K5", "key", "a line: the reference to the header plus a line number, such as `order_id + line_no`"),
    ("K3", "none", "no key: the table can be queried, but nothing can point at it"),
    ("R1", "rel", "a column named after another table: `customer_id` → `customers`"),
    ("R2", "rel", "the same name as another table's single key column"),
    ("R3", "rel", "all columns of another table's composite key"),
    ("R4", "weak", "the weaker match: a role in front of a table's name, such as `billing_account_id` → `accounts`; check it"),
    ("confirm", "conf", "a column that names no table, such as `manager_id`: linked only when you confirm it"),
]

# The three tasks a visitor starts from (the website brief of 26 October 2026): what they say, what they get and the
# tools; each tool's status comes from tool_status. Worded as tasks, not as claims about customers.
TASKS = [
    {"slug": "inherited", "quote": "I inherited a lakehouse nobody has documented.",
     "shows": "An overview: the central tables, how they relate, and the questions you still need to clear up.",
     "tools": ["analyze_schema", "plan_backend", "data_dictionary"],
     "example": ("retail", "a return that belongs to an order line, not just an order")},
    {"slug": "join", "quote": "I need to check how these tables should join.",
     "shows": "A suggested join with its reason, a check against the rows, and what stays uncertain.",
     "tools": ["join_path", "validate_plan", "suggest_relationships"],
     "example": ("pharma-research", "a visit number that is not a unique key on its own")},
    {"slug": "app", "quote": "I want to build an app on this data.",
     "shows": "The reviewed plan, an API created from it in your workspace, and the setup steps the app still needs.",
     "tools": ["create_backend", "app_starter"],
     "example": ("professional-services", "consultant hours that are not invoiced yet")},
]

OUTPUTS = [   # (what, for what, status in the docs' words; "planned" draws the chip dashed)
    ("GraphQL API", "an API for GraphQL item in your workspace, for an app or for questions in Claude",
     "creating it: experimental; querying an existing one: tested end to end"),
    ("SQL views", "wide T-SQL views over the plan's joins on the SQL analytics endpoint", "tested end to end as a dry run; creating them: experimental"),
    ("Fabric IQ ontology draft", "entity types, keys and relationships (preview)", "draft only"),
    ("Semantic model", "a Power BI model in TMDL from the same keys", "draft; the item when enabled by the operator"),
    ("Data agent", "a Fabric data agent with the plan as instructions", "when enabled by the operator"),
]


# ------------------------------------------------------------------ engine -----------------------------------------

def schema_of(ind: dict):
    from .schema import Column, Schema, Table
    s = Schema(schema="dbo")
    for t, cols in ind["tables"].items():
        s.tables[t] = Table(t, [Column(c) for c in cols.split()], schema="dbo")
    return s


@lru_cache(maxsize=None)
def sketch(slug: str) -> dict:
    """What the engine says from names alone, per table: key and rule, links per column, suggestions, roles."""
    from .evidence import suggest_composite_keys
    from .infer import plan
    ind = next(i for i in INDUSTRIES if i["slug"] == slug)
    p = plan(schema_of(ind))
    links: dict[tuple[str, str], tuple[str, str]] = {}
    multi: dict[str, list[tuple[list[str], str, str]]] = {}
    for r in p.relationships:
        if len(r.source_cols) == 1:
            links[(r.source, r.source_cols[0])] = (r.target, r.rule)
        else:
            multi.setdefault(r.source, []).append((r.source_cols, r.target, r.rule))
    roles = {(s, c): t for s, c, t, _tc, _f in ind["checks"].get("roles", [])}
    sugg = {x["table"]: x["columns"] for x in suggest_composite_keys(p)}
    tables = []
    for t, cols in ind["tables"].items():
        key, rule = p.keys.get(t, ([], "K3"))
        tables.append({"name": t, "key": key, "rule": rule, "suggested": sugg.get(t, []), "multi": multi.get(t, []),
                       "columns": [{"name": c, "key": c in key, "link": links.get((t, c)), "role": roles.get((t, c))}
                                   for c in cols.split()]})
    return {"tables": tables, "summary": p.summary().splitlines()[0]}


# ------------------------------------------------------------------ html -------------------------------------------

def _inline(s: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(s, quote=False))


_ICON = ('<svg class="g-ico" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><rect x="1.5" y="2.5" width="13" '
         'height="11" rx="2.6" fill="currentColor" fill-opacity=".22" stroke="currentColor" stroke-width="1.5"/>'
         '<path d="M1.5 6.5h13M6.2 6.5v7" stroke="currentColor" stroke-width="1.5"/></svg>')
_KEY = ('<svg class="g-key" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="5" cy="8" r="3.2" '
        'fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M8.2 8h6M12 8v2.6M14.2 8v2" fill="none" '
        'stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>')

_RULE_CLASS = {"suggested": "sug", "confirm": "conf", "R4": "weak", "K3": "none"}
_RULE_LABEL = {"suggested": "suggested", "confirm": "to confirm"}


def _rule_chip(code: str) -> str:
    cls = _RULE_CLASS.get(code, "key" if code.startswith("K") else "rel")
    return f'<span class="uc-rule {cls}">{html.escape(_RULE_LABEL.get(code, code))}</span>'


def _wbr(name: str) -> str:
    """Long table and column names break after an underscore, never inside a word."""
    return html.escape(name).replace("_", "_<wbr>")


def _table_card(t: dict, color: str, colors: dict[str, str]) -> str:
    e = html.escape
    keyless = not t["key"]
    rows = []
    for c in t["columns"]:
        if c["key"]:
            mark, cls, note = _KEY, "key", f'<span class="uc-c-note">key · {e(t["rule"])}</span>'
        elif c["link"]:
            target, rule = c["link"]
            mark, cls = '<span class="g-pad"></span>', "linked"
            weak = " weak" if rule == "R4" else ""
            note = (f'<span class="uc-c-link c-{colors.get(target, "sage")}{weak}"><span aria-hidden="true">→</span> '
                    f'{e(target)} <b>{e(rule)}</b></span>')
        elif c["role"]:
            mark, cls = '<span class="g-pad"></span>', "role"
            note = f'<span class="uc-c-link role"><span aria-hidden="true">→</span> {e(c["role"])}? <b>confirm</b></span>'
        else:
            mark, cls, note = '<span class="g-pad"></span>', "", ""
        rows.append(f'<li class="{cls}">{mark}<span class="n">{_wbr(c["name"])}</span>{note}</li>')
    foot = "".join(f'<p class="uc-t-multi c-{colors.get(target, "sage")}"><code>{e(" + ".join(cols))}</code> '
                   f'<span class="uc-c-link"><span aria-hidden="true">→</span> {e(target)} <b>{e(rule)}</b></span></p>'
                   for cols, target, rule in t["multi"])
    if keyless:
        foot += (f'<p class="uc-t-foot sug">suggested key: <code>{e(" + ".join(t["suggested"]))}</code></p>' if t["suggested"]
                else '<p class="uc-t-foot">no key · K3</p>')
    return (f'<li class="uc-t c-{color}{" keyless" if keyless else ""}"><p class="uc-t-head">{_ICON}'
            f'<span class="nm">{_wbr(t["name"])}</span></p><ul class="uc-cols">{"".join(rows)}</ul>{foot}</li>')


def _section(n: int, ind: dict) -> str:
    e = html.escape
    sk = sketch(ind["slug"])
    colors = {t["name"]: COLORS[i % len(COLORS)] for i, t in enumerate(sk["tables"])}
    cards = "".join(_table_card(t, colors[t["name"]], colors) for t in sk["tables"])
    finds = "".join(f'<li>{_rule_chip(code)}<span>{_inline(text)}</span></li>' for code, text in ind["finds"])
    build = "".join(f"<li>{_inline(x)}</li>" for x in ind["build"])
    value = "".join(f"<li>{_inline(x)}</li>" for x in ind["value"])
    tid = f'{ind["slug"]}-tables'
    note = (f'<aside class="uc-note"><h3>{e(ind["note"][0])}</h3><p>{_inline(ind["note"][1])}</p></aside>' if ind.get("note") else "")
    return f"""<section class="uc wrap" id="{e(ind["slug"])}" aria-labelledby="{e(ind["slug"])}-h">
  <header class="uc-head">
    <span class="uc-n c-{ind["color"]}" aria-hidden="true">{n:02d}</span>
    <div><h2 id="{e(ind["slug"])}-h">{e(ind["name"])}</h2><p><strong>{_inline(ind["lead"])}</strong></p><p class="muted">{_inline(ind["summary"])}</p></div>
  </header>
  <div class="uc-sketch">
    <div class="uc-sketch-head"><h3 id="{tid}">Typical tables</h3><span class="muted tiny">From names alone, as the engine plans them: {e(sk["summary"])}</span></div>
    <ul class="uc-tables" aria-labelledby="{tid}">{cards}</ul>
  </div>
  <details class="uc-more">
    <summary>What {{{{PRODUCT}}}} finds, and what you could build</summary>
    <div class="uc-body">
      <div class="uc-finds"><h3>What {{{{PRODUCT}}}} finds</h3><ul class="uc-find-list">{finds}</ul></div>
      <div><h3>What you build</h3><ul class="uc-list">{build}</ul></div>
      <div><h3>Why it matters</h3><ul class="uc-list">{value}</ul></div>
    </div>
    {note}
  </details>
  <p class="uc-top tiny"><a href="#industries">Back to the industries</a></p>
</section>"""


def index_html() -> str:
    e = html.escape
    items = "".join(
        f'<li><a href="#{e(i["slug"])}" class="c-{i["color"]}"><span class="uc-n small" aria-hidden="true">{n:02d}</span>'
        f'<span class="uc-i-txt"><span class="uc-i-name">{e(i["name"])}</span>'
        f'<span class="uc-i-tables">{e(", ".join(i["tables"]))}</span></span></a></li>'
        for n, i in enumerate(INDUSTRIES, 1))
    return f'<ul class="uc-index">{items}</ul>'


def legend_html() -> str:
    return "".join(f'<li>{_rule_chip(code)}<span>{_inline(text)}</span></li>' for code, _k, text in RULE_LEGEND)


def outputs_html() -> str:
    e = html.escape
    return "".join(f'<li{" class=planned" if tag == "planned" else ""}><strong>{e(name)}</strong><span>{e(what)}</span>'
                   f'{f"<em>{e(tag)}</em>" if tag else ""}</li>' for name, what, tag in OUTPUTS)


def _tools(task: dict) -> str:
    return ", ".join(f"`{n}`" for n in task["tools"])


def tasks_html() -> str:
    e = html.escape
    names = {i["slug"]: i["name"] for i in INDUSTRIES}
    return "".join(
        f'<li class="uc-task" id="task-{e(t["slug"])}"><p class="uc-task-q">“{e(t["quote"])}”</p><p>{_inline(t["shows"])}</p>'
        f'<p class="muted tiny">Tools: {_inline(_tools(t))}. Status: {_inline(task_status(t["tools"]))}.</p>'
        f'<p class="tiny">For example: <a href="#{e(t["example"][0])}">{e(names[t["example"][0]])}</a>, {e(t["example"][1])}.</p></li>'
        for t in TASKS)


def page_vars() -> dict[str, str]:
    return {"UC_TASKS": tasks_html(), "UC_INDEX": index_html(), "UC_LEGEND": legend_html(), "UC_OUTPUTS": outputs_html(),
            "UC_SECTIONS": "\n".join(_section(n, i) for n, i in enumerate(INDUSTRIES, 1)),
            "UC_FOOTNOTE": html.escape(FOOTNOTE), "UC_COUNT": NUMBER_WORDS[len(INDUSTRIES)], "UC_CONSULTANCY": html.escape(CONSULTANCY_TEXT.format(product="{{PRODUCT}}")),
            "UC_INTRO": html.escape(INTRO.format(product="{{PRODUCT}}"))}


# ------------------------------------------------------------------ markdown ---------------------------------------

def markdown(product: str, origin: str, contact: str) -> str:
    out = [f"# Use cases: what do you need to understand about your data?\n",
           INTRO.format(product=product) + "\n",
           f"*{FOOTNOTE}*\n",
           "## Start from your task\n"]
    out += [f"- **“{t['quote']}”** {t['shows']} Tools: {_tools(t)}. Status: {task_status(t['tools'])}." for t in TASKS]
    out += ["",
           "Plan from names (`plan_backend`, nothing is deployed), check against the rows (`validate_plan`, a step you "
           "ask for), then create (`create_backend`). Ambiguous columns are reported, never guessed.\n",
           "## What comes out\n"]
    out += [f"- **{n}**: {w}{' (' + t + ')' if t else ''}" for n, w, t in OUTPUTS]
    out.append("\n## How to read the rules\n")
    out += [f"- **{_RULE_LABEL.get(c, c)}**: {t}" for c, _k, t in RULE_LEGEND]
    for ind in INDUSTRIES:
        sk = sketch(ind["slug"])
        out.append(f"\n## {ind['name']}\n\n**{ind['lead']}**\n\n{ind['summary']}\n\n### Typical tables\n")
        for t in sk["tables"]:
            cols = []
            for c in t["columns"]:
                if c["key"]:
                    cols.append(f"`{c['name']}` (key, {t['rule']})")
                elif c["link"]:
                    cols.append(f"`{c['name']}` (→ {c['link'][0]}, {c['link'][1]})")
                elif c["role"]:
                    cols.append(f"`{c['name']}` (→ {c['role']}? to confirm)")
                else:
                    cols.append(f"`{c['name']}`")
            extra = "" if t["key"] else (f"; suggested key `{' + '.join(t['suggested'])}`" if t["suggested"] else "; no key (K3)")
            extra += "".join(f"; `{' + '.join(c)}` → {tg} ({r})" for c, tg, r in t["multi"])
            out.append(f"- **{t['name']}**: {', '.join(cols)}{extra}")
        out.append(f"\n### What {product} finds\n")
        out += [f"- **{_RULE_LABEL.get(c, c)}**: {t}" for c, t in ind["finds"]]
        out.append("\n### What you build\n")
        out += [f"- {x}" for x in ind["build"]]
        out.append("\n### Why it matters\n")
        out += [f"- {x}" for x in ind["value"]]
        if ind.get("note"):
            out.append(f"\n### {ind['note'][0]}\n\n{ind['note'][1]}")
    out.append(f"\n## For Fabric consultancies\n\n{CONSULTANCY_TEXT.format(product=product)} "
               f"Start at [{origin}/start]({origin}/start), read [{origin}/docs]({origin}/docs), and email "
               f"Gustav at {contact} to discuss a pilot.\n")
    return "\n".join(out).replace("\n\n\n", "\n\n").replace("{{PRODUCT}}", product)


CONSULTANCY_TEXT = ("Start a client conversation from their own schema instead of a slide. The plan lists every key and "
                    "relationship with the rule behind it, so a review with the client's data owners has something "
                    "concrete to check. The rules and the engine are open source.")

INTRO = ("Start with an unfamiliar lakehouse, a join you need to check or an app you want to build. These examples show "
         "where {product} helps and what still needs your judgement.")
