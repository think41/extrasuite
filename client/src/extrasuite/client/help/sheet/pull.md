Download a Google Sheet to a local folder.

  extrasuite sheets pull <url> [output_dir]

  url           Spreadsheet URL or ID
  output_dir    Output directory (default: creates <spreadsheet_id>/ in CWD)

  --max-rows N  Max rows per sheet (default: 1000; 0 = no limit)
  --no-limit    Fetch all rows (equivalent to --max-rows 0)
  --no-raw      Skip saving raw API responses to .raw/
