# Authority refusal correction

All 280 inherited project files remain exact. The independent vault is unchanged. Only the new importer adds a context boundary that preserves authority JournalError refusals after normal snapshot validation/release; vault expiry or cleanup failure still takes precedence. The original 19 methods are unchanged, and one post-seal revocation method is added. The earlier configuration-change assertion failure remains retained; no state is repaired or reset.
