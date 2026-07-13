# Preview index

`verify_preview_exports.py` writes one row per inspected asset after recursive, multi-batch verification.

Required fields are `uuid`, `inspection_batch`, `preview_path`, `byte_size`, `sha256`, `decode_status`, `pixel_width`, `pixel_height`, and `exported_at`.

Contact-sheet generation accepts only rows whose `decode_status` is `ok`. Paths are local and private; do not publish a preview index.
