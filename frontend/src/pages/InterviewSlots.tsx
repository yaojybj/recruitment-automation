import { useEffect, useState } from 'react';
import {
  Card, Table, Button, Space, Select, Modal, Form, Input, InputNumber,
  Switch, message, Tag, Popconfirm, DatePicker, TimePicker, Typography,
} from 'antd';
import { PlusOutlined, DeleteOutlined, CalendarOutlined } from '@ant-design/icons';
import {
  getPositions, getInterviewSlots, createInterviewSlot, deleteInterviewSlot,
} from '../api';

const { Title } = Typography;

export default function InterviewSlots() {
  const [positions, setPositions] = useState<any[]>([]);
  const [selectedPosition, setSelectedPosition] = useState<number | undefined>();
  const [slots, setSlots] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    getPositions(true).then((r) => setPositions(r.data));
  }, []);

  const fetchSlots = async () => {
    setLoading(true);
    try {
      const res = await getInterviewSlots(selectedPosition);
      setSlots(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSlots();
  }, [selectedPosition]);

  const handleCreate = async () => {
    const values = await form.validateFields();
    const data = {
      position_id: selectedPosition || values.position_id,
      date: values.date,
      start_time: values.start_time,
      end_time: values.end_time,
      interviewer_name: values.interviewer_name,
      interviewer_email: values.interviewer_email,
      location: values.location,
      is_online: values.is_online || false,
      meeting_link: values.meeting_link,
      capacity: values.capacity || 1,
    };
    await createInterviewSlot(data);
    message.success('时间段已创建');
    setModalOpen(false);
    form.resetFields();
    fetchSlots();
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteInterviewSlot(id);
      message.success('已删除');
      fetchSlots();
    } catch (e: any) {
      message.error(e.response?.data?.detail || '删除失败');
    }
  };

  const columns = [
    {
      title: '岗位',
      dataIndex: 'position_title',
      width: 140,
    },
    { title: '日期', dataIndex: 'date', width: 110 },
    { title: '开始', dataIndex: 'start_time', width: 80 },
    { title: '结束', dataIndex: 'end_time', width: 80 },
    { title: '面试官', dataIndex: 'interviewer_name', width: 100 },
    {
      title: '方式',
      width: 80,
      render: (_: any, r: any) => r.is_online ? <Tag color="blue">线上</Tag> : <Tag>线下</Tag>,
    },
    { title: '地点/链接', render: (_: any, r: any) => r.is_online ? r.meeting_link : r.location, ellipsis: true },
    {
      title: '预约',
      width: 80,
      render: (_: any, r: any) => `${r.booked_count}/${r.capacity}`,
    },
    {
      title: '状态',
      width: 80,
      render: (_: any, r: any) => r.is_available ? <Tag color="success">可用</Tag> : <Tag color="error">已满</Tag>,
    },
    {
      title: '操作',
      width: 60,
      render: (_: any, r: any) => (
        <Popconfirm title="确认删除？" onConfirm={() => handleDelete(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <Card>
        <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <Space>
            <CalendarOutlined style={{ fontSize: 18 }} />
            <Title level={5} style={{ margin: 0 }}>面试时间管理</Title>
            <Select
              placeholder="筛选岗位"
              allowClear
              style={{ width: 200 }}
              value={selectedPosition}
              onChange={setSelectedPosition}
              options={positions.map((p) => ({ value: p.id, label: p.title }))}
            />
          </Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setModalOpen(true); }}>
            添加时间段
          </Button>
        </Space>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={slots}
          loading={loading}
          pagination={{ showTotal: (t) => `共 ${t} 个时间段` }}
          size="middle"
        />
      </Card>

      <Modal
        title="添加面试时间段"
        open={modalOpen}
        onOk={handleCreate}
        onCancel={() => setModalOpen(false)}
        width={560}
      >
        <Form form={form} layout="vertical" initialValues={{ capacity: 1, is_online: false }}>
          {!selectedPosition && (
            <Form.Item name="position_id" label="岗位" rules={[{ required: true }]}>
              <Select
                placeholder="选择岗位"
                options={positions.map((p) => ({ value: p.id, label: p.title }))}
              />
            </Form.Item>
          )}
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="date" label="日期" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Input placeholder="2026-03-20" />
            </Form.Item>
            <Form.Item name="start_time" label="开始时间" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Input placeholder="14:00" />
            </Form.Item>
            <Form.Item name="end_time" label="结束时间" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Input placeholder="15:00" />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="interviewer_name" label="面试官" style={{ flex: 1 }}>
              <Input placeholder="面试官姓名" />
            </Form.Item>
            <Form.Item name="interviewer_email" label="面试官邮箱" style={{ flex: 1 }}>
              <Input placeholder="用于 Moka 安排面试" />
            </Form.Item>
          </Space>
          <Form.Item name="is_online" label="线上面试" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="location" label="面试地点">
            <Input placeholder="线下面试地址" />
          </Form.Item>
          <Form.Item name="meeting_link" label="会议链接">
            <Input placeholder="线上面试链接（腾讯会议/Zoom等）" />
          </Form.Item>
          <Form.Item name="capacity" label="容量（可安排人数）">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
