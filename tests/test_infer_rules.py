"""One test per inference rule added for the benchmark in test_inference_quality.py (K2 extensions, K4, K5, R4,
prefix stripping, header names). Each shows the rule firing and the nearest case where it must not."""
from fabric_backend.infer import plan, _words, _line_like
from fabric_backend.schema import Schema


def schema(*tables: tuple[str, list[str]]) -> Schema:
    rows = [("dbo", name, col, "int", i) for name, cols in tables for i, col in enumerate(cols, 1)]
    return Schema.from_information_schema(rows, schema="dbo")


def rels(p) -> dict:
    return {(r.source, tuple(r.source_cols)): (r.target, r.rule) for r in p.relationships}


def test_words_split_camel_case_and_underscores():
    assert _words("ShipToAddressID") == ["ship", "to", "address", "id"]
    assert _words("manager_staff_id") == ["manager", "staff", "id"]
    assert _words("L_ORDERKEY") == ["l", "orderkey"] and _words("SalesOrderID") == ["sales", "order", "id"]


def test_table_wide_prefix_is_not_part_of_the_name():
    """TPC-H: every NATION column is N_…; the key is N_NATIONKEY and S_NATIONKEY in SUPPLIER points at it."""
    p = plan(schema(("NATION", ["N_NATIONKEY", "N_NAME", "N_REGIONKEY"]), ("REGION", ["R_REGIONKEY", "R_NAME"]),
                    ("SUPPLIER", ["S_SUPPKEY", "S_NAME", "S_NATIONKEY"])))
    assert p.keys["NATION"] == (["N_NATIONKEY"], "K2") and p.keys["REGION"] == (["R_REGIONKEY"], "K2")
    assert rels(p)[("NATION", ("N_REGIONKEY",))] == ("REGION", "R1")
    assert rels(p)[("SUPPLIER", ("S_NATIONKEY",))] == ("NATION", "R1")
    # a prefix shared by only some columns is a name, not a prefix
    p = plan(schema(("nation", ["n_nationkey", "name"])))
    assert "nation" in p.keyless


def test_code_suffix_names_a_key_and_a_reference():
    p = plan(schema(("Currency", ["CurrencyCode", "Name"]), ("CountryRegion", ["CountryRegionCode", "Name"]),
                    ("CountryRegionCurrency", ["CountryRegionCode", "CurrencyCode", "ModifiedDate"])))
    assert p.keys["Currency"] == (["CurrencyCode"], "K2")
    assert rels(p)[("CountryRegionCurrency", ("CurrencyCode",))] == ("Currency", "R1")
    assert p.keys["CountryRegionCurrency"] == (["CountryRegionCode", "CurrencyCode"], "K4")
    # an id column still wins over a code column in the same table
    p = plan(schema(("products", ["product_code", "product_id", "name"])))
    assert p.keys["products"] == (["product_id"], "K2")


def test_header_table_answers_to_its_name_without_header():
    p = plan(schema(("SalesOrderHeader", ["SalesOrderID", "OrderDate"]), ("SalesOrderDetail", ["SalesOrderDetailID", "SalesOrderID", "Qty"]),
                    ("sales_order_hdr", ["sales_order_id", "status"]), ("invoice_lines", ["invoice_line_id", "sales_order_id"])))
    assert p.keys["SalesOrderHeader"] == (["SalesOrderID"], "K2") and p.keys["sales_order_hdr"] == (["sales_order_id"], "K2")
    # two tables answer to sales_order_id: ambiguous, not guessed
    assert ("SalesOrderDetail", ("SalesOrderID",)) not in rels(p)
    assert {a["column"] for a in p.ambiguous} == {"SalesOrderID", "sales_order_id"}
    p = plan(schema(("SalesOrderHeader", ["SalesOrderID", "OrderDate"]), ("SalesOrderDetail", ["SalesOrderDetailID", "SalesOrderID", "Qty"])))
    assert rels(p)[("SalesOrderDetail", ("SalesOrderID",))] == ("SalesOrderHeader", "R1")


def test_abbreviated_key_and_reference_need_four_letters_and_no_other_table_of_that_name():
    p = plan(schema(("CUSTOMER", ["C_CUSTKEY", "C_NAME"]), ("ORDERS", ["O_ORDERKEY", "O_CUSTKEY", "O_TOTAL"])))
    assert p.keys["CUSTOMER"] == (["C_CUSTKEY"], "K2")
    assert rels(p)[("ORDERS", ("O_CUSTKEY",))] == ("CUSTOMER", "R2")        # same bare name as CUSTOMER's key: R2 before R4
    assert [r.field_name for r in p.relationships] == ["customer"]            # the field is named after the table
    p = plan(schema(("customers", ["customer_id", "name"]), ("orders", ["order_id", "cust_id"])))
    assert rels(p)[("orders", ("cust_id",))] == ("customers", "R4") and p.relationships[0].field_name == "customer"
    # three letters are not enough on their own; `emp` is in the synonym table, `wrk` is not
    p = plan(schema(("employees", ["emp_id", "name"]), ("orders", ["order_id", "emp_nr"]), ("workers", ["wrk_id", "name"]), ("shifts", ["shift_id", "wrk_id"])))
    assert p.keys["employees"] == (["emp_id"], "K2") and rels(p)[("orders", ("emp_nr",))] == ("employees", "R4")
    assert p.relationships[0].note == "through the synonym table: emp -> employee"
    assert p.synonyms[0] == {"table": "employees", "column": "emp_id", "rule": "K2", "via": "emp -> employee"}
    assert "workers" in p.keyless and ("shifts", ("wrk_id",)) not in rels(p)
    # PARTSUPP: part_ abbreviates partsupp, but PART is a table — so ps_partkey is a reference and the key is K4
    p = plan(schema(("PART", ["P_PARTKEY", "P_NAME"]), ("SUPPLIER", ["S_SUPPKEY", "S_NAME"]),
                    ("PARTSUPP", ["PS_PARTKEY", "PS_SUPPKEY", "PS_AVAILQTY"]),
                    ("LINEITEM", ["L_ORDERKEY", "L_PARTKEY", "L_SUPPKEY", "L_LINENUMBER", "L_QUANTITY"])))
    assert p.keys["PARTSUPP"] == (["PS_PARTKEY", "PS_SUPPKEY"], "K4")
    assert rels(p)[("PARTSUPP", ("PS_PARTKEY",))] == ("PART", "R1")
    assert rels(p)[("LINEITEM", ("L_PARTKEY", "L_SUPPKEY"))] == ("PARTSUPP", "R3")      # composite key found through the prefixes
    # the abbreviation must be a proper prefix of the first word: order_ does not abbreviate order_items
    p = plan(schema(("order_items", ["id", "product_id"]), ("shipments", ["shipment_id", "order_id"])))
    assert ("shipments", ("order_id",)) not in rels(p)
    # two tables it could abbreviate: ambiguous
    p = plan(schema(("products", ["product_id"]), ("producers", ["producer_id"]), ("lines", ["line_id", "prod_id"])))
    assert ("lines", ("prod_id",)) not in rels(p) and p.ambiguous[0]["candidates"] == ["products", "producers"]


def test_role_before_the_target_name_is_a_reference():
    p = plan(schema(("staff", ["staff_id", "name"]), ("address", ["address_id", "city"]), ("language", ["language_id"]),
                    ("store", ["store_id", "manager_staff_id", "address_id"]),
                    ("film", ["film_id", "language_id", "original_language_id"]),
                    ("SalesOrderHeader", ["SalesOrderID", "ShipToAddressID", "BillToAddressID"])))
    r = rels(p)
    assert r[("store", ("manager_staff_id",))] == ("staff", "R4") and r[("store", ("address_id",))] == ("address", "R1")
    assert r[("film", ("original_language_id",))] == ("language", "R4")
    assert r[("SalesOrderHeader", ("ShipToAddressID",))] == ("address", "R4") and r[("SalesOrderHeader", ("BillToAddressID",))] == ("address", "R4")
    names = {tuple(x.source_cols): (x.field_name, x.reverse_name) for x in p.relationships}
    assert names[("manager_staff_id",)] == ("manager_staff", "store_as_manager_staff")   # field names as before the rule
    assert names[("ShipToAddressID",)] == ("shiptoaddress", "salesorderheader_as_shiptoaddress")
    # the match is on a word boundary: catalog_id does not point at log
    p = plan(schema(("log", ["log_id", "text"]), ("items", ["item_id", "catalog_id"])))
    assert ("items", ("catalog_id",)) not in rels(p)
    # and the demo's ship_to_id stays unlinked: "to" is not a table
    p = plan(schema(("addresses", ["address_id"]), ("orders", ["order_id", "ship_to_id"])))
    assert ("orders", ("ship_to_id",)) not in rels(p) and p.ambiguous == []


def test_junction_key_is_the_leading_run_of_references():
    p = plan(schema(("actor", ["actor_id", "name"]), ("film", ["film_id", "title"]),
                    ("film_actor", ["actor_id", "film_id", "last_update"]),
                    ("ProductVendor", ["ProductID", "BusinessEntityID", "AverageLeadTime", "UnitMeasureCode"]),
                    ("Product", ["ProductID"]), ("BusinessEntity", ["BusinessEntityID"]), ("UnitMeasure", ["UnitMeasureCode"])))
    assert p.keys["film_actor"] == (["actor_id", "film_id"], "K4")
    assert p.keys["ProductVendor"] == (["ProductID", "BusinessEntityID"], "K4")          # UnitMeasureCode comes after a non-reference
    # one reference is not a junction; a history table is left for the caller (its key needs the date)
    p = plan(schema(("employee", ["employee_id"]), ("department", ["department_id"]),
                    ("employee_notes", ["employee_id", "note"]),
                    ("employee_department_history", ["employee_id", "department_id", "start_date", "end_date"])))
    assert set(p.keyless) == {"employee_notes", "employee_department_history"}


def test_line_key_is_the_header_reference_plus_the_line_number():
    p = plan(schema(("orders", ["order_id", "customer_id"]), ("products", ["product_id"]),
                    ("order_items", ["order_id", "line_no", "product_id", "quantity"])))
    assert p.keys["order_items"] == (["order_id", "line_no"], "K5")
    # named after no table: the first reference column is the header (TPC-H LINEITEM)
    p = plan(schema(("ORDERS", ["O_ORDERKEY", "O_CUSTKEY"]), ("PART", ["P_PARTKEY", "P_NAME"]),
                    ("LINEITEM", ["L_ORDERKEY", "L_PARTKEY", "L_LINENUMBER", "L_QUANTITY"])))
    assert p.keys["LINEITEM"] == (["L_ORDERKEY", "L_LINENUMBER"], "K5")
    # a column that names a key still wins (K2 before K5)
    p = plan(schema(("orders", ["order_id"]), ("order_lines", ["order_line_id", "order_id", "position"])))
    assert p.keys["order_lines"] == (["order_line_id"], "K2")
    assert _line_like("line_no") and _line_like("OperationSequence") and _line_like("order_line") and not _line_like("deadline")


def test_a_confirmed_column_is_neither_inferred_again_nor_ambiguous():
    """prod_id answers to both products and producers; once the caller confirms products, the column is settled."""
    confirmed = [{"source": "sales", "source_cols": ["prod_id"], "target": "products", "target_cols": ["product_id"]}]
    s = schema(("products", ["product_id", "name"]), ("producers", ["producer_id"]), ("sales", ["sale_id", "prod_id"]))
    assert [a["column"] for a in plan(s).ambiguous] == ["prod_id"]
    p = plan(s, confirmed=confirmed)
    assert p.ambiguous == [] and "ambiguous" not in p.summary()
    assert [(r.target, r.rule) for r in p.relationships if r.source == "sales"] == [("products", "confirmed")]
    # a table named prod would take the column by R1; the confirmed target still stands alone
    s = schema(("products", ["product_id", "name"]), ("prod", ["prod_id"]), ("sales", ["sale_id", "prod_id"]))
    assert rels(plan(s))[("sales", ("prod_id",))] == ("prod", "R1")
    p = plan(s, confirmed=confirmed)
    assert [(r.target, r.rule) for r in p.relationships if r.source == "sales"] == [("products", "confirmed")]


def test_a_confirmed_header_link_keeps_the_line_key():
    """Confirming order_items.order_id -> orders (in any case) must not move the K5 key to the product column."""
    s = schema(("orders", ["order_id", "customer_id"]), ("products", ["product_id"]),
               ("order_items", ["order_id", "line_no", "product_id", "quantity"]))
    p = plan(s, confirmed=[{"source": "Order_Items", "source_cols": ["ORDER_ID"], "target": "ORDERS"}])
    assert p.keys["order_items"] == (["order_id", "line_no"], "K5")
    r = next(r for r in p.relationships if r.rule == "confirmed")
    assert (r.source, r.source_cols, r.target, r.target_cols) == ("order_items", ["order_id"], "orders", ["order_id"])
