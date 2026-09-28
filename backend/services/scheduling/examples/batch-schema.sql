-- Disposable example only. Create this in a new lab SQLite file, never the
-- RobotControl scheduler database. Batch codes need not resemble ExperimentID.
CREATE TABLE Batches (batch_code TEXT PRIMARY KEY, description TEXT NOT NULL, state TEXT NOT NULL);
INSERT INTO Batches VALUES ('B-01','Calibration batch','ready'), ('B-02','Sample batch','ready');
CREATE TABLE InstrumentWorkOrder (slot INTEGER PRIMARY KEY CHECK(slot=1), batch_code TEXT, method TEXT);
INSERT INTO InstrumentWorkOrder VALUES (1,NULL,NULL);
