"""fnOS initialization and configuration; runs in a short-lived container."""
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
WIZARD = Path('/wizard/config')
DATA_EXPR = '${wizard_data_dir:-${TRIM_APPDEST_VOL}/@appshare/' + APP + '/data}'
PHOTO_EXPR = '${wizard_photo_dir:-${TRIM_APPDEST_VOL}/@appshare/' + APP + '/photos}'

def fail(message):
    raise RuntimeError(message)

def port(value):
    if not str(value).isdigit() or not 1024 <= int(value) <= 65535:
        fail('端口必须是 1024–65535 之间的整数。')
    return int(value)

def host_path(value):
    if not re.match(r'^/vol[0-9]+/.+', value) or any(c in value for c in '\n\r\t:$`\\\"\',;'):
        fail('目录须为存储空间下的 NAS 绝对路径，不能包含引号、逗号或控制字符。')
    if any(part in ('.', '..') for part in value.split('/')):
        fail('请填写不含 . 或 .. 的完整目录路径。')
    return value.rstrip('/')

def inside(child, parent):
    return child == parent or child.startswith(parent.rstrip('/') + '/')

def data_path(value):
    value = host_path(value)
    if value.split('/')[2].startswith('@app') and not re.fullmatch(r'/vol[0-9]+/@appshare/' + re.escape(APP) + '/data', value):
        fail('请选择个人文件或共享文件中的独立目录，不要使用应用管理目录。')
    return value

def library_target(path, used=()):
    base = '/app/Photos/' + path.rsplit('/', 1)[-1]
    target, number = base, 2
    while target in used:
        target = f'{base} ({number})'
        number += 1
    return target

def libraries(record):
    if 'libraries' not in record:
        # Existing indexes refer to these paths. Never rename them on upgrade.
        record['libraries'] = [{'source': record['photo_dir'], 'target': '/app/Photos/已有照片', 'read_only': True}]
        for path in record['extra_dirs']:
            name = path.rsplit('/', 1)[-1][:48]
            target = '/app/Photos/' + name + '-' + hashlib.sha256(path.encode('utf-8')).hexdigest()[:12]
            record['libraries'].append({'source': path, 'target': target, 'read_only': True})
    return record['libraries']

def access_mode(value):
    if value not in ('ro', 'rw'):
        fail('图库权限必须为只读或读写。')
    return value == 'ro'

def config_wizard(record):
    items = []
    for entry in libraries(record):
        items.append({'type': 'select', 'field': action_field(entry['source']) + '_' + str(record['wizard_generation']), 'label': entry['source'],
                      'initValue': 'ro' if entry['read_only'] else 'rw',
                      'options': [*mode_options(), {'label': '移除', 'value': 'remove'}]})
    items.extend([
        {'type': 'text', 'field': 'wizard_new_photo_' + str(record['wizard_generation']), 'label': '新增照片目录（多个路径用 ; 分隔）', 'initValue': ''},
        {'type': 'select', 'field': 'wizard_add_photo_mode', 'label': '本次新增目录权限', 'initValue': 'ro', 'options': mode_options()},
    ])
    return [{'stepTitle': '照片目录', 'items': items}]

def action_field(path):
    return 'wizard_photo_access_' + hashlib.sha256(path.encode('utf-8')).hexdigest()[:16]

def remember_targets(record):
    history = record.setdefault('library_history', {})
    for entry in libraries(record):
        history[entry['source']] = entry['target']
    return history

def sync_native(record):
    if 'TS_NATIVE_COUNT' not in os.environ:
        return  # Missing context is not an empty authorization list.
    count = os.environ['TS_NATIVE_COUNT']
    if not count.isdigit() or int(count) > 1024:
        fail('授权目录列表无效。')
    entries = libraries(record)
    history = remember_targets(record)
    requested = {}
    authorized = set()
    for index in range(int(count)):
        path = host_path(os.environ[f'TS_NATIVE_PATH_{index}'])
        authorized.add(path)
        if path in record.get('native_excluded', []):
            continue
        if inside(path, record['data_dir']) or inside(record['data_dir'], path):
            fail('授权照片目录不能与用户数据目录相同或互相包含。')
        folder = CANDIDATE / ('native-' + str(index))
        if not folder.is_dir():
            fail('授权照片目录不存在。')
        try:
            next(folder.iterdir(), None)
        except OSError:
            fail('无法读取授权目录，请检查访问权限。')
        requested[path] = access_mode(os.environ[f'TS_NATIVE_MODE_{index}'])
    kept = [e for e in entries if not e.get('native') or e['source'] in requested]
    for path, readonly in requested.items():
        entry = next((e for e in kept if e['source'] == path), None)
        if entry is None:
            if any(inside(path, e['source']) or inside(e['source'], path) for e in kept):
                fail('授权目录与已有图库互相包含，请选择独立目录。')
            entry = {'source': path, 'target': history.get(path) or library_target(path, set(history.values()))}
            kept.append(entry)
            history[path] = entry['target']
        if not entry.get('manual_control'):
            entry.update(native=True, read_only=readonly)
    record['libraries'] = kept
    record['native_excluded'] = [p for p in record.get('native_excluded', []) if p in authorized]

def mode_options():
    return [{'label': '只读', 'value': 'ro'}, {'label': '读写', 'value': 'rw'}]

def atomic(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)

def render(record):
    # fnOS persists form values. Rotate submitted field names so an old Add or
    # Remove cannot be replayed when reopening settings or reconnecting a path.
    record['wizard_generation'] = record.get('wizard_generation', 0) + 1
    remember_targets(record)
    template = json.loads((PACKAGE / 'docker/compose-template.json').read_text(encoding="utf-8"))
    serialized = json.dumps(template, ensure_ascii=False)
    serialized = serialized.replace(DATA_EXPR, record['data_dir']).replace(PHOTO_EXPR, record['photo_dir'])
    serialized = serialized.replace('${wizard_port:-3180}', str(record['port']))
    compose = json.loads(serialized)
    for service in ['server', 'ai']:
        volumes = compose['services'][service]['volumes']
        volumes[:] = [v for v in volumes if not (isinstance(v, dict) and v['target'].startswith('/app/Photos/'))]
        targets = set()
        for entry in libraries(record):
            target = entry['target']
            if target in targets:
                fail('图库目录标识冲突，请联系支持。')
            targets.add(target)
            compose['services'][service]['volumes'].append({
                'type': 'bind', 'source': entry['source'], 'target': target,
                'read_only': entry['read_only'] if service == 'server' else True, 'bind': {'create_host_path': False},
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
    atomic(WIZARD, config_wizard(record))
    os.chmod(WIZARD.parent, 0o755)
    os.chmod(WIZARD, 0o644)
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
        record['libraries'] = [{'source': photo_host, 'target': library_target(photo_host),
                                'read_only': access_mode(os.environ.get('TS_PHOTO_MODE', 'ro'))}]
    if record.get('layout') != 'catalog-v1':
        fail('旧版图库路径需要迁移，请先保留旧版并备份；此安装包不自动修改已有索引。')
    render(record)
    print('行影集初始化完成，数据目录：' + record['data_dir'])

def configure():
    record = json.loads((META / 'installation.json').read_text(encoding="utf-8"))
    entries = libraries(record)
    remember_targets(record)
    for entry in list(entries):
        field = action_field(entry['source'])
        action = os.environ.get(field + '_' + str(record.get('wizard_generation', 0)), os.environ.get(field, 'keep'))
        if action not in ('keep', 'ro', 'rw', 'remove'):
            fail('旧版目录操作无效。')
        if action == 'remove':
            entries.remove(entry)
            record['native_excluded'] = sorted(set(record.get('native_excluded', [])) | {entry['source']})
        elif action in ('ro', 'rw'):
            entry['read_only'] = access_mode(action)
            entry.update(native=False, manual_control=True)
    for index, entry in enumerate(entries):
        mode = os.environ.get(f'wizard_library_mode_{index}')
        if mode is not None:
            entry['read_only'] = access_mode(mode)
    raw = os.environ.get('TS_ADD_PHOTOS', os.environ.get('TS_ADD_PHOTO', ''))
    candidates = [item.strip() for item in raw.split(';') if item.strip()]
    read_only = access_mode(os.environ.get('TS_ADD_MODE', 'ro'))
    for index, candidate in enumerate(candidates):
        candidate = host_path(candidate)
        record['native_excluded'] = [p for p in record.get('native_excluded', []) if p != candidate]
        if inside(candidate, record['data_dir']) or inside(record['data_dir'], candidate):
            fail('新增图库不能是应用数据目录或其上级、下级目录。')
        folder = CANDIDATE / str(index) if 'TS_ADD_PHOTOS' in os.environ else CANDIDATE
        if not folder.is_dir():
            fail('新增图库目录不存在。')
        try:
            next(folder.iterdir(), None)
        except OSError:
            fail('无法读取新增图库，请检查目录权限。')
        existing = [e['source'] for e in entries]
        if candidate in existing:
            continue
        if any(inside(candidate, path) for path in existing):
            fail('该目录已挂载或位于已有图库内，直接在行影集外部图库中选择其子目录即可。')
        if any(inside(path, candidate) for path in existing):
            fail('该目录包含已有图库，请选择独立目录以免重复索引。')
        record['extra_dirs'].append(candidate)
        history = remember_targets(record)
        entries.append({'source': candidate, 'target': history.get(candidate) or library_target(candidate, set(history.values())), 'read_only': read_only, 'manual_control': True})
    sync_native(record)
    record['extra_dirs'] = [e['source'] for e in record['libraries'] if e['source'] != record['photo_dir']]
    render(record)
    print('配置已保存。重启后，打开行影集「设置 → 外部图库」选择新增文件夹。')

if __name__ == '__main__':
    os.umask(0o077)
    try:
        {'init': initialize, 'configure': configure}[sys.argv[1]]()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
