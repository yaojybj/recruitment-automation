import { useEffect, useState } from 'react';
import {
  Card, Table, Button, Space, Select, Modal, Form, Input, InputNumber, Switch, message,
  Tag, Popconfirm, Empty, Tooltip,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { getPositions, getRules, getRuleMeta, createRule, updateRule, deleteRule } from '../api';

export default function RuleManager() {
  const [positions, setPositions] = useState<any[]>([]);
  const [selectedPosition, setSelectedPosition] = useState<number | undefined>();
  const [rules, setRules] = useState<any[]>([]);
  const [meta, setMeta] = useState<any>({ fields: [], operators: [] });
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    getPositions().then((r) => setPositions(r.data));
    getRuleMeta().then((r) => setMeta(r.data));
  }, []);

  useEffect(() => {
    if (selectedPosition) {
      setLoading(true);
      getRules(selectedPosition)
        .then((r) => setRules(r.data))
        .finally(() => setLoading(false));
    } else {
      setRules([]);
    }
  }, [selectedPosition]);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    values.position_id = selectedPosition;
    if (editing) {
      await updateRule(editing.id, values);
      message.success('规则已更新');
    } else {
      await createRule(values);
      message.success('规则已创建');
    }
    setModalOpen(false);
    setEditing(null);
    form.resetFields();
    getRules(selectedPosition!).then((r) => setRules(r.data));
  };

  const handleEdit = (record: any) => {
    setEditing(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    await deleteRule(id);
    message.success('已删除');
    getRules(selectedPosition!).then((r) => setRules(r.data));
  };

  const fieldLabel = (val: string) => meta.fields.find((f: any) => f.value === val)?.label || val;
  const operatorLabel = (val: string) => meta.operators.find((o: any) => o.value === val)?.label || val;

  const columns = [
    { title: '排序', dataIndex: 'order', width: 60 },
    { title: '规则名称', dataIndex: 'name', width: 200 },
    {
      title: '字段',
      dataIndex: 'field',
      width: 100,
      render: (v: string) => fieldLabel(v),
    },
    {
      title: '条件',
      dataIndex: 'operator',
      width: 100,
      render: (v: string) => operatorLabel(v),
    },
    { title: '期望值', dataIndex: 'value', width: 150 },
    {
      title: '类型',
      dataIndex: 'is_knockout',
      width: 80,
      render: (v: boolean) => v ? <Tag color="error">淘汰项</Tag> : <Tag color="blue">加分项</Tag>,
    },
    {
      title: '权重',
      dataIndex: 'weight',
      width: 70,
      render: (v: number) => v,
    },
    {
      title: '启用',
      dataIndex: 'is_active',
      width: 60,
      render: (v: boolean) => v ? <Tag color="success">是</Tag> : <Tag>否</Tag>,
    },
    {
      title: '操作',
      width: 100,
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
    <div>
      <Card>
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <span style={{ fontWeight: 500 }}>选择岗位：</span>
            <Select
              placeholder="请先选择一个岗位"
              style={{ width: 240 }}
              value={selectedPosition}
              onChange={setSelectedPosition}
              options={positions.map((p) => ({ value: p.id, label: `${p.title}${p.department ? ` (${p.department})` : ''}` }))}
            />
            <Tooltip title="每个岗位可以配置独立的筛选规则。淘汰项不通过则直接淘汰，加分项会影响评分。">
              <InfoCircleOutlined style={{ color: '#999' }} />
            </Tooltip>
          </Space>
          {selectedPosition && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true); }}
            >
              新增规则
            </Button>
          )}
        </Space>

        {selectedPosition ? (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={rules}
            loading={loading}
            pagination={false}
            size="middle"
          />
        ) : (
          <Empty description="请先选择一个岗位来管理其筛选规则" />
        )}
      </Card>

      <Modal
        title={editing ? '编辑规则' : '新增规则'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); setEditing(null); }}
        width={560}
      >
        <Form form={form} layout="vertical" initialValues={{ weight: 1, order: 0, is_knockout: false, is_active: true }}>
          <Form.Item name="name" label="规则名称" rules={[{ required: true }]}>
            <Input placeholder="如: 学历要求本科以上" />
          </Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="field" label="筛选字段" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select
                placeholder="选择字段"
                options={meta.fields.map((f: any) => ({ value: f.value, label: f.label }))}
              />
            </Form.Item>
            <Form.Item name="operator" label="比较方式" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select
                placeholder="选择条件"
                options={meta.operators.map((o: any) => ({ value: o.value, label: o.label }))}
              />
            </Form.Item>
          </Space>
          <Form.Item
            name="value"
            label="期望值"
            rules={[{ required: true }]}
            extra="多个值用英文逗号分隔。学历字段支持: 博士/硕士/本科/大专/高中"
          >
            <Input placeholder="如: 本科 / 3 / Java,Python" />
          </Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="is_knockout" label="淘汰项" valuePropName="checked" style={{ flex: 1 }}>
              <Switch checkedChildren="是" unCheckedChildren="否" />
            </Form.Item>
            <Form.Item name="weight" label="权重" style={{ flex: 1 }}>
              <InputNumber min={0} max={100} step={0.5} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="order" label="排序" style={{ flex: 1 }}>
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="is_active" label="启用" valuePropName="checked" style={{ flex: 1 }}>
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
