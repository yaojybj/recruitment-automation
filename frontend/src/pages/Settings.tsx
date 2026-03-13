import { useEffect, useState } from 'react';
import {
  Card, Table, Button, Space, Modal, Form, Input, InputNumber, Switch, message,
  Tag, Popconfirm, Typography, Divider, Alert,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, MailOutlined, SyncOutlined } from '@ant-design/icons';
import { getEmailConfigs, createEmailConfig, updateEmailConfig, deleteEmailConfig, testEmail, checkEmailNow } from '../api';

const { Title, Paragraph } = Typography;

export default function Settings() {
  const [configs, setConfigs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      const res = await getEmailConfigs();
      setConfigs(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfigs();
  }, []);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    if (editing) {
      await updateEmailConfig(editing.id, values);
      message.success('配置已更新');
    } else {
      await createEmailConfig(values);
      message.success('配置已创建');
    }
    setModalOpen(false);
    setEditing(null);
    form.resetFields();
    fetchConfigs();
  };

  const handleTest = async (id: number) => {
    const hide = message.loading('正在检查...');
    try {
      const res = await testEmail(id);
      hide();
      message.success(res.data.message);
      fetchConfigs();
    } catch {
      hide();
      message.error('连接失败，请检查配置');
    }
  };

  const handleCheckAll = async () => {
    const hide = message.loading('正在检查所有邮箱...');
    try {
      const res = await checkEmailNow();
      hide();
      message.success(res.data.message);
    } catch {
      hide();
      message.error('检查失败');
    }
  };

  const columns = [
    { title: '邮箱地址', dataIndex: 'email_address', width: 220 },
    { title: 'IMAP 服务器', dataIndex: 'imap_server', width: 180 },
    { title: '端口', dataIndex: 'imap_port', width: 70 },
    { title: '发件人过滤', dataIndex: 'sender_filter', width: 140 },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 80,
      render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '上次检查',
      dataIndex: 'last_check_at',
      width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '从未检查',
    },
    {
      title: '操作',
      width: 150,
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" onClick={() => handleTest(record.id)}>测试</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => { setEditing(record); form.setFieldsValue(record); setModalOpen(true); }} />
          <Popconfirm title="确认删除？" onConfirm={() => { deleteEmailConfig(record.id).then(() => { message.success('已删除'); fetchConfigs(); }); }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card>
        <Title level={4}><MailOutlined /> 邮箱监听配置</Title>
        <Paragraph type="secondary">
          配置邮箱后，系统会定时检查新邮件，自动将 Boss 直聘的简历通知解析入库。
        </Paragraph>

        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="配置说明"
          description={
            <ul style={{ marginBottom: 0, paddingLeft: 20 }}>
              <li>QQ 邮箱 IMAP：imap.qq.com，端口 993，密码需使用授权码</li>
              <li>163 邮箱 IMAP：imap.163.com，端口 993，密码需使用授权码</li>
              <li>Gmail IMAP：imap.gmail.com，端口 993，需开启应用专用密码</li>
              <li>企业微信邮箱：imap.exmail.qq.com，端口 993</li>
              <li>发件人过滤填写 Boss 直聘的发件地址关键词（默认 bosszhipin）</li>
            </ul>
          }
        />

        <Space style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true); }}>
            添加邮箱
          </Button>
          <Button icon={<SyncOutlined />} onClick={handleCheckAll}>立即检查所有邮箱</Button>
        </Space>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={configs}
          loading={loading}
          pagination={false}
        />
      </Card>

      <Card style={{ marginTop: 16 }}>
        <Title level={4}>文件夹监控</Title>
        <Paragraph type="secondary">
          系统会自动监控 <code>backend/uploads/inbox/</code> 文件夹。
          将简历文件（PDF/Word/TXT）拖入该文件夹，系统会自动解析并导入到简历池。
        </Paragraph>
        <Alert type="success" showIcon message="文件夹监控已自动启用，每 30 秒扫描一次" />
      </Card>

      <Modal
        title={editing ? '编辑邮箱配置' : '添加邮箱'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); setEditing(null); }}
        width={500}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ imap_port: 993, use_ssl: true, sender_filter: 'bosszhipin' }}
        >
          <Form.Item name="email_address" label="邮箱地址" rules={[{ required: true, type: 'email' }]}>
            <Input placeholder="your@email.com" />
          </Form.Item>
          <Form.Item name="password" label="密码/授权码" rules={[{ required: !editing }]}>
            <Input.Password placeholder={editing ? '留空则不修改' : '输入密码或授权码'} />
          </Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="imap_server" label="IMAP 服务器" rules={[{ required: true }]} style={{ flex: 2 }}>
              <Input placeholder="imap.qq.com" />
            </Form.Item>
            <Form.Item name="imap_port" label="端口" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          <Form.Item name="sender_filter" label="发件人过滤关键词">
            <Input placeholder="bosszhipin" />
          </Form.Item>
          <Space>
            <Form.Item name="use_ssl" label="SSL" valuePropName="checked">
              <Switch />
            </Form.Item>
            {editing && (
              <Form.Item name="is_active" label="启用" valuePropName="checked">
                <Switch />
              </Form.Item>
            )}
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
