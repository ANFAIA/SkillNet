import siteData from '../data/site.json'

export type Claim = (typeof siteData.claims)[number]

export function getClaim(id: string): Claim {
  const claim = siteData.claims.find((entry) => entry.id === id)

  if (!claim) {
    throw new Error(`Unknown public claim: ${id}`)
  }

  return claim
}

export { siteData }
