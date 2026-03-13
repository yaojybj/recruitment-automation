import { useEffect, useState } from 'react';
import {
  Card, Row, Col, Select, Badge, Table, Tag, Button, Space, Modal, Input, message,
  Statistic, Steps, Tooltip, Popconfirm, Drawer, Timeline, Typography,
} from 'antd';
import {
  CheckCircleOutlined, CloseCircleOutlined, SendOutlined,
  MessageOutlined, CalendarOutlined, CopyOutlined, ReloadOutlined,
  RightOutlined,
} from '@ant-design/icons';
import {
  getPositions, getPipelineSummary, getPipelineByStatus,
  recommendToDept, deptReview, generateMessage, markMessageSent,
  submitCandidateReply, scheduleInterview, jdMatchBatch,
  getResumeTimeline, triggerAutoMatch,
} from '../api';

const { TextArea } = Input;
const { Text } = Typography;

const STAGES = [
  { key: 'pending', label: '待处理', color: '#d9d9d9' },
  { key: 'jd_matched', label: 'JD匹配', color: '#1890ff' },
  { key: 'recommended', label: '已推荐', color: '#722ed1' },
  { key: 'dept_approved', label: '部门通过', color: '#52c41a' },
  { key: 'contacting', label: '联系中', color: '#fa8c16' },
  { key: 'time_sent', label: '待回复', color: '#eb2f96' },
  { key: 'time_confirmed', label: '时间确认', color: '#13c2c2' },
  { key: 'interview_scheduled', label: '已安排', color: '#2f54eb' },
];

export default function Pipeline() {
  const [positions, setPositions] = useState<any[]>([]);
  const [selectedPosition, setSelectedPosition] = useState<number | undefined>();
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [activeStage, setActiveStage] = useState('pending');
  const [stageResumes, setStageResumes] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [messageModal, setMessageModal] = useState<any>(null);
  const [replyModal, setReplyModal] = useState<any>(null);
  const [replyText, setReplyText] = useState('');
  const [timelineDrawer, setTimelineDrawer] = useState<any>(null);
  const [timelineData, setTimelineData] = useState<any[]>([]);

  useEffect(() => {
    getPositions(true).then((r) => setPositions(r.data));
  }, []);

  const refreshData = async () => {
    const summaryRes = await getPipelineSummary(selectedPosition);
    setSummary(summaryRes.data);
    const stageRes = await getPipelineByStatus(activeStage, selectedPosition);
    setStageResumes(stageRes.data);
  };

  useEffect(() => {
    refreshData();
  }, [selectedPosition, activeStage]);

  const handleJDMatch = async () => {
    if (!selectedPosition) {
      message.warning('请先选择岗位');
      return;
    }
    setLoading(true);
    try {
      const res = await jdMatchBatch(selectedPosition);
      message.success(`匹配完成: ${res.data.passed} 通过, ${res.data.failed} 未通过`);
      refreshData();
    } catch (e: any) {
      message.error(e.response?.data?.detail || '匹配失败');
    } finally {
      setLoading(false);
    }
  };

  const handleRecommend = async (ids: number[]) => {
    try {
      await recommendToDept(ids);
      message.success('推荐成功');
      refreshData();
    } catch (e: any) {
      message.error(e.response?.data?.detail || '推荐失败');
    }
  };

  const handleDeptReview = async (id: number, approved: boolean) => {
    await deptReview(id, { approved, reviewer: 'HR' });
    message.success(approved ? '已通过' : '已拒绝');
    refreshData();
  };

  const handleGenMessage = async (id: number) => {
    try {
      const res = await generateMessage(id);
      setMessageModal({ resumeId: id, ...res.data });
    } catch (e: any) {
      message.error(e.response?.data?.detail || '生成消息失败');
    }
  };

  const handleMarkSent = async (id: number) => {
    await markMessageSent(id);
    message.success('已标记为已发送');
    setMessageModal(null);
    refreshData();
  };

  const handleSubmitReply = async () => {
    if (!replyModal || !replyText.trim()) return;
    try {
      const res = await submitCandidateReply(replyModal.id, replyText);
      message.success('回复已录入');
      if (res.data.slot_assigned?.success) {
        message.success('面试时间已自动确认');
      }
      setReplyModal(null);
      setReplyText('');
      refreshData();
    } catch (e: any) {
      message.error('录入失败');
    }
  };

  const handleSchedule = async (id: number) => {
    try {
      const res = await scheduleInterview(id);
      if (res.data.moka?.method === 'manual') {
        Modal.info({ title: 'Moka 操作指引', content: res.data.moka.message, width: 500 });
      }
      message.success('面试已安排');
      refreshData();
    } catch (e: any) {
      message.error(e.response?.data?.detail || '安排失败');
    }
  };

  const showTimeline = async (resumeId: number, name: string) => {
    const res = await getResumeTimeline(resumeId);
    setTimelineData(res.data);
    setTimelineDrawer({ id: resumeId, name });
  };

  const stageColumns: Record<string, any[]> = {
    pending: [
      { title: '姓名', dataIndex: 'name', width: 100 },
      { title: '学历', dataIndex: 'education', width: 70 },
      { title: '年限', dataIndex: 'work_years', width: 70, render: (v: number) => v ? `${v}年` : '-' },
      { title: '公司', dataIndex: 'current_company', width: 150, ellipsis: true },
    ],
    jd_matched: [
      { title: '姓名', dataIndex: 'name', width: 100 },
      {
        title: 'JD匹配分',
        dataIndex: 'jd_match_score',
        width: 100,
        sorter: (a: any, b: any) => (a.jd_match_score || 0) - (b.jd_match_score || 0),
        render: (v: number) => {
          const color = v >= 80 ? '#52c41a' : v >= 60 ? '#fa8c16' : '#f5222d';
          return <span style={{ color, fontWeight: 700, fontSize: 16 }}>{v}</span>;
        },
      },
      { title: '学历', dataIndex: 'education', width: 70 },
      { title: '公司', dataIndex: 'current_company', width: 150, ellipsis: true },
      { title: '岗位', dataIndex: 'position_title', width: 120 },
      {
        title: '操作',
        width: 100,
        render: (_: any, r: any) => (
          <Button size="small" type="primary" onClick={() => handleRecommend([r.id])}>
            推荐 <RightOutlined />
          </Button>
        ),
      },
    ],
    recommended: [
      { title: '姓名', dataIndex: 'name', width: 100 },
      { title: 'JD分', dataIndex: 'jd_match_score', width: 80 },
      { title: '岗位', dataIndex: 'position_title', width: 120 },
      {
        title: '审核',
        width: 160,
        render: (_: any, r: any) => (
          <Space>
            <Button size="small" type="primary" onClick={() => handleDeptReview(r.id, true)}>
              <CheckCircleOutlined /> 通过
            </Button>
            <Popconfirm title="确认拒绝？" onConfirm={() => handleDeptReview(r.id, false)}>
              <Button size="small" danger><CloseCircleOutlined /> 拒绝</Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    dept_approved: [
      { title: '姓名', dataIndex: 'name', width: 100 },
      { title: '电话', dataIndex: 'phone', width: 120 },
      { title: '岗位', dataIndex: 'position_title', width: 120 },
      {
        title: '操作',
        width: 150,
        render: (_: any, r: any) => (
          <Button size="small" type="primary" icon={<MessageOutlined />}
            onClick={() => handleGenMessage(r.id)}>
            生成约面消息
          </Button>
        ),
      },
    ],
    time_sent: [
      { title: '姓名', dataIndex: 'name', width: 100 },
      { title: '岗位', dataIndex: 'position_title', width: 120 },
      {
        title: '操作',
        width: 150,
        render: (_: any, r: any) => (
          <Button size="small" icon={<MessageOutlined />}
            onClick={() => { setReplyModal(r); setReplyText(''); }}>
            录入回复
          </Button>
        ),
      },
    ],
    time_confirmed: [
      { title: '姓名', dataIndex: 'name', width: 100 },
      { title: '面试时间', dataIndex: 'interview_time', width: 200 },
      { title: '岗位', dataIndex: 'position_title', width: 120 },
      {
        title: '操作',
        width: 150,
        render: (_: any, r: any) => (
          <Button size="small" type="primary" icon={<CalendarOutlined />}
            onClick={() => handleSchedule(r.id)}>
            安排面试
          </Button>
        ),
      },
    ],
    interview_scheduled: [
      { title: '姓名', dataIndex: 'name', width: 100 },
      { title: '面试时间', dataIndex: 'interview_time', width: 200 },
      { title: '岗位', dataIndex: 'position_title', width: 120 },
      { title: '状态', render: () => <Tag color="success">已安排</Tag>, width: 80 },
    ],
  };

  const defaultCols = [
    { title: '姓名', dataIndex: 'name', width: 100 },
    { title: 'JD分', dataIndex: 'jd_match_score', width: 80 },
    { title: '岗位', dataIndex: 'position_title', width: 120 },
    { title: '状态', dataIndex: 'status', width: 100 },
  ];

  const currentCols = [
    ...(stageColumns[activeStage] || defaultCols),
    {
      title: '',
      width: 50,
      render: (_: any, r: any) => (
        <Tooltip title="查看流程时间线">
          <Button type="text" size="small" onClick={() => showTimeline(r.id, r.name)}>
            <CalendarOutlined />
          </Button>
        </Tooltip>
      ),
    },
  ];

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
          <Space>
            <span style={{ fontWeight: 500 }}>岗位：</span>
            <Select
              placeholder="全部岗位"
              allowClear
              style={{ width: 220 }}
              value={selectedPosition}
              onChange={setSelectedPosition}
              options={positions.map((p) => ({ value: p.id, label: `${p.title}${p.department ? ` (${p.department})` : ''}` }))}
            />
          </Space>
          <Space>
            <Button onClick={() => triggerAutoMatch().then(() => { message.success('自动匹配完成'); refreshData(); })}>
              <ReloadOutlined /> 自动匹配
            </Button>
            <Button type="primary" loading={loading} onClick={handleJDMatch} disabled={!selectedPosition}>
              执行 JD 匹配
            </Button>
          </Space>
        </Space>
      </Card>

      <Row gutter={[8, 8]} style={{ marginBottom: 16 }}>
        {STAGES.map((stage) => (
          <Col key={stage.key} xs={6} sm={3}>
            <Card
              hoverable
              size="small"
              onClick={() => setActiveStage(stage.key)}
              style={{
                borderTop: `3px solid ${stage.color}`,
                background: activeStage === stage.key ? '#f0f5ff' : '#fff',
                cursor: 'pointer',
              }}
            >
              <Statistic
                title={<span style={{ fontSize: 12 }}>{stage.label}</span>}
                value={summary[stage.key] || 0}
                valueStyle={{ fontSize: 20, color: stage.color }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card
        title={
          <Space>
            <Badge color={STAGES.find((s) => s.key === activeStage)?.color} />
            {STAGES.find((s) => s.key === activeStage)?.label}
            <Tag>{stageResumes.length} 人</Tag>
          </Space>
        }
      >
        <Table
          rowKey="id"
          columns={currentCols}
          dataSource={stageResumes}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 人` }}
          size="middle"
        />
      </Card>

      {/* 约面消息弹窗 */}
      <Modal
        title="发送面试邀约"
        open={!!messageModal}
        onCancel={() => setMessageModal(null)}
        width={600}
        footer={[
          <Button key="copy" icon={<CopyOutlined />} onClick={() => {
            navigator.clipboard.writeText(messageModal?.message || '');
            message.success('已复制到剪贴板');
          }}>复制消息</Button>,
          <Button key="sent" type="primary" icon={<SendOutlined />} onClick={() => handleMarkSent(messageModal?.resumeId)}>
            已发送给候选人
          </Button>,
        ]}
      >
        {messageModal && (
          <>
            <p style={{ color: '#666', marginBottom: 12 }}>{messageModal.instruction}</p>
            <TextArea value={messageModal.message} rows={10} readOnly
              style={{ background: '#fafafa', fontFamily: 'monospace' }} />
          </>
        )}
      </Modal>

      {/* 录入回复弹窗 */}
      <Modal
        title={`录入候选人回复 - ${replyModal?.name}`}
        open={!!replyModal}
        onOk={handleSubmitReply}
        onCancel={() => { setReplyModal(null); setReplyText(''); }}
        okText="提交"
      >
        <p style={{ color: '#666', marginBottom: 8 }}>
          将候选人在 Boss 直聘上的回复粘贴到下方。系统会自动识别时间选择。
        </p>
        <TextArea
          rows={4}
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          placeholder='例如: "我选1" 或 "3月20日下午2点可以"'
        />
      </Modal>

      {/* 时间线抽屉 */}
      <Drawer
        title={`${timelineDrawer?.name} - 流程时间线`}
        open={!!timelineDrawer}
        onClose={() => setTimelineDrawer(null)}
        width={400}
      >
        <Timeline
          items={timelineData.map((log) => ({
            color: log.to === 'rejected' || log.to === 'eliminated' || log.to === 'dept_rejected' ? 'red' : 'green',
            children: (
              <div>
                <div style={{ fontWeight: 500 }}>
                  {STAGES.find((s) => s.key === log.to)?.label || log.to}
                </div>
                <div style={{ fontSize: 12, color: '#888' }}>{log.detail}</div>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {log.time ? new Date(log.time).toLocaleString('zh-CN') : ''}
                  {log.operator ? ` · ${log.operator}` : ''}
                </Text>
              </div>
            ),
          }))}
        />
      </Drawer>
    </div>
  );
}
