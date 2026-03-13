# 招聘自动化控制器

纯本地 Python 控制器，实现「简历精准筛选 → 自动化约面 → 候选人二次触达 → 面试自动生成」全流程自动化。

## 架构概览

```
├── config/                  # 配置文件（YAML，无需改代码即可调整规则）
│   ├── settings.yaml        # 系统主配置（API、轮询频率、日志等）
│   ├── screening_rules.yaml # 筛选规则（按职位可独立配置）
│   └── message_templates.yaml # 约面话术模板
├── core/                    # 核心业务模块
│   ├── screener.py          # 模块1: 简历精准筛选（分层筛选 + 打分 + 风险标记）
│   ├── scheduler.py         # 模块2: 自动约面调度（状态监听 + 时间匹配 + 面试创建）
│   ├── follow_up.py         # 模块3: 二次触达管理（未回复检测 + Boss重发 + 超时标记）
│   └── time_matcher.py      # 时间解析与匹配引擎
├── adapters/                # 外部系统适配器
│   ├── moka_api.py          # Moka API 适配（鉴权 + 限流 + 重试）
│   ├── moka_csv.py          # Moka CSV 兜底方案
│   └── boss_plugin.py       # Boss 直聘插件通信
├── models/                  # 数据模型
│   ├── resume.py            # 简历模型
│   ├── interview.py         # 面试/约面模型
│   └── candidate.py         # 候选人跟踪模型
├── ui/
│   └── app.py               # Streamlit 可视化界面
├── utils/                   # 工具层
│   ├── logger.py            # 双轨日志（系统日志 + 审计日志）
│   ├── crypto.py            # 凭据加密存储
│   ├── notifier.py          # 桌面通知
│   └── config_loader.py     # 配置加载器
├── data/                    # 运行时数据
│   ├── logs/                # 日志文件
│   └── exports/             # 导出报告
├── main.py                  # 统一入口
└── requirements.txt         # Python 依赖
```

## 快速开始

### 1. 安装依赖

```bash
cd 招聘自动化控制器
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置

编辑 `config/settings.yaml` 设置：
- Moka API 密钥（或在 UI 中加密存储）
- Boss 直聘插件地址
- 轮询频率、重试策略等

编辑 `config/screening_rules.yaml` 设置：
- 各职位的硬门槛（学历、年限、技能、薪资）
- 打分权重
- 自动过滤规则

编辑 `config/message_templates.yaml` 设置：
- 首次约面话术
- 二次触达话术
- 面试确认话术

### 3. 启动

```bash
# 方式1: 启动可视化界面（推荐）
python main.py --ui

# 方式2: 启动后台守护进程（自动轮询 + 触达）
python main.py --daemon

# 方式3: 单次筛选
python main.py --screen data/moka_csv_import/candidates.csv

# 方式4: 直接启动 Streamlit
streamlit run ui/app.py
```

## 四大核心模块

### 模块1: 简历精准筛选

**流程**: CSV导入 → 自动过滤 → 硬门槛检查 → 匹配度打分(≥85分) → 风险标记 → 待复核清单

- **自动过滤层**: 无项目经验 / 无作品集 / 关键词堆砌 → 直接淘汰
- **硬门槛层**: 学历、工作年限、城市、核心技能、薪资区间 → 100%必须满足
- **打分层**: 行业匹配(20) + 项目经验(25) + 技能熟练度(25) + 稳定性(15) + 学历(10) + 作品集(5) = 100分
- **人工复核**: 仅≥85分的简历进入复核清单，支持批量通过/驳回
- **准确率闭环**: 读取 Moka 备注中 "筛错" 关键词，自动统计准确率，<80%时弹窗提醒

### 模块2: 自动约面

**流程**: 监听Moka待约面 → 匹配Boss候选人 → 发送时间选项 → 解析回复 → 创建面试 → 发送邀约

- 每5分钟轮询 Moka 待约面状态
- 通过 Boss 插件向候选人发送面试官可面时间
- 解析候选人回复（编号选择 / 直接时间 / 拒绝）
- 匹配成功后自动在 Moka 创建面试并发送邀约

### 模块3: 二次触达

**流程**: 24小时未回复 → Boss二次发送 → 再24小时 → 第三次 → 仍未回复 → 标记失败

- 24小时内仅发送1次
- 最多重试2次（共3次触达机会）
- 姓名重复匹配歧义时不自动发送，标记人工确认
- 候选人拒绝或超时未回复 → Moka 自动标记状态

### 模块4: Moka 适配

- **API模式**: 支持 token 鉴权、自动刷新、限流重试(3次)
- **CSV兜底**: API 不可用时，解析 Moka 定时导出的 CSV 文件
- 可在 `settings.yaml` 中切换模式

## 安全特性

- 敏感信息（API密钥、Cookie）通过 PBKDF2+Fernet 加密存储
- 双轨日志：系统日志(system.log) + 审计日志(audit_records.jsonl)
- 所有操作完整可追溯，支持按日期导出
- 异常仅提醒人工，不中断整体流程
- 24小时内同一候选人仅发送1次约面消息

## 技术约束

- 纯本地运行，无需服务器
- 无龙虾 RPA、无浏览器自动化、无界面模拟
- 仅通过 API / CSV / 本地脚本实现
- Python 3.10+
