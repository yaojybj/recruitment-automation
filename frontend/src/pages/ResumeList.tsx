import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table, Card, Button, Space, Tag, Input, Select, Upload, Modal, message, Dropdown, Tooltip, Badge,
} from 'antd';
import {
  UploadOutlined, SearchOutlined, FilterOutlined, ReloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined, DownOutlined, InboxOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload';
import { getResumes, getPositions, uploadResumesBatch, batchAction, checkEmailNow } from '../api';

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

export default function ResumeList() {
  const navigate = useNavigate();
  const [data, setData] = useState<any>({ items: [], total: 0 });
  const [positions, setPositions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [filters, setFilters] = useState({
    page: 1,
    page_size: 20,
    keyword: '',
    status: undefined as string | undefined,
    position_id: undefined as number | undefined,
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { ...filters };
      Object.keys(params).forEach((k) => params[k] === undefined && delete params[k]);
      if (!params.keyword) delete params.keyword;
      const res = await getResumes(params);
      setData(res.data);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    getPositions(true).then((r) => setPositions(r.data));
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleBatchAction = async (action: string, positionId?: number) => {
    if (!selectedRowKeys.length) {
      message.warning('请先选择简历');
      return;
    }
    await batchAction({ resume_ids: selectedRowKeys, action, position_id: positionId });
    message.success('操作成功');
    setSelectedRowKeys([]);
    fetchData();
  };

  const handleUpload = async () => {
    if (!fileList.length) return;
    const files = fileList.map((f) => f.originFileObj as File);
    try {
      await uploadResumesBatch(files);
      message.success('上传成功');
      setUploadModalOpen(false);
      setFileList([]);
      fetchData();
    } catch {
      message.error('上传失败');
    }
  };

  const handleCheckEmail = async () => {
    const hide = message.loading('正在检查邮箱...');
    try {
      const res = await checkEmailNow();
      hide();
      message.success(res.data.message);
      fetchData();
    } catch {
      hide();
      message.error('检查失败，请确认邮箱配置');
    }
  };

  const columns = [
    {
      title: '姓名',
      dataIndex: 'candidate_name',
      width: 100,
      render: (name: string, record: any) => (
        <a onClick={() => navigate(`/resumes/${record.id}`)}>{name || '未知'}</a>
      ),
    },
    { title: '学历', dataIndex: 'education', width: 70 },
    {
      title: '工作年限',
      dataIndex: 'work_years',
      width: 90,
      render: (v: number) => (v ? `${v}年` : '-'),
    },
    { title: '当前公司', dataIndex: 'current_company', width: 150, ellipsis: true },
    { title: '当前职位', dataIndex: 'current_position', width: 120, ellipsis: true },
    { title: '城市', dataIndex: 'city', width: 80 },
    {
      title: '关联岗位',
      dataIndex: 'position_title',
      width: 120,
      render: (v: string) => v || <span style={{ color: '#ccc' }}>未分配</span>,
    },
    {
      title: '筛选分数',
      dataIndex: 'screening_score',
      width: 90,
      sorter: true,
      render: (v: number) => {
        if (v == null) return '-';
        const color = v >= 70 ? '#10b981' : v >= 40 ? '#f59e0b' : '#ef4444';
        return <span style={{ color, fontWeight: 600 }}>{v}</span>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: string) => {
        const info = statusMap[s] || { label: s, color: 'default' };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 90,
      render: (s: string) => {
        const labels: Record<string, string> = {
          email: '邮件', manual_upload: '上传', folder_import: '文件夹',
        };
        return labels[s] || s;
      },
    },
    {
      title: '入池时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
  ];

  const batchMenuItems = [
    { key: 'pass', label: '批量通过', icon: <CheckCircleOutlined /> },
    { key: 'reject', label: '批量淘汰', icon: <CloseCircleOutlined /> },
    { key: 'interview', label: '进入面试', icon: <CheckCircleOutlined /> },
    { type: 'divider' as const },
    ...positions.map((p) => ({
      key: `assign_${p.id}`,
      label: `分配到: ${p.title}`,
    })),
    { type: 'divider' as const },
    ...positions.map((p) => ({
      key: `screen_${p.id}`,
      label: `按「${p.title}」规则筛选`,
      icon: <FilterOutlined />,
    })),
  ];

  return (
    <div>
      <Card>
        <Space wrap style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
          <Space wrap>
            <Input
              placeholder="搜索姓名/公司/学校..."
              prefix={<SearchOutlined />}
              allowClear
              style={{ width: 240 }}
              value={filters.keyword}
              onChange={(e) => setFilters({ ...filters, keyword: e.target.value, page: 1 })}
              onPressEnter={() => fetchData()}
            />
            <Select
              placeholder="状态筛选"
              allowClear
              style={{ width: 130 }}
              value={filters.status}
              onChange={(v) => setFilters({ ...filters, status: v, page: 1 })}
              options={Object.entries(statusMap).map(([k, v]) => ({ value: k, label: v.label }))}
            />
            <Select
              placeholder="岗位筛选"
              allowClear
              style={{ width: 160 }}
              value={filters.position_id}
              onChange={(v) => setFilters({ ...filters, position_id: v, page: 1 })}
              options={positions.map((p) => ({ value: p.id, label: p.title }))}
            />
            <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
          </Space>
          <Space>
            <Button onClick={handleCheckEmail}>检查邮箱</Button>
            <Button icon={<UploadOutlined />} type="primary" onClick={() => setUploadModalOpen(true)}>
              上传简历
            </Button>
            {selectedRowKeys.length > 0 && (
              <Dropdown
                menu={{
                  items: batchMenuItems,
                  onClick: ({ key }) => {
                    if (key.startsWith('assign_')) {
                      handleBatchAction('assign_position', Number(key.split('_')[1]));
                    } else if (key.startsWith('screen_')) {
                      handleBatchAction('screen', Number(key.split('_')[1]));
                    } else {
                      handleBatchAction(key);
                    }
                  },
                }}
              >
                <Button>
                  批量操作 ({selectedRowKeys.length}) <DownOutlined />
                </Button>
              </Dropdown>
            )}
          </Space>
        </Space>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={data.items}
          loading={loading}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as number[]),
          }}
          pagination={{
            current: filters.page,
            pageSize: filters.page_size,
            total: data.total,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (page, pageSize) => setFilters({ ...filters, page, page_size: pageSize }),
          }}
          scroll={{ x: 1200 }}
          size="middle"
        />
      </Card>

      <Modal
        title="上传简历"
        open={uploadModalOpen}
        onOk={handleUpload}
        onCancel={() => { setUploadModalOpen(false); setFileList([]); }}
        okText="开始上传"
      >
        <Upload.Dragger
          multiple
          accept=".pdf,.docx,.doc,.txt"
          fileList={fileList}
          beforeUpload={() => false}
          onChange={({ fileList: fl }) => setFileList(fl)}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽文件到此区域</p>
          <p className="ant-upload-hint">支持 PDF、Word、TXT 格式，可多选</p>
        </Upload.Dragger>
      </Modal>
    </div>
  );
}
