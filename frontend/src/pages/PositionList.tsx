import { useEffect, useState } from 'react';
import {
  Card, Table, Button, Space, Modal, Form, Input, InputNumber, Switch, message, Tag, Popconfirm, Select,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { getPositions, createPosition, updatePosition, deletePosition } from '../api';

export default function PositionList() {
  const [positions, setPositions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await getPositions();
      setPositions(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    if (typeof values.jd_must_have === 'string') {
      values.jd_must_have = values.jd_must_have.split(',').map((s: string) => s.trim()).filter(Boolean);
    }
    if (typeof values.jd_nice_to_have === 'string') {
      values.jd_nice_to_have = values.jd_nice_to_have.split(',').map((s: string) => s.trim()).filter(Boolean);
    }
    if (editing) {
      await updatePosition(editing.id, values);
      message.success('岗位已更新');
    } else {
      await createPosition(values);
      message.success('岗位已创建');
    }
    setModalOpen(false);
    setEditing(null);
    form.resetFields();
    fetchData();
  };

  const handleEdit = (record: any) => {
    setEditing(record);
    const formValues = { ...record };
    if (Array.isArray(formValues.jd_must_have)) {
      formValues.jd_must_have = formValues.jd_must_have.join(', ');
    }
    if (Array.isArray(formValues.jd_nice_to_have)) {
      formValues.jd_nice_to_have = formValues.jd_nice_to_have.join(', ');
    }
    form.setFieldsValue(formValues);
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    await deletePosition(id);
    message.success('已删除');
    fetchData();
  };

  const columns = [
    { title: '岗位名称', dataIndex: 'title', width: 200 },
    { title: '部门', dataIndex: 'department', width: 120 },
    { title: '工作地点', dataIndex: 'location', width: 100 },
    {
      title: '薪资范围',
      width: 150,
      render: (_: any, r: any) =>
        r.salary_min && r.salary_max
          ? `${r.salary_min / 1000}K - ${r.salary_max / 1000}K`
          : '-',
    },
    { title: '招聘人数', dataIndex: 'headcount', width: 90 },
    {
      title: '简历数',
      dataIndex: 'resume_count',
      width: 80,
      render: (v: number) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 80,
      render: (v: boolean) => v ? <Tag color="success">招聘中</Tag> : <Tag>已关闭</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      width: 120,
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true); }}>
          新增岗位
        </Button>
      }
    >
      <Table
        rowKey="id"
        columns={columns}
        dataSource={positions}
        loading={loading}
        pagination={{ showTotal: (t) => `共 ${t} 个岗位` }}
      />

      <Modal
        title={editing ? '编辑岗位' : '新增岗位'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); setEditing(null); }}
        width={720}
      >
        <Form form={form} layout="vertical" initialValues={{ match_threshold: 60, headcount: 1, auto_recommend: false }}>
          <Form.Item name="title" label="岗位名称" rules={[{ required: true, message: '请输入岗位名称' }]}>
            <Input placeholder="如: 前端工程师" />
          </Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="department" label="部门" style={{ flex: 1 }}>
              <Input placeholder="如: 技术部" />
            </Form.Item>
            <Form.Item name="location" label="工作地点" style={{ flex: 1 }}>
              <Input placeholder="如: 北京" />
            </Form.Item>
            <Form.Item name="headcount" label="招聘人数" style={{ flex: 1 }}>
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="salary_min" label="最低薪资(元/月)" style={{ flex: 1 }}>
              <InputNumber min={0} step={1000} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="salary_max" label="最高薪资(元/月)" style={{ flex: 1 }}>
              <InputNumber min={0} step={1000} style={{ width: '100%' }} />
            </Form.Item>
          </Space>

          <div style={{ background: '#f6f8fa', padding: 16, borderRadius: 8, marginBottom: 16 }}>
            <h4 style={{ marginTop: 0 }}>JD 匹配配置</h4>
            <Form.Item name="jd_text" label="完整 JD 文本" extra="粘贴职位 JD 全文，用于语义匹配打分">
              <Input.TextArea rows={5} placeholder="粘贴完整的职位描述..." />
            </Form.Item>
            <Form.Item name="jd_must_have" label="必备技能（淘汰项）"
              extra="用英文逗号分隔。同义词用 / 分隔，如: React/Vue, TypeScript">
              <Input placeholder="React/Vue, TypeScript, Node.js" />
            </Form.Item>
            <Form.Item name="jd_nice_to_have" label="加分技能"
              extra="用英文逗号分隔">
              <Input placeholder="Docker, AWS, GraphQL" />
            </Form.Item>
            <Space style={{ width: '100%' }} size={16}>
              <Form.Item name="jd_education" label="最低学历" style={{ flex: 1 }}>
                <Select placeholder="选择" allowClear
                  options={['博士', '硕士', '本科', '大专'].map((v) => ({ value: v, label: v }))} />
              </Form.Item>
              <Form.Item name="jd_min_years" label="最低工作年限" style={{ flex: 1 }}>
                <InputNumber min={0} step={1} style={{ width: '100%' }} placeholder="如: 3" />
              </Form.Item>
              <Form.Item name="match_threshold" label="及格线(分)" style={{ flex: 1 }}>
                <InputNumber min={0} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Space>
            <Form.Item name="auto_recommend" label="匹配通过后自动推荐给用人部门" valuePropName="checked">
              <Switch />
            </Form.Item>
          </div>

          <Form.Item name="description" label="岗位描述">
            <Input.TextArea rows={3} placeholder="描述岗位职责..." />
          </Form.Item>
          <Form.Item name="requirements" label="任职要求">
            <Input.TextArea rows={3} placeholder="描述任职要求..." />
          </Form.Item>
          {editing && (
            <Form.Item name="is_active" label="是否在招" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </Card>
  );
}
