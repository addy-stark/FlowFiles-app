from datetime import datetime
from decimal import Decimal


def parse_reading_row(fields, line_num):
    # Parse a single ZPT row: ZPT|MPAN|Serial|Date|Value|Type
    mpan = fields[1].strip()
    meter_serial = fields[2].strip()
    reading_date_str = fields[3].strip()
    reading_value_str = fields[4].strip()
    reading_type = fields[5].strip() if len(fields) > 5 else ''

    # Validate MPAN (13 digits)
    if not mpan or not mpan.isdigit():
        raise ValueError(f'Invalid MPAN: {mpan}')

    if not meter_serial:
        raise ValueError('Empty meter serial number')

    # Parse date (YYYYMMDD format)
    reading_date = datetime.strptime(reading_date_str, '%Y%m%d').date()

    # Parse value
    reading_value = Decimal(reading_value_str)

    return {
        'mpan': mpan,
        'meter_serial_number': meter_serial,
        'reading_date': reading_date,
        'reading_value': reading_value,
        'reading_type': reading_type,
    }


def parse_grouped_reading_row(fields, mpan, serial, line_num):
    # Parse a 030 row: 030|Type|DateTime|Value
    reading_type = fields[1].strip()
    reading_datetime_str = fields[2].strip()
    reading_value_str = fields[3].strip()

    # Parse date (take first 8 chars: YYYYMMDD)
    if len(reading_datetime_str) >= 8:
        date_part = reading_datetime_str[:8]
        reading_date = datetime.strptime(date_part, '%Y%m%d').date()
    else:
        raise ValueError(f'Invalid date format: {reading_datetime_str}')

    # Parse value
    reading_value = Decimal(reading_value_str)

    return {
        'mpan': mpan,
        'meter_serial_number': serial,
        'reading_date': reading_date,
        'reading_value': reading_value,
        'reading_type': reading_type,
    }


def parse_d0010_lines(lines, on_skipped_line=None):
    # Parse lines from a D0010 file and return a list of reading dicts.
    # Handles two formats:
    # 1. Simple: ZPT|MPAN|Serial|Date|Value|Type
    # 2. Grouped: 026|MPAN, 028|Serial, 030|Type|DateTime|Value
    #
    # on_skipped_line: optional callable(line_num, exc) called for invalid lines

    readings = []
    current_mpan = None
    current_serial = None

    for line_num, line in enumerate(lines, start=1):
        line = line.strip()

        if not line:
            continue

        fields = line.split('|')
        if not fields:
            continue

        record_type = fields[0]

        if record_type == '026' and len(fields) >= 2:
            current_mpan = fields[1].strip()

        elif record_type == '028' and len(fields) >= 2:
            current_serial = fields[1].strip()

        elif record_type == '030' and len(fields) >= 4:
            if current_mpan and current_serial:
                try:
                    reading_data = parse_grouped_reading_row(
                        fields, current_mpan, current_serial, line_num
                    )
                    if reading_data:
                        readings.append(reading_data)
                except Exception as exc:
                    if on_skipped_line:
                        on_skipped_line(line_num, exc)

        elif record_type == 'ZPT' and len(fields) >= 6:
            try:
                reading_data = parse_reading_row(fields, line_num)
                if reading_data:
                    readings.append(reading_data)
            except Exception as exc:
                if on_skipped_line:
                    on_skipped_line(line_num, exc)

    return readings
