from django.core.management.base import BaseCommand
from learning_logs.models import Attachment
import os

class Command(BaseCommand):
    help = "List Attachment records whose underlying file is missing on disk."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=200, help='Max lines to print for missing list (default 200)')

    def handle(self, *args, **opts):
        total = Attachment.objects.count()
        missing = []
        for att in Attachment.objects.iterator():
            try:
                path = att.file.path
            except Exception:
                path = ''
            if not path or not os.path.exists(path):
                missing.append((att.id, getattr(att, 'original_name', ''), getattr(att, 'relative_path', ''), path))
        self.stdout.write(f'Total attachments: {total}')
        self.stdout.write(f'Missing files: {len(missing)}')
        limit = int(opts.get('limit') or 200)
        for i, (aid, name, rel, p) in enumerate(missing[:limit], 1):
            self.stdout.write(f'{i:04d}. id={aid} name={name} rel={rel} path={p}')
        if len(missing) > limit:
            self.stdout.write(f"... {len(missing)-limit} more")
