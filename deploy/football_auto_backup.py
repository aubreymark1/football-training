#!/usr/bin/env python3
"""Create verified SQLite and data-directory backups, retaining seven days."""
import argparse
from contextlib import closing
import datetime
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import zipfile

PATTERN = re.compile(r'^football-auto-\d{8}T\d{6}Z\.zip$')

def run(data, dest, days=7):
    data, dest = Path(data).resolve(strict=True), Path(dest).resolve()
    if dest == data or data in dest.parents:
        raise ValueError('backup directory must be outside the data directory')
    dest.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(dest, 0o700)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target=dest/('football-auto-'+stamp+'.zip')
    if target.exists(): raise FileExistsError(target)
    with tempfile.TemporaryDirectory(prefix='football-backup-',dir=dest) as tmp:
        tmp=Path(tmp); snapshot=tmp/'team.sqlite3'; pending=tmp/'backup.zip'
        with closing(sqlite3.connect((data/'team.sqlite3').as_uri()+'?mode=ro',uri=True)) as source, closing(sqlite3.connect(snapshot)) as copy:
            source.backup(copy)
            if copy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('database integrity check failed')
        os.chmod(snapshot,0o600)
        with zipfile.ZipFile(pending,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot,'team.sqlite3')
            for root, dirs, files in os.walk(data,followlinks=False):
                root=Path(root); dirs[:]=[d for d in dirs if not (root/d).is_symlink()]
                for name in files:
                    path=root/name; rel=path.relative_to(data)
                    if path.is_symlink() or not path.is_file() or str(rel) in ('team.sqlite3','team.sqlite3-wal','team.sqlite3-shm','team.sqlite3-journal'): continue
                    archive.write(path,rel.as_posix())
        os.chmod(pending,0o600)
        with zipfile.ZipFile(pending) as archive:
            bad=archive.testzip()
            if bad: raise ValueError('archive verification failed: '+bad)
        os.replace(pending,target)
    cutoff=time.time()-days*86400
    removed=0
    for item in dest.iterdir():
        if PATTERN.fullmatch(item.name) and item.is_file() and not item.is_symlink() and item != target and item.stat().st_mtime < cutoff:
            item.unlink(); removed+=1
    print('backup verified:',target,'expired removed:',removed)
    return target

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',default='/var/lib/football-training')
    parser.add_argument('--output-dir',default='/var/lib/football-training-backups/automatic')
    parser.add_argument('--retention-days',type=int,default=7)
    args=parser.parse_args()
    if args.retention_days<1: parser.error('retention must be at least one day')
    run(args.data_dir,args.output_dir,args.retention_days)
