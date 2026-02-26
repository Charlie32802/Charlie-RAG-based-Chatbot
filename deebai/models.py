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
    
    # Basic info
    title = models.CharField(max_length=200)
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description of the document content"
    )
    
    # File
    file = models.FileField(
        upload_to='documents/%Y/%m/',
        validators=[FileExtensionValidator(['pdf', 'docx', 'txt'])],
        help_text="Supported formats: PDF, DOCX, TXT"
    )
    
    # Metadata
    uploaded_by = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=[
            ('draft', 'Draft'),
            ('published', 'Published'),
        ],
        default='draft'
    )
    
    # Processing status
    processed = models.BooleanField(
        default=False,
        help_text="Whether this document has been processed and added to ChromaDB"
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the document was last processed"
    )
    chunk_count = models.IntegerField(
        default=0,
        help_text="Number of text chunks created from this document"
    )
    
    def __str__(self):
        return self.title
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Document"
        verbose_name_plural = "Documents"


class ConversationSession(models.Model):
    """Tracks conversation sessions"""
    
    session_key = models.CharField(
        max_length=100,
        unique=True,
        help_text="Django session key"
    )
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
        """Delete sessions older than 1 day"""
        cutoff = timezone.now() - timedelta(days=1)
        old_sessions = cls.objects.filter(last_activity__lt=cutoff)
        count = old_sessions.count()
        old_sessions.delete()
        return count


class ConversationMessage(models.Model):
    """Stores individual messages in a conversation"""
    
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    session = models.ForeignKey(
        ConversationSession,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # RAG metadata
    categories_searched = models.CharField(
        max_length=200,
        blank=True,
        help_text="Categories searched (e.g., 'government,tourism')"
    )
    chunks_retrieved = models.IntegerField(
        default=0,
        help_text="Number of RAG chunks retrieved"
    )
    context_topics = models.TextField(
        blank=True,
        help_text="AI-generated summary of topics discussed"
    )
    
    def __str__(self):
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.role}: {preview}"
    
    class Meta:
        ordering = ['timestamp']
        verbose_name = "Conversation Message"
        verbose_name_plural = "Conversation Messages"