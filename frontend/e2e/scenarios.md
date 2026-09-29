# Work in progress: failure cases

Before changing behavior, list here how the change could go wrong. Once the checks
exist, move the lasting cases into the header comment of the spec or backend check
that covers them, then delete them from this file. Keep this file short; finished
work stays in Git history, not here.

## Restore from a `.bck` path (`POST /api/admin/backup/restore` with `file_path`)

- The path restore never reaches SQL Server (it called a connection helper that
  `BackupService` does not have) and every request reports "Database restore failed".
- A successful response while the database still holds the old rows.
- An open session on the target database blocks the restore instead of being disconnected.
- A missing file, a folder, or a wrong extension touches the database instead of failing first.
- A file SQL Server cannot restore (not a backup) reports success, returns an empty message,
  changes the rows, or leaves the database in single-user mode.
- The path restore uses the 5-minute backup timeout instead of `RESTORE_TIMEOUT`.
- The check itself touches EvoYeast or any database it did not create, or leaves its
  disposable database or backup file behind.
