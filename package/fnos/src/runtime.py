"""fnOS initialization and configuration; runs in a short-lived container."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys

APP = '@@APP@@'
META = Path('/meta')
STATE = Path('/state')
PACKAGE = Path('/package')
CANDIDATE = Path('/candidate')
DATA_EXPR = '${wizard_data_dir:?请选择用户数据目录}'
PHOTO_EXPR = '${wizard_photo_dir:-${TRIM_APPDEST_VOL}/@appshare/' + APP + '/photos}'

def fail(message):
    raise RuntimeError(message)

def port(value):
    if not str(value).isdigit() or not 1024 <= int(value) <= 65535:
        fail('端口必须是 1024–65535 之间的整数。')
    return int(value)

def host_path(value):
    if not re.match(r'^/vol[0-9]+/.+', value) or any(c in value for c in '\n\r\t:$`\\\"\','):
        fail('目录须为存储空间下的 NAS 绝对路径，不能包含引号、逗号或控制字符。')
    if any(part in ('.', '..') for part in value.split('/')):
        fail('请填写不含 . 或 .. 的完整目录路径。')
    return value.rstrip('/')

def inside(child, parent):
    return child == parent or child.startswith(parent.rstrip('/') + '/')

def data_path(value):
    value = host_path(value)
    if value.split('/')[2].startswith('@app'):
        fail('请选择个人文件或共享文件中的独立目录，不要使用应用管理目录。')
    return value

def library_target(path):
    # Full-path digest prevents equal basenames on different volumes colliding.
    name = path.rsplit('/', 1)[-1][:48]
    return '/app/Photos/' + name + '-' + hashlib.sha256(path.encode('utf-8')).hexdigest()[:12]

def atomic(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)

def render(record):
    template = json.loads((PACKAGE / 'docker/compose-template.json').read_text(encoding="utf-8"))
    serialized = json.dumps(template, ensure_ascii=False)
    serialized = serialized.replace(DATA_EXPR, record['data_dir']).replace(PHOTO_EXPR, record['photo_dir'])
    serialized = serialized.replace('${wizard_port:-3180}', str(record['port']))
    compose = json.loads(serialized)
    for service in ['server', 'ai']:
        targets = set()
        for path in record['extra_dirs']:
            target = library_target(path) if record.get('layout') == 'catalog-v1' else path
            if target in targets:
                fail('图库目录标识冲突，请联系支持。')
            targets.add(target)
            compose['services'][service]['volumes'].append({
                'type': 'bind', 'source': path, 'target': target,
                'read_only': True, 'bind': {'create_host_path': False},
            })
    atomic(PACKAGE / 'docker/docker-compose.yaml', compose)
    ui = json.loads((PACKAGE / 'ui/config').read_text(encoding="utf-8"))
    ui['.url'][APP + '.Application']['port'] = '${wizard_port}'
    atomic(PACKAGE / 'ui/config', ui)
    for path in [PACKAGE / 'docker/docker-compose.yaml', PACKAGE / 'ui/config']:
        os.chown(path, record['uid'], record['gid'])
        os.chmod(path, 0o644)
    atomic(META / 'installation.json', record)
    atomic(STATE / 'runtime/installation.json', record)
    (META / 'data-path').write_text(record['data_dir'] + '\n', encoding='utf-8')
    for path in [META / 'installation.json', META / 'data-path', STATE / 'runtime/installation.json']:
        os.chown(path, record['uid'], record['gid'])
        os.chmod(path, 0o600)

def initialize():
    uid, gid = int(os.environ['TS_UID']), int(os.environ['TS_GID'])
    data_host = data_path(os.environ.get('TS_DATA_HOST', ''))
    photo_host = host_path(os.environ['TS_PHOTO_HOST'])
    if inside(photo_host, data_host) or inside(data_host, photo_host):
        fail('数据目录与外部照片目录不能相同或互相包含，请选择独立目录。')
    marker = STATE / 'runtime/installation.json'
    legacy = STATE / 'runtime/postgres.env'
    if not marker.exists() and not legacy.exists():
        # Docker may have created empty bind targets. Never adopt unrelated files.
        for child in STATE.iterdir():
            if not child.is_dir() or child.name not in {'data', 'runtime', 'pg_data', 'backups'} or any(child.iterdir()):
                fail('数据目录已有其他内容。请选择新的空目录或已有的行影集数据目录。')
    META.mkdir(parents=True, exist_ok=True)
    os.chown(META, uid, gid)
    for name in ['', 'runtime', 'data', 'pg_data', 'backups']:
        folder = STATE / name
        folder.mkdir(parents=True, exist_ok=True)
        if name != 'pg_data' or not (folder / 'pgdata/PG_VERSION').exists():
            os.chown(folder, uid, gid)
    password_path = STATE / 'runtime/postgres.env'
    if not password_path.exists():
        if (STATE / 'pg_data/pgdata/PG_VERSION').exists():
            fail('已有数据库但凭据丢失，请恢复 runtime 目录，不能重新生成密码。')
        password_path.write_text('POSTGRES_DB=trailsnap\nPOSTGRES_USER=trailsnap\nPOSTGRES_PASSWORD=' + secrets.token_hex(32) + '\n')
    settings = dict(line.split('=', 1) for line in password_path.read_text(encoding="utf-8").splitlines() if '=' in line)
    password = settings.get('POSTGRES_PASSWORD', '')
    if not re.fullmatch('[a-f0-9]{64}', password):
        fail('保存的数据库凭据格式无效。')
    server_env = STATE / 'runtime/server.env'
    server_env.write_text(f'DB_URL=postgresql://trailsnap:{password}@postgres:5432/trailsnap\nRAILWAY_DB_URL=postgresql://trailsnap:{password}@postgres:5432/railway\n')
    config = STATE / 'data/system_config.json'
    if not config.exists():
        atomic(config, {'security': {'secret_key': secrets.token_hex(32), 'allow_registration': False}})
    for path in [password_path, server_env, config]:
        os.chown(path, uid, gid)
        os.chmod(path, 0o600)
    if marker.exists():
        record = json.loads(marker.read_text(encoding="utf-8"))
        if record['appname'] != APP or record['data_dir'] != data_host:
            fail('数据目录属于其他应用或路径已变更，请备份并按迁移说明操作。')
        record.update(uid=uid, gid=gid)
    else:
        record = {'appname': APP, 'revision': 3, 'layout': 'catalog-v1', 'port': port(os.environ['TS_PORT']),
                  'data_dir': data_host, 'photo_dir': photo_host, 'extra_dirs': [], 'uid': uid, 'gid': gid}
    if record.get('layout') != 'catalog-v1':
        fail('旧版图库路径需要迁移，请先保留旧版并备份；此安装包不自动修改已有索引。')
    render(record)
    print('行影集初始化完成，数据目录：' + record['data_dir'])

def configure():
    record = json.loads((META / 'installation.json').read_text(encoding="utf-8"))
    candidate = os.environ.get('TS_ADD_PHOTO', '')
    if candidate:
        candidate = host_path(candidate)
        if inside(candidate, record['data_dir']) or inside(record['data_dir'], candidate):
            fail('新增图库不能是应用数据目录或其上级、下级目录。')
        if not CANDIDATE.is_dir():
            fail('新增图库目录不存在。')
        try:
            next(CANDIDATE.iterdir(), None)
        except OSError:
            fail('无法读取新增图库，请检查目录权限。')
        existing = [record['photo_dir'], *record['extra_dirs']]
        if candidate in existing:
            render(record)
            print('该图库已接入，已保留原设置。')
            return
        if any(inside(candidate, path) for path in existing):
            fail('该目录已挂载或位于已有图库内，直接在行影集外部图库中选择其子目录即可。')
        if any(inside(path, candidate) for path in existing):
            fail('该目录包含已有图库，请选择独立目录以免重复索引。')
        record['extra_dirs'].append(candidate)
    render(record)
    print('配置已保存。重启后，打开行影集「设置 → 外部图库」选择新增文件夹。')

if __name__ == '__main__':
    os.umask(0o077)
    try:
        {'init': initialize, 'configure': configure}[sys.argv[1]]()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
