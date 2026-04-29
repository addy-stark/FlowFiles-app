import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from readings.models import FlowFile, MeterReading
from readings.parsers import parse_d0010_lines


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
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        reading_dicts = parse_d0010_lines(
            lines,
            on_skipped_line=lambda line_num, exc: self.stdout.write(
                self.style.WARNING(f'Skipping line {line_num}: {exc}')
            ),
        )

        if not reading_dicts:
            raise CommandError(f'No valid meter readings found in file {file_path}')

        return [
            MeterReading(flow_file=flow_file, **reading_data)
            for reading_data in reading_dicts
        ]
