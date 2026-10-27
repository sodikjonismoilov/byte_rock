COMPILE USL renter_records_v1 DEPLOY NAMESPACE lightning.metastore.${namespace} DDL
CREATE TABLE events (
  dataset_id varchar(32),
  record_id varchar(128),
  bin varchar(32),
  bbl varchar(32),
  hpd_building_id varchar(32),
  borough varchar(128),
  block varchar(32),
  lot varchar(32),
  event_date varchar(128),
  record_status varchar(512),
  source_url varchar(2048),
  scope_note varchar(1024)
)
