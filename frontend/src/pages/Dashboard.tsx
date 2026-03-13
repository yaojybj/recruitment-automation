import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Table, Tag, Spin } from 'antd';
import {
  FileTextOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CalendarOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { getDashboardStats, getDashboardTrend, getResumesBySource, getRecentLogs } from '../api';

const COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [trend, setTrend] = useState<any[]>([]);
  const [sources, setSources] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getDashboardStats(),
      getDashboardTrend(30),
      getResumesBySource(),
      getRecentLogs(10),
    ]).then(([statsRes, trendRes, sourceRes, logsRes]) => {
      setStats(statsRes.data);
      setTrend(trendRes.data);
      setSources(sourceRes.data);
      setLogs(logsRes.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100, textAlign: 'center' }} />;

  const statCards = [
    { title: '简历总数', value: stats?.total_resumes, icon: <FileTextOutlined />, color: '#4f46e5' },
    { title: '待处理', value: stats?.pending_resumes, icon: <ClockCircleOutlined />, color: '#f59e0b' },
    { title: '已通过', value: stats?.passed_resumes, icon: <CheckCircleOutlined />, color: '#10b981' },
    { title: '已淘汰', value: stats?.rejected_resumes, icon: <CloseCircleOutlined />, color: '#ef4444' },
    { title: '今日新增', value: stats?.today_new_resumes, icon: <CalendarOutlined />, color: '#8b5cf6' },
    { title: '在招岗位', value: stats?.active_positions, icon: <TeamOutlined />, color: '#06b6d4' },
  ];

  const actionLabels: Record<string, string> = {
    resume_imported: '简历导入',
    resume_uploaded: '简历上传',
    resume_updated: '简历更新',
    batch_pass: '批量通过',
    batch_reject: '批量淘汰',
  };

  return (
    <div>
      <Row gutter={[16, 16]}>
        {statCards.map((card, i) => (
          <Col xs={12} sm={8} md={4} key={i}>
            <Card hoverable style={{ borderTop: `3px solid ${card.color}` }}>
              <Statistic
                title={card.title}
                value={card.value || 0}
                prefix={card.icon}
                valueStyle={{ color: card.color }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="简历入池趋势（近30天）">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={trend}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#4f46e5" name="简历数" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="来源分布">
            {sources.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={sources} dataKey="count" nameKey="source" cx="50%" cy="50%" outerRadius={100} label>
                    {sources.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>
                暂无数据
              </div>
            )}
          </Card>
        </Col>
      </Row>

      <Card title="最近操作" style={{ marginTop: 16 }}>
        <Table
          dataSource={logs}
          rowKey="id"
          pagination={false}
          size="small"
          columns={[
            {
              title: '操作',
              dataIndex: 'action',
              render: (v: string) => <Tag color="blue">{actionLabels[v] || v}</Tag>,
            },
            { title: '详情', dataIndex: 'detail', ellipsis: true },
            { title: '操作者', dataIndex: 'operator' },
            { title: '时间', dataIndex: 'created_at', width: 180 },
          ]}
        />
      </Card>
    </div>
  );
}
