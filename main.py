"""PyCharm中直接运行本文件。数据/时间在settings.json，算法参数在configs。"""
import argparse
import sys
from gnss_project.runner import read_settings, run_profile

# 留为None时采用settings.json中的profile；也可改为"RR_FH"等配置名。
PROFILE = None
SETTINGS_FILE = 'settings.json'


def main():
    parser = argparse.ArgumentParser(description='移动基线解算入口')
    parser.add_argument('--profile', default=PROFILE)
    parser.add_argument('--settings', default=SETTINGS_FILE)
    args = parser.parse_args()
    run_profile(read_settings(args.settings), args.profile)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileNotFoundError, RuntimeError) as error:
        print('\n运行中止：'+str(error), file=sys.stderr)
        raise SystemExit(1)
