"""seed() with a fake Spark: schema-enabled lakehouse vs one without schemas."""
from fabric_backend import seed as seedmod


class FakeDF:
    def __init__(self, log): self.log = log; self.write = self
    def mode(self, *_): return self
    def option(self, *_): return self
    def saveAsTable(self, name): self.log.append(("save", name))


class FakeSpark:
    def __init__(self, schemas):
        self.schemas, self.log = schemas, []

    def sql(self, q):
        self.log.append(("sql", q))
        outer = self

        class R:
            def collect(self_inner):
                return [(s,) for s in outer.schemas]
        return R()

    def createDataFrame(self, data, schema):
        return FakeDF(self.log)


def test_schema_enabled_lakehouse_writes_into_the_schema():
    spark = FakeSpark(["dbo"])
    counts = seedmod.seed(spark, "shop")
    assert counts["customers"] == 10 and len(counts) == 7
    assert ("sql", "CREATE SCHEMA IF NOT EXISTS shop") in spark.log
    assert ("save", "shop.customers") in spark.log


def test_lakehouse_without_schemas_falls_back_to_the_default(capsys):
    spark = FakeSpark(["demo_lh", "default"])
    seedmod.seed(spark, "shop")
    assert not any(e[0] == "sql" and e[1].startswith("CREATE SCHEMA") for e in spark.log)
    assert ("save", "customers") in spark.log
    assert "schema='dbo'" in capsys.readouterr().out
