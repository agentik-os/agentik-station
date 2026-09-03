# Update Rollback and Receipts

Station retains:
- pre-update Station snapshot reference;
- Hermes full backup for LAB candidate update;
- Hermes update receipt;
- pre/post commit/version matrix;
- config migration diff;
- Station lockfile before/after;
- test/eval/doctor results;
- rollback rehearsal evidence.

If candidate fails, rollback is immediate and candidate is not promoted. Stable release rollback reactivates the previous immutable Station release plus compatible state snapshot according to each OS recovery contract.
