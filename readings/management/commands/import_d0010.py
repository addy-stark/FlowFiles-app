import os
from datetime import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from readings.models import FlowFile, MeterReading


class Command(BaseCommand):
    help = 'Import D0010 flow files containing meter reading data'

    def add_arguments(self, parser):
        parser.add_argument(
            'files',
            nargs='+',
            type=str,
            help='Path(s) to D0010 file(s) to import'
        )
        parser.add_argument(
            '--skip-duplicates',
            action='store_true',
            help='Skip files that have already been imported'
        )

    def handle(self, *args, **options):
        # Import all specified files
        files = options['files']
        skip_duplicates = options['skip_duplicates']
        
        self.stdout.write(self.style.SUCCESS(f'Starting import of {len(files)} file(s)...'))
        
        total_imported = 0
        total_skipped = 0
        
        for file_path in files:
            try:
                imported, skipped = self.import_file(file_path, skip_duplicates)
                total_imported += imported
                total_skipped += skipped
            except CommandError:
                raise
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error processing {file_path}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS(f'\nImport complete! Total readings imported: {total_imported}'))
        if total_skipped > 0:
            self.stdout.write(self.style.WARNING(f'Skipped {total_skipped} duplicate file(s)'))

    def import_file(self, file_path, skip_duplicates):
        # Import a single D0010 file
        if not os.path.exists(file_path):
            raise CommandError(f'File does not exist: {file_path}')
        
        filename = os.path.basename(file_path)
        
        # Check if file already imported
        if FlowFile.objects.filter(filename=filename).exists():
            if skip_duplicates:
                self.stdout.write(self.style.WARNING(f'Skipping {filename} (already imported)'))
                return 0, 1
            raise CommandError(f'File {filename} has already been imported. Use --skip-duplicates to skip it.')
        
        # Parse and import file
        self.stdout.write(f'Processing {filename}...')
        
        with transaction.atomic():
            flow_file = FlowFile.objects.create(filename=filename)
            readings = self.parse_d0010_file(file_path, flow_file)
            
            MeterReading.objects.bulk_create(readings)
            
            flow_file.record_count = len(readings)
            flow_file.save()
        
        self.stdout.write(self.style.SUCCESS(f'✓ Imported {len(readings)} reading(s) from {filename}'))
        
        return len(readings), 0

    def parse_d0010_file(self, file_path, flow_file):
        # Parse D0010 file and extract meter readings
        # Handles two formats:
        # 1. Simple: ZPT|MPAN|Serial|Date|Value|Type
        # 2. Grouped: 026|MPAN, 028|Serial, 030|Type|DateTime|Value
        
        readings = []
        current_mpan = None
        current_serial = None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                
                fields = line.split('|')
                if not fields:
                    continue
                
                record_type = fields[0]
                
                # Handle grouped format
                if record_type == '026' and len(fields) >= 2:
                    current_mpan = fields[1].strip()
                
                elif record_type == '028' and len(fields) >= 2:
                    current_serial = fields[1].strip()
                
                elif record_type == '030' and len(fields) >= 4:
                    if current_mpan and current_serial:
                        try:
                            reading = self.parse_grouped_reading_row(
                                fields, current_mpan, current_serial, flow_file, line_num
                            )
                            if reading:
                                readings.append(reading)
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f'Skipping line {line_num}: {str(e)}'))
                
                # Handle simple ZPT format
                elif record_type == 'ZPT' and len(fields) >= 6:
                    try:
                        reading = self.parse_reading_row(fields, flow_file, line_num)
                        if reading:
                            readings.append(reading)
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Skipping line {line_num}: {str(e)}'))
        
        if not readings:
            raise CommandError(f'No valid meter readings found in file {file_path}')
        
        return readings

    def parse_reading_row(self, fields, flow_file, line_num):
        # Parse ZPT row: ZPT|MPAN|Serial|Date|Value|Type
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
        
        # Parse date (YYYYMMDD)
        reading_date = datetime.strptime(reading_date_str, '%Y%m%d').date()
        
        # Parse value
        reading_value = Decimal(reading_value_str)
        
        return MeterReading(
            flow_file=flow_file,
            mpan=mpan,
            meter_serial_number=meter_serial,
            reading_date=reading_date,
            reading_value=reading_value,
            reading_type=reading_type
        )
    
    def parse_grouped_reading_row(self, fields, mpan, serial, flow_file, line_num):
        # Parse 030 row: 030|Type|DateTime|Value
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
        
        return MeterReading(
            flow_file=flow_file,
            mpan=mpan,
            meter_serial_number=serial,
            reading_date=reading_date,
            reading_value=reading_value,
            reading_type=reading_type
        )
