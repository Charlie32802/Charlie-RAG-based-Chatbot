from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from charlie import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/chat-stream/', views.chat_stream_api, name='chat_stream_api'),
    path('api/load-history/', views.load_history_api, name='load_history_api'),
    path('api/delete-conversation/', views.delete_conversation_api, name='delete_conversation_api'),
    path('api/edit-message/',  views.edit_message_api,         name='edit_message'),
    path('api/regenerate/',    views.regenerate_response_api,  name='regenerate_response'),
    path('api/save-partial/', views.save_partial_bot_message_api, name='save_partial'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)