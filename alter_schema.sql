ALTER TABLE dxspot RENAME TO old_spot;
CREATE TABLE IF NOT EXISTS dxspot
(
  de TEXT,
  frequency NUMERIC,
  dx TEXT,
  message TEXT,
  de_cont TEXT,
  to_cont TEXT,
  de_ituzone INTEGER,
  to_ituzone INTEGER,
  de_cqzone INTEGER,
  to_cqzone INTEGER,
  mode TEXT,
  signal INTEGER,
  band INTEGER,
  time TIMESTAMP
);
INSERT INTO dxspot("de", "frequency", "dx", "message", "de_cont", "to_cont", "de_ituzone", "to_ituzone", "de_cqzone", "to_cqzone", "band", "time") SELECT * FROM old_spot;
DROP TABLE old_spot;
CREATE INDEX idx_time on dxspot (time DESC);
CREATE INDEX idx_de_cont on dxspot (de_cont);
CREATE INDEX idx_de_cqzone on dxspot (de_cqzone);
VACUUM MAIN;
