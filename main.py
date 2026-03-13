"""
招聘自动化控制器 - 主入口
启动方式:
  1. streamlit run ui/app.py          # 启动可视化界面
  2. python main.py --daemon          # 启动后台调度守护进程
  3. python main.py --screen <csv>    # 单次批量筛选
  4. python main.py --poll            # 单次轮询待约面
"""

from __future__ import annotations

import sys
import os
import argparse
import time
import signal
from pathlib import Path
from datetime import datetime

os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import get_logger
from utils.config_loader import get_settings
from utils.notifier import notify
from core.screener import ResumeScreener
from core.scheduler import InterviewScheduler
from core.follow_up import FollowUpManager
from adapters.moka_api import MokaAPI, MokaAPIError
from adapters.moka_csv import MokaCSVParser
from adapters.boss_plugin import BossPluginAdapter


class RecruitmentDaemon:
    """后台调度守护进程"""

    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger(
            log_dir=self.settings.get("logging", {}).get("log_directory", "./data/logs"),
            level=self.settings.get("logging", {}).get("level", "INFO"),
            max_size_mb=self.settings.get("logging", {}).get("max_log_size_mb", 50),
            backup_count=self.settings.get("logging", {}).get("backup_count", 10),
            log_to_console=self.settings.get("logging", {}).get("log_to_console", True),
        )
        self.running = True

        self.moka_api = self._init_moka_api()
        self.moka_csv = MokaCSVParser(
            import_dir=self.settings.get("moka_csv", {}).get("import_directory", "./data/moka_csv_import"),
            export_dir=self.settings.get("moka_csv", {}).get("export_directory", "./data/moka_csv_export"),
        )
        boss_cfg = self.settings.get("boss", {})
        self.boss = BossPluginAdapter(
            api_url=boss_cfg.get("plugin_api_url", "http://localhost:8800"),
            timeout=boss_cfg.get("message_send_timeout_seconds", 10),
        )

        self.screener = ResumeScreener()
        self.scheduler = InterviewScheduler(
            moka_api=self.moka_api,
            moka_csv=self.moka_csv,
            boss=self.boss,
        )
        self.followup = FollowUpManager(
            scheduler=self.scheduler,
            boss=self.boss,
            moka_api=self.moka_api,
        )

        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _init_moka_api(self) -> MokaAPI | None:
        moka_cfg = self.settings.get("moka", {})
        if not moka_cfg.get("api_enabled", False):
            self.logger.info("Moka API 未启用，使用 CSV 兜底模式")
            return None

        app_key = moka_cfg.get("app_key", "")
        app_secret = moka_cfg.get("app_secret", "")

        if not app_key or not app_secret:
            try:
                from utils.crypto import load_credentials, credential_store_exists
                if credential_store_exists():
                    self.logger.info("尝试从加密存储加载 Moka 凭据...")
                    return None
            except Exception:
                pass
            self.logger.warning("Moka API 密钥未配置，使用 CSV 兜底模式")
            return None

        return MokaAPI(
            base_url=moka_cfg.get("base_url", ""),
            app_key=app_key,
            app_secret=app_secret,
            org_id=moka_cfg.get("org_id", ""),
            retry_max=moka_cfg.get("retry_max", 3),
            retry_delay=moka_cfg.get("retry_delay_seconds", 5),
            rate_limit_per_minute=moka_cfg.get("rate_limit_per_minute", 60),
        )

    def _handle_shutdown(self, signum, frame):
        self.logger.info("收到停止信号，正在安全关闭...")
        self.running = False

    def run_daemon(self):
        """主循环：按配置频率执行各任务"""
        polling = self.settings.get("polling", {})
        poll_interval = polling.get("moka_pending_interview_minutes", 5) * 60
        reply_check_interval = polling.get("candidate_response_check_minutes", 30) * 60
        screen_interval = polling.get("screening_batch_minutes", 10) * 60

        self.logger.info("=" * 60)
        self.logger.info("招聘自动化控制器 - 后台守护进程启动")
        self.logger.info(f"  轮询待约面间隔: {poll_interval // 60} 分钟")
        self.logger.info(f"  回复检测间隔: {reply_check_interval // 60} 分钟")
        self.logger.info(f"  筛选批处理间隔: {screen_interval // 60} 分钟")
        self.logger.info("=" * 60)
        notify("控制器已启动", "后台守护进程开始运行", level="info")

        last_poll = 0
        last_reply_check = 0
        last_screen = 0

        while self.running:
            now = time.time()

            if now - last_poll >= poll_interval:
                self._task_poll_pending()
                last_poll = now

            if now - last_reply_check >= reply_check_interval:
                self._task_check_replies()
                self._task_followup()
                last_reply_check = now

            time.sleep(10)

        self.logger.info("守护进程已安全关闭")

    def _task_poll_pending(self):
        """任务：轮询待约面"""
        try:
            new_schedules = self.scheduler.poll_pending_interviews()
            for schedule in new_schedules:
                self.scheduler.process_new_schedule(schedule)
        except Exception as e:
            self.logger.error(f"轮询待约面异常: {e}")
            notify("轮询异常", str(e)[:100], level="error")

    def _task_check_replies(self):
        """任务：检查候选人回复"""
        try:
            results = self.followup.check_replies()
            for r in results:
                self.logger.info(
                    f"回复处理: {r['candidate']} -> {r['action']} ({r['status']})"
                )
        except Exception as e:
            self.logger.error(f"回复检查异常: {e}")

    def _task_followup(self):
        """任务：二次触达"""
        try:
            results = self.followup.check_and_followup()
            for r in results:
                self.logger.info(
                    f"二次触达: {r['candidate']} -> {r['action']}"
                )
        except Exception as e:
            self.logger.error(f"二次触达异常: {e}")


def cmd_screen(csv_path: str):
    """单次批量筛选"""
    logger = get_logger()
    screener = ResumeScreener()
    csv_parser = MokaCSVParser()

    logger.info(f"开始筛选: {csv_path}")
    resumes = csv_parser.parse_candidates_csv(csv_path)

    if not resumes:
        logger.warning("未解析到有效简历")
        return

    results = screener.screen_batch(resumes)
    print(f"\n筛选结果:")
    print(f"  待复核: {len(results['pending_review'])} 条")
    print(f"  自动淘汰: {len(results['rejected'])} 条")

    for r in results["pending_review"]:
        risks = ", ".join(r.risk_flags) if r.risk_flags else "无"
        print(f"  [待复核] {r.name} | {r.total_work_years}年 | {r.match_score}分 | {', '.join(r.skills[:3])} | 风险: {risks}")

    report_path = csv_parser.export_screening_report(resumes)
    print(f"\n筛选报告已导出: {report_path}")


def cmd_poll():
    """单次轮询"""
    logger = get_logger()
    settings = get_settings()
    csv_parser = MokaCSVParser()
    boss_cfg = settings.get("boss", {})
    boss = BossPluginAdapter(api_url=boss_cfg.get("plugin_api_url", "http://localhost:8800"))
    scheduler = InterviewScheduler(moka_csv=csv_parser, boss=boss)

    new = scheduler.poll_pending_interviews()
    print(f"新增待约面: {len(new)} 条")
    for s in new:
        print(f"  {s.candidate_name} | {s.applied_position} | 时段数: {len(s.interviewer_time_slots)}")


def main():
    parser = argparse.ArgumentParser(description="招聘自动化控制器")
    parser.add_argument("--daemon", action="store_true", help="启动后台调度守护进程")
    parser.add_argument("--screen", type=str, metavar="CSV_PATH", help="单次批量筛选指定CSV")
    parser.add_argument("--poll", action="store_true", help="单次轮询Moka待约面")
    parser.add_argument("--ui", action="store_true", help="启动Streamlit可视化界面")
    args = parser.parse_args()

    if args.ui:
        import subprocess
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", "ui/app.py",
            "--server.headless", "true",
        ])
    elif args.daemon:
        daemon = RecruitmentDaemon()
        daemon.run_daemon()
    elif args.screen:
        cmd_screen(args.screen)
    elif args.poll:
        cmd_poll()
    else:
        parser.print_help()
        print("\n常用启动方式:")
        print("  python main.py --ui       # 启动可视化界面")
        print("  python main.py --daemon   # 启动后台守护进程")
        print("  python main.py --screen data/moka_csv_import/candidates.csv")


if __name__ == "__main__":
    main()
