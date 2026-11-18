"""WP1 (18 November 2026): the one n175 manifest check that needs the server, moved here from
tests/test_workload_manifest.py so that file runs in a clean Azure Cloud Shell with pytest and pillow only
(tools/workload_package.py). CI runs this file with the full server extras, as before."""
from starlette.testclient import TestClient

from fabric_backend import server


def test_the_it_page_lists_the_hosts(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    with TestClient(server.build_app()) as client:
        html = client.get("/it").text
    section = html.split('id="network"')[1].split("<h2")[0]
    for word in ("workload.krusgraph.com", "<code>krusgraph.com</code>", "443", "TLS 1.2", "keeps loading",
                 "ERR_SSL_VERSION_OR_CIPHER_MISMATCH", "allow"):
        assert word in section, word
