import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import FlowFile, MeterReading


class FlowFileUploadForm(forms.ModelForm):
    file_upload = forms.FileField(
        label='Upload D0010 Flow File',
        help_text='Select a D0010 flow file (.txt or .flo) to import',
        required=True
    )
    
    class Meta:
        model = FlowFile
        fields = []
    
    def clean_file_upload(self):
        # Validate the uploaded file
        uploaded_file = self.cleaned_data.get('file_upload')
        
        if not uploaded_file:
            raise ValidationError('No file was uploaded.')
        
        filename = uploaded_file.name
        
        # Check file extension (.txt or .flo only)
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in ['.txt', '.flo']:
            raise ValidationError(
                f'Invalid file type. Please upload a .txt or .flo file. '
                f'Your file has extension: {file_ext}'
            )
        
        # Check file size (max 10MB)
        if uploaded_file.size > 10 * 1024 * 1024:
            raise ValidationError('File is too large. Maximum size is 10MB.')
        
        # Check if file already imported
        if FlowFile.objects.filter(filename=filename).exists():
            raise ValidationError(
                f'File "{filename}" has already been imported. '
                f'Please rename the file or delete the previous import.'
            )
        
        return uploaded_file
    
    def clean(self):
        # Parse the D0010 file content
        cleaned_data = super().clean()
        uploaded_file = cleaned_data.get('file_upload')
        
        if not uploaded_file:
            return cleaned_data
        
        filename = uploaded_file.name
        
        # Read file content
        content = uploaded_file.read()
        
        # Try to decode as UTF-8, fallback to latin-1
        try:
            text_content = content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text_content = content.decode('latin-1')
            except UnicodeDecodeError:
                raise ValidationError('Unable to read file. Please ensure it is a text file.')
        
        # Reset file pointer for later use
        uploaded_file.seek(0)
        
        # Parse the file
        readings = self.parse_d0010_content(text_content, filename)
        
        if not readings:
            raise ValidationError('No valid meter readings found in the file.')
        
        # Store parsed data for use in save()
        cleaned_data['_parsed_readings'] = readings
        cleaned_data['_filename'] = filename
        
        return cleaned_data
    
    def parse_d0010_content(self, content, filename):
        # Parse D0010 file and extract meter readings
        # Handles two formats:
        # 1. Simple: ZPT|MPAN|Serial|Date|Value|Type
        # 2. Grouped: 026|MPAN, 028|Serial, 030|Type|DateTime|Value
        
        readings = []
        lines = content.split('\n')
        
        # Track MPAN and serial for grouped format
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
            
            # Handle grouped format lines
            if record_type == '026' and len(fields) >= 2:
                current_mpan = fields[1].strip()
            
            elif record_type == '028' and len(fields) >= 2:
                current_serial = fields[1].strip()
            
            elif record_type == '030' and len(fields) >= 4:
                if current_mpan and current_serial:
                    try:
                        reading_data = self.parse_grouped_reading_row(
                            fields, current_mpan, current_serial, line_num
                        )
                        if reading_data:
                            readings.append(reading_data)
                    except Exception:
                        pass  # Skip invalid lines
            
            # Handle simple ZPT format
            elif record_type == 'ZPT' and len(fields) >= 6:
                try:
                    reading_data = self.parse_reading_row(fields, line_num)
                    if reading_data:
                        readings.append(reading_data)
                except Exception:
                    pass  # Skip invalid lines
        
        return readings
        
        return readings
    
    def parse_reading_row(self, fields, line_num):
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
            'reading_type': reading_type
        }
    
    def parse_grouped_reading_row(self, fields, mpan, serial, line_num):
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
            'reading_type': reading_type
        }
    
    def save(self, commit=True):
        # Save the FlowFile and create MeterReading records
        parsed_readings = self.cleaned_data.get('_parsed_readings', [])
        filename = self.cleaned_data.get('_filename')
        
        if not commit:
            # Create unsaved FlowFile instance
            flow_file = FlowFile(
                filename=filename,
                record_count=len(parsed_readings)
            )
            flow_file._parsed_readings = parsed_readings
            self.instance = flow_file
            return flow_file
        
        # Save everything in a transaction
        with transaction.atomic():
            # Check if instance already exists
            if hasattr(self.instance, 'pk') and self.instance.pk:
                flow_file = self.instance
            else:
                # Create FlowFile
                flow_file = FlowFile.objects.create(
                    filename=filename,
                    record_count=len(parsed_readings)
                )
            
            # Create MeterReading records
            meter_readings = [
                MeterReading(flow_file=flow_file, **reading_data)
                for reading_data in parsed_readings
            ]
            MeterReading.objects.bulk_create(meter_readings)
        
        return flow_file
    
    def save_m2m(self):
        # Create deferred MeterReading records
        if hasattr(self.instance, '_parsed_readings'):
            parsed_readings = self.instance._parsed_readings
            
            with transaction.atomic():
                # Create MeterReading records
                meter_readings = [
                    MeterReading(flow_file=self.instance, **reading_data)
                    for reading_data in parsed_readings
                ]
                MeterReading.objects.bulk_create(meter_readings)
                
                # Update record count
                self.instance.record_count = len(meter_readings)
                self.instance.save(update_fields=['record_count'])
            
            # Clean up temporary attribute
            delattr(self.instance, '_parsed_readings')
