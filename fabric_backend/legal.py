"""G1 (15 November 2026): the site's company details, what it stores in a visitor's browser, and the pages that say so
(/cookies, /accessibility), from one place.

STORAGE is every cookie and every localStorage or sessionStorage key the site or the service can set, with why and for
how long. The footer's "Cookies and storage" panel, /cookies and the privacy page read it; tests/test_g1_legal_site.py
fails when a script or a route sets a key that is not listed here, and the browser check fails when any page stores
something before the visitor clicks. Everything listed is strictly necessary for something the visitor asked for (a
theme they chose, a demo they opened, a sign-in they started), so the site asks for no consent and shows no banner.
Adding analytics, an embed or anything else that is not strictly necessary means adding a real opt-in first.

Company details: the org. no. and registered address are the company's public registry details as the founder gave them
(docs/HUB-ATTESTATION.md, Section I, W11, 15 November 2026); the deployment can override them (COMPANY_ORGNR,
COMPANY_ADDRESS) and adds the VAT number (COMPANY_VAT) when set. A value set to empty shows as a marked placeholder
rather than being guessed.
"""
from __future__ import annotations

import html
import os

COMPANY = "Kruse Consulting AB"
COUNTRY = "Sweden"
# the public registry details given by the founder (docs/HUB-ATTESTATION.md, Section I, 15 November 2026)
ORGNR = "559174-8719"
ADDRESS = "Svartmangatan 4 D, 753 12 Uppsala"
ADDRESS_PLACEHOLDER = "[registered address to be added]"
ORGNR_PLACEHOLDER = "[org. no. to be added]"
# the date the texts on /cookies and /accessibility were last changed, by hand with the text
COOKIES_UPDATED = "15 November 2026"
ACCESSIBILITY_UPDATED = "15 November 2026"
# what the accessibility check on 15 November 2026 covered (G1): every page in discovery.PUBLIC_PAGES plus /pilot/fabric,
# /docs/get-started and /blog, at three widths, light and dark, with axe-core 4.10.3 (rules for WCAG 2.0, 2.1 and 2.2 A
# and AA), and the site's own browser check (tests/g1_site_browser.js)
A11Y_CHECKED = "15 November 2026"

LOCAL, SESSION, COOKIE = "localStorage", "sessionStorage", "Cookie"

# (name, kind, where and when it is set, why, how long, sent to the server)
STORAGE = (
    ("theme", LOCAL, "Any page, only when you press the light or dark theme button in the header",
     "Remembers the theme you chose, so the next page opens in it", "Until you clear this site's data in your browser",
     "No"),
    ("krusgraph.mascots", LOCAL, "Any page with mascots, only when you press “Mascots: on/off”",
     "Remembers whether you turned the mascots off", "Until you clear this site's data in your browser", "No"),
    ("krusgraph.chat", SESSION, "Any page, only after you open the “Try a demo” chat",
     "Lets the demo chat carry on where you were on the next page: whether it is open and which of its own steps you "
     "clicked, nothing from your files or the page", "Until you close the tab; “Start over” in the chat clears the steps",
     "No"),
    ("__Host-kg_flow_…, __Host-kg_csrf_…", COOKIE, "The sign-in pages under /oauth, only when you sign in from an MCP "
     "client other than Claude", "Ties Microsoft's answer to the sign-in you started, and stops a forged approval",
     "10 minutes", "Yes, to this site only"),
    ("__Host-kg_user", COOKIE, "The same sign-in pages, after you approve an MCP client that receives the answer at a web "
     "address", "Recognises your earlier approval, so you are not asked again; it holds a signed, keyed hash, not your "
     "name or ids", "180 days", "Yes, to this site only"),
    ("__Host-kg_mp_flow, __Host-kg_mp_sub", COOKIE, "The pages under /marketplace, only during a purchase through "
     "Microsoft Marketplace (not switched on yet)", "Carries the sign-in and the subscription you are activating, and "
     "stops a forged activation", "10 minutes", "Yes, to this site only"),
    ("__Host-kg_app_flow, __Host-kg_app", COOKIE, "A guided page open only to organisations Kruse Consulting AB has invited, "
     "only when you sign in to it with Microsoft", "Ties Microsoft's answer to the sign-in you started, then keeps you signed "
     "in; it holds a random session number, not your name, ids or a token", "10 minutes for the sign-in; at most 1 hour for "
     "the session, or until you sign out", "Yes, to this site only"),
)
# the keys the site's own scripts write (static/*.js); the test compares them with the scripts
SCRIPT_KEYS = ("theme", "krusgraph.mascots", "krusgraph.chat")
# the cookie names the service sets (registration_flow.py, marketplace.py, guided_app.py), as their prefixes
COOKIE_PREFIXES = ("__Host-kg_flow_", "__Host-kg_csrf_", "__Host-kg_user", "__Host-kg_mp_flow", "__Host-kg_mp_sub",
                   "__Host-kg_app_flow", "__Host-kg_app")


def orgnr() -> str:
    return os.environ.get("COMPANY_ORGNR", ORGNR).strip()


def address() -> str:
    return os.environ.get("COMPANY_ADDRESS", ADDRESS).strip()


def vat() -> str:
    return os.environ.get("COMPANY_VAT", "").strip()


def missing() -> list[str]:
    """What the founder still has to fill in for the company details on the site (shown as placeholders until then)."""
    return [name for name, value in (("COMPANY_ORGNR", orgnr()), ("COMPANY_ADDRESS", address())) if not value]


def company_line() -> str:
    """Kruse Consulting AB · Org. no. … · address · VAT no. (when set), as plain text."""
    parts = [COMPANY, "Org. no. " + (orgnr() or ORGNR_PLACEHOLDER), address() or ADDRESS_PLACEHOLDER]
    if vat():
        parts.append("VAT no. " + vat())
    return " · ".join(parts)


def company_vars() -> dict[str, str]:
    return {"COMPANY": COMPANY, "COMPANY_LINE": company_line(), "COMPANY_ADDRESS": address() or ADDRESS_PLACEHOLDER,
            "COMPANY_ORGNR": orgnr() or ORGNR_PLACEHOLDER, "COMPANY_VAT_LINE": ("VAT no. " + vat()) if vat() else "",
            "COOKIES_UPDATED": COOKIES_UPDATED, "ACCESSIBILITY_UPDATED": ACCESSIBILITY_UPDATED, "A11Y_CHECKED": A11Y_CHECKED}


_COOKIE_ICON = ('<svg class="cookie-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">'
                '<path d="M12 3a9 9 0 1 0 9 9 3 3 0 0 1-3.6-3A3 3 0 0 1 14 5.4 3 3 0 0 1 12 3z" fill="none" '
                'stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>'
                '<circle cx="8.5" cy="10" r="1.3" fill="currentColor"/><circle cx="12" cy="15.5" r="1.3" fill="currentColor"/>'
                '<circle cx="16.5" cy="14" r="1.1" fill="currentColor"/><circle cx="8" cy="15" r=".9" fill="currentColor"/></svg>')


def storage_table_html() -> str:
    e = html.escape
    rows = "".join(
        f"<tr><th scope=\"row\"><code>{e(name)}</code></th><td>{e(kind)}</td>"
        + f"<td>{e(where)}</td><td>{e(why)}</td><td>{e(kept)}</td><td>{e(sent)}</td></tr>"
        for name, kind, where, why, kept, sent in STORAGE)
    head = ("<tr><th scope=\"col\">Name</th><th scope=\"col\">Type</th><th scope=\"col\">Set where and when</th>"
            "<th scope=\"col\">Why</th><th scope=\"col\">How long</th><th scope=\"col\">Sent to us</th></tr>")
    return (f'<div class="table-scroll" role="region" aria-label="Cookies and storage" tabindex="0"><table class="storage-table">'
            f"<thead>{head}</thead><tbody>{rows}</tbody></table></div>")


def storage_list_html() -> str:
    """The panel's short form: one item per entry, name, type and how long, then why."""
    e = html.escape
    items = "".join(f'<li><code>{e(name)}</code> <span class="muted">{e(kind)}, {e(kept[0].lower() + kept[1:])}.</span> '
                    f'{e(why)}.</li>' for name, kind, _, why, kept, _ in STORAGE)
    return f'<ul class="storage-list tiny">{items}</ul>'


def storage_md() -> str:
    lines = ["| Name | Type | Set where and when | Why | How long | Sent to us |", "| --- | --- | --- | --- | --- | --- |"]
    for name, kind, where, why, kept, sent in STORAGE:
        lines.append(f"| `{name}` | {kind} | {where} | {why} | {kept} | {sent} |")
    return "\n".join(lines)


SUMMARY = ("This site sets no cookies on its pages, uses no analytics or advertising tools and loads nothing from other "
           "websites. It stores something in your browser only when you ask for it: a theme or mascot choice, the demo "
           "chat's place in this tab. Cookies are set only on the sign-in and purchase pages, for the sign-in itself.")


def cookie_panel_html() -> str:
    """The footer's cookie icon: a <details> (works without JavaScript, opens with Enter or Space) listing exactly what
    is stored, with a link to /cookies. No banner: nothing here needs consent (see the module docstring). n241: the
    summary is the same pill as "Mascots: on" (btn ghost small), with no card around it, and sits under that button."""
    return (f'<details class="cookie-panel"><summary class="btn ghost small">{_COOKIE_ICON}<span>Cookies and storage</span></summary>'
            f'<div class="cookie-panel-body"><p class="tiny">{html.escape(SUMMARY)} Nothing needs your consent, so there is '
            f'no banner.</p>{storage_list_html()}<p class="tiny"><a href="/cookies">Cookie policy</a> · '
            f'<a href="/privacy">Privacy</a></p></div></details>')


def page_vars() -> dict[str, str]:
    """{{LEGAL_*}} placeholders on /cookies and /accessibility (raw HTML, built here)."""
    return {"LEGAL_STORAGE_TABLE": storage_table_html(), "LEGAL_SUMMARY": html.escape(SUMMARY)}
