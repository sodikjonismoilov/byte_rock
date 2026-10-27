ACTIVATE USL TABLE lightning.metastore.${namespace}.renter_records_v1.events AS
SELECT 'wvxf-dwi5' AS dataset_id, CAST(violationid AS STRING) AS record_id,
  CAST(bin AS STRING) AS bin, CAST(bbl AS STRING) AS bbl,
  CAST(buildingid AS STRING) AS hpd_building_id, CAST(boro AS STRING) AS borough,
  CAST(block AS STRING) AS block, CAST(lot AS STRING) AS lot,
  CAST(inspectiondate AS STRING) AS event_date, CAST(currentstatus AS STRING) AS record_status,
  CONCAT('https://data.cityofnewyork.us/resource/wvxf-dwi5.json?violationid=', CAST(violationid AS STRING)) AS source_url,
  'ZIP 10017; existing source cap 200; not complete history or a verified property match' AS scope_note
FROM ${hpd_table}
UNION ALL
SELECT 'ipu4-2q9a', CAST(permit_si_no AS STRING), CAST(bin__ AS STRING), CAST(NULL AS STRING),
  CAST(NULL AS STRING), CAST(borough AS STRING), CAST(block AS STRING), CAST(lot AS STRING),
  CAST(issuance_date AS STRING), CAST(permit_status AS STRING),
  CONCAT('https://data.cityofnewyork.us/resource/ipu4-2q9a.json?permit_si_no=', CAST(permit_si_no AS STRING)),
  'ZIP 10017; source cap 20; original BIN retained; no inferred BBL/property match'
FROM ${source_db}.dob_permits
UNION ALL
SELECT 'jz4z-kudi', CAST(ticket_number AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING),
  CAST(NULL AS STRING), CAST(violation_location_borough AS STRING),
  CAST(violation_location_block_no AS STRING), CAST(violation_location_lot_no AS STRING),
  CAST(violation_date AS STRING), CAST(hearing_status AS STRING),
  CONCAT('https://data.cityofnewyork.us/resource/jz4z-kudi.json?ticket_number=', CAST(ticket_number AS STRING)),
  'ZIP 10017; FDNY subset; source cap 20; raw borough/block/lot are not verified building links'
FROM ${source_db}.oath_fdny
