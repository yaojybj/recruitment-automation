# 招聘自动化系统 v2

Boss 直聘简历自动入池 + 规则筛选 + 招聘管理后台

## 架构

```
Boss直聘 → 邮件通知 → 邮件监听服务 → 简历解析 → 本地简历池(SQLite)
                                                        ↓
手动下载 → 文件夹监控 / 手动上传  ──────────→  简历解析 → 本地简历池
                                                        ↓
                                              Web 管理后台(React)
                                              · 数据看板
                                              · 简历池管理
                                              · 岗位管理
                                              · 筛选规则配置
                                              · 邮箱设置
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python + FastAPI |
| 数据库 | SQLite + SQLAlchemy |
| 简历解析 | pdfplumber + python-docx + 正则提取 |
| 邮件监听 | imaplib (IMAP 协议) |
| 文件夹监控 | 定时扫描 |
| 定时任务 | APScheduler |
| 前端 | React + TypeScript + Ant Design |
| 图表 | Recharts |

## 快速启动

### 一键启动

```bash
./start.sh
```

### 手动启动

**后端：**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**前端：**

```bash
cd frontend
npm install
npm run dev
```

### 访问

- 前端界面: http://localhost:3000
- 后端 API 文档: http://localhost:8000/docs
- 简历投递箱文件夹: `backend/uploads/inbox/`

## 功能说明

### 1. 简历入池

三种方式，可同时使用：

- **邮件自动入池**：配置邮箱后，系统每 2 分钟检查一次，自动将 Boss 直聘的简历通知邮件解析入库
- **文件夹监控**：将简历文件拖入 `backend/uploads/inbox/`，系统每 30 秒自动扫描解析
- **手动上传**：在管理后台直接上传 PDF/Word/TXT 格式的简历

### 2. 岗位管理

- 创建岗位（名称、部门、地点、薪资范围、人数）
- 每个岗位可配置独立的筛选规则

### 3. 筛选规则

每个岗位可以配置多条筛选规则，支持：

- **淘汰项**：不满足直接淘汰（如学历不达标）
- **加分项**：满足则获得加权分数
- **可用字段**：学历、工作年限、年龄、城市、学校、专业、技能、性别、薪资、简历全文等
- **比较方式**：等于、包含、大于、小于、正则匹配等

### 4. 简历管理

- 列表查看所有简历，支持搜索、筛选、排序
- 查看简历详情，包括结构化信息和原文
- 批量操作：通过、淘汰、分配岗位、执行筛选
- 状态流转：待处理 → 已通过/已淘汰 → 面试中 → 已发Offer → 已入职

### 5. 数据看板

- 简历总数、待处理数、通过率等关键指标
- 入池趋势图（近 30 天）
- 来源分布（邮件/上传/文件夹）
- 操作日志

## 邮箱配置

在「系统设置」页面配置邮箱：

| 邮箱类型 | IMAP 服务器 | 端口 | 备注 |
|---------|-----------|-----|-----|
| QQ 邮箱 | imap.qq.com | 993 | 密码用授权码 |
| 163 邮箱 | imap.163.com | 993 | 密码用授权码 |
| Gmail | imap.gmail.com | 993 | 需应用专用密码 |
| 企业微信邮箱 | imap.exmail.qq.com | 993 | - |

发件人过滤关键词默认为 `bosszhipin`，匹配 Boss 直聘的发件地址。
