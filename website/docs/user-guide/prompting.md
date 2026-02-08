# Prompting Guide

Learn how to write effective prompts for working with Google Workspace files through ExtraSuite. While many examples below use Sheets, the same principles apply to Docs, Slides, and Forms.

## The Golden Rule

**Provide context.** The more context you give your AI agent, the better the results.

!!! tip "Context is King"
    A vague prompt like "update the spreadsheet" will produce vague results. A specific prompt with context about your data, goals, and constraints will produce exactly what you need.

## Anatomy of a Good Prompt

### 1. State Your Goal

Start with what you want to accomplish:

```
I need to create a monthly sales report...
I want to analyze customer retention...
Help me clean up this messy data...
```

### 2. Provide the Spreadsheet URL

Always include the full URL:

```
...in this spreadsheet: https://docs.google.com/spreadsheets/d/abc123/edit
```

### 3. Describe the Data

Give context about what's in the spreadsheet:

```
The spreadsheet has three sheets:
- "Raw Data" with daily transactions (columns: Date, Product, Amount, Customer)
- "Summary" which is currently empty
- "Settings" with lookup values
```

### 4. Specify the Output

Be clear about what you expect:

```
Create a pivot table showing total revenue by product category and month.
Put the result in a new sheet called "Analysis".
Use a currency format for all dollar values.
```

## Prompt Templates

### Data Analysis

```
I have sales data in https://docs.google.com/spreadsheets/d/abc123/edit

The "Sales" sheet contains:
- Column A: Date (MM/DD/YYYY format)
- Column B: Product Name
- Column C: Quantity
- Column D: Unit Price
- Column E: Customer ID

Please:
1. Calculate total revenue per product
2. Find the top 5 customers by total spend
3. Create a monthly trend analysis
4. Put all results in a new sheet called "Analysis"
```

### Data Cleaning

```
Clean the data in https://docs.google.com/spreadsheets/d/abc123/edit

Issues to fix:
- Remove duplicate rows (based on columns A and B)
- Standardize date format to YYYY-MM-DD
- Fix inconsistent capitalization in the "Category" column
- Remove rows where "Amount" is empty or zero

Don't delete the original data - create a cleaned version in a new sheet.
```

### Report Generation

```
Using the data in https://docs.google.com/spreadsheets/d/abc123/edit,
create a quarterly business report.

Include:
- Executive summary (3-5 bullet points)
- Revenue by region (table + chart)
- Year-over-year comparison
- Top 10 products by units sold

Use proper formatting:
- Currency format for money values
- Percentage format for growth rates
- Bold headers
- Alternating row colors
```

### Formula Creation

```
In https://docs.google.com/spreadsheets/d/abc123/edit, add formulas to the "Metrics" sheet:

- Cell B2: Calculate total revenue from Sheet1!D:D
- Cell B3: Calculate average order value
- Cell B4: Count unique customers from Sheet1!E:E
- Cell B5: Growth rate compared to B2 in previous row

Use IFERROR to handle division by zero.
Use absolute references where appropriate.
```

## Common Prompt Patterns

### Reading Data

```
Read the data from https://docs.google.com/spreadsheets/d/abc123/edit
and tell me:
- How many rows of data are there?
- What are the column headers?
- Are there any empty cells in the first 5 columns?
```

### Writing Data

```
In https://docs.google.com/spreadsheets/d/abc123/edit:
- Add a new row at the bottom with these values: ["2024-01-15", "Product A", 100, 25.99]
- Update cell B5 to "Updated Product Name"
- Clear the contents of range D10:D20
```

### Creating Structure

```
In https://docs.google.com/spreadsheets/d/abc123/edit:
- Create a new sheet called "Dashboard"
- Add headers in row 1: Date, Metric, Value, Target, Status
- Freeze the first row
- Set column widths: A=100, B=150, C=80, D=80, E=100
```

### Conditional Logic

```
In https://docs.google.com/spreadsheets/d/abc123/edit:
- Add a "Status" formula in column E that shows:
  - "On Track" if C > D (green background)
  - "At Risk" if C is between 80% and 100% of D (yellow background)
  - "Behind" if C < 80% of D (red background)
```

## What to Avoid

### Too Vague

❌ **Bad**: "Fix the spreadsheet"
✅ **Good**: "In the Sales sheet, fix the date format in column A to be YYYY-MM-DD"

### Missing URL

❌ **Bad**: "Update my sales data"
✅ **Good**: "Update the sales data in https://docs.google.com/spreadsheets/d/abc123/edit"

### Ambiguous References

❌ **Bad**: "Sum up the numbers"
✅ **Good**: "Calculate the sum of column D (Revenue) from row 2 to the last row with data"

### No Context About Data

❌ **Bad**: "Create a chart"
✅ **Good**: "Create a line chart showing monthly revenue (column B) over time (column A) for the past 12 months"

## Multi-Step Workflows

For complex tasks, break them down:

```
Let's work on the quarterly report in https://docs.google.com/spreadsheets/d/abc123/edit

Step 1: First, read the raw data from the "Transactions" sheet and confirm:
- How many transactions are there?
- What's the date range?
- What columns are available?

[Wait for response]

Step 2: Now create a summary in a new "Q4 Summary" sheet with:
- Total transactions
- Total revenue
- Average transaction value
- Top 5 products

[Wait for response]

Step 3: Finally, add a chart showing daily revenue trends.
```

## Tips for Better Results

### 1. Be Explicit About Format

```
Format the revenue column as currency with 2 decimal places ($1,234.56)
Format the growth column as percentage with 1 decimal place (12.3%)
```

### 2. Specify Sheet Names

```
Read from the "Raw Data" sheet
Write results to the "Analysis" sheet
```

### 3. Mention Edge Cases

```
If a cell is empty, treat it as zero
If there are duplicate customer IDs, use the most recent record
```

### 4. Request Verification

```
After making changes, verify:
- The formula in B10 correctly sums B2:B9
- No #REF! or #DIV/0! errors exist
- Row count matches expected (150 rows)
```

## Real-World Examples

### Example 1: Financial Analysis

```
I'm preparing for a board meeting. In https://docs.google.com/spreadsheets/d/abc123/edit:

The "Financials" sheet has our monthly P&L data:
- Column A: Month (Jan 2024 - Dec 2024)
- Column B: Revenue
- Column C: COGS
- Column D: Operating Expenses
- Column E: Net Income

Please:
1. Add a "Metrics" section starting in column G with:
   - Gross Margin % (B-C)/B
   - Operating Margin % (E/B)
   - MoM Revenue Growth %

2. Create a "Board Summary" sheet with:
   - YTD totals for each line item
   - Full year comparison vs 2023 (data in "Prior Year" sheet)
   - Visual indicators for positive/negative trends

3. Add a revenue waterfall chart showing how we got from Jan to Dec revenue
```

### Example 2: Data Reconciliation

```
I need to reconcile two data sources in https://docs.google.com/spreadsheets/d/abc123/edit

- "System A" sheet: Export from our CRM (columns: CustomerID, Email, Status, LastContact)
- "System B" sheet: Export from billing (columns: CustID, EmailAddress, SubscriptionStatus, LastPayment)

Please:
1. Find customers in System A but not in System B (match on CustomerID = CustID)
2. Find customers in System B but not in System A
3. Find customers where email doesn't match
4. Find customers where status is "Active" in one system but not the other

Put results in a "Reconciliation" sheet with clear headers and counts of each issue type.
```

---

**Next**: Learn how to [share documents](sharing.md) with your AI agent.
