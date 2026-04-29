import os
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import FlowFile, MeterReading
from .parsers import parse_d0010_lines


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
        return parse_d0010_lines(content.split('\n'))
    
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
