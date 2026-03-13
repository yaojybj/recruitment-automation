import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout as AntLayout, Menu, theme } from 'antd';
import {
  DashboardOutlined,
  FileTextOutlined,
  TeamOutlined,
  FilterOutlined,
  SettingOutlined,
  FunnelPlotOutlined,
  CalendarOutlined,
} from '@ant-design/icons';

const { Sider, Content, Header } = AntLayout;

const menuItems = [
  { key: '/pipeline', icon: <FunnelPlotOutlined />, label: '招聘流程' },
  { key: '/dashboard', icon: <DashboardOutlined />, label: '数据看板' },
  { key: '/resumes', icon: <FileTextOutlined />, label: '简历池' },
  { key: '/positions', icon: <TeamOutlined />, label: '岗位管理' },
  { key: '/rules', icon: <FilterOutlined />, label: '筛选规则' },
  { key: '/interview-slots', icon: <CalendarOutlined />, label: '面试时间' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
];

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { token } = theme.useToken();

  const selectedKey = '/' + location.pathname.split('/')[1];

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        style={{
          background: '#fff',
          borderRight: '1px solid #f0f0f0',
        }}
        theme="light"
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <span
            style={{
              fontSize: collapsed ? 16 : 18,
              fontWeight: 700,
              color: token.colorPrimary,
              whiteSpace: 'nowrap',
            }}
          >
            {collapsed ? 'HR' : '招聘自动化'}
          </span>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <AntLayout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: 16, fontWeight: 500 }}>
            {menuItems.find((m) => m.key === selectedKey)?.label || '招聘自动化系统'}
          </span>
        </Header>
        <Content style={{ margin: 24, minHeight: 280 }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
}
