"""Defines URL patterns for learning_logs."""

from django.urls import path

from . import views

app_name = 'learning_logs'
urlpatterns = [
    # Home page
    path('', views.index, name='index'),
    # Page that shows all topics.
    path('topics/', views.topics, name='topics'),
    # Delete a topic (owner only) - define before detail route to avoid path catch-all
    path('topics/<path:topic_name>/delete/', views.delete_topic, name='delete_topic'),
    # Detail page for a single topic by name
    path('topics/<path:topic_name>/', views.topic, name='topic'),
    # Discovery view: URL used from "发现" for browsing a topic (read-only, no edit button)
    path('discovey/<path:topic_name>/', views.discovey, name='discovey'),
    # Page for adding a new topic.
    path('new_topic/', views.new_topic, name='new_topic'),
    # Page for adding a new entry.
    path('new_entry/<int:topic_id>/', views.new_entry, name='new_entry'),
    # Page for editing an entry.
    path('edit_entry/<int:entry_id>/', views.edit_entry, name='edit_entry'),
    # Delete an entry (owner only)
    path('entries/<int:entry_id>/delete/', views.delete_entry, name='delete_entry'),
    # Add a comment to a public entry.
    path('add_comment/<int:entry_id>/', views.add_comment, name='add_comment'),
    # Attachment preview
    path('attachments/preview/<int:attachment_id>/', views.preview_attachment, name='preview_attachment'),
    # Attachment downloads
    path('attachments/download/<int:attachment_id>/', views.download_attachment, name='download_attachment'),
    path('attachments/download_folder/', views.download_folder, name='download_folder'),
    # Attachment APIs
    path('attachments/delete/<int:attachment_id>/', views.delete_attachment, name='delete_attachment'),
    path('attachments/upload/', views.upload_attachments_api, name='upload_attachments_api'),
    path('attachments/delete_folder/', views.delete_folder_api, name='delete_folder_api'),
]