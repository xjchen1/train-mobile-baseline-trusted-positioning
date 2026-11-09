"""顺序运行当前四组移动基线配置；每组结果保留在独立输出目录。"""
import argparse
import datetime as dt
from gnss_project.runner import ROOT, read_settings, run_profile, write_csv

PROFILES = ['R0_CONT', 'R0_FH', 'RR_CONT', 'RR_FH']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', default='settings.json')
    args = parser.parse_args()
    settings = read_settings(args.settings)
    rows = []
    for index, profile in enumerate(PROFILES, 1):
        print('\n[%d/4] %s' % (index, profile), flush=True)
        _, summary = run_profile(settings, profile)
        rows.append({k: v for k, v in summary.items() if not isinstance(v, dict)})
    output = ROOT/'outputs'/('four_groups_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.csv')
    output.parent.mkdir(exist_ok=True)
    write_csv(output, rows)
    print('\n四组运行汇总：'+str(output))


if __name__ == '__main__':
    main()
