A hand-written semantic model over the synthetic shop schema (`fabric_backend/seed.py`), in the TMDL layout of a PBIP
folder, for `compare_semantic_model`'s tests. Against the plan it has one relationship missing
(`products.category_id -> categories.id`) and one wrong (`products.category_id -> Customer.customer_id`), a model table
named differently from its source (`Customer` reads `customers`, `Order Lines` reads `order_items`), `ship_to_id`
summarized as a sum, and a measure that sums an id.
