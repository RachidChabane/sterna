from django.contrib import admin
from .models import Spark, SparkDeployment, App


@admin.register(Spark)
class SparkAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'framework', 'version', 'storage_type', 'created_at']
    list_filter = ['framework', 'storage_type', 'created_at']
    search_fields = ['title', 'description', 'user__email']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['user', 'chat', 'message', 'parent']

    fieldsets = [
        (None, {
            'fields': ['id', 'user', 'title', 'description', 'framework']
        }),
        ('Associations', {
            'fields': ['chat', 'message'],
            'classes': ['collapse']
        }),
        ('Storage', {
            'fields': ['storage_type', 'code', 'r2_bucket', 'r2_key']
        }),
        ('Versioning', {
            'fields': ['version', 'parent']
        }),
        ('Metadata', {
            'fields': ['dependencies', 'preview_url', 'created_at', 'updated_at']
        }),
    ]


@admin.register(SparkDeployment)
class SparkDeploymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'spark', 'user', 'status', 'preview_url', 'cost_usd', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['spark__title', 'user__email', 'deployment_id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['spark', 'user']


@admin.register(App)
class AppAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'spark', 'version', 'project_path', 'created_at']
    list_filter = ['user', 'created_at']
    search_fields = ['title', 'user__email', 'spark__title']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['user', 'spark', 'chat']
