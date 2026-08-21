export type TierSlug = 'free' | 'plus' | 'pro'

export interface Tier {
  slug: TierSlug
  name: string
  monthlyPrice: number
  description: string
  features: string[]
  highlighted?: boolean
}

export const TIERS: Tier[] = [
  {
    slug: 'free',
    name: 'Free',
    monthlyPrice: 0,
    description: 'Try Sterna with limited usage.',
    features: [
      '5 image gens / week',
      'Knowledge base (50 MB)',
      'BYOK supported',
    ],
  },
  {
    slug: 'plus',
    name: 'Plus',
    monthlyPrice: 20,
    description: 'For regular users who want more.',
    highlighted: true,
    features: [
      '50 image gens / week',
      '5 voice rooms / week',
      'Code sessions (20 / week)',
      'KB: 1 GB / 100 docs',
      'Email support',
    ],
  },
  {
    slug: 'pro',
    name: 'Pro',
    monthlyPrice: 100,
    description: 'The highest weekly limits for heavy daily use.',
    features: [
      '500 image gens / week',
      '30 voice rooms / week',
      'Code sessions (200 / week)',
      'KB: 10 GB / unlimited docs',
      'Priority support',
    ],
  },
]

export function yearlyTotal(tier: Tier): number {
  return tier.monthlyPrice * 10
}
