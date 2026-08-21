import { useEffect } from 'react'

interface SeoProps {
  title: string
  description: string
  ogImage?: string
}

export function useSeoHead({ title, description, ogImage = '/og-image.png' }: SeoProps) {
  useEffect(() => {
    document.title = title
    upsertMeta('name', 'description', description)
    upsertMeta('property', 'og:title', title)
    upsertMeta('property', 'og:description', description)
    upsertMeta('property', 'og:image', window.location.origin + ogImage)
    upsertMeta('name', 'twitter:card', 'summary_large_image')
    upsertMeta('name', 'twitter:title', title)
    upsertMeta('name', 'twitter:description', description)
  }, [title, description, ogImage])
}

function upsertMeta(attr: string, value: string, content: string) {
  let el = document.querySelector<HTMLMetaElement>(`meta[${attr}="${value}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, value)
    document.head.appendChild(el)
  }
  el.content = content
}
