/**
 * Provider icon components registry
 *
 * Icons are vendored locally as static SVG files under
 * `src/assets/provider-icons/{mono,color}/` (extracted from the MIT-licensed
 * `@lobehub/icons-static-svg` package — see that directory's README.md for
 * attribution) and imported as React components via `vite-plugin-svgr`
 * (`?react` suffix), the same convention used for `src/assets/logos/`.
 *
 * This avoids depending on `@lobehub/icons` at runtime, which pulls in a
 * much larger transitive graph (`@lobehub/ui`, antd, framer-motion,
 * `@splinetool/runtime`, `@giscus/react`, ...) for the ~37 marks this app
 * actually renders.
 *
 * Icon Strategy:
 * - Icons with a distinct brand color: rendered from `color/<slug>.svg` with
 *   native colors, and self-reference their own `.Color` property so the
 *   adaptive-color logic below treats them as "not monochrome" (matching the
 *   original @lobehub/icons Icon.Color contract).
 * - Icons with no distinct brand color (OpenAI, Anthropic, Grok, ...):
 *   rendered from `mono/<slug>.svg` (`fill="currentColor"`) with adaptive
 *   color overrides so they stay visible in both light and dark modes.
 */

import { forwardRef } from 'react'
import type { ComponentType, SVGProps } from 'react'

// Monochrome marks (no distinct brand color in the source icon set)
import OpenAISvg from '@/assets/provider-icons/mono/openai.svg?react'
import AnthropicSvg from '@/assets/provider-icons/mono/anthropic.svg?react'
import OpenRouterSvg from '@/assets/provider-icons/mono/openrouter.svg?react'
import GrokSvg from '@/assets/provider-icons/mono/grok.svg?react'
import XAISvg from '@/assets/provider-icons/mono/xai.svg?react'
import ZaiSvg from '@/assets/provider-icons/mono/zai.svg?react'
import Ai21Svg from '@/assets/provider-icons/mono/ai21.svg?react'
import InflectionSvg from '@/assets/provider-icons/mono/inflection.svg?react'
import LiquidSvg from '@/assets/provider-icons/mono/liquid.svg?react'
import MoonshotSvg from '@/assets/provider-icons/mono/moonshot.svg?react'
import NousResearchSvg from '@/assets/provider-icons/mono/nousresearch.svg?react'
import AionLabsSvg from '@/assets/provider-icons/mono/aionlabs.svg?react'

// Native-color marks
import GoogleSvg from '@/assets/provider-icons/color/google.svg?react'
import MicrosoftSvg from '@/assets/provider-icons/color/microsoft.svg?react'
import MetaSvg from '@/assets/provider-icons/color/meta.svg?react'
import MistralSvg from '@/assets/provider-icons/color/mistral.svg?react'
import CohereSvg from '@/assets/provider-icons/color/cohere.svg?react'
import PerplexitySvg from '@/assets/provider-icons/color/perplexity.svg?react'
import DeepSeekSvg from '@/assets/provider-icons/color/deepseek.svg?react'
import TogetherSvg from '@/assets/provider-icons/color/together.svg?react'
import AzureSvg from '@/assets/provider-icons/color/azure.svg?react'
import HuggingFaceSvg from '@/assets/provider-icons/color/huggingface.svg?react'
import ClaudeSvg from '@/assets/provider-icons/color/claude.svg?react'
import QwenSvg from '@/assets/provider-icons/color/qwen.svg?react'
import YiSvg from '@/assets/provider-icons/color/yi.svg?react'
import BaichuanSvg from '@/assets/provider-icons/color/baichuan.svg?react'
import ChatGLMSvg from '@/assets/provider-icons/color/chatglm.svg?react'
import VertexAISvg from '@/assets/provider-icons/color/vertexai.svg?react'
import AlibabaCloudSvg from '@/assets/provider-icons/color/alibabacloud.svg?react'
import AwsSvg from '@/assets/provider-icons/color/aws.svg?react'
import GeminiSvg from '@/assets/provider-icons/color/gemini.svg?react'
import NovaSvg from '@/assets/provider-icons/color/nova.svg?react'
import GLMVSvg from '@/assets/provider-icons/color/glmv.svg?react'
import NvidiaSvg from '@/assets/provider-icons/color/nvidia.svg?react'
import BaiduSvg from '@/assets/provider-icons/color/baidu.svg?react'
import MinimaxSvg from '@/assets/provider-icons/color/minimax.svg?react'
import TencentSvg from '@/assets/provider-icons/color/tencent.svg?react'

/**
 * Type for icon components, matching the shape @lobehub/icons used to
 * expose: a renderable component with an optional `.Color` variant and
 * brand metadata.
 */
export type IconComponent = ComponentType<SVGProps<SVGSVGElement> & { size?: number }> & {
  Color?: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>
  colorPrimary?: string
  colorGradient?: string
  title?: string
}

type RawSvgComponent = ComponentType<SVGProps<SVGSVGElement>>

/**
 * Wrap a raw SVGR-imported SVG component into an IconComponent: maps the
 * `size` prop to width/height (matching the old @lobehub/icons API used by
 * every call site) and attaches brand metadata.
 */
function wrapIcon(
  Svg: RawSvgComponent,
  displayName: string,
  colorPrimary: string,
  isColorMark: boolean
): IconComponent {
  const Icon = forwardRef<SVGSVGElement, SVGProps<SVGSVGElement> & { size?: number }>(
    ({ size = 24, ...props }, ref) => (
      <Svg ref={ref} width={size} height={size} {...props} />
    )
  ) as unknown as IconComponent
  Icon.displayName = displayName
  Icon.colorPrimary = colorPrimary
  if (isColorMark) {
    // Icons with a native brand color never fall back to a Mono render in
    // this app (getIconRenderComponent always prefers .Color when present),
    // so the color mark is its own .Color variant. This also keeps
    // `isMonochrome = !iconComponent.Color` false for these icons, exactly
    // matching the original @lobehub/icons behavior.
    Icon.Color = Icon
  }
  return Icon
}

const OpenAI = wrapIcon(OpenAISvg, 'OpenAIIcon', '#000', false)
const Anthropic = wrapIcon(AnthropicSvg, 'AnthropicIcon', '#F1F0E8', false)
const OpenRouter = wrapIcon(OpenRouterSvg, 'OpenRouterIcon', '#6566F1', false)
const GrokIcon = wrapIcon(GrokSvg, 'GrokIcon', '#000', false)
const XAIIcon = wrapIcon(XAISvg, 'XAIIcon', '#fff', false)
const ZaiIcon = wrapIcon(ZaiSvg, 'ZaiIcon', '#000', false)
const Ai21Icon = wrapIcon(Ai21Svg, 'Ai21Icon', '#E91E63', false)
const InflectionIcon = wrapIcon(InflectionSvg, 'InflectionIcon', '#038247', false)
const LiquidIcon = wrapIcon(LiquidSvg, 'LiquidIcon', '#fff', false)
const MoonshotIcon = wrapIcon(MoonshotSvg, 'MoonshotIcon', '#16191E', false)
const NousResearchIcon = wrapIcon(NousResearchSvg, 'NousResearchIcon', '#2D6376', false)
// AionLabs ships a very detailed logo; the static-svg color variant is ~73KB
// of path data vs. ~16KB for the mono mark, for a rarely-used provider.
// Rendered monochrome (with a dark-mode override below) as a deliberate
// bundle-size tradeoff.
const AionLabsIcon = wrapIcon(AionLabsSvg, 'AionLabsIcon', '#0f172a', false)

const GoogleIcon = wrapIcon(GoogleSvg, 'GoogleIcon', '#fff', true)
const MicrosoftIcon = wrapIcon(MicrosoftSvg, 'MicrosoftIcon', '#00A4EF', true)
const MetaIcon = wrapIcon(MetaSvg, 'MetaIcon', '#1d65c1', true)
const MistralIcon = wrapIcon(MistralSvg, 'MistralIcon', '#FA520F', true)
const CohereIcon = wrapIcon(CohereSvg, 'CohereIcon', '#39594D', true)
const PerplexityIcon = wrapIcon(PerplexitySvg, 'PerplexityIcon', '#22B8CD', true)
const DeepSeekIcon = wrapIcon(DeepSeekSvg, 'DeepSeekIcon', '#4D6BFE', true)
const TogetherIcon = wrapIcon(TogetherSvg, 'TogetherIcon', '#0f6fff', true)
const AzureIcon = wrapIcon(AzureSvg, 'AzureIcon', '#fff', true)
const HuggingFaceIcon = wrapIcon(HuggingFaceSvg, 'HuggingFaceIcon', '#fff', true)
const ClaudeIcon = wrapIcon(ClaudeSvg, 'ClaudeIcon', '#D97757', true)
const QwenIcon = wrapIcon(QwenSvg, 'QwenIcon', '#615ced', true)
const YiIcon = wrapIcon(YiSvg, 'YiIcon', '#003425', true)
const BaichuanIcon = wrapIcon(BaichuanSvg, 'BaichuanIcon', '#FF6933', true)
const ChatGLMIcon = wrapIcon(ChatGLMSvg, 'ChatGLMIcon', '#4268FA', true)
const VertexAIIcon = wrapIcon(VertexAISvg, 'VertexAIIcon', '#4285F4', true)
const AlibabaCloudIcon = wrapIcon(AlibabaCloudSvg, 'AlibabaCloudIcon', '#FF6A00', true)
const AwsIcon = wrapIcon(AwsSvg, 'AwsIcon', '#222F3E', true)
const GeminiIcon = wrapIcon(GeminiSvg, 'GeminiIcon', '#fff', true)
const NovaIcon = wrapIcon(NovaSvg, 'NovaIcon', '#222F3E', true)
const GLMVIcon = wrapIcon(GLMVSvg, 'GLMVIcon', '#0039C6', true)
const NvidiaIcon = wrapIcon(NvidiaSvg, 'NvidiaIcon', '#74B71B', true)
const BaiduIcon = wrapIcon(BaiduSvg, 'BaiduIcon', '#2932E1', true)
const MinimaxIcon = wrapIcon(MinimaxSvg, 'MinimaxIcon', '#F23F5D', true)
const TencentIcon = wrapIcon(TencentSvg, 'TencentIcon', '#0052D9', true)

// Custom icons (not from LobeHub)
const OrnithopsIcon = forwardRef<SVGSVGElement, SVGProps<SVGSVGElement> & { size?: number }>(
  ({ size = 24, ...props }, ref) => (
    <svg ref={ref} xmlns="http://www.w3.org/2000/svg" viewBox="100 100 824 824" width={size} height={size} fill="currentColor" {...props}>
      <g transform="translate(0,1024) scale(0.1,-0.1)" stroke="none">
        <path d="M4900 8814 c-19 -2 -87 -9 -150 -15 -621 -58 -1243 -289 -1750 -652 -324 -232 -654 -564 -875 -878 -346 -492 -562 -1047 -647 -1659 -29 -208 -36 -640 -14 -847 39 -366 115 -678 249 -1023 58 -150 229 -483 322 -630 283 -445 643 -815 1065 -1097 320 -213 660 -366 1019 -459 112 -29 145 -34 195 -28 498 52 967 397 1276 935 151 263 239 503 346 939 91 373 136 514 223 695 114 236 220 384 407 565 177 172 328 275 579 396 129 62 365 154 397 154 13 0 4 -142 -18 -300 -85 -625 -325 -1150 -704 -1544 -222 -230 -442 -385 -693 -486 l-89 -36 -44 -119 c-120 -323 -305 -623 -529 -854 -172 -177 -316 -285 -515 -387 l-95 -48 145 -9 c267 -14 637 17 932 79 669 141 1319 503 1798 1000 855 888 1223 2124 989 3324 -185 950 -716 1775 -1489 2317 -512 360 -1073 573 -1705 648 -123 15 -550 28 -625 19z m458 -1264 c285 -31 557 -110 820 -240 259 -127 472 -281 668 -482 261 -268 438 -560 560 -923 l43 -130 58 -14 c76 -18 695 -21 763 -4 24 7 46 10 48 9 1 -2 -34 -27 -78 -56 -256 -164 -540 -200 -1025 -129 -77 11 -297 52 -490 90 -463 93 -574 109 -796 116 -380 12 -677 -50 -994 -205 -377 -186 -661 -439 -979 -876 -114 -156 -386 -563 -570 -853 -82 -128 -152 -230 -157 -227 -21 12 -191 281 -242 381 -272 534 -349 1119 -221 1691 95 425 323 839 634 1152 395 397 920 645 1490 703 81 9 378 6 468 -3z"/>
      </g>
    </svg>
  )
) as unknown as IconComponent
OrnithopsIcon.displayName = 'OrnithopsIcon'
OrnithopsIcon.colorPrimary = '#000000'

const SternaIcon = forwardRef<SVGSVGElement, SVGProps<SVGSVGElement> & { size?: number }>(
  ({ size = 24, ...props }, _ref) => (
    <svg viewBox="75 55 230 240" fill="none" xmlns="http://www.w3.org/2000/svg" width={size} height={size} {...props}>
      <defs>
        <linearGradient id="sterna-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#6480ea" />
          <stop offset="50%" stopColor="#3d5ce4" />
          <stop offset="100%" stopColor="#1d3ee0" />
        </linearGradient>
      </defs>
      <g transform="translate(0,370) scale(0.1,-0.1)" fill="url(#sterna-grad)" stroke="none">
        <path d="M2490 3079 c-126 -8 -314 -38 -431 -68 -184 -47 -330 -124 -426 -224 -56 -58 -108 -139 -101 -156 3 -8 73 -67 213 -181 194 -157 513 -431 548 -469 78 -86 140 -203 162 -305 l6 -28 28 44 c66 103 180 158 394 189 45 6 88 15 96 19 8 4 -21 16 -72 28 -128 32 -206 74 -285 151 -81 80 -133 107 -244 128 -194 36 -243 64 -274 155 -63 191 120 431 444 585 98 46 312 123 344 123 10 0 18 5 18 10 0 12 -245 11 -420 -1z"/>
        <path d="M818 3034 c-7 -6 17 -160 43 -269 40 -172 125 -370 222 -515 60 -89 242 -275 347 -352 41 -30 131 -94 200 -142 186 -128 246 -181 295 -255 78 -119 96 -254 47 -364 -19 -44 -115 -157 -133 -157 -4 0 6 30 22 66 39 85 48 178 25 255 -14 51 -112 217 -121 207 -2 -2 0 -33 5 -68 21 -150 -58 -320 -224 -485 -118 -117 -313 -243 -515 -332 l-76 -34 50 7 c683 88 1214 397 1320 768 24 84 17 268 -14 347 -27 70 -84 159 -142 220 -65 69 -310 270 -976 801 -126 100 -260 210 -299 244 -39 35 -74 61 -76 58z"/>
      </g>
    </svg>
  )
) as unknown as IconComponent
SternaIcon.displayName = 'SternaIcon'
SternaIcon.colorPrimary = '#3d5ce4'

/**
 * Registry of icon components for common providers.
 * Stores complete icon objects with colorPrimary and .Color properties.
 */
export const PROVIDER_ICON_COMPONENTS: Record<string, IconComponent> = {
  // Monochrome providers (no .Color variant available)
  openai: OpenAI,
  anthropic: Anthropic,
  openrouter: OpenRouter,

  // Providers with .Color variant (native colors) - store complete icon
  google: GoogleIcon,
  microsoft: MicrosoftIcon,
  meta: MetaIcon,
  mistral: MistralIcon,
  cohere: CohereIcon,
  perplexity: PerplexityIcon,
  deepseek: DeepSeekIcon,
  together: TogetherIcon,
  azure: AzureIcon,
  huggingface: HuggingFaceIcon,
  claude: ClaudeIcon,
  qwen: QwenIcon,
  yi: YiIcon,
  baichuan: BaichuanIcon,
  chatglm: ChatGLMIcon,
  vertexai: VertexAIIcon,
  alibabacloud: AlibabaCloudIcon,
  aws: AwsIcon,
  gemini: GeminiIcon,
  nova: NovaIcon,
  grok: GrokIcon,  // No .Color variant (monochrome)
  xai: XAIIcon,    // No .Color variant (monochrome)
  zai: ZaiIcon,    // No .Color variant (monochrome)
  glmv: GLMVIcon,
  nvidia: NvidiaIcon,
  ai21: Ai21Icon,
  aionlabs: AionLabsIcon,
  baidu: BaiduIcon,
  inflection: InflectionIcon,
  liquid: LiquidIcon,
  minimax: MinimaxIcon,
  moonshot: MoonshotIcon,
  nousresearch: NousResearchIcon,
  tencent: TencentIcon,

  // Provider variations
  'together-ai': TogetherIcon,
  'meta-llama': MetaIcon,
  mistralai: MistralIcon,
  'aws-bedrock': AwsIcon,
  'vertex-ai': VertexAIIcon,
  'google-vertex': VertexAIIcon,
  'alibaba-cloud': AlibabaCloudIcon,
  alibaba: AlibabaCloudIcon,
  'hugging-face': HuggingFaceIcon,

  // Model-specific icons (aliases)
  chatgpt: OpenAI,  // ChatGPT is an OpenAI product
  llama: MetaIcon,  // Llama is a Meta model

  // Custom icons (Ornithops / Sterna)
  ornithops: OrnithopsIcon,
  sterna: SternaIcon,
}

/**
 * Get a colored React icon component for a provider/model slug.
 *
 * @param slug - The provider or model icon slug
 * @returns Icon component if available, null otherwise
 */
export function getColoredIconComponent(slug: string | undefined): IconComponent | null {
  if (!slug) return null

  const normalizedSlug = slug.toLowerCase()
  return PROVIDER_ICON_COMPONENTS[normalizedSlug] || null
}

/**
 * Check if a colored icon component is available for a slug.
 *
 * @param slug - The provider or model icon slug
 * @returns True if colored icon is available
 */
export function hasColoredIcon(slug: string | undefined): boolean {
  if (!slug) return false
  const normalizedSlug = slug.toLowerCase()
  return normalizedSlug in PROVIDER_ICON_COMPONENTS
}

/**
 * Get the render component for an icon (prefers .Color variant if available).
 *
 * @param iconComponent - The complete icon component
 * @returns The .Color variant if available, otherwise the icon itself
 */
export function getIconRenderComponent(iconComponent: IconComponent | null): ComponentType<SVGProps<SVGSVGElement> & { size?: number }> | null {
  if (!iconComponent) return null

  // Return .Color if available, otherwise return the icon itself (which is the Mono variant)
  return iconComponent.Color || iconComponent
}

/**
 * Get the primary color from an icon component.
 *
 * @param iconComponent - The complete icon component
 * @returns The primary color if available
 */
export function getIconColorPrimary(iconComponent: IconComponent | null): string | undefined {
  if (!iconComponent) return undefined
  return iconComponent.colorPrimary
}

/**
 * Configuration for monochrome icons that need color overrides based on theme.
 *
 * - darkMode: Color to use in dark mode (for black icons that are invisible on dark backgrounds)
 * - lightMode: Color to use in light mode (for white icons that are invisible on light backgrounds)
 * - null means use the original colorPrimary
 */
interface MonochromeOverride {
  darkMode: string | null
  lightMode: string | null
}

const MONOCHROME_ICON_OVERRIDES: Record<string, MonochromeOverride> = {
  // Ornithops icon is black, needs white in dark mode
  ornithops: {
    darkMode: '#FFFFFF',  // White in dark mode
    lightMode: null,      // Original color (black) in light mode
  },
  // OpenAI icon is black, needs white in dark mode
  openai: {
    darkMode: '#FFFFFF',  // White in dark mode
    lightMode: null,      // Original color (black) in light mode
  },
  // ChatGPT uses OpenAI icon (black)
  chatgpt: {
    darkMode: '#FFFFFF',  // White in dark mode
    lightMode: null,      // Original color (black) in light mode
  },
  // Grok icon is black, needs white in dark mode
  grok: {
    darkMode: '#FFFFFF',  // White in dark mode
    lightMode: null,      // Original color (black) in light mode
  },
  // ZAI icon is black, needs white in dark mode
  zai: {
    darkMode: '#FFFFFF',  // White in dark mode
    lightMode: null,      // Original color (black) in light mode
  },
  // xAI icon is white, needs black in light mode
  xai: {
    darkMode: null,       // Original color (white) in dark mode
    lightMode: '#000000', // Black in light mode
  },
  // Liquid icon is white, needs black in light mode
  liquid: {
    darkMode: null,       // Original color (white) in dark mode
    lightMode: '#000000', // Black in light mode
  },
  // Moonshot icon is black, needs white in dark mode
  moonshot: {
    darkMode: '#FFFFFF',  // White in dark mode
    lightMode: null,      // Original color (black) in light mode
  },
  // AionLabs icon is dark navy, needs white in dark mode (rendered
  // monochrome here as a bundle-size tradeoff — see wrapIcon call above)
  aionlabs: {
    darkMode: '#FFFFFF',  // White in dark mode
    lightMode: null,      // Original color (dark navy) in light mode
  },
  // Note: All other icons now use .Color variant with native colors
  // No overrides needed for them (Google, Gemini, Meta, Mistral, etc.)
}

/**
 * Get the adaptive color for an icon based on the current theme.
 * Returns appropriate color for monochrome icons to ensure visibility.
 *
 * @param slug - The icon slug
 * @param isDark - Whether dark mode is active
 * @param iconComponent - The icon component (to get colorPrimary)
 * @returns The color to use for the icon
 */
export function getAdaptiveIconColor(
  slug: string | undefined,
  isDark: boolean,
  iconComponent: IconComponent | null
): string | undefined {
  const originalColor = getIconColorPrimary(iconComponent)

  // Default to original color
  if (!slug || !iconComponent) {
    return originalColor
  }

  // Check if this icon needs an override
  const normalizedSlug = slug.toLowerCase()
  const override = MONOCHROME_ICON_OVERRIDES[normalizedSlug]

  if (!override) {
    // No override needed, use original color
    return originalColor
  }

  // Apply theme-specific override
  if (isDark && override.darkMode) {
    return override.darkMode
  }

  if (!isDark && override.lightMode) {
    return override.lightMode
  }

  // Fallback to original color
  return originalColor
}
