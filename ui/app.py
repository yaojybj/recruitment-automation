"""
招聘自动化控制器 - Streamlit 可视化界面
核心体验：一键从 Moka 同步简历 → 自动筛选打分 → 直接在界面复核通过/驳回
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

import json
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd

from core.screener import ResumeScreener
from core.scheduler import InterviewScheduler
from core.follow_up import FollowUpManager
from models.resume import Resume, ScreeningStatus
from models.interview import InterviewSchedule, InterviewStatus
from adapters.moka_api import MokaAPI, MokaAPIError
from adapters.moka_csv import MokaCSVParser
from adapters.boss_plugin import BossPluginAdapter
from utils.config_loader import get_settings, reload_settings
from utils.logger import get_logger
from utils.crypto import (
    credential_store_exists, init_credential_store,
    save_credentials, load_credentials,
)


st.set_page_config(
    page_title="招聘自动化控制器",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_moka_api() -> MokaAPI | None:
    """从配置/加密存储中初始化 Moka API"""
    settings = get_settings()
    moka_cfg = settings.get("moka", {})

    if not moka_cfg.get("api_enabled", False):
        return None

    org_id = moka_cfg.get("org_id", "")
    api_key = moka_cfg.get("api_key", "")
    client_id = moka_cfg.get("client_id", "")
    client_secret = moka_cfg.get("client_secret", "")

    if not org_id:
        return None
    if not api_key and not (client_id and client_secret):
        return None

    return MokaAPI(
        org_id=org_id,
        api_key=api_key,
        client_id=client_id,
        client_secret=client_secret,
        retry_max=moka_cfg.get("retry_max", 3),
    )


def get_components():
    if "screener" not in st.session_state:
        st.session_state.screener = ResumeScreener()
    if "moka_api" not in st.session_state:
        st.session_state.moka_api = init_moka_api()
    if "moka_csv" not in st.session_state:
        st.session_state.moka_csv = MokaCSVParser()
    return st.session_state.screener, st.session_state.moka_api


def main():
    st.sidebar.title("招聘自动化控制器")

    moka_api = st.session_state.get("moka_api")
    if moka_api:
        st.sidebar.success("Moka API 已连接")
    else:
        st.sidebar.warning("Moka API 未配置")

    page = st.sidebar.radio("功能导航", [
        "简历筛选与复核",
        "约面管理",
        "筛选准确率",
        "系统配置",
        "操作日志",
    ])

    screener, moka_api = get_components()

    if page == "简历筛选与复核":
        page_screening(screener, moka_api)
    elif page == "约面管理":
        page_scheduling()
    elif page == "筛选准确率":
        page_accuracy(screener)
    elif page == "系统配置":
        page_config()
    elif page == "操作日志":
        page_logs()


# ==================== 简历筛选与复核 ====================

def page_screening(screener: ResumeScreener, moka_api: MokaAPI | None):
    st.header("简历筛选与复核")

    # ---- 顶部操作区 ----
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        stage_option = st.selectbox("Moka 阶段", [
            "all - 全部阶段",
            "preliminary_filter - 初筛",
            "filter - 筛选型阶段",
            "interview - 面试型阶段",
        ])
        stage_key = stage_option.split(" - ")[0]

    with col2:
        st.write("")  # 占位
        st.write("")
        sync_btn = st.button("🔄 从 Moka 同步简历并筛选", type="primary",
                              use_container_width=True)

    with col3:
        st.write("")
        st.write("")
        csv_fallback = st.button("📂 CSV 兜底导入", use_container_width=True)

    # ---- 同步并筛选 ----
    if sync_btn:
        if moka_api:
            with st.spinner("正在从 Moka 拉取候选人数据..."):
                try:
                    candidates = moka_api.get_moved_applications(stage=stage_key)
                    if not candidates:
                        st.info("该阶段暂无新的候选人数据")
                    else:
                        st.success(f"从 Moka 拉取到 {len(candidates)} 条候选人")
                        resumes = []
                        for c in candidates:
                            resume_data = moka_api.parse_candidate_to_resume_data(c)
                            resumes.append(Resume.from_dict(resume_data))

                        with st.spinner(f"正在筛选 {len(resumes)} 份简历..."):
                            results = screener.screen_batch(resumes)

                        st.success(
                            f"筛选完成！待复核 **{len(results['pending_review'])}** 条，"
                            f"自动淘汰 **{len(results['rejected'])}** 条"
                        )

                        if results["rejected"]:
                            with st.expander(f"查看自动淘汰详情 ({len(results['rejected'])} 条)", expanded=False):
                                _show_rejected_table(results["rejected"])

                except MokaAPIError as e:
                    st.error(f"Moka API 调用失败: {e}")
                    st.info("请检查「系统配置」中的 API 密钥是否正确，或使用 CSV 兜底导入")
        else:
            st.error("Moka API 未配置！请先到「系统配置」页面填写 API 密钥，或使用右侧 CSV 兜底导入")

    # ---- CSV 兜底 ----
    if csv_fallback:
        st.session_state.show_csv_upload = True

    if st.session_state.get("show_csv_upload"):
        with st.expander("CSV 兜底导入", expanded=True):
            uploaded = st.file_uploader("上传 Moka 导出的候选人 CSV", type=["csv"])
            if uploaded and st.button("开始筛选 CSV"):
                csv_parser = st.session_state.moka_csv
                import_path = Path("./data/moka_csv_import")
                import_path.mkdir(parents=True, exist_ok=True)
                save_path = import_path / uploaded.name
                save_path.write_bytes(uploaded.getvalue())
                with st.spinner("筛选中..."):
                    resumes = csv_parser.parse_candidates_csv(str(save_path))
                    if resumes:
                        results = screener.screen_batch(resumes)
                        st.success(
                            f"筛选完成！待复核 {len(results['pending_review'])} 条，"
                            f"自动淘汰 {len(results['rejected'])} 条"
                        )
                    else:
                        st.warning("CSV 中未解析到有效简历")

    st.divider()

    # ---- 待复核清单 ----
    st.subheader("📋 待复核清单")
    queue = screener.load_review_queue()

    if not queue:
        st.info("暂无待复核简历。点击上方「从 Moka 同步简历并筛选」获取最新数据。")
        return

    st.write(f"共 **{len(queue)}** 条待复核")

    review_data = []
    for r in queue:
        review_data.append({
            "姓名": r.name,
            "应聘职位": r.applied_position,
            "工作年限": f"{r.total_work_years}年",
            "匹配分": r.match_score,
            "核心技能": ", ".join(r.skills[:5]),
            "学历": r.education,
            "城市": r.city,
            "风险点": "; ".join(r.risk_flags) if r.risk_flags else "✓ 无",
        })

    df = pd.DataFrame(review_data)
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={
                     "匹配分": st.column_config.ProgressColumn(
                         "匹配分", min_value=0, max_value=100, format="%d"
                     ),
                 })

    st.write("---")
    st.write("**批量操作：**")
    col_a, col_b, col_c, col_d = st.columns([1, 1, 2, 1])

    with col_a:
        select_mode = st.radio("选择范围", ["全部", "按分数线", "手动输入序号"], horizontal=True, label_visibility="collapsed")

    selected_indices = list(range(len(queue)))
    if select_mode == "按分数线":
        with col_b:
            min_score = st.number_input("最低分", min_value=0, max_value=100, value=85)
        selected_indices = [i for i, r in enumerate(queue) if r.match_score >= min_score]
        st.caption(f"已选中 {len(selected_indices)}/{len(queue)} 条（≥{min_score}分）")
    elif select_mode == "手动输入序号":
        with col_b:
            idx_input = st.text_input("输入序号（如 1,3,5）", "")
        if idx_input:
            try:
                selected_indices = [int(x.strip()) - 1 for x in idx_input.split(",")]
                selected_indices = [i for i in selected_indices if 0 <= i < len(queue)]
            except ValueError:
                st.warning("请输入有效的序号")
                selected_indices = []
        st.caption(f"已选中 {len(selected_indices)} 条")

    with col_c:
        reject_reason = st.text_input("驳回原因（驳回时填写）", placeholder="如：技能不符 / 年限不足")

    with col_d:
        st.write("")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ 批量通过", type="primary", use_container_width=True):
                selected = [queue[i] for i in selected_indices]
                if selected:
                    screener.batch_approve(selected)
                    screener.update_review_queue(selected)
                    st.success(f"已通过 {len(selected)} 条简历")
                    st.rerun()
        with c2:
            if st.button("❌ 批量驳回", use_container_width=True):
                selected = [queue[i] for i in selected_indices]
                if selected:
                    screener.batch_reject(selected, reason=reject_reason)
                    screener.update_review_queue(selected)
                    st.success(f"已驳回 {len(selected)} 条")
                    st.rerun()

    # ---- 筛选历史 ----
    with st.expander("📜 筛选历史"):
        history_file = Path("./data/screening_history.json")
        if history_file.exists():
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
            if history:
                st.dataframe(
                    pd.DataFrame([
                        {
                            "姓名": h.get("name", ""),
                            "职位": h.get("applied_position", ""),
                            "分数": h.get("match_score", 0),
                            "状态": h.get("screening_status", ""),
                            "原因": h.get("reject_reason", ""),
                            "时间": h.get("created_at", "")[:16],
                        }
                        for h in history[-100:]
                    ]),
                    use_container_width=True, hide_index=True,
                )


def _show_rejected_table(rejected: list[Resume]):
    st.dataframe(
        pd.DataFrame([
            {
                "姓名": r.name,
                "职位": r.applied_position,
                "淘汰原因": r.reject_reason,
                "分数": r.match_score,
                "学历": r.education,
            }
            for r in rejected
        ]),
        use_container_width=True, hide_index=True,
    )


# ==================== 约面管理 ====================

def page_scheduling():
    st.header("约面管理")
    st.info("约面管理功能依赖后台守护进程自动运行。启动方式：`python main.py --daemon`")

    schedules_file = Path("./data/interview_schedules.json")
    if not schedules_file.exists():
        st.info("暂无约面记录")
        return

    with open(schedules_file, "r", encoding="utf-8") as f:
        schedules = json.load(f)

    if not schedules:
        st.info("暂无约面记录")
        return

    STATUS_LABELS = {
        "pending_schedule": "⏳ 待约面",
        "time_sent": "📤 已发送时间",
        "followup_1": "🔄 第1次触达",
        "followup_2": "🔄 第2次触达",
        "time_confirmed": "✅ 时间已确认",
        "interview_created": "✅ 面试已创建",
        "invite_sent": "✅ 邀约已发送",
        "no_response": "⛔ 未回复",
        "candidate_rejected": "⛔ 候选人拒绝",
        "manual_required": "⚠️ 需人工处理",
        "failed": "❌ 失败",
    }

    data = []
    for s in schedules:
        status = s.get("status", "")
        matched = s.get("matched_slot")
        data.append({
            "候选人": s.get("candidate_name", ""),
            "职位": s.get("applied_position", ""),
            "面试官": s.get("interviewer_name", ""),
            "状态": STATUS_LABELS.get(status, status),
            "触达次数": s.get("followup_count", 0),
            "确认时间": f"{matched['date']} {matched['start_time']}" if matched else "-",
            "备注": s.get("error_message", "") or "-",
        })

    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)


# ==================== 筛选准确率 ====================

def page_accuracy(screener: ResumeScreener):
    st.header("筛选准确率")
    st.info("准确率基于 Moka 简历备注中含「筛错」关键词的记录统计。如 '筛错-技能不符'、'筛错-年限不符'")

    col1, col2 = st.columns(2)
    with col1:
        position_filter = st.text_input("按职位筛选（留空=全部）", "")
    with col2:
        if st.button("计算准确率", type="primary"):
            result = screener.calculate_accuracy(position=position_filter)
            st.metric(
                f"{'职位 ' + position_filter if position_filter else '总体'} 准确率",
                result["accuracy_percent"],
            )
            st.write(f"- 已通过简历总数: {result['total_approved']}")
            st.write(f"- 筛错数量: {result['error_count']}")
            if result["accuracy"] < 0.80:
                st.warning("⚠️ 准确率低于 80%，建议在 config/screening_rules.yaml 中收紧筛选规则！")


# ==================== 系统配置 ====================

def page_config():
    st.header("系统配置")

    tab1, tab2, tab3 = st.tabs(["Moka API 配置", "筛选规则预览", "系统参数"])

    with tab1:
        st.subheader("Moka API 连接设置")
        st.write("在下方填写 Moka Open API 的密钥信息，保存后即可使用「从 Moka 同步」功能。")

        settings = get_settings()
        moka_cfg = settings.get("moka", {})

        api_enabled = st.checkbox("启用 Moka API", value=moka_cfg.get("api_enabled", False))
        org_id = st.text_input("Moka Org ID（租户标识）", value=moka_cfg.get("org_id", ""),
                               help="在 Moka 后台 → 设置 → 公司信息中查看")

        st.write("**鉴权方式（二选一）：**")

        auth_tab1, auth_tab2 = st.tabs(["方式1：API Key（Basic Auth）", "方式2：OAuth2（clientID + clientSecret）"])

        with auth_tab1:
            api_key = st.text_input("API Key", value=moka_cfg.get("api_key", ""), type="password",
                                    help="向 Moka CSM（客户成功经理）索取")

        with auth_tab2:
            client_id = st.text_input("Client ID", value=moka_cfg.get("client_id", ""),
                                      help="向 Moka CSM 索取")
            client_secret = st.text_input("Client Secret", value=moka_cfg.get("client_secret", ""),
                                          type="password")

        if st.button("保存并测试连接", type="primary"):
            import yaml
            settings["moka"]["api_enabled"] = api_enabled
            settings["moka"]["org_id"] = org_id
            settings["moka"]["api_key"] = api_key
            settings["moka"]["client_id"] = client_id
            settings["moka"]["client_secret"] = client_secret

            config_path = Path("./config/settings.yaml")
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(settings, f, allow_unicode=True, default_flow_style=False)

            reload_settings()

            if api_enabled and org_id and (api_key or (client_id and client_secret)):
                with st.spinner("正在测试 Moka API 连接..."):
                    try:
                        api = MokaAPI(
                            org_id=org_id,
                            api_key=api_key,
                            client_id=client_id,
                            client_secret=client_secret,
                        )
                        result = api.get_moved_applications(stage="all")
                        st.success(f"✅ 连接成功！获取到 {len(result)} 条候选人数据")
                        st.session_state.moka_api = api
                    except Exception as e:
                        st.error(f"❌ 连接失败: {e}")
                        st.write("请检查：")
                        st.write("1. Org ID 是否正确")
                        st.write("2. API Key 或 Client ID/Secret 是否有效")
                        st.write("3. 网络是否可以访问 api.mokahr.com")
            else:
                st.session_state.moka_api = None
                st.info("已保存配置（API 未启用或密钥未填写）")

    with tab2:
        st.subheader("当前筛选规则")
        rules_path = Path("./config/screening_rules.yaml")
        if rules_path.exists():
            st.code(rules_path.read_text(encoding="utf-8"), language="yaml")
        st.caption("修改请直接编辑 config/screening_rules.yaml 文件")

    with tab3:
        st.subheader("系统参数总览")
        st.json(get_settings())
        st.caption("修改请编辑 config/settings.yaml")
        if st.button("重新加载配置"):
            reload_settings()
            st.session_state.pop("moka_api", None)
            st.success("配置已重新加载")
            st.rerun()


# ==================== 操作日志 ====================

def page_logs():
    st.header("操作日志")

    tab1, tab2 = st.tabs(["审计日志", "系统日志"])

    with tab1:
        audit_file = Path("./data/logs/audit_records.jsonl")
        if audit_file.exists():
            records = []
            with open(audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

            if records:
                recent = records[-200:]
                df = pd.DataFrame(recent)
                display_cols = [c for c in ["timestamp", "action", "module", "target", "result"] if c in df.columns]
                st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
                st.caption(f"显示最近 {len(recent)} 条，共 {len(records)} 条")

                if st.button("导出日志"):
                    logger = get_logger()
                    path = logger.export_audit_logs()
                    st.success(f"日志已导出: {path}")
            else:
                st.info("暂无审计日志")
        else:
            st.info("暂无审计日志")

    with tab2:
        system_log = Path("./data/logs/system.log")
        if system_log.exists():
            content = system_log.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            st.code("\n".join(lines[-80:]), language="log")
            st.caption(f"显示最近 {min(80, len(lines))} 行，共 {len(lines)} 行")
        else:
            st.info("暂无系统日志")


if __name__ == "__main__":
    main()
