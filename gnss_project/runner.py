"""Run the included C solvers and export current moving-baseline solutions.

Python handles configuration and evidence; all GNSS estimation stays in C.
The Python launcher itself requires only the standard library (Python >=3.9).
"""
import csv
import datetime as dt
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
TICKS_PER_SECOND = 10_000_000
QUALITY = {0: 'NONE', 1: 'FIX', 2: 'FLOAT', 3: 'SBAS', 4: 'DGPS', 5: 'SINGLE', 6: 'PPP'}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def project_path(value):
    path = Path(os.path.expandvars(os.path.expanduser(str(value))))
    return path.resolve() if path.is_absolute() else (ROOT/path).resolve()


def read_settings(path='settings.json'):
    result = json.loads(project_path(path).read_text(encoding='utf-8'))
    start = dt.datetime.fromisoformat(result['start_gpst'])
    end = dt.datetime.fromisoformat(result['end_gpst'])
    interval = float(result['interval_s'])
    if start.tzinfo is not None or end.tzinfo is not None:
        raise ValueError('GPST时间请写为YYYY-MM-DD HH:MM:SS，不附UTC时区。')
    if end < start or not math.isfinite(interval) or interval <= 0:
        raise ValueError('结束时间须不早于开始时间；历元间隔须为正数。')
    if result.get('export_baseline', True) and start.date() != end.date():
        raise ValueError('当前基线导出按单个GPST日组织；跨日运行请关闭export_baseline。')
    dataset = result['datasets'][result['dataset']]
    for key in ['master_observation', 'rover_observation']:
        if not project_path(dataset[key]).is_file():
            raise FileNotFoundError('请在settings.json中设置有效的'+key+'路径：'+dataset[key])
    nav = dataset['navigation']
    if isinstance(nav, str):
        nav = [nav]
    if not nav or not all(project_path(p).is_file() for p in nav):
        raise FileNotFoundError('导航文件不存在，请检查settings.json中的navigation。')
    return result


def config_values(path):
    values = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if line and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def check_binary(variant):
    manifest_path = ROOT/'bin'/(variant+'.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    binary = ROOT/manifest['binary']
    if not binary.is_file() or sha256(binary) != manifest['binary_sha256']:
        raise RuntimeError('程序缺失或已改变，请运行build_solvers.py重新编译：'+variant)
    tree = ROOT/manifest['source_root']
    for record in manifest['source_files']:
        source = tree/record['path']
        if not source.is_file() or sha256(source) != record['sha256']:
            raise RuntimeError('源码已修改，先运行build_solvers.py再解算：'+str(source))
    return binary, manifest


def observation_counts(path, start, end):
    """RINEX 3 input roster, used only to label missing epochs."""
    counts = {}
    with Path(path).open(encoding='ascii', errors='replace') as stream:
        for line in stream:
            if not line.startswith('>'):
                continue
            fields = line.split()
            if len(fields) < 9:
                continue
            try:
                midnight = dt.datetime(*map(int, fields[1:4]))
                seconds = int(fields[4])*3600+int(fields[5])*60+float(fields[6])
                moment = midnight+dt.timedelta(seconds=seconds)
                flag, number = int(fields[7]), int(fields[8])
            except ValueError:
                continue
            if start <= moment <= end and flag in [0, 1]:
                counts[round(seconds*TICKS_PER_SECOND)] = number
    return counts


def write_csv(path, rows):
    if not rows:
        Path(path).write_text('', encoding='utf-8-sig')
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def native_position_csv(source, output):
    rows = []
    for line in Path(source).read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip() or line.startswith('%'):
            continue
        values = line.split()
        if len(values) < 7:
            continue
        quality = int(values[5])
        rows.append(dict(time_gpst=values[0]+' '+values[1],
            rover_x_m=float(values[2]), rover_y_m=float(values[3]), rover_z_m=float(values[4]),
            native_quality=quality, solution=QUALITY.get(quality, str(quality)), satellites=int(values[6])))
    write_csv(output, rows)
    return rows


def flatten(value):
    return [x[0] if isinstance(x, list) else x for x in value]


def audit_baseline_csv(log_path, output, settings, relative_model):
    """FIX uses xa/Pa; FLOAT uses x/P; SINGLE/stale never becomes baseline."""
    by = {}
    current_spp = {}
    current_hold = False
    with Path(log_path).open(encoding='utf-8') as stream:
        for line in stream:
            z = json.loads(line)
            event = z['event']
            if event == 'SPP':
                current_spp[z['role']] = z['ok']
            elif event == 'HOLD':
                current_hold = True
            elif event == 'REL':
                q = by.setdefault(int(z['tick']), {})
                q.update(rel=z, HOLD=current_hold)
                current_hold = False
            elif event == 'EPOCH':
                q = by.setdefault(int(z['tick']), {})
                if 'epoch' in q:
                    raise ValueError('输入包含重复调用历元，未覆盖已有基线记录：'+str(z['tick']))
                q.update(epoch=z, spp=current_spp.copy())
                current_spp.clear()
                current_hold = False
    start = dt.datetime.fromisoformat(settings['start_gpst'])
    end = dt.datetime.fromisoformat(settings['end_gpst'])
    step_ticks = round(float(settings['interval_s'])*TICKS_PER_SECOND)
    if step_ticks < 1:
        raise ValueError('interval_s小于当前导出时间分辨率。')
    midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
    first = round((start-midnight).total_seconds()*TICKS_PER_SECOND)
    last = round((end-midnight).total_seconds()*TICKS_PER_SECOND)
    dataset = settings['datasets'][settings['dataset']]
    roster = observation_counts(project_path(dataset['rover_observation']), start, end)
    rows = []
    for tick in range(first, last+1, step_ticks):
        item = by.get(tick, {})
        e, rel = item.get('epoch'), item.get('rel')
        updated = bool(e and rel and e['rc'] and rel['stat'] in [1, 2] and not e.get('rel_error', 0))
        state = 'FIX' if updated and rel['stat'] == 1 else 'FLOAT' if updated else 'NO_UPDATE'
        status = ('CURRENT_UPDATE' if updated else 'ROVER_OBS_ABSENT' if roster.get(tick) == 0
                  else 'NATIVE_NOT_DISPATCHED' if not e else 'NO_CURRENT_BASELINE')
        moment = midnight+dt.timedelta(seconds=tick/TICKS_PER_SECOND)
        row = dict(time_gpst=moment.isoformat(sep=' ', timespec='milliseconds'),
            tick=tick, native_called=e is not None, current_update=updated, solution=state,
            status=status, native_quality=e.get('stat') if e else None,
            SPP_rover_ok=item.get('spp', {}).get(1), SPP_master_ok=item.get('spp', {}).get(2),
            HOLD_this_epoch=item.get('HOLD', False), ratio=rel.get('ratio') if rel else None,
            nfix=rel.get('nfix') if rel else None, mean_source='',
            covariance_scope='conditional baseline given master SPP',
            state_dt_s=e.get('state_dt') if e else None, model_error=e.get('rel_error') if e else None)
        if updated:
            x = flatten(rel['fixed_x'] if state == 'FIX' else rel['x'])
            P = rel['fixed_P'] if state == 'FIX' else rel['P']
            base = flatten(e['rb'])
            row['mean_source'] = 'xa/Pa' if state == 'FIX' else 'x/P'
            b = [x[i]-base[i] for i in range(3)]
            assert all(math.isfinite(v) for v in b)
            row['baseline_length_m'] = math.sqrt(sum(v*v for v in b))
            for i, axis in enumerate('xyz'):
                row['rover_'+axis+'_m'] = x[i]
                row['master_'+axis+'_m'] = base[i]
                row['baseline_'+axis+'_m'] = b[i]
                if relative_model:
                    assert rel['na'] == 6
                    assert e['state_time'] == e['time']
                    assert flatten(e['state_anchor']) == base[:3]
                    row['relative_v_'+axis+'_mps'] = x[i+3]
            blocks = [('Pbb', 0, 0)]
            if relative_model:
                blocks += [('Pbu', 0, 3), ('Puu', 3, 3)]
            for name, a, b0 in blocks:
                for i in range(3):
                    for j in range(3):
                        row[name+'_'+str(i)+str(j)] = P[i+a][j+b0]
        rows.append(row)
    write_csv(output, rows)
    return rows


def run_profile(settings, profile_name=None):
    name = profile_name or settings['profile']
    profiles = json.loads((ROOT/'configs/profiles.json').read_text(encoding='utf-8'))
    if name not in profiles:
        raise ValueError('未知配置：'+name+'；可选：'+', '.join(profiles))
    profile = profiles[name]
    export = bool(settings.get('export_baseline', True))
    variant = profile['variant']
    actual_variant = 'original_audit' if variant == 'original' and export else variant
    binary, identity = check_binary(actual_variant)
    config = project_path(profile['config'])
    options = config_values(config)
    if options.get('pos1-posmode') != 'movingbase' or options.get('out-solformat') != 'xyz':
        raise ValueError('本项目入口要求pos1-posmode=movingbase、out-solformat=xyz。')
    relative_model = options.get('pos1-relmotion', 'off') in ['cv', '1']
    if relative_model and variant != 'relative_cv':
        raise ValueError('相对CV需使用RR_CONT或RR_FH对应的研究版程序。')
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder = project_path(settings.get('output_directory', 'outputs'))/(stamp+'_'+name+'_'+uuid.uuid4().hex[:4])
    folder.mkdir(parents=True, exist_ok=False)
    used_config = folder/'used.conf'
    shutil.copyfile(config, used_config)
    dataset = settings['datasets'][settings['dataset']]
    A, B = [project_path(dataset[k]) for k in ['master_observation', 'rover_observation']]
    nav = dataset['navigation']
    nav = [nav] if isinstance(nav, str) else nav
    nav = [project_path(p) for p in nav]
    start = dt.datetime.fromisoformat(settings['start_gpst'])
    end = dt.datetime.fromisoformat(settings['end_gpst'])
    pos = folder/'solution.pos'
    command = [str(binary), '-k', str(used_config), '-ts', start.strftime('%Y/%m/%d'),
        start.strftime('%H:%M:%S.%f'), '-te', end.strftime('%Y/%m/%d'), end.strftime('%H:%M:%S.%f'),
        '-ti', str(settings['interval_s']), '-o', str(pos), str(B), str(A)]+[str(p) for p in nav]
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1')
    for key in ['RTK_RESEARCH_AUDIT', 'RTK_RESEARCH_LEVEL', 'RTK_TIMING_CSV']:
        env.pop(key, None)
    audit = folder/'state_audit.jsonl'
    if export:
        env.update(RTK_RESEARCH_AUDIT=str(audit), RTK_RESEARCH_LEVEL='2')
    manifest = dict(profile=name, label=profile['label'], engine=actual_variant,
        binary_sha256=identity['binary_sha256'], source_root=identity['source_root'],
        source_files=identity['source_files'], settings=settings, configuration=options,
        config_sha256=sha256(used_config), command=command,
        inputs=[dict(path=str(p), sha256=sha256(p)) for p in [A, B]+nav],
        full_state_audit_enabled=export,
        wall_time_scope='native process including RINEX/nav loading, solver, output and enabled audit IO',
        baseline_definition='rover minus master at the solver synchronized epoch',
        output_directory=str(folder))
    save_json(folder/'run_manifest.json', manifest)
    print('\n运行：'+name+' / '+profile['label'], flush=True)
    print('数据：'+settings['dataset']+'；GPST '+str(start)+' 至 '+str(end), flush=True)
    print('结果目录：'+str(folder), flush=True)
    tic = time.perf_counter()
    with (folder/'native.log').open('wb') as stream:
        process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
            env=env, timeout=float(settings.get('timeout_s', 300)))
    wall = time.perf_counter()-tic
    baseline_rows = []
    if export and audit.exists():
        baseline_rows = audit_baseline_csv(audit, folder/'baseline.csv', settings, relative_model)
        with audit.open('rb') as src, gzip.open(str(audit)+'.gz', 'wb') as dst:
            shutil.copyfileobj(src, dst)
        audit.unlink()  # This run's temporary raw log has an intact compressed copy.
    positions = native_position_csv(pos, folder/'position.csv') if pos.exists() else []
    counts = {k: sum(q['solution'] == k for q in positions) for k in ['FIX', 'FLOAT', 'SINGLE']}
    summary = dict(profile=name, label=profile['label'], returncode=process.returncode,
        native_process_wall_s=wall, native_position_rows=len(positions),
        native_position_counts=counts, planned_baseline_rows=len(baseline_rows) if export else None,
        current_baseline_updates=sum(q['current_update'] for q in baseline_rows) if export else None,
        baseline_FIX=sum(q['solution']=='FIX' for q in baseline_rows) if export else None,
        baseline_FLOAT=sum(q['solution']=='FLOAT' for q in baseline_rows) if export else None,
        model_error_epochs=sum(bool(q['model_error']) for q in baseline_rows) if export else None,
        output_directory=str(folder), audit_IO_included_in_wall_time=export)
    save_json(folder/'summary.json', summary)
    if process.returncode or (summary['model_error_epochs'] or 0):
        raise RuntimeError('解算未正常完成；已保留日志和结果，请查看：'+str(folder/'native.log'))
    print('完成：原生输出'+str(len(positions))+'行，FIX/FLOAT/SINGLE='+str(counts), flush=True)
    if export:
        print('当前有效基线：'+str(summary['current_baseline_updates'])+'/'+str(len(baseline_rows))
              +'；FIX/FLOAT='+str(summary['baseline_FIX'])+'/'+str(summary['baseline_FLOAT']), flush=True)
    print('进程墙钟：%.3f s（包含加载、结果输出及已启用日志）。'%wall, flush=True)
    return folder, summary
