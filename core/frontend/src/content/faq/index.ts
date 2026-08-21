import whyCharged from './billing/why-was-i-charged.mdx?raw'
import cancelSub from './billing/cancel-my-subscription.mdx?raw'
import refundRequest from './billing/refund-request.mdx?raw'
import byok from './byok/bringing-my-openrouter-key.mdx?raw'
import emailNotVerified from './account/email-not-verified.mdx?raw'
import deleteAccount from './account/delete-my-account.mdx?raw'
import forgotPassword from './account/forgot-password.mdx?raw'
import voiceRoomQuality from './troubleshooting/voice-room-quality.mdx?raw'
import sparkDeployFailed from './troubleshooting/spark-deploy-failed.mdx?raw'
import codingAgentHung from './troubleshooting/coding-agent-hung.mdx?raw'
import exportData from './data/export-my-data.mdx?raw'
import whereData from './data/where-is-my-data-stored.mdx?raw'

export interface FaqArticle {
  slug: string
  title: string
  category: string
  lastUpdated: string
  body: string
}

function parseMdx(raw: string, slug: string): FaqArticle {
  const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/)
  if (!match) return { slug, title: slug, category: 'General', lastUpdated: '', body: raw }
  const [, fm, body] = match
  const title = fm.match(/title:\s*(.+)/)?.[1]?.trim() ?? slug
  const category = fm.match(/category:\s*(.+)/)?.[1]?.trim() ?? 'General'
  const lastUpdated = fm.match(/last_updated:\s*(.+)/)?.[1]?.trim() ?? ''
  return { slug, title, category, lastUpdated, body: body.trim() }
}

export const faqArticles: FaqArticle[] = [
  parseMdx(whyCharged, 'billing/why-was-i-charged'),
  parseMdx(cancelSub, 'billing/cancel-my-subscription'),
  parseMdx(refundRequest, 'billing/refund-request'),
  parseMdx(byok, 'byok/bringing-my-openrouter-key'),
  parseMdx(emailNotVerified, 'account/email-not-verified'),
  parseMdx(deleteAccount, 'account/delete-my-account'),
  parseMdx(forgotPassword, 'account/forgot-password'),
  parseMdx(voiceRoomQuality, 'troubleshooting/voice-room-quality'),
  parseMdx(sparkDeployFailed, 'troubleshooting/spark-deploy-failed'),
  parseMdx(codingAgentHung, 'troubleshooting/coding-agent-hung'),
  parseMdx(exportData, 'data/export-my-data'),
  parseMdx(whereData, 'data/where-is-my-data-stored'),
]

export const faqCategories = [...new Set(faqArticles.map((a) => a.category))]
