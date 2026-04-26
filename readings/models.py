from django.db import models
from django.utils import timezone


class FlowFile(models.Model):
    # Tracks imported D0010 flow files
    filename = models.CharField(max_length=255, unique=True, help_text="Name of the imported file")
    imported_at = models.DateTimeField(default=timezone.now, help_text="When the file was imported")
    record_count = models.IntegerField(default=0, help_text="Number of readings imported")
    
    class Meta:
        ordering = ['-imported_at']
        verbose_name = 'Flow File'
        verbose_name_plural = 'Flow Files'
    
    def __str__(self):
        return f"{self.filename} ({self.imported_at.strftime('%Y-%m-%d %H:%M')})"


class MeterReading(models.Model):
    # Single meter reading from a D0010 file
    flow_file = models.ForeignKey(
        FlowFile, 
        on_delete=models.CASCADE, 
        related_name='readings',
        help_text="Source file for this reading"
    )
    mpan = models.CharField(
        max_length=13, 
        db_index=True,
        help_text="Meter Point Administration Number (13 digits)"
    )
    meter_serial_number = models.CharField(
        max_length=50, 
        db_index=True,
        help_text="Meter serial number"
    )
    reading_value = models.DecimalField(
        max_digits=12, 
        decimal_places=3,
        help_text="Meter reading value"
    )
    reading_date = models.DateField(
        db_index=True,
        help_text="Date of the reading"
    )
    reading_type = models.CharField(
        max_length=10,
        blank=True,
        help_text="Type of reading (e.g., Normal, Estimate)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-reading_date', 'mpan']
        verbose_name = 'Meter Reading'
        verbose_name_plural = 'Meter Readings'
        indexes = [
            models.Index(fields=['mpan', 'reading_date']),
            models.Index(fields=['meter_serial_number', 'reading_date']),
        ]
    
    def __str__(self):
        return f"MPAN {self.mpan} - {self.reading_date} - {self.reading_value}"
