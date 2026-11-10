# Microsoft Marketplace: Notes for certification (draft) and the listing checklist

Round n204, 10 November 2026. A **draft** for the founder. Nothing here was entered in Partner Center. Section 1 is
the text to paste into the offer's **Notes for certification** field (policy 100.14 Testability: "Your offer
submission must include any necessary instructions and resources for successful certification of your offer" [C1]).
Section 2 lists what the listing must pass, from policies 100.1 to 100.7 and 1000.x [C1], each marked **Met** (the
repository shows it) or **To check by the founder** (it lives in Partner Center, YouTube or on the live site).
Setup of the offer and the apps: `docs/MARKETPLACE-SETUP.md`.

Words in brackets `<like this>` are filled in by the founder before pasting. Plan ids are those of
`docs/MARKETPLACE-SETUP.md` section 3 (`team`, `pilot`); change them if Partner Center has others.

## 1. The text to paste (plain English, about 2,800 characters)

> **What Krusgraph does.** Krusgraph reads the table and column names of a customer's data in Microsoft Fabric (a
> lakehouse or warehouse) and shows how the tables connect, with the rule behind each link and checks run against the
> rows (keys that are not unique, references with no matching row, totals that double after a join). From the plan the
> customer reviews, it can create items in the customer's own Fabric workspace: notebooks, a pipeline, a semantic
> model, a report, an API for GraphQL and a data agent. The subscription decides whether creating items is included;
> reading, checks, drafts and every dry run are free.
>
> **Buying the test plan.** Open the offer from the preview link and choose the plan `<plan id, e.g. team>`
> (`<price and currency as entered in Partner Center>`). Select **Subscribe**, complete the purchase, then
> **Configure account**.
>
> **Signing in on the landing page.** Configure account opens https://krusgraph.com/marketplace/landing. Sign in with
> either a **work or school account** (Microsoft Entra ID) or a **personal Microsoft account**; both are accepted. The
> page asks only for your basic profile (openid, profile, email); it does not call Microsoft Graph and asks for no
> admin consent.
>
> **Activating.** The page shows the offer, the plan, the status and the tenant id the subscription is for. Select
> **Activate the subscription**. The page then says the subscription is active and shows the next steps (open Fabric,
> or connect Claude). If the plan uses automatic activation, the page says there is nothing to activate. No payment
> details are asked for; billing is Microsoft's.
>
> **What needs a work account and Fabric.** Creating items in Fabric needs a work account in the tenant shown on the
> landing page, the organisation administrator's one-time admin consent for the Krusgraph app, and a Fabric capacity.
> A reviewer who signed in with a personal Microsoft account sees a line on the landing page saying exactly this.
>
> **A test path that needs neither.** (1) The landing page itself, as above, with any account. (2)
> https://krusgraph.com/check: no account, no Fabric, no administrator. Select the example **A total that doubles**:
> the page shows how the seven synthetic tables connect and flags the order amount that doubles when joined to its
> lines. The files are read in the browser and are not uploaded. https://krusgraph.com/demo opens the same example
> with a short guided tour.
>
> **If you have a Fabric capacity and a work account.** After admin consent
> (https://krusgraph.com/it lists each permission), open Fabric, create a Krusgraph item in a workspace on that
> capacity, point it at a lakehouse, select **Review**, then **Create**. Before activation the same Create answers that
> creating needs a subscription, with a link to the offer.
>
> **Support.** `<support e-mail, e.g. hello@krusgraph.com>`, https://krusgraph.com/support. Privacy:
> https://krusgraph.com/privacy. Terms: https://krusgraph.com/terms.

Before pasting, the founder checks that each step still matches the live site after the redeploy, and that the plan,
price and currency match Partner Center. The text claims no certification, no partnership with Microsoft and no
speed; keep it that way when editing (`CONTRIBUTING.md`, "Claims the product cannot back").

## 2. What the listing must pass

Policy text quoted from the Microsoft Marketplace certification policies [C1]. "Met" means the repository or the code
shows it; everything in Partner Center or on YouTube is the founder's to check.

### 100.1 Value proposition and offer requirements

| Check | Status |
| --- | --- |
| "Test offers are only permitted for private offers." The DEV offer `krusgraph-dev` stays in preview and is never published live (`docs/MARKETPLACE-SETUP.md` section 5) | To check by the founder |
| 100.1.1 Title accurate and descriptive; "the title on the promotional website should match the title in Marketplace" (Krusgraph on krusgraph.com) | To check by the founder |
| 100.1.2 Summary, at most 100 characters | To check by the founder |
| 100.1.3 Description: audience, value, supported Microsoft products (Microsoft Fabric), prerequisites (a Fabric capacity, a work account, admin consent), limitations; no competitor names or logos | To check by the founder |
| 100.1.4 Non-English content: if any text is not in English, the description begins or ends with "This application is available in <languages>." | To check by the founder |
| 100.1.5 At least one public plan (`team`); the offer commercially available and supported | To check by the founder |

### 100.2 Discoverability

| Check | Status |
| --- | --- |
| At most two categories, relevant to the description; an industry only if the description names it | To check by the founder |
| Keywords relevant; no competitor names, no categories or titles as keywords | To check by the founder |
| Several versions of the product grouped as plans of one listing (DEV is a separate preview offer, not a listing) | To check by the founder |

### 100.3 Graphic elements

| Check | Status |
| --- | --- |
| Logo: a .png between 216 and 350 pixels square | To check by the founder |
| Screenshots: "Images must be 1280x720 pixel .png files", sharp, legible; no competitor logos | To check by the founder |
| Screenshot captions. Policy 1140 (Microsoft 365 apps and agents) says "Screenshots must include a caption"; for a SaaS offer, captions are good practice. Write one per screenshot | To check by the founder |
| Video: hosted on YouTube or Vimeo, a direct link to the video (no short URL, playlist or channel page), "publicly viewable and embeddable". On YouTube, **Public or Unlisted** with **Allow embedding** on | To check by the founder |
| Ads off on the video. The policy text says "You must turn off ads in YouTube/Vimeo settings" under 1140 (Microsoft 365 apps and agents); turn them off for this offer too | To check by the founder |

### 100.4 Acquisition, pricing, and terms

| Check | Status |
| --- | --- |
| The description states "Pricing, including currency" and how the offer is provided (trial or purchase). Prices are not in the repository (`docs/MARKETPLACE-SETUP.md`: plans and prices live in Partner Center only); write the price and currency of each plan into the description | To check by the founder |
| The description discloses dependencies: a Microsoft Fabric capacity, a Microsoft Entra work account, admin consent | To check by the founder |
| Every purchase starts in Marketplace; the listing does not send buyers to buy elsewhere and names no other cloud marketplace. Today `/pricing` says "Contact us" and "invoiced" for Pilot and Team (`docs/MARKETPLACE-SETUP.md` section 6): change it to the Marketplace offer before the listing goes live, and do not link the listing to the invoiced route | To check by the founder |
| Pricing model flat rate, the same for all plans [M10] | To check by the founder |

### 100.5 Offer information and 100.6 Personal information

| Check | Status |
| --- | --- |
| Terms and conditions link: https://krusgraph.com/terms exists (today "Preview terms"); choose Microsoft's Standard Contract or own terms (`docs/MARKETPLACE-SETUP.md` section 6) | To check by the founder |
| Privacy policy link: https://krusgraph.com/privacy exists. Before the first subscription it needs the subscription row (`docs/MARKETPLACE-SETUP.md` section 6) | To check by the founder |
| Documentation link: https://krusgraph.com/docs exists | Met (the page exists in `fabric_backend/page_templates/DOCS.md`) |
| Links work and download nothing by themselves | To check by the founder (after the redeploy) |
| No third-party personal information in the listing | To check by the founder |

### 100.7 Accurate source

| Check | Status |
| --- | --- |
| "References to Business Programs participation or eligibility are not allowed", for example MACC, Partner Co-sell, Co-sell Prioritized, IP Co-sell, MPN Competency, Cloud Solution Partner Designation, "anywhere in the metadata of your offer". Also: no "Azure benefit eligible" wording in the listing text (`docs/WORKLOAD-LISTING-AND-PAYMENT.md` mentions it as background; it must not reach the offer) | To check by the founder |
| Microsoft names used as the Trademark and Brand Guidelines say ("Microsoft Fabric" descriptively; no claim of affiliation) | To check by the founder |
| The offer is unique and its content Krusgraph's own or licensed (`THIRD_PARTY_NOTICES.md`) | Met |

### 1000 Software as a Service

| Check | Status |
| --- | --- |
| 1000.1 Primarily platformed on Azure: Krusgraph runs on Azure Container Apps (`deploy/azure_containerapp.py`) | Met |
| 1000.3 The buyer activates with Microsoft Entra single sign-on | Met (`fabric_backend/marketplace.py`, `SignIn`) |
| 1000.3 "Offers must support both Azure AD and Microsoft Account (MSA) types" | Met in code (n204); **live only after** the founder creates *Krusgraph Marketplace sign-in*, sets `marketplace_signin_client_id` and the secret, and redeploys (`docs/MARKETPLACE-SETUP.md` 2a and 4) |
| 1000.3 Microsoft Graph at most `User.Read` during activation | Met: no Graph call at all; scopes `openid profile email` (`tests/test_n204_marketplace_personal_accounts.py`) |
| 1000.4 Integrated with the SaaS fulfilment APIs v2 and the webhook as documented | Met in code (n171, `tests/test_marketplace.py`); to be seen working with the DEV offer |
| 1000.4 Metered billing | Not used (no meters) |
| 1000.6 Landing page "always available and functional" | To check by the founder (the live site after the redeploy) |
| 1000.6 Clear messages for errors and access denials | Met (expired purchase, expired sign-in, another organisation, a failed step: each a plain page) |
| 1000.6 Shows what is needed to complete the configuration, and no sensitive customer data (tokens, passwords, keys) | Met: offer, plan, quantity, status, tenant id; the purchase token is in a cookie, never on the page or in the log |
| 1000.6 No installs or downloads prompted on the landing page | Met (a plain page without scripts) |

## Sources

| # | Title | URL | Read | Learn commit |
| --- | --- | --- | --- | --- |
| C1 | Microsoft Marketplace certification policies (page `ms.date` 2025-08-06, "updated" 2026-10-27; the page itself says "Document version: 1.67") | https://learn.microsoft.com/legal/marketplace/certification-policies | 10 November 2026 | `d07b2d8` |
| M10, M11 | Plan a SaaS offer for Microsoft Marketplace (2026-07-22) | https://learn.microsoft.com/partner-center/marketplace-offers/plan-saas-offer | 10 November 2026 | `3d1a72a` |

**Unverified:** the exact Partner Center field name *Notes for certification* and its length limit (Partner Center was
not opened); whether the certification team tests with a personal Microsoft account; whether the screenshot caption
and the ads-off rule, written under 1140, are applied to SaaS offers.
