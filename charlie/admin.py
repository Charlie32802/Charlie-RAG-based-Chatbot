from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from .models import Document, ConversationSession, ConversationMessage
from .rag_utils import add_document_to_chromadb, delete_document_from_chromadb
import os
import logging

logger = logging.getLogger(__name__)


def cleanup_empty_directories(path):
    """
    Remove empty directories after file deletion
    Stops at media/documents/ to preserve Django's media structure
    """
    try:
        from django.conf import settings
        
        # Normalize paths for accurate comparison (especially on Windows)
        media_root = os.path.normpath(os.path.abspath(str(settings.MEDIA_ROOT)))
        documents_dir = os.path.normpath(os.path.join(media_root, 'documents'))
        
        # Only clean up directories inside media/documents/
        # Don't delete media/ or media/documents/ themselves
        while path and os.path.isdir(path) and not os.listdir(path):
            # Normalize current path for comparison
            current_path = os.path.normpath(os.path.abspath(path))
            
            # Stop if we've reached media/documents/ or higher
            if current_path == documents_dir or current_path == media_root:
                break
            
            os.rmdir(path)
            logger.info(f"[OK] Removed empty directory: {path}")
            path = os.path.dirname(path)
            
    except Exception as e:
        logger.warning(f"Could not remove empty directory: {e}")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        'title', 
        'category', 
        'status', 
        'processed_status',
        'chunk_count',
        'created_at',
        'process_button'
    ]
    list_filter = ['category', 'status', 'processed', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['processed', 'processed_at', 'chunk_count', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Document Information', {
            'fields': ('title', 'category', 'description', 'file')
        }),
        ('Metadata', {
            'fields': ('uploaded_by', 'status')
        }),
        ('Processing Status', {
            'fields': ('processed', 'processed_at', 'chunk_count', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['process_documents', 'reprocess_documents', 'mark_as_published']
    
    def processed_status(self, obj):
        """Display processing status with color"""
        if obj.processed:
            return mark_safe('<span style="color: green;">✓ Processed</span>')
        return mark_safe('<span style="color: orange;">⚠ Not Processed</span>')
    processed_status.short_description = 'Processing Status'
    
    def process_button(self, obj):
        """Add process button for each document"""
        if obj.processed:
            return format_html(
                '<a class="button default" href="{}" style="padding: 5px 10px; text-decoration: none; white-space: nowrap; display: inline-block;">Reprocess</a>',
                f'/admin/charlie/document/{obj.pk}/process/'
            )
        return format_html(
            '<a class="button default" href="{}" style="padding: 5px 10px; text-decoration: none; white-space: nowrap; display: inline-block;">Process Now</a>',
            f'/admin/charlie/document/{obj.pk}/process/'
        )
    process_button.short_description = 'Actions'
    
    def _delete_document_completely(self, obj):
        """
        Helper method: Delete document from ChromaDB and filesystem
        Used by both delete_model and delete_queryset
        """
        try:
            # Delete from ChromaDB
            delete_document_from_chromadb(obj.id)
            
            # Delete physical file
            if obj.file and os.path.isfile(obj.file.path):
                file_path = obj.file.path
                file_dir = os.path.dirname(file_path)
                os.remove(file_path)
                logger.info(f"[OK] Deleted file: {file_path}")
                
                # Cleanup empty directories
                cleanup_empty_directories(file_dir)
                
            return True
        except Exception as e:
            logger.error(f"Error deleting '{obj.title}': {e}")
            return False
    
    def process_documents(self, request, queryset):
        """Bulk action to process selected documents"""
        success_count = 0
        error_count = 0
        
        for document in queryset:
            try:
                if not document.processed or document.status == 'draft':
                    result = add_document_to_chromadb(document)
                    if result:
                        document.processed = True
                        document.processed_at = timezone.now()
                        document.chunk_count = result
                        document.save()
                        success_count += 1
                    else:
                        error_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"Error processing '{document.title}': {str(e)}",
                    level=messages.ERROR
                )
                error_count += 1
        
        if success_count > 0:
            self.message_user(request, f"Successfully processed {success_count} document(s).", level=messages.SUCCESS)
        if error_count > 0:
            self.message_user(request, f"Failed to process {error_count} document(s).", level=messages.ERROR)
    
    process_documents.short_description = "Process selected documents into ChromaDB"
    
    def reprocess_documents(self, request, queryset):
        """Bulk action to reprocess documents"""
        success_count = 0
        error_count = 0
        
        for document in queryset:
            try:
                delete_document_from_chromadb(document.id)
                result = add_document_to_chromadb(document)
                if result:
                    document.processed = True
                    document.processed_at = timezone.now()
                    document.chunk_count = result
                    document.save()
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"Error reprocessing '{document.title}': {str(e)}",
                    level=messages.ERROR
                )
                error_count += 1
        
        if success_count > 0:
            self.message_user(request, f"Successfully reprocessed {success_count} document(s).", level=messages.SUCCESS)
        if error_count > 0:
            self.message_user(request, f"Failed to reprocess {error_count} document(s).", level=messages.ERROR)
    
    reprocess_documents.short_description = "Reprocess selected documents (delete & re-add to ChromaDB)"
    
    def mark_as_published(self, request, queryset):
        """Mark selected documents as published"""
        updated = queryset.update(status='published')
        self.message_user(request, f"Successfully marked {updated} document(s) as published.", level=messages.SUCCESS)
    mark_as_published.short_description = "Mark as Published"
    
    def get_urls(self):
        """Add custom URL for processing individual documents"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:document_id>/process/',
                self.admin_site.admin_view(self.process_document_view),
                name='charlie_document_process',
            ),
        ]
        return custom_urls + urls
    
    def process_document_view(self, request, document_id):
        """View to process a single document"""
        try:
            document = Document.objects.get(pk=document_id)
            
            if document.processed:
                delete_document_from_chromadb(document.id)
            
            result = add_document_to_chromadb(document)
            
            if result:
                document.processed = True
                document.processed_at = timezone.now()
                document.chunk_count = result
                document.save()
                
                self.message_user(
                    request,
                    f"Successfully processed '{document.title}' into ChromaDB ({result} chunks created).",
                    level=messages.SUCCESS
                )
            else:
                self.message_user(request, f"Failed to process '{document.title}'.", level=messages.ERROR)
        except Document.DoesNotExist:
            self.message_user(request, "Document not found.", level=messages.ERROR)
        except Exception as e:
            self.message_user(request, f"Error processing document: {str(e)}", level=messages.ERROR)
        
        return redirect('admin:charlie_document_changelist')
    
    def delete_model(self, request, obj):
        """Delete document from ChromaDB and filesystem"""
        if not self._delete_document_completely(obj):
            self.message_user(
                request,
                f"Error deleting '{obj.title}' from ChromaDB/filesystem",
                level=messages.WARNING
            )
        super().delete_model(request, obj)
    
    def delete_queryset(self, request, queryset):
        """Delete documents from ChromaDB and filesystem (bulk deletion)"""
        for obj in queryset:
            if not self._delete_document_completely(obj):
                self.message_user(
                    request,
                    f"Error deleting '{obj.title}' from ChromaDB/filesystem",
                    level=messages.WARNING
                )
        super().delete_queryset(request, queryset)


@admin.register(ConversationSession)
class ConversationSessionAdmin(admin.ModelAdmin):
    list_display = ['session_key_short', 'started_at', 'last_activity', 'message_count']
    list_filter = ['started_at', 'last_activity']
    search_fields = ['session_key']
    readonly_fields = ['session_key', 'started_at', 'last_activity', 'message_count']
    
    def session_key_short(self, obj):
        return f"{obj.session_key[:20]}..."
    session_key_short.short_description = 'Session Key'
    
    def has_add_permission(self, request):
        return False


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = ['session_short', 'role', 'content_preview', 'timestamp', 'categories_searched']
    list_filter = ['role', 'timestamp', 'categories_searched']
    search_fields = ['content', 'context_topics']
    readonly_fields = ['session', 'role', 'content', 'timestamp', 'categories_searched', 'chunks_retrieved', 'context_topics']
    
    def session_short(self, obj):
        return f"{obj.session.session_key[:10]}..."
    session_short.short_description = 'Session'
    
    def content_preview(self, obj):
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'
    
    def has_add_permission(self, request):
        return False