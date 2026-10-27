# Verified NYC source inventory

> **Note:** the `reports/...` files mentioned below were local, gitignored captures and are not in this repository; `data/source_registry.json` is the committed source of truth (20 registered sources: 17 machine-readable, 3 manual-only). See the [root README](../../../README.md).

Verified 2026-10-25 against official NYC metadata and genuine Zetaris REST row queries.

All 17 machine-readable datasets below returned an actual row in the capability probe. This verifies connector/schema/agency-key access, not complete historical or address-specific coverage. The probe registrations were temporary and removed. Per-address availability, empty filters, budgets, and truncation are reported separately.

Publisher-provided coverage descriptions, full column schemas, update frequency, and metadata timestamps are preserved in `reports/source_metadata.json` and `data/source_registry.json`. Exact earliest/latest historical dates have not been independently audited.

## Buildings Subject to HPD Jurisdiction

- Capability: live_row_verified.
- Publisher: Department of Housing Preservation and Development (HPD).
- Official reference: https://data.cityofnewyork.us/d/kj4p-ruqc.
- Dataset: `kj4p-ruqc`; original record key fields: `buildingid`.
- Property fields: hpd_building_id→buildingid, bin→bin.
- Update frequency (publisher metadata): Monthly.

## Multiple Dwelling Registrations

- Capability: live_row_verified.
- Publisher: Department of Housing Preservation and Development (HPD).
- Official reference: https://data.cityofnewyork.us/d/tesw-yqqr.
- Dataset: `tesw-yqqr`; original record key fields: `registrationid`.
- Property fields: hpd_building_id→buildingid, bin→bin.
- Update frequency (publisher metadata): Monthly.

## Registration Contacts

- Capability: live_row_verified.
- Publisher: Department of Housing Preservation and Development (HPD).
- Official reference: https://data.cityofnewyork.us/d/feu5-w2e2.
- Dataset: `feu5-w2e2`; original record key fields: `registrationcontactid`.
- Property fields: registration_id→registrationid.
- Update frequency (publisher metadata): Monthly.

## Housing Maintenance Code Violations

- Capability: live_row_verified.
- Publisher: Department of Housing Preservation and Development (HPD).
- Official reference: https://data.cityofnewyork.us/d/wvxf-dwi5.
- Dataset: `wvxf-dwi5`; original record key fields: `violationid`.
- Property fields: hpd_building_id→buildingid, bin→bin, bbl→bbl.
- Update frequency (publisher metadata): Daily.

## Housing Maintenance Code Complaints and Problems

- Capability: live_row_verified.
- Publisher: Department of Housing Preservation & Development (HPD).
- Official reference: https://data.cityofnewyork.us/d/ygpa-z7cr.
- Dataset: `ygpa-z7cr`; original record key fields: `problem_id`.
- Property fields: hpd_building_id→building_id, bin→bin, bbl→bbl.
- Update frequency (publisher metadata): Daily.

## DOB Complaints Received

- Capability: live_row_verified.
- Publisher: Department of Buildings (DOB).
- Official reference: https://data.cityofnewyork.us/d/eabe-havv.
- Dataset: `eabe-havv`; original record key fields: `complaint_number`.
- Property fields: bin→bin.
- Update frequency (publisher metadata): Daily.

## DOB Violations

- Capability: live_row_verified.
- Publisher: Department of Buildings (DOB).
- Official reference: https://data.cityofnewyork.us/d/3h2n-5cm9.
- Dataset: `3h2n-5cm9`; original record key fields: `isn_dob_bis_viol`.
- Property fields: bin→bin.
- Update frequency (publisher metadata): Every weekday.

## DOB ECB Violations

- Capability: live_row_verified.
- Publisher: Department of Buildings (DOB).
- Official reference: https://data.cityofnewyork.us/d/6bgk-3dad.
- Dataset: `6bgk-3dad`; original record key fields: `isn_dob_bis_extract`.
- Property fields: bin→bin.
- Update frequency (publisher metadata): Every weekday.
- Limitation: An ECB/OATH summons is not an adjudicated finding; retain original hearing/certification status. Respondent mailing addresses are not property addresses.

## DOB Permit Issuance

- Capability: live_row_verified.
- Publisher: Department of Buildings (DOB).
- Official reference: https://data.cityofnewyork.us/d/ipu4-2q9a.
- Dataset: `ipu4-2q9a`; original record key fields: `permit_si_no`.
- Property fields: bin→bin__, bbl→bbl.
- Update frequency (publisher metadata): Daily.
- Paging uses documented Socrata internal `:id` order; that ID is not used as an agency citation.
- Limitation: Socrata internal :id is used only for stable pagination after agency-ID sorting timed out. Citations still use original permit_si_no; no system ID is represented as an agency ID.

## DOB Job Application Filings

- Capability: live_row_verified.
- Publisher: Department of Buildings (DOB).
- Official reference: https://data.cityofnewyork.us/d/ic3t-wcy2.
- Dataset: `ic3t-wcy2`; original record key fields: `job_s1_no`.
- Property fields: bin→bin__, bbl→bbl.
- Update frequency (publisher metadata): Daily.

## OATH Hearings Division Case Status

- Capability: live_row_verified.
- Publisher: Office of Administrative Trials and Hearings (OATH).
- Official reference: https://data.cityofnewyork.us/d/jz4z-kudi.
- Dataset: `jz4z-kudi`; original record key fields: `ticket_number`.
- Property fields: OATH violation-location borough/block/lot; never respondent mailing address.
- Update frequency (publisher metadata): Daily.
- Limitation: OATH summons/administrative records are not automatically adjudicated findings. Verify recorded hearing_result separately. FDNY subset only, not all fire inspections.
- Limitation: Exact issuing_agency value FIRE DEPARTMENT OF NYC was observed through the live Zetaris source probe.

## Buildings Selected for the Alternative Enforcement Program (AEP)

- Capability: live_row_verified.
- Publisher: NYC Department of Housing Preservation and Development (HPD).
- Official reference: https://data.cityofnewyork.us/d/hcir-3275.
- Dataset: `hcir-3275`; original record key fields: `building_id`, `aep_round`.
- Property fields: hpd_building_id→building_id, bin→bin, bbl→bbl.
- Update frequency (publisher metadata): Monthly.

## Evictions

- Capability: live_row_verified.
- Publisher: Department of Investigation (DOI).
- Official reference: https://data.cityofnewyork.us/d/6z8x-wfk4.
- Dataset: `6z8x-wfk4`; original record key fields: `court_index_number`, `docket_number`, `executed_date`.
- Property fields: bin→bin, bbl→bbl.
- Update frequency (publisher metadata): Daily.
- Limitation: Executed marshal actions are not filings; unit scope is retained. Empty results are not a complete court history.

## Certification of No Harassment (CONH) Pilot Building List

- Capability: live_row_verified.
- Publisher: Housing Preservation and Development (HPD).
- Official reference: https://data.cityofnewyork.us/d/bzxi-2tsw.
- Dataset: `bzxi-2tsw`; original record key fields: `building_id`.
- Property fields: hpd_building_id→building_id, bin→bin, bbl→bbl.
- Update frequency (publisher metadata): As needed.
- Limitation: Pilot-list membership is not itself a finding of harassment or proof of apartment rent-regulated status.

## Housing Litigations

- Capability: live_row_verified.
- Publisher: Department of Housing Preservation and Development (HPD).
- Official reference: https://data.cityofnewyork.us/d/59kj-x8nc.
- Dataset: `59kj-x8nc`; original record key fields: `litigationid`.
- Property fields: hpd_building_id→buildingid, bin→bin, bbl→bbl.
- Update frequency (publisher metadata): Monthly.

## DOB NOW: Build – Approved Permits

- Capability: live_row_verified.
- Publisher: Department of Buildings (DOB).
- Official reference: https://data.cityofnewyork.us/d/rbx6-tga4.
- Dataset: `rbx6-tga4`; original record key fields: `job_filing_number`, `work_permit`, `sequence_number`.
- Property fields: bin→bin, bbl→bbl.
- Update frequency (publisher metadata): Daily.
- Limitation: DOB NOW general Build datasets exclude some Electrical, Elevator and LAA records. Consult specialty sources/official DOB portal.

## DOB NOW: Build – Job Application Filings

- Capability: live_row_verified.
- Publisher: Department of Buildings (DOB).
- Official reference: https://data.cityofnewyork.us/d/w9ak-ipjd.
- Dataset: `w9ak-ipjd`; original record key fields: `job_filing_number`.
- Property fields: bin→bin, bbl→bbl.
- Update frequency (publisher metadata): Daily.
- Limitation: DOB NOW general Build datasets exclude some Electrical, Elevator and LAA records. Consult specialty sources/official DOB portal.

## HCR rent-regulated building reference / apartment rent history

- Capability: manual_only.
- Publisher: NYS Homes and Community Renewal.
- Official reference: https://hcr.ny.gov/office-rent-administration-ora.
- Limitation: Building-list membership does not establish the requested apartment status. No verified machine-readable address API is configured. Tenant must obtain unit rent history.

## WebCivil Local / Housing Court

- Capability: manual_only.
- Publisher: New York State Unified Court System.
- Official reference: https://www.nycourts.gov/e-courts.
- Limitation: No authorized structured case connector configured. LT listings have limited calendar visibility; no result is not proof of no proceedings. Do not scrape access controls.

## WebCivil Supreme / NYSCEF

- Capability: manual_only.
- Publisher: New York State Unified Court System.
- Official reference: https://www.nycourts.gov/help/representing-yourself-court/getting-court-records-case-information.
- Limitation: Manual party/index/document verification required. Aggregated/de-identified case statistics cannot establish address-specific proceedings.

## Court and rent-reference boundaries

WebCivil Local/Housing Court and WebCivil Supreme/NYSCEF remain manual-only capabilities. No case search was scraped, no de-identified statistics were attributed to an address, and no empty query proves litigation-free status. HPD Housing Litigations is an independent, live agency dataset; it is not a complete court docket connector.

HCR reference information is manual-only. Building list membership and HPD CONH pilot membership never establish apartment rent status. DOB NOW general Build datasets exclude some specialty Electrical, Elevator and LAA records, which must be checked separately in official DOB sources. FDNY coverage is the verified FIRE DEPARTMENT OF NYC subset of OATH, not all FDNY inspections or fire incidents.
