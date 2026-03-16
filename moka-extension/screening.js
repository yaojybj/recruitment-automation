/**
 * 简历筛选打分引擎
 * 从 Python screener.py 移植，在浏览器端运行
 */

const DEFAULT_RULES = {
  hard_requirements: {
    min_education: '本科',
    min_work_years: 3,
    cities: [],
    required_skills: [],
    salary_range: [0, 0],
    require_portfolio: false,
  },
  scoring_weights: {
    industry_match: 20,
    project_experience: 25,
    skill_proficiency: 25,
    stability: 15,
    education_bonus: 10,
    portfolio_bonus: 5,
  },
  auto_filter: {
    reject_no_project_experience: false,
    reject_irrelevant_position: true,
    reject_no_portfolio: false,
  },
  risk_flags: {
    high_salary_deviation_percent: 30,
    frequent_job_change_threshold: 3,
    short_tenure_months: 6,
  },
};

const EDUCATION_LEVELS = {
  '高中': 1, '中专': 1,
  '大专': 2,
  '本科': 3,
  '硕士': 4, 'MBA': 4,
  '博士': 5,
};

class ResumeScreener {
  constructor(rules = null) {
    this.rules = rules || DEFAULT_RULES;
  }

  updateRules(rules) {
    this.rules = { ...DEFAULT_RULES, ...rules };
  }

  screen(candidate) {
    const result = {
      score: 0,
      breakdown: {},
      risks: [],
      hardFail: null,
      autoFilterReason: null,
      passed: false,
    };

    const autoReason = this._autoFilter(candidate);
    if (autoReason) {
      result.autoFilterReason = autoReason;
      return result;
    }

    const hardFail = this._checkHardRequirements(candidate);
    if (hardFail) {
      result.hardFail = hardFail;
      return result;
    }

    const { score, breakdown } = this._calculateScore(candidate);
    result.score = score;
    result.breakdown = breakdown;
    result.risks = this._detectRisks(candidate);
    result.passed = score >= 85;

    return result;
  }

  _autoFilter(c) {
    const af = this.rules.auto_filter || {};
    if (af.reject_no_project_experience && (!c.projectCount || c.projectCount === 0) && (!c.experiences || c.experiences.length === 0)) {
      return '无项目/工作经验';
    }
    if (af.reject_no_portfolio && !c.hasPortfolio) {
      return '无作品集';
    }
    return null;
  }

  _checkHardRequirements(c) {
    const hr = this.rules.hard_requirements || {};

    if (hr.min_education && c.education) {
      const minLevel = EDUCATION_LEVELS[hr.min_education] || 0;
      const candidateLevel = EDUCATION_LEVELS[c.education] || 0;
      if (candidateLevel > 0 && candidateLevel < minLevel) {
        return `学历不足: 要求${hr.min_education}, 实际${c.education}`;
      }
    }

    if (hr.min_work_years && c.workYears !== null && c.workYears !== undefined) {
      if (c.workYears < hr.min_work_years) {
        return `年限不足: 要求${hr.min_work_years}年, 实际${c.workYears}年`;
      }
    }

    if (hr.cities && hr.cities.length > 0 && c.city) {
      const matched = hr.cities.some(city => c.city.includes(city));
      if (!matched) {
        return `城市不匹配: ${c.city}`;
      }
    }

    if (hr.required_skills && hr.required_skills.length > 0 && c.skills && c.skills.length > 0) {
      const candidateSkillsLower = c.skills.map(s => s.toLowerCase());
      const missing = hr.required_skills.filter(s => !candidateSkillsLower.includes(s.toLowerCase()));
      if (missing.length > 0) {
        return `缺少技能: ${missing.join(', ')}`;
      }
    }

    if (hr.require_portfolio && !c.hasPortfolio) {
      return '未提供作品集';
    }

    return null;
  }

  _calculateScore(c) {
    const w = this.rules.scoring_weights || {};
    const breakdown = {};
    let total = 0;

    // 行业匹配
    const maxIndustry = w.industry_match || 20;
    let industryRaw;
    if (c.workYears >= 5) industryRaw = 85;
    else if (c.workYears >= 3) industryRaw = 70;
    else if (c.workYears >= 1) industryRaw = 55;
    else industryRaw = 30;

    if (c.experiences && c.experiences.length > 0) {
      industryRaw = 60;
      if (c.experiences.length >= 2) industryRaw += 20;
      const hasLongTenure = c.experiences.some(e => e.durationMonths && e.durationMonths >= 24);
      if (hasLongTenure) industryRaw += 20;
      industryRaw = Math.min(industryRaw, 100);
    }

    const industryScore = Math.min(Math.round(industryRaw * maxIndustry / 100), maxIndustry);
    breakdown['行业匹配'] = industryScore;
    total += industryScore;

    // 项目经验
    const maxProject = w.project_experience || 25;
    let projectRaw;
    if (c.projectCount >= 5) projectRaw = 100;
    else if (c.projectCount >= 3) projectRaw = 80;
    else if (c.projectCount >= 1) projectRaw = 60;
    else if (c.workYears >= 3 || (c.experiences && c.experiences.length > 0)) projectRaw = 50;
    else projectRaw = 10;

    const projectScore = Math.min(Math.round(projectRaw * maxProject / 100), maxProject);
    breakdown['项目经验'] = projectScore;
    total += projectScore;

    // 技能匹配
    const maxSkill = w.skill_proficiency || 25;
    let skillRaw = 70;
    const requiredSkills = (this.rules.hard_requirements || {}).required_skills || [];
    if (requiredSkills.length > 0 && c.skills && c.skills.length > 0) {
      const candidateLower = c.skills.map(s => s.toLowerCase());
      const matched = requiredSkills.filter(s => candidateLower.includes(s.toLowerCase())).length;
      const ratio = matched / requiredSkills.length;
      const extra = Math.min((c.skills.length - matched) * 2, 10);
      skillRaw = Math.min(Math.round(ratio * 90 + extra), 100);
    } else if (c.skills && c.skills.length >= 3) {
      skillRaw = 75;
    }

    const skillScore = Math.min(Math.round(skillRaw * maxSkill / 100), maxSkill);
    breakdown['技能匹配'] = skillScore;
    total += skillScore;

    // 稳定性
    const maxStability = w.stability || 15;
    let stabilityRaw = 55;
    if (c.experiences && c.experiences.length > 0 && c.workYears > 0) {
      const avgTenure = c.workYears / c.experiences.length;
      if (avgTenure >= 3) stabilityRaw = 100;
      else if (avgTenure >= 2) stabilityRaw = 80;
      else if (avgTenure >= 1) stabilityRaw = 50;
      else stabilityRaw = 20;
    } else if (c.workYears >= 5) {
      stabilityRaw = 80;
    } else if (c.workYears >= 3) {
      stabilityRaw = 70;
    }

    const stabilityScore = Math.min(Math.round(stabilityRaw * maxStability / 100), maxStability);
    breakdown['稳定性'] = stabilityScore;
    total += stabilityScore;

    // 学历
    const maxEdu = w.education_bonus || 10;
    const eduLevel = EDUCATION_LEVELS[c.education] || 0;
    let eduRaw;
    if (eduLevel >= 4) eduRaw = 100;
    else if (eduLevel >= 3) eduRaw = 70;
    else if (eduLevel >= 2) eduRaw = 40;
    else eduRaw = 10;

    const eduScore = Math.min(Math.round(eduRaw * maxEdu / 100), maxEdu);
    breakdown['学历'] = eduScore;
    total += eduScore;

    // 作品集
    const maxPortfolio = w.portfolio_bonus || 5;
    const portfolioScore = c.hasPortfolio ? maxPortfolio : 0;
    breakdown['作品集'] = portfolioScore;
    total += portfolioScore;

    return { score: total, breakdown };
  }

  _detectRisks(c) {
    const risks = [];
    const rc = this.rules.risk_flags || {};

    if (c.experiences && c.experiences.length > 0) {
      const shortThreshold = rc.short_tenure_months || 6;
      const shortJobs = c.experiences.filter(e => e.durationMonths > 0 && e.durationMonths < shortThreshold);
      if (shortJobs.length > 0) {
        risks.push(`${shortJobs.length}份工作不满${shortThreshold}个月`);
      }

      const changeThreshold = rc.frequent_job_change_threshold || 3;
      const recentShort = c.experiences.filter(e => e.durationMonths > 0 && e.durationMonths < 24);
      if (recentShort.length >= changeThreshold) {
        risks.push(`频繁跳槽(${recentShort.length}份<2年)`);
      }
    }

    return risks;
  }
}

if (typeof window !== 'undefined') {
  window.ResumeScreener = ResumeScreener;
  window.DEFAULT_SCREENING_RULES = DEFAULT_RULES;
}
