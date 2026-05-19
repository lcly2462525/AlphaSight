/**
 * AlphaSight Skill Registry
 *
 * This file is intentionally declarative. The repository's executable
 * pipeline is Python under reference_submission/. These entries document
 * the local skills/sub-agent contracts used to coordinate that pipeline.
 */

export type AlphaSightSkill = {
  name: string;
  description: string;
  path: string;
  triggers: string[];
  authority: 'deterministic' | 'retrieval' | 'weak-signal' | 'orchestration';
};

export const skills: AlphaSightSkill[] = [
  {
    name: 'fact-store-quality',
    description: 'Structured fact normalization: availability, basis, period, YTD, and EPS scale safeguards.',
    path: 'alphasight-skills/fact-store-quality/SKILL.md',
    triggers: ['earnings', 'financials', 'EPS', 'YTD', 'GAAP', 'non-GAAP', 'scale', 'NFLX'],
    authority: 'deterministic',
  },
  {
    name: 'retrieval-router',
    description: 'Hybrid retrieval policy for filings, news, dense/BM25 fusion, compression, and kind bias.',
    path: 'alphasight-skills/retrieval-router/SKILL.md',
    triggers: ['retrieval', 'router', 'BM25', 'dense', 'RRF', 'filing chunk', 'news chunk'],
    authority: 'retrieval',
  },
  {
    name: 'news-evidence',
    description: 'News source cleaning, event attribution, duplicate handling, and news false-positive controls.',
    path: 'alphasight-skills/news-evidence/SKILL.md',
    triggers: ['news', 'Reuters', 'Bloomberg', 'CNBC', 'source attribution', 'event'],
    authority: 'retrieval',
  },
  {
    name: 'social-signal',
    description: 'Use social data as ticker/date aggregated sentiment and attention, never as primary fact evidence.',
    path: 'alphasight-skills/social-signal/SKILL.md',
    triggers: ['social', 'twitter', 'sentiment', 'tweet', 'attention', 'rumor'],
    authority: 'weak-signal',
  },
  {
    name: 'review-agent',
    description: 'Claim extraction and verification tiers for report error detection.',
    path: 'alphasight-skills/review-agent/SKILL.md',
    triggers: ['review', 'claim', 'issue', 'false positive', 'false negative', 'adjudicator'],
    authority: 'orchestration',
  },
  {
    name: 'generate-agent',
    description: 'Grounded report generation with subject lock, evidence discipline, and self-audit.',
    path: 'alphasight-skills/generate-agent/SKILL.md',
    triggers: ['generate', 'report', 'citation', 'self-audit', 'subject lock'],
    authority: 'orchestration',
  },
  {
    name: 'tool-agent',
    description: 'Deterministic tool contracts for prices, metrics, ratios, filings, citations, and social signals.',
    path: 'alphasight-skills/tool-agent/SKILL.md',
    triggers: ['tool', 'price_event', 'financial_metric', 'ratio', 'filing_lookup', 'citation_check'],
    authority: 'deterministic',
  },
];

export default skills;
