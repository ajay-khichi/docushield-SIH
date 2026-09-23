"""Layout registry. Each supported document type declares where its fields
live (x, y, w, h) on a canonical 1000x700 canvas. Adding a new document type =
adding one more entry here (that's the extensibility story for phase 2)."""

CANVAS = (1000, 700)

TEMPLATES = {
    "UTO-MOCK-PASSPORT": {
        "photo": (40, 150, 240, 300),
        # visual-zone value boxes; kind drives OCR whitelist & parsing
        "fields": {
            "doc_number":     {"box": (320, 190, 300, 44), "kind": "docno",  "label": "PASSPORT NO."},
            "nationality":    {"box": (640, 190, 320, 44), "kind": "alpha",  "label": "NATIONALITY"},
            "surname":        {"box": (320, 265, 640, 44), "kind": "alpha",  "label": "SURNAME"},
            "given_names":    {"box": (320, 340, 640, 44), "kind": "alpha",  "label": "GIVEN NAMES"},
            "dob":            {"box": (320, 415, 300, 44), "kind": "date",   "label": "DATE OF BIRTH"},
            "sex":            {"box": (640, 415, 100, 44), "kind": "sex",    "label": "SEX"},
            "date_of_issue":  {"box": (320, 490, 300, 44), "kind": "date",   "label": "DATE OF ISSUE"},
            "date_of_expiry": {"box": (640, 490, 320, 44), "kind": "date",   "label": "DATE OF EXPIRY"},
        },
        "mrz_lines": [(30, 566, 940, 52), (30, 622, 940, 52)],
    }
}
DEFAULT_TEMPLATE = "UTO-MOCK-PASSPORT"
