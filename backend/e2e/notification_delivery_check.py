"""Repeatable HTTP/SQLite/SMTP check. Uses disposable state and a local mail sink.

Failure cases: pending, sent and error records appear over HTTP, including manual,
test and recovery emails. Partial refusal or log-storage failure never resends mail
that was already accepted.
"""
import argparse
import json
import socketserver
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import scheduling
from backend.models import NotificationLogEntry, ScheduledExperiment, NotificationContact
from backend.services.auth import get_current_user
from backend.services.notifications import EmailNotificationService, EmailConfig
from backend.services.notifications import SchedulingNotificationService, ScheduleAlertResult
from backend.services.scheduling.scheduler_engine import SchedulerEngine
from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase


class MailSink(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b'220 local fixture\r\n')
        data = False
        while line := self.rfile.readline():
            if data:
                if line == b'.\r\n':
                    self.server.entered.set()
                    self.server.release.wait(5)
                    self.server.messages += 1
                    self.wfile.write(b'250 accepted\r\n')
                    data = False
                continue
            command = line.upper()
            if command.startswith(b'EHLO'):
                self.wfile.write(b'250-local fixture\r\n250 AUTH PLAIN\r\n')
            elif command.startswith(b'AUTH'):
                self.wfile.write(b'235 authenticated\r\n')
            elif command.startswith(b'RCPT') and (self.server.mode == 'error' or (self.server.mode == 'partial' and b'REFUSED' in command)):
                self.wfile.write(b'550 recipient refused\r\n')
            elif command.startswith(b'DATA'):
                self.wfile.write(b'354 end with dot\r\n')
                data = True
            elif command.startswith(b'QUIT'):
                self.wfile.write(b'221 bye\r\n')
                return
            else:
                self.wfile.write(b'250 OK\r\n')


def run(baseline=False):
    results = []
    with tempfile.TemporaryDirectory(prefix='rc-mail-') as folder, socketserver.ThreadingTCPServer(('127.0.0.1', 0), MailSink) as smtp:
        smtp.mode, smtp.messages = 'sent', 0
        smtp.entered, smtp.release = threading.Event(), threading.Event()
        smtp.release.set()
        threading.Thread(target=smtp.serve_forever, daemon=True).start()
        db = SQLiteSchedulingDatabase(str(Path(folder)/'schedule.db'))
        schedule = ScheduledExperiment('fixture', 'Fixture', 'fixture.med', 'once', notification_contacts=['contact'])
        contact = NotificationContact('contact', 'Fixture', 'accepted@example.com')
        manager = SimpleNamespace(get_schedule_by_id=lambda key: schedule, get_notification_contacts=lambda **kw: [contact],
            create_notification_log=db.create_notification_log, update_notification_log=db.update_notification_log,
            get_notification_logs=db.get_notification_logs)
        def email():
            service = EmailNotificationService.__new__(EmailNotificationService)
            service.config = EmailConfig('127.0.0.1', smtp.server_address[1], 'fixture', 'fixture', 'sender@example.com', [], [], False, False)
            service.last_error = service._settings_error = None
            service._smtp_timeout, service._smtp_retries, service._smtp_retry_delay = 3, 1, 0
            return service
        app = FastAPI()
        app.include_router(scheduling.router)
        app.dependency_overrides[get_current_user] = lambda: {'username': 'fixture', 'role': 'admin'}
        with patch.object(scheduling, 'get_services', return_value=(None, manager, None)), patch.object(scheduling, 'EmailNotificationService', side_effect=email), patch('backend.services.scheduling.get_scheduling_database_manager', return_value=manager), TestClient(app, client=('127.0.0.1', 1234)) as client:
            for status in ['pending', 'sent', 'error']:
                db.create_notification_log(NotificationLogEntry('', None, None, 'seed', status))
            records = client.get('/api/scheduling/notifications/logs').json()['data']
            assert {r['status'] for r in records} == {'pending', 'sent', 'error'}
            results.append('HTTP logs return pending, sent and error: passed')
            for mode in ['sent', 'error']:
                smtp.mode = mode
                response = client.post('/api/scheduling/notifications/settings/test', json={'recipient': 'accepted@example.com'})
                assert response.status_code == (200 if mode == 'sent' else 502), response.text
                records = client.get('/api/scheduling/notifications/logs').json()['data']
                recorded = any(r['event_type'] == 'smtp_test' and r['status'] == mode for r in records)
                results.append(f'SMTP test {mode} persisted: {recorded}')
                if not baseline:
                    assert recorded
            if not baseline:
                smtp.mode = 'sent'
                smtp.entered.clear(); smtp.release.clear()
                responses = []
                sender = threading.Thread(target=lambda: responses.append(client.post('/api/scheduling/notifications/send',
                    json={'schedule_id':'fixture', 'subject':'Manual', 'body':'Fixture body'})))
                sender.start()
                try:
                    assert smtp.entered.wait(3)
                    rows = client.get('/api/scheduling/notifications/logs').json()['data']
                    assert any(row['event_type']=='manual_email' and row['status']=='pending' for row in rows)
                finally:
                    smtp.release.set(); sender.join(5)
                assert responses[0].status_code == 200
                assert any(row.event_type=='manual_email' and row.status=='sent' for row in db.get_notification_logs())
                results.append('Manual email pending during SMTP, then sent: passed')
                recovery = SchedulingNotificationService.__new__(SchedulingNotificationService)
                recovery.email = email()
                recovery._manual_recovery_recipients = lambda schedule: ['accepted@example.com']
                recovery.manual_recovery_required(schedule, note='Fixture', actor='fixture')
                recovery.manual_recovery_cleared(schedule, note='Fixture', actor='fixture')
                for event in ['manual_recovery_required','manual_recovery_cleared']:
                    assert any(row.event_type==event and row.status=='sent' for row in db.get_notification_logs())
                results.append('Recovery notifications recorded: passed')
                from backend.services.notification_delivery import send_recorded
                smtp.mode = 'partial'; partial = email(); before = smtp.messages
                assert not send_recorded(partial, 'Partial', 'Fixture', event_type='partial_fixture',
                    to=['accepted@example.com','refused@example.com'])
                assert smtp.messages == before+1
                assert any(row.event_type=='partial_fixture' and row.status=='partial' for row in db.get_notification_logs())
                smtp.mode='sent'
                original = manager.update_notification_log
                manager.update_notification_log = lambda *args, **kw: False
                before=smtp.messages; sent=email()
                assert send_recorded(sent, 'Storage fault', 'Fixture', event_type='storage_fault', to=['accepted@example.com'])
                assert smtp.messages==before+1 and sent.delivery_log_warning
                manager.update_notification_log=original
                results.append('Partial refusal and log-storage failure do not resend accepted email: passed')
                # Exercise the existing scheduler owner: one event, one record, repeated dispatch deduplicates.
                manager.notification_log_exists = db.notification_log_exists
                engine=SchedulerEngine.__new__(SchedulerEngine)
                engine.config=SimpleNamespace(enable_notifications=True)
                engine.db_manager=manager
                engine.get_notification_contact=lambda _: contact
                engine.run_log_monitor=SimpleNamespace(snapshot=lambda _: None)
                engine._notification_service=SimpleNamespace(schedule_alert=lambda *args, **kw: ScheduleAlertResult(True,'Automatic','Fixture',['accepted@example.com']))
                execution=SimpleNamespace(execution_id='fixture-execution')
                for _ in range(2):
                    engine._dispatch_execution_notification(schedule, execution, event_type='automatic_fixture', context={}, contact_ids={'contact'})
                rows=[row for row in db.get_notification_logs() if row.event_type=='automatic_fixture']
                assert len(rows)==1 and rows[0].status=='sent'
                results.append('Existing automatic-alert success and deduplication: passed')
        smtp.shutdown()
    evidence = Path('test-output/database-verification')
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence/('notification-baseline.json' if baseline else 'notification-results.json')).write_text(json.dumps(results, indent=2))
    print('\n'.join(results))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', action='store_true')
    run(parser.parse_args().baseline)
