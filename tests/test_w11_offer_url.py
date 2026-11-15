"""Round W11 (15 November 2026): the Marketplace offer link for Microsoft's publishing requirements 1.3.1 and 1.3.2.

`workload/scripts/build-package --offer-url <url>` puts the live production offer's page in Product.json's license link.
It takes only Microsoft Marketplace or AppSource addresses, and refuses the DEV offer (krusgraph-dev, never live), a
preview-audience link and the storefront's front page. Without it the package is unchanged and the build still names the
gap. docs/PUBLISHING-READINESS.md lists every requirement; nothing here creates an offer or uploads a package."""
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WL_ID = "99999999-8888-7777-6666-555555555555"
OFFER = "https://marketplace.microsoft.com/en-us/product/saas/krusconsultingab.krusgraph-example?tab=Overview"


def _builder():
    spec = importlib.util.spec_from_file_location("build_package_w11", ROOT / "workload/scripts/build_package.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _product(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        return json.loads(z.read("FE/Product.json"))


def _fe(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist() if n.startswith("FE/")}


def test_without_offer_url_the_license_link_is_the_mit_licence_and_the_gap_is_named(tmp_path):
    bp = _builder()
    path = bp.build(WL_ID, "1.0.5", out_dir=tmp_path, name=bp.PUBLISHED_NAME)
    assert _product(path)["productDetail"]["supportLink"]["license"]["url"] == bp.LICENSE_URL
    gaps = bp.publishing_gaps(_fe(path))
    assert len(gaps) == 1 and "1.3.1" in gaps[0] and "--offer-url" in gaps[0]


@pytest.mark.parametrize("name", ["Org.Krusgraph", "Krusgraph.Modeler"])
def test_offer_url_fills_the_license_link_and_closes_the_gap(tmp_path, name):
    bp = _builder()
    path = bp.build(WL_ID, "1.0.5", out_dir=tmp_path, name=name, offer_url=OFFER)
    links = _product(path)["productDetail"]["supportLink"]
    assert links["license"]["url"] == OFFER
    assert links["terms"]["url"] == "https://krusgraph.com/terms"          # nothing else moves
    assert bp.publishing_gaps(_fe(path)) == []


@pytest.mark.parametrize("url", [
    "https://azuremarketplace.microsoft.com/marketplace/apps/krusconsultingab.krusgraph-dev?tab=Overview",
    "https://appsource.microsoft.com/product/web-apps/KrusConsultingAB.Krusgraph-DEV",
    "https://azuremarketplace.microsoft.com/marketplace/apps/krusconsultingab.krusgraph?flightCodes=abc",
    "https://marketplace.microsoft.com/",
    "http://marketplace.microsoft.com/product/saas/krusconsultingab.krusgraph",
    "https://marketplace.microsoft.com.example.com/product/saas/krusconsultingab.krusgraph",
    "https://github.com/Krusmaster/fabric-backend/blob/main/LICENSE",
    "",
])
def test_offer_url_refuses_the_dev_offer_previews_and_other_hosts(tmp_path, url):
    bp = _builder()
    with pytest.raises(bp.PackageError):
        bp.build(WL_ID, "1.0.5", out_dir=tmp_path, name=bp.PUBLISHED_NAME, offer_url=url or " ")
    assert not list(tmp_path.glob("*.nupkg"))


def test_the_cli_takes_offer_url_and_stops_on_the_dev_offer(tmp_path, capsys):
    bp = _builder()
    assert bp.main(["--frontend-app-id", WL_ID, "--version", "1.0.5", "--out", str(tmp_path),
                    "--name", "Krusgraph.Modeler", "--offer-url", OFFER]) == 0
    out = capsys.readouterr().out
    assert "Not ready for Microsoft's publishing review yet" not in out
    assert bp.main(["--frontend-app-id", WL_ID, "--version", "1.0.6", "--out", str(tmp_path),
                    "--name", "Krusgraph.Modeler",
                    "--offer-url", OFFER.replace("krusgraph-example", "krusgraph-dev")]) == 1
    assert "DEV offer" in capsys.readouterr().err


def test_the_readiness_page_exists_cites_learn_and_makes_no_claims():
    text = (ROOT / "docs/PUBLISHING-READINESS.md").read_text(encoding="utf-8")
    assert text.startswith("# ") and "W11" in text and "15 November 2026" in text
    for stage in ("Preview", "General availability", "Marketplace"):
        assert stage in text, stage
    assert "learn.microsoft.com/fabric/extensibility-toolkit/publishing-requirements-workload" in text
    assert "--offer-url" in text and "krusgraph-dev" in text
    low = text.lower()
    for claim in ("we are certified", "is certified", "endorsed by", "microsoft partner", "is compliant", "faster than",
                  "guaranteed"):
        assert claim not in low, claim
    # prices and people stay in the private repository
    for word in ("sek ", "kr/", "€", "$", "per user per month"):
        assert word not in low, word


def test_the_readiness_page_plans_the_name_switch_and_carries_the_company_details():
    text = (ROOT / "docs/PUBLISHING-READINESS.md").read_text(encoding="utf-8")
    assert "The switch to Krusgraph.Modeler" in text and "What happens to `Org.Krusgraph`" in text
    for detail in ("Kruse Consulting AB", "559174-8719", "Svartmangatan 4 D", "753 12 Uppsala", "hello@krusgraph.com"):
        assert detail in text, detail
    attestation = (ROOT / "docs/HUB-ATTESTATION.md").read_text(encoding="utf-8")
    assert "559174-8719" in attestation and "| Postal Code: | 753 12 |" in attestation
