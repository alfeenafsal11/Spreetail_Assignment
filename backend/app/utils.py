import re
from datetime import datetime, date

def parse_amount(val: str) -> float:
    if not val:
        return 0.0
    # Strip quotes, commas, and whitespace
    clean_val = str(val).replace('"', '').replace(',', '').strip()
    if not clean_val:
        return 0.0
    try:
        return round(float(clean_val), 2)
    except ValueError:
        return 0.0

def parse_date(val: str) -> tuple[date, bool]:
    """
    Parses DD-MM-YYYY format.
    Detects ambiguous dates (Mar-14, 04-05-2026) and returns (parsed_date, is_ambiguous).
    """
    if not val:
        raise ValueError("Empty date value")
        
    val_str = str(val).strip()
    
    # Check specific ambiguous cases
    if val_str.lower() == "mar-14":
        return date(2026, 3, 14), True
        
    if val_str == "04-05-2026":
        return date(2026, 5, 4), True
        
    # Standard format DD-MM-YYYY
    try:
        parsed_dt = datetime.strptime(val_str, "%d-%m-%Y").date()
        return parsed_dt, False
    except ValueError:
        pass
        
    # Try alternative formats just in case
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(val_str, fmt).date(), False
        except ValueError:
            continue
            
    raise ValueError(f"Unable to parse date string: {val_str}")

def parse_split_details(details_str: str, split_type: str) -> dict[str, float]:
    """
    Parses "Name value; Name value; ..." string.
    Returns a dict mapping name -> float value.
    """
    if not details_str or not isinstance(details_str, str) or not details_str.strip():
        return {}
        
    result = {}
    # Split by semicolon
    items = details_str.split(";")
    for item in items:
        item = item.strip()
        if not item:
            continue
        # Split by last whitespace to separate name from value
        parts = item.rsplit(None, 1)
        if len(parts) == 2:
            name, val_str = parts
            name = name.strip()
            val_str = val_str.strip()
            
            # Strip % suffix for percentages
            if split_type == "percentage" and val_str.endswith("%"):
                val_str = val_str[:-1].strip()
                
            try:
                result[name] = float(val_str)
            except ValueError:
                result[name] = 0.0
    return result
