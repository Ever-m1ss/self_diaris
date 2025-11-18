from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
import json


class AttachmentUploadTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='tester', password='test')
        self.client.login(username='tester', password='test')
        from .models import Topic
        self.topic = Topic.objects.create(owner=self.user, text='t')

    def test_upload_api_preserve_relative_path(self):
        content = b'testdata'
        f = SimpleUploadedFile('file.txt', content)
        rel_path = 'folder1/folder2/file.txt'
        rp_json = json.dumps([{"name": 'file.txt', "size": len(content), "path": rel_path}])
        resp = self.client.post(reverse('learning_logs:upload_attachments_api'), {'parent_type': 'topic', 'parent_id': self.topic.id, 'relative_paths_json': rp_json}, files={'files': f})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['files'][0].get('relative_path'), rel_path)

    def test_upload_and_reassign_to_new_entry_preserves_path(self):
        from .models import Attachment
        content = b'hello'
        f = SimpleUploadedFile('hello.txt', content)
        rel_path = 'a/b/hello.txt'
        rp_json = json.dumps([{"name": 'hello.txt', "size": len(content), "path": rel_path}])
        upload_session = 'sess12345'
        resp = self.client.post(reverse('learning_logs:upload_attachments_api'), {'parent_type': 'topic', 'parent_id': self.topic.id, 'relative_paths_json': rp_json, 'upload_session': upload_session}, files={'files': f})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('ok'))
        att_id = data['files'][0]['id']
        att = Attachment.objects.get(id=att_id)
        self.assertEqual(att.relative_path, rel_path)
        # Create new entry and reassign
        resp2 = self.client.post(reverse('learning_logs:new_entry', kwargs={'topic_id': self.topic.id}), {'title': 'a', 'text': '', 'upload_session': upload_session})
        self.assertIn(resp2.status_code, (302, 301))
        att.refresh_from_db()
        self.assertIsNotNone(att.entry)
        self.assertEqual(att.relative_path, rel_path)
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import Topic, Entry, Attachment
from django.core.files.uploadedfile import SimpleUploadedFile


class LearningLogsTests(TestCase):
	def test_new_entry_with_async_topic_upload_reassigns_to_entry(self):
		# Create user and topic
		User = get_user_model()
		user = User.objects.create_user(username='tuser', password='pass')
		topic = Topic.objects.create(owner=user, text='MyTopic')
		self.client.login(username='tuser', password='pass')

		# upload an attachment asynchronously to the topic (simulate upload_attachments_api)
		file_content = b'Hello, world'
		file = SimpleUploadedFile('hello.txt', file_content, content_type='text/plain')
		upload_session_key = 'testsession123'
		resp = self.client.post(reverse('learning_logs:upload_attachments_api'), {'parent_type': 'topic', 'parent_id': topic.id, 'upload_session': upload_session_key}, files={'files': file})
		self.assertIn(resp.status_code, (200, 201))
		data = resp.json()
		self.assertTrue(data.get('ok'))
		self.assertTrue(len(data.get('files', [])) >= 1)
		att_id = data['files'][0]['id']
		att = Attachment.objects.get(id=att_id)
		self.assertEqual(att.topic, topic)
		self.assertIsNone(att.entry)

		# Now create a new entry with upload_session and ensure the attachment is reassigned
		form_data = {
			'title': 'entry title',
			'text': '',
			'upload_session': upload_session_key,
		}
		resp = self.client.post(reverse('learning_logs:new_entry', kwargs={'topic_id': topic.id}), data=form_data)
		# Should redirect
		self.assertIn(resp.status_code, (302, 301))
		# Reload attachment
		att.refresh_from_db()
		self.assertIsNotNone(att.entry)
		self.assertEqual(att.entry.topic, topic)

