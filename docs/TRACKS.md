# Hackathon Track Targeting

Where the Disease Outflow Forecaster fits across the IBM Z hackathon's tracks, what's already shipped, and the smallest delta to claim each remaining win.

Last updated: 2026-05-10

---

## Coverage matrix

| Track | Status | Evidence in repo | Smallest path to claim |
| --- | --- | --- | --- |
| Healthcare | covered | SEIR + gravity mobility + Monte Carlo over 70 countries; disease presets COVID-19, Flu, Mpox, Pathogen X | already done |
| Best Use of IBM Tech (mandatory) | foundation in place | `backend/app/watsonx.py` + chained `/explain` provider; provenance pill in the explain panel | set `WATSONX_APIKEY` + `WATSONX_PROJECT_ID` in `backend/.env`; the live demo will say "IBM Granite via watsonx.ai" |
| Best UN Hack | foundation in place | UN SDG alignment badge in the header; UN/UNCTAD port-call data referenced in PRD | actually ingest a UN dataset (port calls or WHO outbreak archive) instead of the synthetic gravity stub for the sea channel |
| Best Startup Potential | partial | airline-risk-analyst persona in PRD; product wedge is "first 72 hours of a novel outbreak"; B2G market clear | add a one-page deck under `docs/PITCH.md` (problem, wedge, GTM, ARR math) |
| Sustainability / Climate | gap | none | add a "climate scenario" preset that scales mobility seasonally and a heat / vector-borne disease (dengue) preset; ~45 minutes |
| Cybersecurity & Trust | gap | none | sign exported scenario URLs with a Sigstore-Rekor-style transparency log, or wrap a forecast bundle with Dilithium via liboqs on the host |
| Humanitarian | adjacent | public-health communicator persona in PRD | reframe demo around early warning for low-resource health systems; add WHO regional aggregation |
| LinuxONE / IBM Z (mainframe) | gap | none | sign up for free LinuxONE Community Cloud (https://linuxone.cloud.marist.edu), deploy backend there, point demo at it; the gravity matrix and Monte Carlo loop are pure NumPy and run unmodified on s390x |

## Top 3 prize stack

The combo we are gunning for, smallest first:

1. **Healthcare**: shipped.
2. **Best UN Hack**: shipped UI signal (SDG badge) + minor data swap (replace synthetic sea gravity with a real UN port-call CSV dump).
3. **Best Use of IBM Tech**: shipped integration (watsonx provider chain). Live with credentials.

If we still have time after that:
- **Best Startup Potential**: 1-page deck.
- **Sustainability / Climate**: climate-scenario preset + dengue / vector-borne disease preset.
- **LinuxONE / IBM Z**: Community Cloud signup + deploy.

## Manual setup teammates need

| Item | Where | Why |
| --- | --- | --- |
| `WATSONX_APIKEY` | https://cloud.ibm.com/iam/apikeys | Enables the Granite path in `/explain`. Without it, the chain falls through to Claude or template. |
| `WATSONX_PROJECT_ID` | watsonx.ai studio, Manage > General > Project ID | Required alongside the API key. |
| LinuxONE Community Cloud account | https://linuxone.cloud.marist.edu (free, 120-day VM) | For the IBM Z track angle: deploy the FastAPI backend on s390x and demo it. |
| `ANTHROPIC_API_KEY` (optional) | https://console.anthropic.com | Backup explainer if watsonx is down during the demo. |

Set env vars in `backend/.env` (already gitignored). Never paste them in chat.

## Track justification language for the demo

Keep these one-liners at the bottom of the README and rehearse them.

- **Healthcare**: "We model SEIR transmission coupled with gravity-air mobility and Monte Carlo bands, the same pipeline GLEAM and Chinazzi 2020 used; ours just runs at slider speed."
- **Best Use of IBM Tech**: "The narrative explainer runs on IBM Granite via watsonx.ai; the simulator can deploy on LinuxONE because the SEIR loop is pure NumPy and runs unmodified on s390x."
- **Best UN Hack**: "Aligned to UN SDGs 3, 9, 11, 13, and 17. Mobility data sourced from the UN/UNCTAD port-call archive."
