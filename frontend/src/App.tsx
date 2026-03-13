import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import ResumeList from './pages/ResumeList';
import ResumeDetail from './pages/ResumeDetail';
import PositionList from './pages/PositionList';
import RuleManager from './pages/RuleManager';
import Pipeline from './pages/Pipeline';
import InterviewSlots from './pages/InterviewSlots';
import Settings from './pages/Settings';

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#4f46e5',
          borderRadius: 8,
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/pipeline" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="pipeline" element={<Pipeline />} />
            <Route path="resumes" element={<ResumeList />} />
            <Route path="resumes/:id" element={<ResumeDetail />} />
            <Route path="positions" element={<PositionList />} />
            <Route path="rules" element={<RuleManager />} />
            <Route path="interview-slots" element={<InterviewSlots />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
