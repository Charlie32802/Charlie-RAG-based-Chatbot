from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from datetime import timedelta

class Document(models.Model):
    """Stores uploaded documents for RAG"""
    
    CATEGORY_CHOICES = [
        ('government', 'Government'),
        ('biography', 'Biography'),
        ('programs', 'Programs'),
        ('projects', 'Projects'),
        ('tourism', 'Tourism'),
        ('events', 'Events'),
        ('history', 'History'),
        ('announcements', 'Announcements'),
    ]
    
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True, help_text="Brief description of the document content")
    file = models.FileField(
        upload_to='documents/%Y/%m/',
        validators=[FileExtensionValidator(['pdf', 'docx', 'txt'])],
        help_text="Supported formats: PDF, DOCX, TXT"
    )
    uploaded_by = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=[('draft', 'Draft'), ('published', 'Published')],
        default='draft'
    )
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    chunk_count = models.IntegerField(default=0)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Document"
        verbose_name_plural = "Documents"


class ConversationSession(models.Model):
    """Tracks conversation sessions"""
    
    session_key = models.CharField(max_length=100, unique=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    message_count = models.IntegerField(default=0)

    def __str__(self):
        return f"Session {self.session_key[:8]}... ({self.message_count} messages)"

    class Meta:
        ordering = ['-last_activity']
        verbose_name = "Conversation Session"
        verbose_name_plural = "Conversation Sessions"

    @classmethod
    def cleanup_old_sessions(cls):
        cutoff = timezone.now() - timedelta(days=1)
        old_sessions = cls.objects.filter(last_activity__lt=cutoff)
        count = old_sessions.count()
        old_sessions.delete()
        return count


class ConversationMessage(models.Model):
    """Stores individual messages in a conversation"""
    
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]

    session = models.ForeignKey(ConversationSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    categories_searched = models.CharField(max_length=200, blank=True)
    chunks_retrieved = models.IntegerField(default=0)
    context_topics = models.TextField(blank=True)

    def __str__(self):
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.role}: {preview}"

    class Meta:
        ordering = ['timestamp']
        verbose_name = "Conversation Message"
        verbose_name_plural = "Conversation Messages"


class TrackedDocument(models.Model):
    """Local copy of the remote documenttracker MySQL table"""

    pdid = models.AutoField(primary_key=True)
    slug = models.CharField(max_length=300, unique=True)
    title = models.CharField(max_length=255, blank=True)
    agency = models.CharField(max_length=255, blank=True)
    office = models.CharField(max_length=255, blank=True)
    subject = models.TextField(blank=True)
    file_type = models.CharField(max_length=50, blank=True, default='n/a')
    is_public = models.BooleanField(default=True)
    created_at = models.CharField(max_length=50, blank=True)
    created_by = models.CharField(max_length=100, blank=True)
    validated_at = models.CharField(max_length=100, blank=True)
    validated_by = models.CharField(max_length=100, blank=True)
    document_type = models.CharField(max_length=100, blank=True)
    user_retention = models.CharField(max_length=200, blank=True)
    office_retention = models.CharField(max_length=200, blank=True)
    overall_days_onprocess = models.CharField(max_length=200, blank=True)
    document_completed_status = models.BooleanField(default=False)
    details = models.JSONField(default=dict, blank=True)
    created_timestamp = models.DateTimeField(null=True, blank=True)
    updated_timestamp = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"[PDID {self.pdid}] {self.title} — {self.office}"

    def get_current_location(self):
        try:
            routes = self.details.get('routes', [])
            if routes:
                return routes[-1].get('office', 'Unknown')
        except Exception:
            pass
        return 'Unknown'

    def get_last_action(self):
        try:
            routes = self.details.get('routes', [])
            if routes:
                employees = routes[-1].get('staff_operation', {}).get('employee', [])
                if employees:
                    processes = employees[-1].get('processing', {}).get('process', [])
                    if processes:
                        return processes[-1].get('action', '')
        except Exception:
            pass
        return ''

    class Meta:
        ordering = ['-updated_timestamp']
        verbose_name = "Tracked Document"
        verbose_name_plural = "Tracked Documents"