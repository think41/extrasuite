Share a Google Workspace file with one or more trusted contacts.

## Usage

  extrasuite sheet share <url> <email> [<email>...] [--role reader|writer|commenter]
  extrasuite doc   share <url> <email> [<email>...] [--role reader|writer|commenter]
  extrasuite slide share <url> <email> [<email>...] [--role reader|writer|commenter]
  extrasuite form  share <url> <email> [<email>...] [--role reader|writer|commenter]

## Arguments

  url      Spreadsheet, document, presentation, or form URL (or file ID)
  email    One or more email addresses to share with

## Options

  --reason TEXT  State the user's intent that led to this command (required). Also -r or -m.

  --role   Permission role: reader, writer, or commenter (default: reader)

## Trusted Contacts

Sharing is restricted to email addresses and domains listed in your settings file:

  ~/.config/extrasuite/settings.toml

Example settings.toml:

  [trusted_contacts]
  domains = ["yourcompany.com"]
  emails  = ["partner@other.com"]

## Notes

- All provided emails are validated against trusted contacts before any API call.
- No invitation email is sent to recipients.
- The file must have been created by or shared with your Google account.
