SELECT dataset_id, COUNT(*) AS record_count FROM lightning.metastore.${namespace}.renter_records_v1.events GROUP BY dataset_id ORDER BY dataset_id;
SELECT dataset_id, record_status, COUNT(*) AS record_count FROM lightning.metastore.${namespace}.renter_records_v1.events GROUP BY dataset_id, record_status ORDER BY dataset_id, record_status;
SELECT dataset_id, record_id, bin, bbl, hpd_building_id, borough, block, lot, event_date, record_status, source_url FROM lightning.metastore.${namespace}.renter_records_v1.events LIMIT 3;
