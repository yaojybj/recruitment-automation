import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from .database import init_db, SessionLocal
from .services.email_monitor import check_email_for_resumes
from .services.folder_watcher import scan_folder
from .services.jd_matcher import auto_match_new_resumes
from .api import positions, resumes, rules, screening, email_config, dashboard, pipeline, interview_slots, extension

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def scheduled_email_check():
    db = SessionLocal()
    try:
        results = check_email_for_resumes(db)
        if results:
            logger.info(f"定时邮件检查: 导入 {len(results)} 份简历")
    except Exception as e:
        logger.error(f"定时邮件检查失败: {e}")
    finally:
        db.close()


def scheduled_folder_scan():
    db = SessionLocal()
    try:
        results = scan_folder(db)
        if results:
            logger.info(f"文件夹扫描: 导入 {len(results)} 份简历")
    except Exception as e:
        logger.error(f"文件夹扫描失败: {e}")
    finally:
        db.close()


def scheduled_auto_match():
    db = SessionLocal()
    try:
        auto_match_new_resumes(db)
    except Exception as e:
        logger.error(f"自动JD匹配失败: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("数据库初始化完成")

    scheduler.add_job(scheduled_email_check, "interval", minutes=2, id="email_check")
    scheduler.add_job(scheduled_folder_scan, "interval", seconds=30, id="folder_scan")
    scheduler.add_job(scheduled_auto_match, "interval", minutes=3, id="auto_jd_match")
    scheduler.start()
    logger.info("后台任务调度器已启动")

    yield

    scheduler.shutdown()
    logger.info("后台任务调度器已停止")


app = FastAPI(
    title="招聘自动化系统",
    description="Boss 直聘简历自动入池、规则筛选、招聘管理后台",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(resumes.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(screening.router, prefix="/api")
app.include_router(email_config.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(interview_slots.router, prefix="/api")
app.include_router(extension.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "招聘自动化系统运行中"}
