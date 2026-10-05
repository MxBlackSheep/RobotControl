"""Repeatable HTTP/SQLite/SMTP check. Uses disposable state and a local mail sink.

Failure cases: pending, sent and error records appear over HTTP, including manual,
test and recovery emails. Partial refusal or log-storage failure never resends mail
that was already accepted.

Alert layout, read back from the bytes the mail sink received:
- every schedule-alert trigger (log_inactive, monitoring_unavailable, long_running,
  aborted, execution_failed, an unknown one) and both recovery emails arrive as a
  text part plus an HTML part carrying the same facts in the same order, and the
  delivery record stores exactly the text part;
- a hostile experiment name, note, path, error or unknown context value appears as
  escaped text in the HTML, never as markup, and the subject stays on one line;
- an unknown trigger gets a generic sentence and its unknown context keys appear as
  "key: value"; missing optional fields leave no empty rows and no "None";
- the SMTP test and manual email stay single-part plain text.

`--render DIR` also writes each sample as .eml, .html and .txt for review.
"""
import argparse
import email
import email.policy
import html
import json
import re
import socketserver
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import scheduling
from backend.models import JobExecution, NotificationLogEntry, ScheduledExperiment, NotificationContact
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
                    self.server.raw.append(b''.join(body))
                    self.wfile.write(b'250 accepted\r\n')
                    data = False
                else:
                    body.append(line[1:] if line.startswith(b'..') else line)
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
                data, body = True, []
            elif command.startswith(b'QUIT'):
                self.wfile.write(b'221 bye\r\n')
                return
            else:
                self.wfile.write(b'250 OK\r\n')


HOSTILE = 'Cham<script>alert(1)</script> & "Fl" <img src=x onerror=alert(2)>'


def alert_samples(now):
    """Fixed alerts: one per trigger, an unknown trigger, missing fields and hostile values."""
    guid = '5f0c2a9e-1b7d-4e43-9a61-0c8f2d7b3e15'
    method = r'C:\Program Files\HAMILTON\Methods\ChamFl\ChamFl_Fluorence.med'
    run = {'run_guid': guid, 'method_path': method, 'run_state': 'Running', 'raw_run_state': '1',
           'trace_filename': f'ChamFl_Fluorence_{guid}_Trace.trc'}
    def schedule(name='ChamFl_Fluorence', duration=60):
        return ScheduledExperiment('sched-chamfl', name, method, 'interval', estimated_duration=duration,
                                   log_inactivity_threshold_minutes=10, notification_contacts=['contact'])
    def execution(started=42, ended=None, **fields):
        return JobExecution('exec-7f3a', 'sched-chamfl', 'running', start_time=now - timedelta(minutes=started) if started else None,
                            end_time=now - timedelta(minutes=ended) if ended is not None else None, **fields)
    return [
        ('log_inactive', 'log_inactive', schedule(), execution(), {**run, 'inactivity_minutes': 12.4, 'threshold_minutes': 10,
            'last_activity_at': (now - timedelta(minutes=12.4)).isoformat(), 'observed_at': now.isoformat(),
            'note': 'The run log has stopped updating; operator attention may be required.'}),
        ('monitoring_unavailable', 'monitoring_unavailable', schedule(), execution(), {**run, 'run_state': None, 'raw_run_state': None,
            'unavailable_minutes': 3.6, 'threshold_minutes': 3, 'last_activity_at': (now - timedelta(minutes=5)).isoformat(),
            'observed_at': now.isoformat(), 'note': 'No matching Hamilton run was found in SQL within five minutes of launch'}),
        ('long_running', 'long_running', schedule(), execution(started=95), {**run, 'elapsed_minutes': 95.0, 'expected_minutes': 60, 'threshold_minutes': 90}),
        ('aborted', 'aborted', schedule(), execution(started=30, ended=2), {'error_message': f'Hamilton reported run {guid} as Aborted',
            'note': f'Hamilton reported run {guid} as Aborted', 'runtime_minutes': 27.8}),
        ('execution_failed', 'execution_failed', schedule(), execution(started=1, ended=1),
            {'error_message': 'HxRun exited with return code 1: the method file could not be opened'}),
        ('unknown_trigger', 'pump_pressure_high', schedule(), execution(), {'pressure_kpa': 212.5, 'operator_hint': 'Check the tubing'}),
        ('missing_fields', 'log_inactive', schedule(duration=0), execution(started=None), {}),
        ('hostile', 'execution_failed', schedule(HOSTILE), execution(), {'error_message': HOSTILE,
            'method_path': r'C:\Methods\<b>bold</b>.med', 'detail': HOSTILE}),
    ]


def message_parts(raw):
    message = email.message_from_bytes(raw, policy=email.policy.default)
    text, page = message.get_body(('plain',)), message.get_body(('html',))
    # SMTP carries CRLF line endings; the stored record uses LF.
    read = lambda part: part.get_content().replace('\r\n', '\n') if part else None
    return message, read(text), read(page)


def check_alert(raw, stored):
    """Both parts present; the HTML shows every fragment of the text part, in order, escaped."""
    message, text, page = message_parts(raw)
    subject = message['Subject']
    assert text and page, f'{subject}: expected a text part and an HTML part'
    assert '\n' not in subject and subject.startswith('RobotControl alert: '), subject
    assert text.strip() == stored.strip(), f'{subject}: the delivery record must store the text part'
    assert 'None' not in text and not re.search(r'(?m):[ \t]*$', text), f'{subject}: empty field in text part'
    tags = re.findall(r'<[^>]*>', page)
    assert not any(re.match(r'<\s*/?\s*(script|img|link|style|iframe|object)\b', tag, re.I) for tag in tags), subject
    assert not any(re.search(r'\bon\w+\s*=|\bsrc\s*=|https?:', tag, re.I) for tag in tags), subject
    assert all(int(width) <= 600 for width in re.findall(r'width="(\d+)"', page)), subject
    shown = ' '.join(html.unescape(re.sub(r'<[^>]*>', ' ', re.sub(r'(?is)<head\b.*?</head>', ' ', page))).split())
    assert 'None' not in shown, subject
    position = 0
    for line in text.splitlines():
        for fragment in re.split(r':\s+|\s{2,}', line.strip().removeprefix('- ')):
            fragment = ' '.join(fragment.split())
            if fragment:
                found = shown.find(fragment, position)
                assert found >= 0, f'{subject}: {fragment!r} missing from the HTML part or out of order'
                position = found + len(fragment)
    return message, text, page


def run_layout_checks(smtp, email_service, db, render):
    now = datetime.now().replace(second=0, microsecond=0)
    out = Path(render) if render else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rc-alert-') as folder:
        trace = Path(folder) / 'ChamFl_Fluorence_5f0c2a9e_Trace.trc'
        trace.write_text('2026-10-03 14:02:11> Start method - complete;\n', encoding='utf-8')
        clip = Path(folder) / 'clip.avi'
        clip.write_bytes(b'clip')
        def summary_clip(_clips):
            path = Path(tempfile.mkstemp(prefix='robotcontrol_rolling_summary_', suffix='.mp4')[1])
            path.write_bytes(b'\0' * 3_400_000)
            return path
        def deliver(name, send, stored):
            before = len(smtp.raw)
            send()
            assert len(smtp.raw) == before + 1, f'{name}: expected one message'
            message, text, page = check_alert(smtp.raw[-1], stored())
            if out:
                (out / f'{name}.eml').write_bytes(smtp.raw[-1])
                (out / f'{name}.html').write_text(page, encoding='utf-8')
                (out / f'{name}.txt').write_text(f"Subject: {message['Subject']}\n\n{text}", encoding='utf-8')
            return message, text, page
        contact = NotificationContact('contact', 'Operator', 'accepted@example.com')
        for name, trigger, schedule, execution, context in alert_samples(now):
            service = SchedulingNotificationService.__new__(SchedulingNotificationService)
            service.email = email_service()
            missing = name == 'missing_fields'
            service._collect_recent_rolling_clips = lambda limit, missing=missing: [] if missing else [clip]
            service._transcode_clips_to_mp4 = summary_clip
            outcome = {}
            def send():
                outcome['result'] = service.schedule_alert(schedule, execution, contacts=[contact], trigger=trigger, context=context,
                    trace_path=Path(folder) / 'absent.trc' if missing else trace, exact_trace=True)
                assert outcome['result'].sent, f'{name}: {outcome["result"].error}'
            message, text, page = deliver(name, send, lambda: outcome['result'].body)
            if name == 'hostile':
                assert HOSTILE in text and HOSTILE not in page and '&lt;script&gt;' in page
            if name == 'unknown_trigger':
                assert 'Pump pressure high' in text and 'operator_hint: Check the tubing' in text
        recovery = SchedulingNotificationService.__new__(SchedulingNotificationService)
        recovery.email = email_service()
        recovery._manual_recovery_recipients = lambda schedule: ['accepted@example.com']
        guid = '5f0c2a9e-1b7d-4e43-9a61-0c8f2d7b3e15'
        flagged = ScheduledExperiment('sched-chamfl', 'ChamFl_Fluorence', 'ChamFl_Fluorence.med', 'interval',
            recovery_marked_at=now - timedelta(minutes=2), recovery_resolved_at=now)
        def stored(event):
            # An unknown schedule ID is kept in metadata, not the schedule_id column.
            return lambda: next(row.message for row in db.get_notification_logs(event_type=event)
                                if (row.metadata or {}).get('original_schedule_id') == 'sched-chamfl')
        deliver('manual_recovery_required', lambda: recovery.manual_recovery_required(
            flagged, note=f'Hamilton reported run {guid} as Aborted', actor='scheduler'), stored('manual_recovery_required'))
        deliver('manual_recovery_cleared', lambda: recovery.manual_recovery_cleared(
            flagged, note='Deck cleared and used tips removed.', actor='andy'), stored('manual_recovery_cleared'))


def run(baseline=False, render=None):
    results = []
    with tempfile.TemporaryDirectory(prefix='rc-mail-') as folder, socketserver.ThreadingTCPServer(('127.0.0.1', 0), MailSink) as smtp:
        smtp.mode, smtp.messages, smtp.raw = 'sent', 0, []
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
                for subject in ['RobotControl SMTP test message', 'Manual']:
                    message = next(m for m in (message_parts(raw)[0] for raw in smtp.raw) if m['Subject'] == subject)
                    assert message.get_content_type() == 'text/plain' and not message.is_multipart(), subject
                results.append('SMTP test and manual email stay plain text: passed')
                run_layout_checks(smtp, email, db, render)
                results.append('Alert and recovery emails: text and HTML parts with the same facts, escaped, recorded as text: passed')
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
    parser.add_argument('--render', metavar='DIR', help='also write every sample alert as .eml, .html and .txt')
    arguments = parser.parse_args()
    run(arguments.baseline, arguments.render)
