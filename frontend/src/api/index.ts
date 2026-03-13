import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

// ── Dashboard ──
export const getDashboardStats = () => api.get('/dashboard/stats');
export const getDashboardTrend = (days = 30) => api.get('/dashboard/trend', { params: { days } });
export const getResumesByPosition = () => api.get('/dashboard/by-position');
export const getResumesBySource = () => api.get('/dashboard/by-source');
export const getRecentLogs = (limit = 50) => api.get('/dashboard/recent-logs', { params: { limit } });

// ── Positions ──
export const getPositions = (isActive?: boolean) =>
  api.get('/positions', { params: isActive !== undefined ? { is_active: isActive } : {} });
export const getPosition = (id: number) => api.get(`/positions/${id}`);
export const createPosition = (data: any) => api.post('/positions', data);
export const updatePosition = (id: number, data: any) => api.put(`/positions/${id}`, data);
export const deletePosition = (id: number) => api.delete(`/positions/${id}`);

// ── Resumes ──
export const getResumes = (params: any) => api.get('/resumes', { params });
export const getResumeStats = () => api.get('/resumes/stats');
export const getResume = (id: number) => api.get(`/resumes/${id}`);
export const updateResume = (id: number, data: any) => api.put(`/resumes/${id}`, data);
export const deleteResume = (id: number) => api.delete(`/resumes/${id}`);
export const uploadResume = (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/resumes/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};
export const uploadResumesBatch = (files: File[]) => {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));
  return api.post('/resumes/upload-batch', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};
export const batchAction = (data: any) => api.post('/resumes/batch-action', data);

// ── Rules ──
export const getRuleMeta = () => api.get('/rules/meta');
export const getRules = (positionId?: number) =>
  api.get('/rules', { params: positionId ? { position_id: positionId } : {} });
export const createRule = (data: any) => api.post('/rules', data);
export const updateRule = (id: number, data: any) => api.put(`/rules/${id}`, data);
export const deleteRule = (id: number) => api.delete(`/rules/${id}`);

// ── Screening ──
export const screenResume = (resumeId: number, positionId: number) =>
  api.post(`/screening/${resumeId}`, null, { params: { position_id: positionId } });
export const getScreeningLogs = (resumeId: number) => api.get(`/screening/logs/${resumeId}`);

// ── Email Config ──
export const getEmailConfigs = () => api.get('/email-config');
export const createEmailConfig = (data: any) => api.post('/email-config', data);
export const updateEmailConfig = (id: number, data: any) => api.put(`/email-config/${id}`, data);
export const deleteEmailConfig = (id: number) => api.delete(`/email-config/${id}`);
export const testEmail = (id: number) => api.post(`/email-config/test/${id}`);
export const checkEmailNow = () => api.post('/email-config/check-now');

// ── Pipeline (招聘流程) ──
export const jdMatchBatch = (positionId: number, resumeIds?: number[]) =>
  api.post('/pipeline/jd-match', { position_id: positionId, resume_ids: resumeIds });
export const jdMatchSingle = (resumeId: number, positionId: number) =>
  api.post(`/pipeline/jd-match/${resumeId}`, null, { params: { position_id: positionId } });
export const triggerAutoMatch = () => api.post('/pipeline/auto-match');
export const advanceStatus = (resumeId: number, data: any) =>
  api.post(`/pipeline/advance/${resumeId}`, data);
export const recommendToDept = (resumeIds: number[]) =>
  api.post('/pipeline/recommend', { resume_ids: resumeIds });
export const notifyDept = (resumeIds: number[], reviewerName = '', baseUrl = '') =>
  api.post('/pipeline/notify-dept', { resume_ids: resumeIds, reviewer_name: reviewerName, base_url: baseUrl });
export const deptReview = (resumeId: number, data: any) =>
  api.post(`/pipeline/dept-review/${resumeId}`, data);
export const deptReviewBatch = (resumeIds: number[], approved: boolean, reviewer = '') =>
  api.post('/pipeline/dept-review-batch', { resume_ids: resumeIds, approved, reviewer });
export const getMokaGuide = (resumeId: number) => api.get(`/pipeline/moka-guide/${resumeId}`);
export const getPendingContacts = (positionId?: number) =>
  api.get('/pipeline/pending-contacts', { params: positionId ? { position_id: positionId } : {} });
export const generateMessage = (resumeId: number) =>
  api.post(`/pipeline/generate-message/${resumeId}`);
export const markMessageSent = (resumeId: number) =>
  api.post(`/pipeline/message-sent/${resumeId}`);
export const getAwaitingReplies = (positionId?: number) =>
  api.get('/pipeline/awaiting-replies', { params: positionId ? { position_id: positionId } : {} });
export const submitCandidateReply = (resumeId: number, replyText: string) =>
  api.post(`/pipeline/candidate-reply/${resumeId}`, { reply_text: replyText });
export const scheduleInterview = (resumeId: number) =>
  api.post(`/pipeline/schedule-interview/${resumeId}`);
export const getPipelineSummary = (positionId?: number) =>
  api.get('/pipeline/summary', { params: positionId ? { position_id: positionId } : {} });
export const getPipelineByStatus = (status: string, positionId?: number) =>
  api.get(`/pipeline/by-status/${status}`, { params: positionId ? { position_id: positionId } : {} });
export const getResumeTimeline = (resumeId: number) => api.get(`/pipeline/timeline/${resumeId}`);

// ── Interview Slots ──
export const getInterviewSlots = (positionId?: number, availableOnly = false) =>
  api.get('/interview-slots', { params: { position_id: positionId, available_only: availableOnly } });
export const createInterviewSlot = (data: any) => api.post('/interview-slots', data);
export const createInterviewSlotsBatch = (slots: any[]) =>
  api.post('/interview-slots/batch', { slots });
export const updateInterviewSlot = (id: number, data: any) => api.put(`/interview-slots/${id}`, data);
export const deleteInterviewSlot = (id: number) => api.delete(`/interview-slots/${id}`);

// ── Extension (Chrome 插件) ──
export const extensionImportCandidate = (data: any) => api.post('/extension/import-candidate', data);
export const extensionSearch = (params: any) => api.get('/extension/search', { params });
export const extensionBatchImport = (candidates: any[]) => api.post('/extension/batch-import', candidates);

export default api;
