# Conditional Branching in Google Forms

Google Forms supports section-level branching: send respondents to different
sections based on their answer to a RADIO or DROP_DOWN question.

## How It Works

Branching is set on individual **options** inside a RADIO or DROP_DOWN question.
Each option can specify where to send the respondent:

```json
{
  "value": "Option label",
  "goToSectionId": "<itemId of a pageBreakItem>"
}
```

Or use a named action instead of a specific section:

```json
{
  "value": "Option label",
  "goToAction": "SUBMIT_FORM"
}
```

`goToAction` values:
  NEXT_SECTION    Go to the next section (default behaviour)
  RESTART_FORM    Send respondent back to the beginning
  SUBMIT_FORM     Submit the form immediately

## Complete Example

```json
{
  "items": [
    {
      "title": "Are you a current customer?",
      "questionItem": {
        "question": {
          "required": true,
          "choiceQuestion": {
            "type": "RADIO",
            "options": [
              {"value": "Yes", "goToSectionId": "section-existing"},
              {"value": "No",  "goToSectionId": "section-new"}
            ]
          }
        }
      }
    },
    {
      "itemId": "section-existing",
      "title": "Existing Customers",
      "pageBreakItem": {}
    },
    {
      "title": "How long have you been a customer?",
      "questionItem": {"question": {"choiceQuestion": {"type": "RADIO",
        "options": [{"value": "<1 year"}, {"value": "1-3 years"}, {"value": "3+ years"}]}}}
    },
    {
      "itemId": "section-new",
      "title": "New Customers",
      "pageBreakItem": {}
    },
    {
      "title": "How did you hear about us?",
      "questionItem": {"question": {"textQuestion": {"paragraph": false}}}
    }
  ]
}
```

## Referencing Sections

`goToSectionId` must be the `itemId` of a `pageBreakItem` in the same form.

**Existing sections** (already on the form, have API-assigned itemIds):
  Use the itemId as-is. You can see it in the pulled form.json.

**New sections** (being added in this edit):
  Give the pageBreakItem a meaningful itemId of your choice (e.g.
  "feedback-section"). The push command detects that this ID is new,
  creates the section first to get the real API-assigned ID, then
  creates/updates the question with the resolved ID. This happens
  automatically in two API calls.

  Rules for agent-chosen IDs:
  - Must not match any existing itemId in the form (check the pulled form.json)
  - Can be any string: "feedback-section", "skip-to-end", etc.
  - After push, form.json is automatically rewritten with the real API IDs

## Constraints

- Branching only works on RADIO and DROP_DOWN question types
- Only one of goToSectionId or goToAction may be set per option
- You cannot show/hide individual questions — only entire sections
- Sections without explicit branching always advance to the next section
