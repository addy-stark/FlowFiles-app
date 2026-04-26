import logging
from django.contrib import admin
from django.db.models import Count
from .models import FlowFile, MeterReading
from .forms import FlowFileUploadForm

logger = logging.getLogger(__name__)


@admin.register(FlowFile)
class FlowFileAdmin(admin.ModelAdmin):
    # What to show in the list view
    list_display = ['filename', 'imported_at', 'record_count', 'readings_count']
    list_filter = ['imported_at']
    search_fields = ['filename']
    readonly_fields = ['filename', 'imported_at', 'record_count']
    date_hierarchy = 'imported_at'
    actions = ['delete_selected']
    
    def get_actions(self, request):
        # Only show delete action
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            return {'delete_selected': actions['delete_selected']}
        return {}
    
    def get_form(self, request, obj=None, **kwargs):
        # New files: show upload form. Existing files: show readonly fields
        if obj is None:
            kwargs['form'] = FlowFileUploadForm
        return super().get_form(request, obj, **kwargs)
    
    def get_fields(self, request, obj=None):
        # New files: show upload field. Existing files: show info fields
        if obj is None:
            return ['file_upload']
        return ['filename', 'imported_at', 'record_count']
    
    def has_change_permission(self, request, obj=None):
        # Prevent editing existing files (they're read-only once imported)
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)
    
    def get_queryset(self, request):
        # Add readings count to avoid extra database queries
        queryset = super().get_queryset(request)
        return queryset.annotate(_readings_count=Count('readings'))
    
    def readings_count(self, obj):
        # Show how many readings this file has
        return obj._readings_count
    readings_count.short_description = 'Readings Count'
    readings_count.admin_order_field = '_readings_count'


@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    # What to show in the list view
    list_display = [
        'mpan', 
        'meter_serial_number', 
        'reading_date', 
        'reading_value', 
        'reading_type',
        'flow_file_name',
        'created_at'
    ]
    list_filter = ['reading_date', 'reading_type', 'flow_file__filename', 'created_at']
    search_fields = ['mpan', 'meter_serial_number', 'flow_file__filename']
    date_hierarchy = 'reading_date'
    readonly_fields = ['created_at']
    actions = ['delete_selected']
    list_select_related = ['flow_file']  # Avoid extra database queries
    
    def get_actions(self, request):
        # Only show delete action
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            return {'delete_selected': actions['delete_selected']}
        return {}
    
    # Group fields in the detail view
    fieldsets = (
        ('Meter Information', {
            'fields': ('mpan', 'meter_serial_number')
        }),
        ('Reading Data', {
            'fields': ('reading_date', 'reading_value', 'reading_type')
        }),
        ('Source Information', {
            'fields': ('flow_file', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def flow_file_name(self, obj):
        # Show which file this reading came from
        return obj.flow_file.filename
    flow_file_name.short_description = 'Source File'
    flow_file_name.admin_order_field = 'flow_file__filename'


# Customize admin site titles
admin.site.site_header = 'FlowFiles Administration'
admin.site.site_title = 'FlowFiles Admin'
admin.site.index_title = 'Meter Reading Management'
