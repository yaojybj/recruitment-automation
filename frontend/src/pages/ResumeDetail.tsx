import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Descriptions, Tag, Button, Space, Select, Spin, message, Divider, Table, Modal, Input,
  Tabs, Timeline, Badge, Row, Col,
} from 'antd';
import {
  ArrowLeftOutlined, CheckCircleOutlined, CloseCircleOutlined, EditOutlined,
} from '@ant-design/icons';
import { getResume, updateResume, getPositions, getScreeningLogs, screenResume } from '../api';

const statusMap: Record<string, { label: string; color: string }> = {
  pending: { label: '待处理', color: 'default' },
  jd_matched: { label: 'JD匹配', color: 'blue' },
  recommended: { label: '已推荐', color: 'purple' },
  dept_approved: { label: '部门通过', color: 'success' },
  dept_rejected: { label: '部门拒绝', color: 'error' },
  contacting: { label: '联系中', color: 'orange' },
  time_sent: { label: '待回复', color: 'magenta' },
  time_confirmed: { label: '时间确认', color: 'cyan' },
  interview_scheduled: { label: '已安排面试', color: 'geekblue' },
  interview_done: { label: '面试完成', color: 'lime' },
  offer: { label: '已发Offer', color: 'gold' },
  onboard: { label: '已入职', color: 'green' },
  rejected: { label: '已淘汰', color: 'error' },
  eliminated: { label: '已淘汰', color: 'red' },
};

export default function ResumeDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [resume, setResume] = useState<any>(null);
  const [positions, setPositions] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [remarkModalOpen, setRemarkModalOpen] = useState(false);
  const [remark, setRemark] = useState('');

  useEffect(() => {
    Promise.all([
      getResume(Number(id)),
      getPositions(true),
      getScreeningLogs(Number(id)),
    ]).then(([resumeRes, posRes, logsRes]) => {
      setResume(resumeRes.data);
      setPositions(posRes.data);
      setLogs(logsRes.data);
      setRemark(resumeRes.data.remark || '');
      setLoading(false);
    });
  }, [id]);

  const handleStatusChange = async (status: string) => {
    await updateResume(Number(id), { status });
    message.success('状态已更新');
    const res = await getResume(Number(id));
    setResume(res.data);
  };

  const handleAssignPosition = async (positionId: number) => {
    await updateResume(Number(id), { position_id: positionId });
    message.success('岗位已分配');
    const res = await getResume(Number(id));
    setResume(res.data);
  };

  const handleScreen = async () => {
    if (!resume.position_id) {
      message.warning('请先分配岗位');
      return;
    }
    const res = await screenResume(Number(id), resume.position_id);
    message.success(res.data.passed ? '筛选通过' : '筛选未通过');
    const [resumeRes, logsRes] = await Promise.all([
      getResume(Number(id)),
      getScreeningLogs(Number(id)),
    ]);
    setResume(resumeRes.data);
    setLogs(logsRes.data);
  };

  const handleSaveRemark = async () => {
    await updateResume(Number(id), { remark });
    message.success('备注已保存');
    setRemarkModalOpen(false);
    const res = await getResume(Number(id));
    setResume(res.data);
  };

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />;
  if (!resume) return <div>简历不存在</div>;

  const info = resume;

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/resumes')}>返回列表</Button>
      </Space>

      <Row gutter={16}>
        <Col xs={24} lg={16}>
          <Card
            title={
              <Space>
                <span style={{ fontSize: 20, fontWeight: 600 }}>{info.candidate_name || '未知'}</span>
                <Tag color={statusMap[info.status]?.color}>{statusMap[info.status]?.label}</Tag>
                {info.screening_score != null && (
                  <Badge
                    count={`${info.screening_score}分`}
                    style={{
                      backgroundColor: info.screening_score >= 70 ? '#10b981' : info.screening_score >= 40 ? '#f59e0b' : '#ef4444',
                    }}
                  />
                )}
              </Space>
            }
            extra={
              <Space>
                <Button icon={<EditOutlined />} onClick={() => setRemarkModalOpen(true)}>备注</Button>
                <Button onClick={handleScreen} type="primary" ghost>执行筛选</Button>
                <Select
                  placeholder="更新状态"
                  style={{ width: 120 }}
                  onChange={handleStatusChange}
                  options={Object.entries(statusMap).map(([k, v]) => ({ value: k, label: v.label }))}
                />
              </Space>
            }
          >
            <Descriptions column={{ xs: 1, sm: 2, md: 3 }} bordered size="small">
              <Descriptions.Item label="手机">{info.phone || '-'}</Descriptions.Item>
              <Descriptions.Item label="邮箱">{info.email || '-'}</Descriptions.Item>
              <Descriptions.Item label="性别">{info.gender || '-'}</Descriptions.Item>
              <Descriptions.Item label="年龄">{info.age ? `${info.age}岁` : '-'}</Descriptions.Item>
              <Descriptions.Item label="城市">{info.city || '-'}</Descriptions.Item>
              <Descriptions.Item label="学历">{info.education || '-'}</Descriptions.Item>
              <Descriptions.Item label="学校">{info.school || '-'}</Descriptions.Item>
              <Descriptions.Item label="专业">{info.major || '-'}</Descriptions.Item>
              <Descriptions.Item label="工作年限">{info.work_years ? `${info.work_years}年` : '-'}</Descriptions.Item>
              <Descriptions.Item label="当前公司">{info.current_company || '-'}</Descriptions.Item>
              <Descriptions.Item label="当前职位">{info.current_position || '-'}</Descriptions.Item>
              <Descriptions.Item label="期望薪资">
                {info.expected_salary_min && info.expected_salary_max
                  ? `${info.expected_salary_min / 1000}K - ${info.expected_salary_max / 1000}K`
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="关联岗位" span={2}>
                <Select
                  placeholder="选择岗位"
                  style={{ width: 200 }}
                  value={info.position_id}
                  onChange={handleAssignPosition}
                  options={positions.map((p: any) => ({ value: p.id, label: p.title }))}
                  allowClear
                />
              </Descriptions.Item>
              <Descriptions.Item label="来源">
                {{ email: '邮件导入', manual_upload: '手动上传', folder_import: '文件夹导入' }[info.source as string] || info.source}
              </Descriptions.Item>
            </Descriptions>

            {info.skills?.length > 0 && (
              <>
                <Divider plain>技能标签</Divider>
                <Space wrap>
                  {info.skills.map((s: string, i: number) => (
                    <Tag key={i} color="blue">{s}</Tag>
                  ))}
                </Space>
              </>
            )}

            {info.remark && (
              <>
                <Divider plain>备注</Divider>
                <p style={{ whiteSpace: 'pre-wrap', color: '#666' }}>{info.remark}</p>
              </>
            )}
          </Card>

          <Card title="简历原文" style={{ marginTop: 16 }}>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.8, maxHeight: 600, overflow: 'auto' }}>
              {info.raw_text || '无原文内容'}
            </pre>
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title="筛选结果">
            {info.screening_detail?.length > 0 ? (
              <Table
                dataSource={info.screening_detail}
                rowKey="rule_id"
                size="small"
                pagination={false}
                columns={[
                  { title: '规则', dataIndex: 'rule_name', ellipsis: true },
                  {
                    title: '结果',
                    dataIndex: 'passed',
                    width: 60,
                    render: (v: boolean, record: any) =>
                      record.is_knockout && !v ? (
                        <Tag color="error">淘汰</Tag>
                      ) : v ? (
                        <CheckCircleOutlined style={{ color: '#10b981' }} />
                      ) : (
                        <CloseCircleOutlined style={{ color: '#ef4444' }} />
                      ),
                  },
                  { title: '实际值', dataIndex: 'actual', width: 80, ellipsis: true },
                ]}
              />
            ) : (
              <p style={{ color: '#999', textAlign: 'center' }}>暂未执行筛选</p>
            )}

            {info.screening_risks?.length > 0 && (
              <>
                <Divider plain>风险提示</Divider>
                {info.screening_risks.map((r: string, i: number) => (
                  <Tag key={i} color="error" style={{ marginBottom: 4 }}>{r}</Tag>
                ))}
              </>
            )}
          </Card>

          <Card title="筛选日志" style={{ marginTop: 16 }}>
            {logs.length > 0 ? (
              <Timeline
                items={logs.slice(0, 20).map((log) => ({
                  color: log.passed ? 'green' : 'red',
                  children: (
                    <div>
                      <div style={{ fontWeight: 500 }}>{log.rule_name}</div>
                      <div style={{ fontSize: 12, color: '#888' }}>
                        期望: {log.expected} | 实际: {log.actual}
                      </div>
                    </div>
                  ),
                }))}
              />
            ) : (
              <p style={{ color: '#999', textAlign: 'center' }}>暂无日志</p>
            )}
          </Card>
        </Col>
      </Row>

      <Modal
        title="编辑备注"
        open={remarkModalOpen}
        onOk={handleSaveRemark}
        onCancel={() => setRemarkModalOpen(false)}
      >
        <Input.TextArea
          rows={4}
          value={remark}
          onChange={(e) => setRemark(e.target.value)}
          placeholder="输入备注..."
        />
      </Modal>
    </div>
  );
}
