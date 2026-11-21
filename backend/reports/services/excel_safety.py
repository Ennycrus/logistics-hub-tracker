"""
Keep typed text as text in the Excel files the app makes.

In Excel, a cell whose text starts with "=" is a formula. A note, reason or
incident you type that begins with "=" (for example "=see attached") would
become a formula when your manager opens the file: usually an error, at worst
something unexpected. None of our files use real formulas, so every cell that
looks like one is saved as plain text instead.
"""


def keep_as_text(workbook):
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.data_type == 'f':  # openpyxl took text starting with "=" for a formula
                    cell.data_type = 's'
    return workbook