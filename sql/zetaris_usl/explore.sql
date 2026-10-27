SELECT violationid, buildingid, bin, bbl, inspectiondate, currentstatus FROM ${hpd_table} LIMIT 3;
SELECT currentstatus, COUNT(*) AS record_count FROM ${hpd_table} GROUP BY currentstatus;
SELECT permit_si_no, bin__, issuance_date, permit_status FROM ${source_db}.dob_permits LIMIT 3;
SELECT permit_status, COUNT(*) AS record_count FROM ${source_db}.dob_permits GROUP BY permit_status;
SELECT ticket_number, violation_location_borough, violation_location_block_no, violation_location_lot_no, violation_date, hearing_status FROM ${source_db}.oath_fdny LIMIT 3;
SELECT hearing_status, COUNT(*) AS record_count FROM ${source_db}.oath_fdny GROUP BY hearing_status;
