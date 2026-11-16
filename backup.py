"""Create a consistent SQLite snapshot and include its referenced images."""
import argparse
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile


def backup(data_dir, output):
    data_dir = Path(data_dir).resolve()
    output = Path(output).resolve()
    source = data_dir / 'team.sqlite3'
    if not source.is_file():
        raise FileNotFoundError('找不到球队数据库')
    if output == source or data_dir in output.parents:
        raise ValueError('备份应放在数据目录之外')
    with tempfile.TemporaryDirectory(prefix='football-backup-') as temp:
        snapshot = Path(temp) / 'team.sqlite3'
        source_db = sqlite3.connect(f'{source.as_uri()}?mode=ro', uri=True)
        target_db = sqlite3.connect(snapshot)
        try:
            source_db.backup(target_db)
            names = [row[0] for row in target_db.execute('SELECT DISTINCT image FROM records')]
        finally:
            target_db.close()
            source_db.close()
        for name in names:
            if not name or Path(name).name != name or not (data_dir / 'uploads' / name).is_file():
                raise ValueError('数据库中存在无效或缺失的图片，备份未创建')
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create prevents accidentally replacing an existing backup.
        with open(output, 'xb') as destination:
            if os.name != 'nt':
                os.chmod(output, 0o600)
            try:
                with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
                    archive.write(snapshot, 'team.sqlite3')
                    for name in names:
                        archive.write(data_dir / 'uploads' / name, 'uploads/' + name)
            except Exception:
                destination.close()
                output.unlink(missing_ok=True)
                raise
    return len(names)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='备份球队数据库和记录截图')
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    count = backup(args.data_dir, args.output)
    print(f'备份完成：{args.output}（{count} 张截图）')
