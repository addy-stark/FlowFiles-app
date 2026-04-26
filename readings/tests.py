"""
Test suite for the readings app.

Tests cover:
- Model creation and validation
- D0010 file import functionality
- Admin interface search capabilities
"""
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from io import StringIO

from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model

from .models import FlowFile, MeterReading
from .admin import FlowFileAdmin, MeterReadingAdmin


User = get_user_model()


class FlowFileModelTests(TestCase):
    """Tests for the FlowFile model."""
    
    def test_flow_file_creation(self):
        """Test creating a FlowFile instance."""
        flow_file = FlowFile.objects.create(
            filename='test_file.txt',
            record_count=10
        )
        
        self.assertEqual(flow_file.filename, 'test_file.txt')
        self.assertEqual(flow_file.record_count, 10)
        self.assertIsNotNone(flow_file.imported_at)
    
    def test_flow_file_str_representation(self):
        """Test string representation of FlowFile."""
        flow_file = FlowFile.objects.create(filename='test.txt')
        str_repr = str(flow_file)
        
        self.assertIn('test.txt', str_repr)
        self.assertIn('imported', str_repr.lower())
    
    def test_flow_file_unique_filename(self):
        """Test that filenames must be unique."""
        FlowFile.objects.create(filename='unique.txt')
        
        with self.assertRaises(Exception):  # IntegrityError
            FlowFile.objects.create(filename='unique.txt')


class MeterReadingModelTests(TestCase):
    """Tests for the MeterReading model."""
    
    def setUp(self):
        """Set up test data."""
        self.flow_file = FlowFile.objects.create(
            filename='test_readings.txt',
            record_count=1
        )
    
    def test_meter_reading_creation(self):
        """Test creating a MeterReading instance."""
        reading = MeterReading.objects.create(
            flow_file=self.flow_file,
            mpan='1234567890123',
            meter_serial_number='MTR12345',
            reading_date=date(2026, 4, 15),
            reading_value=Decimal('12345.678'),
            reading_type='Normal'
        )
        
        self.assertEqual(reading.mpan, '1234567890123')
        self.assertEqual(reading.meter_serial_number, 'MTR12345')
        self.assertEqual(reading.reading_value, Decimal('12345.678'))
    
    def test_meter_reading_str_representation(self):
        """Test string representation of MeterReading."""
        reading = MeterReading.objects.create(
            flow_file=self.flow_file,
            mpan='1234567890123',
            meter_serial_number='MTR12345',
            reading_date=date(2026, 4, 15),
            reading_value=Decimal('12345.678')
        )
        
        str_repr = str(reading)
        self.assertIn('1234567890123', str_repr)
        self.assertIn('2026-04-15', str_repr)
    
    def test_meter_reading_relationships(self):
        """Test foreign key relationship with FlowFile."""
        reading = MeterReading.objects.create(
            flow_file=self.flow_file,
            mpan='1234567890123',
            meter_serial_number='MTR12345',
            reading_date=date(2026, 4, 15),
            reading_value=Decimal('12345.678')
        )
        
        self.assertEqual(reading.flow_file, self.flow_file)
        self.assertEqual(self.flow_file.readings.count(), 1)
        self.assertEqual(self.flow_file.readings.first(), reading)


class ImportD0010CommandTests(TestCase):
    """Tests for the import_d0010 management command."""
    
    def create_test_file(self, content):
        """Helper to create a temporary test file."""
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            delete=False
        )
        temp_file.write(content)
        temp_file.close()
        return temp_file.name
    
    def tearDown(self):
        """Clean up temporary files."""
        # Remove any temporary files created during tests
        pass
    
    def test_import_valid_file(self):
        """Test importing a valid D0010 file."""
        content = """ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|20260415|12345.678|Normal
ZPT|9876543210987|MTR67890|20260416|54321.100|Normal
ZTR|2|20260426|143500"""
        
        file_path = self.create_test_file(content)
        
        try:
            out = StringIO()
            call_command('import_d0010', file_path, stdout=out)
            
            # Check database
            self.assertEqual(FlowFile.objects.count(), 1)
            self.assertEqual(MeterReading.objects.count(), 2)
            
            # Check first reading
            reading = MeterReading.objects.get(mpan='1234567890123')
            self.assertEqual(reading.meter_serial_number, 'MTR12345')
            self.assertEqual(reading.reading_value, Decimal('12345.678'))
            self.assertEqual(reading.reading_date, date(2026, 4, 15))
            self.assertEqual(reading.reading_type, 'Normal')
            
            # Check output
            output = out.getvalue()
            self.assertIn('2', output)  # 2 readings imported
            self.assertIn('complete', output.lower())
        finally:
            os.unlink(file_path)
    
    def test_import_nonexistent_file(self):
        """Test error when file doesn't exist."""
        with self.assertRaises(CommandError) as context:
            call_command('import_d0010', 'nonexistent_file.txt')
        
        self.assertIn('does not exist', str(context.exception))
    
    def test_import_duplicate_file(self):
        """Test error when importing same file twice."""
        content = """ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|20260415|12345.678|Normal
ZTR|1|20260426|143500"""
        
        file_path = self.create_test_file(content)
        
        try:
            # First import should succeed
            call_command('import_d0010', file_path, stdout=StringIO())
            
            # Second import should fail
            with self.assertRaises(CommandError) as context:
                call_command('import_d0010', file_path, stdout=StringIO())
            
            self.assertIn('already been imported', str(context.exception))
        finally:
            os.unlink(file_path)
    
    def test_skip_duplicates_option(self):
        """Test --skip-duplicates option."""
        content = """ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|20260415|12345.678|Normal
ZTR|1|20260426|143500"""
        
        file_path = self.create_test_file(content)
        
        try:
            # First import
            call_command('import_d0010', file_path, stdout=StringIO())
            
            # Second import with skip flag should not error
            out = StringIO()
            call_command('import_d0010', file_path, skip_duplicates=True, stdout=out)
            
            output = out.getvalue()
            self.assertIn('Skipped', output)
        finally:
            os.unlink(file_path)
    
    def test_import_multiple_files(self):
        """Test importing multiple files at once."""
        content1 = """ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|20260415|12345.678|Normal
ZTR|1|20260426|143500"""
        
        content2 = """ZHD|D0010|20260427|090000|SUPPLIER002|DISTRIBUTOR002
ZPT|9876543210987|MTR67890|20260416|54321.100|Normal
ZTR|1|20260427|090500"""
        
        file1 = self.create_test_file(content1)
        file2 = self.create_test_file(content2)
        
        try:
            out = StringIO()
            call_command('import_d0010', file1, file2, stdout=out)
            
            self.assertEqual(FlowFile.objects.count(), 2)
            self.assertEqual(MeterReading.objects.count(), 2)
            
            output = out.getvalue()
            self.assertIn('2 file(s)', output)
        finally:
            os.unlink(file1)
            os.unlink(file2)
    
    def test_invalid_date_format(self):
        """Test handling of invalid date format."""
        # File with one invalid and one valid row
        content = """ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|2026-04-15|12345.678|Normal
ZPT|9876543210987|MTR67890|20260416|54321.100|Normal
ZTR|2|20260426|143500"""
        
        file_path = self.create_test_file(content)
        
        try:
            out = StringIO()
            call_command('import_d0010', file_path, stdout=out)
            
            # Should skip invalid row with warning but import valid row
            output = out.getvalue()
            self.assertIn('Warning', output)
            
            # Only 1 valid reading should be imported
            self.assertEqual(MeterReading.objects.count(), 1)
            self.assertEqual(
                MeterReading.objects.first().mpan,
                '9876543210987'
            )
        finally:
            os.unlink(file_path)


class AdminTests(TestCase):
    """Tests for the admin interface."""
    
    def setUp(self):
        """Set up test data and admin user."""
        self.site = AdminSite()
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password123'
        )
        
        self.flow_file = FlowFile.objects.create(
            filename='admin_test.txt',
            record_count=2
        )
        
        self.reading1 = MeterReading.objects.create(
            flow_file=self.flow_file,
            mpan='1234567890123',
            meter_serial_number='MTR12345',
            reading_date=date(2026, 4, 15),
            reading_value=Decimal('12345.678'),
            reading_type='Normal'
        )
        
        self.reading2 = MeterReading.objects.create(
            flow_file=self.flow_file,
            mpan='9876543210987',
            meter_serial_number='MTR67890',
            reading_date=date(2026, 4, 16),
            reading_value=Decimal('54321.100'),
            reading_type='Estimate'
        )
    
    def test_flow_file_admin_list_display(self):
        """Test FlowFile admin list display."""
        admin = FlowFileAdmin(FlowFile, self.site)
        
        self.assertIn('filename', admin.list_display)
        self.assertIn('imported_at', admin.list_display)
        self.assertIn('record_count', admin.list_display)
    
    def test_meter_reading_admin_search(self):
        """Test MeterReading admin search functionality."""
        admin = MeterReadingAdmin(MeterReading, self.site)
        
        # Verify search fields include MPAN and serial number
        self.assertIn('mpan', admin.search_fields)
        self.assertIn('meter_serial_number', admin.search_fields)
    
    def test_meter_reading_admin_list_display(self):
        """Test MeterReading admin list display."""
        admin = MeterReadingAdmin(MeterReading, self.site)
        
        expected_fields = [
            'mpan',
            'meter_serial_number',
            'reading_date',
            'reading_value',
            'flow_file_name'
        ]
        
        for field in expected_fields:
            self.assertIn(field, admin.list_display)
    
    def test_flow_file_name_method(self):
        """Test the flow_file_name method in admin."""
        admin = MeterReadingAdmin(MeterReading, self.site)
        
        file_name = admin.flow_file_name(self.reading1)
        self.assertEqual(file_name, 'admin_test.txt')


class IntegrationTests(TestCase):
    """Integration tests for the complete workflow."""
    
    def test_complete_workflow(self):
        """Test the complete workflow from import to query."""
        # Create test file
        content = """ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|20260415|12345.678|Normal
ZPT|1234567890123|MTR12345|20260416|12367.890|Normal
ZPT|9876543210987|MTR67890|20260415|54321.100|Normal
ZTR|3|20260426|143500"""
        
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            delete=False
        )
        temp_file.write(content)
        temp_file.close()
        
        try:
            # Import file
            call_command('import_d0010', temp_file.name, stdout=StringIO())
            
            # Query by MPAN
            readings_by_mpan = MeterReading.objects.filter(
                mpan='1234567890123'
            ).order_by('reading_date')
            
            self.assertEqual(readings_by_mpan.count(), 2)
            self.assertEqual(
                readings_by_mpan.first().reading_value,
                Decimal('12345.678')
            )
            
            # Query by serial number
            readings_by_serial = MeterReading.objects.filter(
                meter_serial_number='MTR67890'
            )
            
            self.assertEqual(readings_by_serial.count(), 1)
            self.assertEqual(
                readings_by_serial.first().mpan,
                '9876543210987'
            )
            
            # Verify source file is tracked
            reading = readings_by_mpan.first()
            self.assertIn('.txt', reading.flow_file.filename)
            
        finally:
            os.unlink(temp_file.name)


class FlowFileUploadFormTests(TestCase):
    """Tests for the file upload form in admin interface."""
    
    def test_form_save_with_commit_false(self):
        """Test Django admin's save(commit=False) and save_m2m() workflow."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from readings.forms import FlowFileUploadForm
        
        content = b"""ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|20260415|12345.678|Normal
ZPT|9876543210987|MTR67890|20260416|54321.100|Normal
ZTR|2|20260426|143500"""
        
        uploaded_file = SimpleUploadedFile(
            'test_commit_false.txt',
            content,
            content_type='text/plain'
        )
        
        form = FlowFileUploadForm(
            data={},
            files={'file_upload': uploaded_file}
        )
        
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Simulate Django admin's workflow
        # Step 1: save(commit=False) returns unsaved instance
        flow_file = form.save(commit=False)
        self.assertIsNone(flow_file.pk)  # Not saved yet
        self.assertTrue(hasattr(flow_file, '_parsed_readings'))  # Has deferred data
        self.assertEqual(flow_file.record_count, 2)
        self.assertIs(form.instance, flow_file)  # form.instance should be the same object
        
        # Step 2: Admin saves the instance
        flow_file.save()
        self.assertIsNotNone(flow_file.pk)  # Now it's saved
        self.assertEqual(MeterReading.objects.count(), 0)  # No readings yet
        
        # Step 3: Admin calls save_m2m() - form.instance should already be correct
        self.assertTrue(hasattr(form.instance, '_parsed_readings'))  # Still has deferred data
        form.save_m2m()
        
        # Verify everything was created
        self.assertEqual(MeterReading.objects.count(), 2)
        self.assertTrue(
            MeterReading.objects.filter(mpan='1234567890123').exists()
        )
        self.assertEqual(flow_file.record_count, 2)
        self.assertFalse(hasattr(flow_file, '_parsed_readings'))  # Cleaned up
    
    def test_valid_file_upload(self):
        """Test uploading a valid D0010 file through the form."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from readings.forms import FlowFileUploadForm
        
        content = b"""ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|20260415|12345.678|Normal
ZPT|9876543210987|MTR67890|20260416|54321.100|Normal
ZTR|2|20260426|143500"""
        
        uploaded_file = SimpleUploadedFile(
            'test_upload.txt',
            content,
            content_type='text/plain'
        )
        
        form = FlowFileUploadForm(
            data={},
            files={'file_upload': uploaded_file}
        )
        
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Save the form
        flow_file = form.save()
        
        # Verify FlowFile was created
        self.assertEqual(flow_file.filename, 'test_upload.txt')
        self.assertEqual(flow_file.record_count, 2)
        self.assertIsNotNone(flow_file.imported_at)
        
        # Verify MeterReadings were created
        self.assertEqual(MeterReading.objects.count(), 2)
        self.assertTrue(
            MeterReading.objects.filter(mpan='1234567890123').exists()
        )
    
    def test_duplicate_filename_rejected(self):
        """Test that uploading a file with existing filename is rejected."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from readings.forms import FlowFileUploadForm
        
        # Create existing FlowFile
        FlowFile.objects.create(filename='duplicate.txt')
        
        content = b"""ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|20260415|12345.678|Normal
ZTR|1|20260426|143500"""
        
        uploaded_file = SimpleUploadedFile(
            'duplicate.txt',
            content,
            content_type='text/plain'
        )
        
        form = FlowFileUploadForm(
            data={},
            files={'file_upload': uploaded_file}
        )
        
        self.assertFalse(form.is_valid())
        self.assertIn('already been imported', str(form.errors))
    
    def test_empty_file_rejected(self):
        """Test that empty files are rejected."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from readings.forms import FlowFileUploadForm
        
        uploaded_file = SimpleUploadedFile(
            'empty.txt',
            b'',
            content_type='text/plain'
        )
        
        form = FlowFileUploadForm(
            data={},
            files={'file_upload': uploaded_file}
        )
        
        self.assertFalse(form.is_valid())
        # Django's FileField validation catches empty files
        self.assertTrue(
            'empty' in str(form.errors).lower() or 
            'no valid meter readings' in str(form.errors).lower()
        )
    
    def test_invalid_format_rejected(self):
        """Test that files with invalid format are rejected."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from readings.forms import FlowFileUploadForm
        
        # File with no valid ZPT rows
        content = b"""ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
INVALID|DATA|HERE
ZTR|0|20260426|143500"""
        
        uploaded_file = SimpleUploadedFile(
            'invalid.txt',
            content,
            content_type='text/plain'
        )
        
        form = FlowFileUploadForm(
            data={},
            files={'file_upload': uploaded_file}
        )
        
        self.assertFalse(form.is_valid())
        self.assertIn('No valid meter readings', str(form.errors))
    
    def test_partial_invalid_data_handled(self):
        """Test that files with some invalid rows still import valid rows."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from readings.forms import FlowFileUploadForm
        
        # File with one invalid and one valid row
        content = b"""ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|BADDATE|12345.678|Normal
ZPT|9876543210987|MTR67890|20260416|54321.100|Normal
ZTR|2|20260426|143500"""
        
        uploaded_file = SimpleUploadedFile(
            'partial_valid.txt',
            content,
            content_type='text/plain'
        )
        
        form = FlowFileUploadForm(
            data={},
            files={'file_upload': uploaded_file}
        )
        
        # Form should be valid but have warnings
        self.assertTrue(form.is_valid())
        
        # Save and check only valid row was imported
        flow_file = form.save()
        self.assertEqual(flow_file.record_count, 1)
        self.assertEqual(MeterReading.objects.count(), 1)
        self.assertEqual(
            MeterReading.objects.first().mpan,
            '9876543210987'
        )
    
    def test_flo_file_extension_accepted(self):
        """Test that .flo file extension is accepted."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from readings.forms import FlowFileUploadForm
        
        content = b"""ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|20260415|12345.678|Normal
ZPT|9876543210987|MTR67890|20260416|54321.100|Normal
ZTR|2|20260426|143500"""
        
        uploaded_file = SimpleUploadedFile(
            'test_file.flo',
            content,
            content_type='application/octet-stream'
        )
        
        form = FlowFileUploadForm(
            data={},
            files={'file_upload': uploaded_file}
        )
        
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Save the form
        flow_file = form.save()
        
        # Verify FlowFile was created with .flo extension
        self.assertEqual(flow_file.filename, 'test_file.flo')
        self.assertEqual(flow_file.record_count, 2)
        
        # Verify MeterReadings were created
        self.assertEqual(MeterReading.objects.count(), 2)
    
    def test_invalid_file_extension_rejected(self):
        """Test that invalid file extensions are rejected."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from readings.forms import FlowFileUploadForm
        
        content = b"""ZHD|D0010|20260426|143000|SUPPLIER001|DISTRIBUTOR001
ZPT|1234567890123|MTR12345|20260415|12345.678|Normal
ZTR|1|20260426|143500"""
        
        # Try with .csv extension
        uploaded_file = SimpleUploadedFile(
            'test_file.csv',
            content,
            content_type='text/csv'
        )
        
        form = FlowFileUploadForm(
            data={},
            files={'file_upload': uploaded_file}
        )
        
        self.assertFalse(form.is_valid())
        self.assertIn('Invalid file type', str(form.errors))
        self.assertIn('.csv', str(form.errors))
    
    def test_grouped_format_parsing(self):
        """Test that grouped format (026/028/030) is correctly parsed."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from readings.forms import FlowFileUploadForm
        
        # Grouped format with multiple readings per meter
        content = b"""ZHV|0000475656|D0010002|D|UDMS|X|MRCY|20160302153151||||OPER|
026|1200023305967|V|
028|F75A00802|D|
030|S|20160222000000|56311.0|||T|N|
026|1900001059816|V|
028|S95105287|C|
030|TO|20160224000000|81641.0|||T|N|
030|DY|20160225000000|82000.0|||T|N|
ZPT|0000475656|7||7|20160302154650|"""
        
        uploaded_file = SimpleUploadedFile(
            'grouped_format.flo',
            content,
            content_type='application/octet-stream'
        )
        
        form = FlowFileUploadForm(
            data={},
            files={'file_upload': uploaded_file}
        )
        
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Save the form
        flow_file = form.save()
        
        # Verify FlowFile was created
        self.assertEqual(flow_file.filename, 'grouped_format.flo')
        self.assertEqual(flow_file.record_count, 3)
        
        # Verify MeterReadings were created
        self.assertEqual(MeterReading.objects.count(), 3)
        
        # Verify first meter's reading
        first_reading = MeterReading.objects.filter(mpan='1200023305967').first()
        self.assertIsNotNone(first_reading)
        self.assertEqual(first_reading.meter_serial_number, 'F75A00802')
        self.assertEqual(first_reading.reading_value, Decimal('56311.0'))
        
        # Verify second meter has 2 readings
        second_meter_readings = MeterReading.objects.filter(mpan='1900001059816')
        self.assertEqual(second_meter_readings.count(), 2)
        self.assertEqual(second_meter_readings.first().meter_serial_number, 'S95105287')


class HealthAPITests(TestCase):
    """Tests for the health API endpoint."""
    
    def test_health_get_request(self):
        """Test GET request to /api/health/ returns 200 with 'health' status."""
        response = self.client.get('/api/health/')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        data = response.json()
        self.assertEqual(data['status'], 'health')
    
    def test_health_post_request_with_data(self):
        """Test POST request to /api/health/ with JSON data."""
        test_data = {'test_key': 'test_value'}
        
        response = self.client.post(
            '/api/health/',
            data=test_data,
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        data = response.json()
        self.assertEqual(data['status'], 200)
        self.assertIn('test_key', data['message'])
        self.assertEqual(data['message'], 'Data test_key was successfully received')
    
    def test_health_post_request_with_multiple_keys(self):
        """Test POST request with multiple keys returns first key."""
        test_data = {'first_key': 'value1', 'second_key': 'value2'}
        
        response = self.client.post(
            '/api/health/',
            data=test_data,
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('first_key', data['message'])
    
    def test_health_post_request_empty_data(self):
        """Test POST request with empty JSON returns 400."""
        response = self.client.post(
            '/api/health/',
            data={},
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['status'], 400)
        self.assertIn('No data provided', data['message'])
    
    def test_health_post_request_invalid_json(self):
        """Test POST request with invalid JSON returns 400."""
        response = self.client.post(
            '/api/health/',
            data='invalid json',
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['status'], 400)
        self.assertIn('Invalid JSON', data['message'])

