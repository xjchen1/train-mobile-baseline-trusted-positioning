"""修改研究版C源码后，在PyCharm运行本文件重新编译。"""
import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
from gnss_project.runner import ROOT, save_json, sha256


def build(variant):
    specs = json.loads((ROOT/'configs/build_specs.json').read_text(encoding='utf-8'))
    spec = specs[variant]
    compiler = shutil.which('clang')
    if not compiler:
        raise RuntimeError('未找到clang。当前构建配置用于安装了Xcode Command Line Tools的macOS。')
    source = ROOT/spec['source_root']
    work = ROOT/'build'/variant/dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    work.mkdir(parents=True)
    flags = spec['flags']+['-I'+str(source/'src')]
    objects, commands = [], []
    for relative in spec['compile_sources']:
        src = source/relative
        obj = work/(src.stem+'.o')
        command = [compiler]+flags+['-c', str(src), '-o', str(obj)]
        p = subprocess.run(command, capture_output=True)
        (work/(src.stem+'.log')).write_bytes(p.stdout+p.stderr)
        if p.returncode:
            raise RuntimeError('编译失败：'+str(src)+'；详情：'+str(work/(src.stem+'.log')))
        commands.append(command)
        objects.append(obj)
    target = ROOT/'bin'/('rnx2rtkp_'+variant)
    temporary = work/target.name
    command = [compiler]+flags+[str(source/spec['entry'])]+[str(p) for p in objects]
    command += ['-o', str(temporary)]+spec['link_flags']
    p = subprocess.run(command, capture_output=True)
    (work/'link.log').write_bytes(p.stdout+p.stderr)
    if p.returncode:
        raise RuntimeError('链接失败，详情：'+str(work/'link.log'))
    commands.append(command)
    # Update only after the entire new build succeeds.
    shutil.copy2(temporary, target)
    records = [dict(path=str(p.relative_to(source)), sha256=sha256(p))
               for p in sorted(source.rglob('*')) if p.is_file() and p.suffix in ['.c','.h']]
    identity = dict(variant=variant, source_root=spec['source_root'],
        binary=str(target.relative_to(ROOT)), binary_sha256=sha256(target), source_files=records,
        built_at=dt.datetime.now().isoformat(), compiler=compiler, commands=commands,
        identity_note='local rebuild; record source identity when comparing results')
    save_json(ROOT/'bin'/(variant+'.json'), identity)
    save_json(work/'build_manifest.json', identity)
    print('编译完成：'+str(target), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', choices=['relative_cv','original','original_audit','all'], default='relative_cv')
    args = parser.parse_args()
    variants = ['original','original_audit','relative_cv'] if args.variant=='all' else [args.variant]
    for variant in variants:
        build(variant)


if __name__ == '__main__':
    main()
