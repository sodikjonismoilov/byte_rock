REGISTER DQ source_identity_integrity TABLE lightning.metastore.${namespace}.renter_records_v1.events AS
record_id IS NOT NULL AND LENGTH(TRIM(record_id)) > 0
AND dataset_id IN ('wvxf-dwi5', 'ipu4-2q9a', 'jz4z-kudi')
AND source_url LIKE 'https://data.cityofnewyork.us/resource/%'
AND (bin IS NULL OR bin RLIKE '^[1-5][0-9]{6}$')
AND (bbl IS NULL OR bbl RLIKE '^[1-5][0-9]{9}$')
