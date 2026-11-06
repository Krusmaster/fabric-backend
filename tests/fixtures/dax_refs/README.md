A hand-written semantic model over the synthetic shop schema (`fabric_backend/seed.py`), in the TMDL layout of a PBIP
folder, for the DAX reference scanner (`fabric_backend/dax_refs.py`, `tests/test_dax_refs.py`). It holds, on purpose:

- direct references (`'Order Lines'[quantity]`), a calculated column (`Line Amount`) and measures over measures
  (`Revenue` -> `Avg Price` -> `Avg Price Label`), so a dropped column reaches measures two steps away;
- a model column with another name than its source column (`products[List Price]` reads `list_price`);
- quoted names (`'Order Lines'`, `'Order Lines'[Line Amount]`, a measure `'Revenue (net)'` with `]]`-free brackets);
- column names inside strings and comments (`//`, `--`, `/* */`) that must not count;
- expressions the scanner cannot settle: SELECTEDMEASURE, a measure that uses it, an unknown measure, an unclosed
  string, `[order_id]` with two candidate tables, `[quantity]` that ADDCOLUMNS may add itself.
